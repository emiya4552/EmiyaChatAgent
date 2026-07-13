# -*- coding: utf-8 -*-
"""聊天业务逻辑 — 分析 graph + 真流式回复生成。"""
import json
import logging
from dataclasses import replace
from typing import AsyncGenerator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.services.langgraph.chat_graph import build_analysis_graph
from app.services.langgraph.nodes import (
    node_post_process,
)
from app.services.langgraph.state import ChatState
from app.services.llm_service import call_deepseek_stream
from app.services.output_contracts import (
    build_contract_sse,
    build_visible_output_contract,
    compile_contract,
    continue_missing_tail_blocks,
    resolve_policy,
    strict_available,
    validate_visible_output,
)
from app.services.prompt_renderer import DEFAULT_TEMPLATE_BLOCKS
from app.services.token_budget import resolve_reply_max_tokens

logger = logging.getLogger(__name__)


async def _broadcast(conversation_id: UUID, event_type: str, data: dict) -> None:
    """向 Redis PubSub 广播聊天事件，供前端 live SSE 订阅。"""
    try:
        from app.services.redis_client import publish_token
        await publish_token(str(conversation_id), event_type, data)
    except Exception:
        pass  # Redis 不可用时静默降级


def _build_mvu_browser_sync(final_state: dict) -> dict | None:
    """ADR-0008c 阶段1 down-channel：抓本回合层 1 的原料给前端 MVU Host。

    仅当 `MVU_BROWSER_RUNTIME` 开 且 `persona_uses_mvu` 时返回 dict，否则 None。
    **必须在 node_post_process 应用之前调用** —— base_stat 要的是应用前的 S(N-1)。
    ops 来源无关：inline `<UpdateVariable>` 在 raw_reply 里，tool 通道在 tool_calls 里，
    前端薄 Mvu 层（ADR-0008b）自己解析+应用+派生。base_stat 深拷贝，避免后续 apply 改到它。
    """
    if not (settings.MVU_BROWSER_RUNTIME and final_state.get("persona_uses_mvu")):
        return None
    import copy
    base_local = (final_state.get("mvu_scope") or {}).get("local") or {}
    return {
        "base_stat": copy.deepcopy(base_local.get("stat_data") or {}),
        "raw_reply": final_state.get("assistant_reply") or "",
        "tool_calls": final_state.get("mvu_tool_calls") or [],
        "double_ai_ops": final_state.get("mvu_double_ai_ops") or [],
    }


async def process_chat(
    db: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
    content: str,
    reply_length: str = "medium",
) -> AsyncGenerator[str, None]:
    """处理一次聊天，yield SSE 事件字符串。

    内部使用 LangGraph State Graph 编排执行流程。
    """
    # 1. 验证对话所有权
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        logger.warning(f"用户 {user_id} 尝试访问不存在的对话 {conversation_id}")
        return

    # 2. 保存用户消息
    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=content,
    )
    db.add(user_msg)
    await db.commit()

    # 2.5 加载当前 template 的启用 block 集合（功能开关）
    # 每个 dynamic block 的 dynamic_ref 都算一个 "feature key"；
    # 节点据此 gating：关 block 等于关功能。
    enabled_blocks = await _load_enabled_blocks(db, conversation.template_id)

    # 2.6 MVU 兼容总开关（账户级，CARD-0002）：载入 state，node_build_prompt 据此把
    # persona_uses_mvu 压成有效值 + 剔除 MVU 标签条目 + 跳过 EJS + 隐藏卡 UI（前端）。
    _user_row = await db.get(User, user_id)
    mvu_compat_enabled = bool(_user_row.mvu_compat_enabled) if _user_row else True

    # 2.7 可见输出契约聊天期执行配置（ADR-1f）：账户默认 + 对话 chat_config 覆盖。
    # node_post_process 用它 resolve_policy 出 executor 运行策略。
    _conv_cfg = conversation.chat_config or {}
    output_contract_config = {
        "account_defaults": {
            "output_contract_default_mode": (
                _user_row.output_contract_default_mode if _user_row else "auto"
            ),
            "output_contract_allow_full_rewrite": (
                _user_row.output_contract_allow_full_rewrite if _user_row else False
            ),
            "output_contract_strict_fallback": (
                _user_row.output_contract_strict_fallback if _user_row else "repair"
            ),
        },
        "overrides": {
            "output_contract_mode": _conv_cfg.get("output_contract_mode"),
            "output_contract_allow_full_rewrite": _conv_cfg.get(
                "output_contract_allow_full_rewrite"
            ),
            "output_contract_strict_fallback": _conv_cfg.get(
                "output_contract_strict_fallback"
            ),
        },
    }

    # 3. 构建初始 state
    graph = build_analysis_graph()
    initial_state: ChatState = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "persona_id": conversation.persona_id,
        "user_persona_id": conversation.user_persona_id,
        "user_message": content,
        "emotion": None,
        "emotion_intensity": 5,
        "emotion_confidence": 0.3,
        "emotion_triggers": [],
        "current_mood": conversation.current_mood,
        "mood_intensity": conversation.mood_intensity,
        "recalled_memories": [],
        "wi_activated": [],
        "profile": None,
        "profile_section": "",
        "relationship": None,
        "relationship_section": "",
        "relationship_level": 0,
        "level_changed": False,
        "new_milestone": None,
        "recent_messages": [],
        "summary_context": "",
        "dialogue_message_count": 0,
        "system_prompt": "",
        "messages": [],
        "persona_name": None,
        "assistant_reply": "",
        "new_memories_count": 0,
        "is_first_round": False,
        "assistant_message_id": None,
        "affinity_delta": 0,
        "affinity_reason": "",
        "affinity_score": None,
        "error": None,
        "reply_length": reply_length,
        "mvu_scope": {},
        "mvu_tool_calls": [],
        "mvu_double_ai_ops": [],
        "enabled_blocks": enabled_blocks,
        "mvu_compat_enabled": mvu_compat_enabled,
        "output_contract_config": output_contract_config,
        "token_budget_report": None,
    }

    # 4. 执行 graph（astream 逐节点推送中间状态，消除沉默期）
    # 必须用 initial_state 初始化 —— astream updates 模式只产出各节点的增量输出，
    # 不含 conversation_id / user_id 等初始字段，node_post_process 依赖这些字段。
    final_state: dict = dict(initial_state)
    try:
        async for chunk in graph.astream(initial_state, stream_mode="updates"):
            for node_name, node_output in chunk.items():
                final_state.update(node_output)

                # ADR-0019：情绪已后置到 node_post_process，不再在分析阶段发 emotion SSE；
                # 情绪随 message_done 透出（见下方 msg_done_data["emotion"]）。
                if node_name == "retrieve_memories":
                    recalled = node_output.get("recalled_memories") or []
                    if recalled:
                        yield f"event: memory_recall\ndata: {json.dumps({'memories': recalled}, ensure_ascii=False)}\n\n"
                        await _broadcast(conversation_id, "memory_recall", {"memories": recalled})

                elif node_name == "activate_worldbook":
                    wi = node_output.get("wi_activated") or []
                    if wi:
                        # 前端只关心简短的"哪些条目被激活了"
                        compact = [
                            {
                                "uid": e.get("uid"),
                                "comment": e.get("comment", ""),
                                "worldbook_id": e.get("worldbook_id"),
                                "worldbook_name": e.get("worldbook_name"),
                                "position": e.get("position"),
                            }
                            for e in wi
                        ]
                        yield f"event: worldinfo_activated\ndata: {json.dumps({'entries': compact}, ensure_ascii=False)}\n\n"
                        await _broadcast(conversation_id, "worldinfo_activated", {"entries": compact})

                elif node_output.get("error"):
                    yield f"event: error\ndata: {json.dumps({'error': node_output['error']}, ensure_ascii=False)}\n\n"
                    return

    except Exception as e:
        logger.error(f"LangGraph 执行失败: {e}", exc_info=True)
        yield f"event: error\ndata: {json.dumps({'error': '回复生成失败，请稍后重试'}, ensure_ascii=False)}\n\n"
        return

    # Yield relationship_change SSE 事件（等级变化时）
    if final_state.get("level_changed"):
        rel = final_state.get("relationship") or {}
        yield f"event: relationship_change\ndata: {json.dumps({'level': final_state.get('relationship_level', 0), 'level_name': rel.get('level_name', ''), 'affinity_score': rel.get('affinity_score', 0)}, ensure_ascii=False)}\n\n"

    # Yield milestone SSE 事件（达成新里程碑时）
    nm = final_state.get("new_milestone")
    if nm:
        from app.services.relationship_service import MILESTONE_DEFINITIONS
        milestone_name = MILESTONE_DEFINITIONS.get(nm, nm)
        yield f"event: milestone\ndata: {json.dumps({'key': nm, 'name': milestone_name}, ensure_ascii=False)}\n\n"

    # 5. 真流式回复生成 — call_deepseek_stream 逐 token yield
    messages = final_state.get("messages") or []
    if not messages:
        logger.warning("build_prompt 未产出 messages，无法生成回复")
        yield f"event: error\ndata: {json.dumps({'error': '回复生成失败'}, ensure_ascii=False)}\n\n"
        return

    buffer: list[str] = []
    chat_config = conversation.chat_config or {}

    # ADR-1g：strict 模式在生成前判定。可用时草稿不作为 message_delta 流式下发（改发
    # contract_stage 阶段事件），最终由 node_post_process 的确定性渲染经 message_done 一次
    # 性提交。strict 永不自动开启——只有账户/对话显式设为 strict 且启用前提满足才为真。
    _strict_contract = compile_contract(final_state.get("wi_activated"))
    strict_active = False
    if _strict_contract.required_sections:
        _strict_policy = resolve_policy(
            _strict_contract,
            account_defaults=output_contract_config["account_defaults"],
            conversation_overrides=output_contract_config["overrides"],
        )
        strict_active = (
            _strict_policy["mode"] == "strict"
            and strict_available(_strict_contract, _strict_policy)[0]
        )
    if strict_active:
        _stage_evt = {"stage": "drafting"}
        yield f"event: contract_stage\ndata: {json.dumps(_stage_evt, ensure_ascii=False)}\n\n"
        await _broadcast(conversation_id, "contract_stage", _stage_evt)

    # max_tokens：预设 openai_max_tokens 优先，否则按 reply_length 映射
    dynamic_max_tokens = resolve_reply_max_tokens(
        chat_config,
        final_state.get("reply_length", "medium"),
    )
    llm_temperature = chat_config.get("temperature", settings.CHAT_TEMPERATURE)
    llm_top_p = chat_config.get("top_p")
    llm_frequency_penalty = chat_config.get("frequency_penalty")
    llm_presence_penalty = chat_config.get("presence_penalty")

    # ADR-0005：tool-calling 更新通道（默认关；仅 uses_mvu 卡）。单次调用同时拿
    # content + update_variables tool_call；tool_calls_acc 在流结束后被填充。
    tool_calls_acc: list = []
    wi_activated_for_tool = final_state.get("wi_activated") or []
    mvu_update_entry_count = sum(
        1
        for e in wi_activated_for_tool
        if "[mvu_update]" in str((e or {}).get("comment") or "").lower()
    )
    mvu_tool_meta = {
        "mode": "double_ai",
        "enabled_flag": bool(final_state.get("persona_uses_mvu")),
        "persona_uses_mvu": bool(final_state.get("persona_uses_mvu")),
        "tools_sent": False,
        "tool_count": 0,
        "mvu_update_entries": mvu_update_entry_count,
        "tool_calls_received": 0,
        "tool_call_names": [],
        "double_ai": None,
    }
    final_state["mvu_tool_meta"] = mvu_tool_meta
    logger.info(
        "[MVU-DOUBLE-AI] gate conv=%s enabled=%s persona_uses_mvu=%s "
        "tools_sent=%s tool_count=%s mvu_update_entries=%s",
        conversation_id,
        mvu_tool_meta["enabled_flag"],
        mvu_tool_meta["persona_uses_mvu"],
        mvu_tool_meta["tools_sent"],
        mvu_tool_meta["tool_count"],
        mvu_tool_meta["mvu_update_entries"],
    )

    try:
        async for token in call_deepseek_stream(
            messages=messages,
            temperature=llm_temperature,
            max_tokens=dynamic_max_tokens,
            top_p=llm_top_p,
            frequency_penalty=llm_frequency_penalty,
            presence_penalty=llm_presence_penalty,
        ):
            buffer.append(token)
            # strict：草稿不流式暴露；前端只看阶段状态，最终一次性替换（ADR-1g）。
            if not strict_active:
                yield f"event: message_delta\ndata: {json.dumps({'content': token}, ensure_ascii=False)}\n\n"
                await _broadcast(conversation_id, "message_delta", {"content": token})

    except Exception as e:
        logger.error(f"流式生成中断: {e}")
        partial_message_id: str | None = None
        if buffer:
            final_state["assistant_reply"] = "".join(buffer) + "[流式中断]"
            try:
                interrupt_result = await node_post_process(final_state)
                partial_message_id = interrupt_result.get("assistant_message_id")
            except Exception:
                logger.exception("post_process 失败（中断恢复）")
        error_data: dict = {"error": "生成中断，请稍后重试"}
        if partial_message_id:
            error_data["partial_message_id"] = partial_message_id
        yield f"event: error\ndata: {json.dumps(error_data, ensure_ascii=False)}\n\n"
        return

    mvu_tool_meta["tool_calls_received"] = len(tool_calls_acc)
    mvu_tool_meta["tool_call_names"] = [
        str(((tc or {}).get("function") or {}).get("name") or "")
        for tc in tool_calls_acc
    ]
    final_state["mvu_tool_meta"] = mvu_tool_meta
    logger.info(
        "[MVU-ADR5] stream done conv=%s content_chunks=%s content_chars=%s "
        "tool_calls=%s tool_call_names=%s",
        conversation_id,
        len(buffer),
        len("".join(buffer)),
        mvu_tool_meta["tool_calls_received"],
        mvu_tool_meta["tool_call_names"],
    )

    final_state["assistant_reply"] = "".join(buffer)
    final_state["mvu_tool_calls"] = tool_calls_acc

    logger.info(f"LLM 原始回复 (conv={conversation_id}):\n{final_state['assistant_reply']}")

    if not buffer and not tool_calls_acc:
        yield f"event: message_delta\ndata: {json.dumps({'content': '[没有收到回复]'}, ensure_ascii=False)}\n\n"
        yield f"event: message_done\ndata: {json.dumps({'message_id': '', 'conversation_id': str(conversation_id), 'new_memories': 0}, ensure_ascii=False)}\n\n"
        return

    # 5.5 可见输出契约诊断 + 尾部模板兜底。
    # 先对原始回复做一次校验，续写后再校验一次；message_done 下发最终诊断。
    final_state["assistant_reply"] = "".join(buffer)
    output_contract = build_visible_output_contract(
        final_state.get("wi_activated"),
        chat_config,
    )
    output_contract_diag = validate_visible_output(
        final_state["assistant_reply"],
        output_contract,
    )
    # 保留初次校验，供 message_done 的稳定诊断结构（ADR-1f）区分 initial / final。
    tail_initial_diag = output_contract_diag
    tail_method = "initial"
    tail_extra_calls = 0

    # ADR-1f：tail 契约的执行模式（auto → repair）。off 时连尾部续写也不做。
    _tail_policy = resolve_policy(
        output_contract,
        account_defaults=output_contract_config["account_defaults"],
        conversation_overrides=output_contract_config["overrides"],
    )
    tail_execution_on = _tail_policy["mode"] != "off"

    tail_repair_needed = bool(
        output_contract.required_tail_blocks
        and output_contract_diag.missing
        and tail_execution_on
    )

    logger.info(
        "[契约校验] mode=%s ok=%s required=%d missing=%d repair_needed=%s",
        output_contract_diag.mode,
        output_contract_diag.ok,
        output_contract_diag.required,
        len(output_contract_diag.missing),
        tail_repair_needed,
    )

    # 把本次 tool_call 交给 node_post_process 走同一校验+应用核心
    final_state["mvu_tool_calls"] = tool_calls_acc
    if (
        buffer
        and output_contract.required_tail_blocks
        and settings.WORLDBOOK_TAIL_CONTINUATION_ENABLED
        and tail_execution_on
    ):
        async for delta in continue_missing_tail_blocks(
            reply=final_state["assistant_reply"],
            contract=output_contract,
            messages=messages,
            conversation_id=conversation_id,
            chat_config=chat_config,
            broadcast=_broadcast,
            update_reply=lambda reply: final_state.__setitem__("assistant_reply", reply),
        ):
            yield delta
        repaired_diag = validate_visible_output(
            final_state["assistant_reply"],
            output_contract,
        )
        tail_extra_calls = 1
        if tail_repair_needed and repaired_diag.ok:
            output_contract_diag = replace(
                repaired_diag,
                repaired=True,
                repair_mode="continuation",
            )
            tail_method = "reconstructed"
        else:
            output_contract_diag = repaired_diag
            if repaired_diag != tail_initial_diag:
                tail_method = "reconstructed"

    # 6. 保存回复 + 后处理（情绪记录、关系更新、记忆提取）
    if final_state.get("persona_uses_mvu") and (final_state.get("assistant_reply") or "").strip():
        try:
            from app.services.mvu_runtime import run_update_pass

            scope = final_state.get("mvu_scope") or {}
            local_bucket = scope.get("local") or {}
            stat_data = local_bucket.get("stat_data") or {}
            ops, double_ai_meta = await run_update_pass(
                reply=final_state.get("assistant_reply") or "",
                wi_activated=final_state.get("wi_activated"),
                stat_data=stat_data if isinstance(stat_data, dict) else {},
            )
            final_state["mvu_double_ai_ops"] = ops
            mvu_tool_meta["double_ai"] = double_ai_meta
            mvu_tool_meta["tool_calls_received"] = int(double_ai_meta.get("tool_calls") or 0)
            mvu_tool_meta["tool_call_names"] = (
                ["update_variables"] if mvu_tool_meta["tool_calls_received"] else []
            )
            final_state["mvu_tool_meta"] = mvu_tool_meta
            logger.info(
                "[MVU-DOUBLE-AI] pass done conv=%s ops=%s tool_calls=%s fallback=%s error=%s",
                conversation_id,
                double_ai_meta.get("ops"),
                double_ai_meta.get("tool_calls"),
                double_ai_meta.get("fallback"),
                double_ai_meta.get("error"),
            )
        except Exception:
            logger.exception("[MVU-DOUBLE-AI] update pass crashed")
            final_state["mvu_double_ai_ops"] = []

    logger.info(f"LLM pre-process 回复 (conv={conversation_id}):\n{final_state['assistant_reply']}")
    logger.debug(f"即将调用 node_post_process, conv_id={conversation_id}, "
                f"reply_len={len(final_state['assistant_reply'])}, "
                f"state_keys={sorted(final_state.keys())}")
    # ADR-0008c 阶段1：MVU 浏览器运行时 down-channel。必须在 node_post_process 应用
    # **之前**抓，base_stat 才是 S(N-1)。off 时返回 None，完全不产生该字段。
    mvu_browser_sync = _build_mvu_browser_sync(final_state)

    # ADR-1g：strict 的结构化槽位 pass + 确定性渲染在 node_post_process 内执行。
    if strict_active:
        _stage_evt = {"stage": "structuring"}
        yield f"event: contract_stage\ndata: {json.dumps(_stage_evt, ensure_ascii=False)}\n\n"
        await _broadcast(conversation_id, "contract_stage", _stage_evt)

    post_result: dict = {}
    try:
        post_result = await node_post_process(final_state)
        logger.debug(f"node_post_process 成功, new_memories={post_result.get('new_memories_count', 0)}")
    except Exception:
        logger.exception("post_process 失败，回复已生成但状态未更新")

    if strict_active:
        _stage_evt = {"stage": "done"}
        yield f"event: contract_stage\ndata: {json.dumps(_stage_evt, ensure_ascii=False)}\n\n"
        await _broadcast(conversation_id, "contract_stage", _stage_evt)

    # 7. 推送好感度变动（如有）
    affinity_delta = post_result.get("affinity_delta", 0)
    affinity_reason = post_result.get("affinity_reason", "")
    affinity_score = post_result.get("affinity_score")
    if affinity_delta != 0 and affinity_reason:
        yield f"event: affinity_update\ndata: {json.dumps({'delta': affinity_delta, 'reason': affinity_reason, 'score': affinity_score}, ensure_ascii=False)}\n\n"

    # 8. Yield message_done with real assistant message id
    new_count = post_result.get("new_memories_count", 0)
    real_message_id = post_result.get("assistant_message_id") or ""
    msg_done_data = {
        "message_id": real_message_id,
        "conversation_id": str(conversation_id),
        "new_memories": new_count,
        # ADR-0015：node_post_process 已经把 reply 正则 + UpdateVariable 解析过的
        # 文本写回 final_state["assistant_reply"]（prompt 真相版），这里透传给前端
        # 覆盖累积版。final_display_content 是 markdownOnly 美化后的显示版（ADR-0003
        # 双管线）——前端优先渲染它，流式期间看到的未清洗版在 message_done 时静默替换。
        "final_content": final_state.get("assistant_reply") or "",
        "final_display_content": (
            final_state.get("assistant_display")
            or final_state.get("assistant_reply")
            or ""
        ),
    }
    if affinity_score is not None:
        msg_done_data["affinity_score"] = affinity_score
    # ADR-0019：情绪后置到 post_process，随 message_done 透出（emoji 在回合结束时更新）
    _emotion = post_result.get("emotion")
    if _emotion:
        msg_done_data["emotion"] = _emotion
        msg_done_data["emotion_intensity"] = post_result.get("emotion_intensity", 5)
    # 把最新 conv 变量透出来，前端 ConfigPanel「对话状态变量」实时刷新
    # （MVU 写回后 conv.variables 已更新，不传则前端要等手动 refetch 才看到）
    mvu_scope = final_state.get("mvu_scope") or {}
    msg_done_data["variables"] = dict(mvu_scope.get("local") or {})
    # MVU 诊断运行时视图（ADR-0003 §3）：按需派生、不持久化、不进列表
    from app.services.mvu_runtime import build_runtime_view
    msg_done_data["mvu_runtime_view"] = build_runtime_view(
        final_state.get("wi_activated"),
        update_diag=final_state.get("mvu_update_diag"),
        update_channel=final_state.get("mvu_update_channel"),
        update_meta=final_state.get("mvu_tool_meta"),
    )
    # ADR-0008c 阶段1：附加 down-channel（仅 MVU_BROWSER_RUNTIME on 时存在）
    if final_state.get("token_budget_report"):
        msg_done_data["token_budget"] = final_state["token_budget_report"]
    # ADR-1f 稳定诊断结构：tail 契约在此按 initial/final 组装；full_document 由
    # node_post_process 在双视图之后执行并产出诊断，覆盖此处对 raw reply 的诊断。
    if output_contract.active:
        msg_done_data["output_contract"] = build_contract_sse(
            contract=output_contract,
            contract_mode=output_contract.mode,
            requested_mode=_tail_policy["requested_mode"],
            effective_mode=_tail_policy["mode"],
            outcome="passed" if output_contract_diag.ok else "failed",
            coverage="full" if output_contract.required_tail_blocks else "none",
            method=tail_method,
            initial=tail_initial_diag,
            final=output_contract_diag,
            extra_calls=tail_extra_calls,
        )
    if post_result.get("output_contract"):
        msg_done_data["output_contract"] = post_result["output_contract"]
    if mvu_browser_sync is not None:
        msg_done_data["mvu_browser_sync"] = mvu_browser_sync
    yield f"event: message_done\ndata: {json.dumps(msg_done_data, ensure_ascii=False)}\n\n"
    await _broadcast(conversation_id, "message_done", msg_done_data)


async def _load_enabled_blocks(db: AsyncSession, template_id) -> set[str]:
    """加载当前 conversation 的 template，提取启用 block 的关键集合。

    集合元素包含：
    - dynamic block 的 dynamic_ref（如 "relationship" / "memories" / "profile" /
      "constraints" / "summary"）：用于节点 gating（关 block = 关功能）
    - 其他类型 block 的 type 名（"static" / "mes_example" 等）：当前 gating 不用，
      但放进去便于未来扩展

    template_id is None → 用 DEFAULT_TEMPLATE_BLOCKS（内置默认）的启用集合。
    """
    blocks_data: list = []
    if template_id is not None:
        from app.models.prompt_template import PromptTemplate as PTModel
        result = await db.execute(select(PTModel).where(PTModel.id == template_id))
        template = result.scalar_one_or_none()
        if template and template.blocks:
            blocks_data = template.blocks
    if not blocks_data:
        # 用内置默认（DEFAULT_TEMPLATE_BLOCKS 是 dataclass 列表，不是 dict 列表）
        return {
            (b.dynamic_ref if b.type == "dynamic" else b.type)
            for b in DEFAULT_TEMPLATE_BLOCKS
            if b.enabled
        }

    enabled = set()
    for b in blocks_data:
        if not b.get("enabled", True):
            continue
        if b.get("type") == "dynamic":
            ref = b.get("dynamic_ref")
            if ref:
                enabled.add(ref)
        else:
            enabled.add(b.get("type", ""))
    return enabled
