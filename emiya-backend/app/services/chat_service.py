# -*- coding: utf-8 -*-
"""聊天业务逻辑 — 分析 graph + 真流式回复生成。"""
import json
import logging
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
    compile_contract,
    continue_missing_tail_blocks,
    enforce_visible_output_contract,
    resolve_policy,
    resolve_require_confirmed,
    strict_available,
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
    ops 来源无关：inline `<UpdateVariable>`（ADR-0022 默认）在 raw_reply 里，double_ai 在
    double_ai_ops 里，前端薄 Mvu 层（ADR-0008b）自己解析+应用+派生。base_stat 深拷贝，避免后续
    apply 改到它。（前端 applyTurn 的 tool_calls 形参保留但后端不再产出，恒为空。）
    """
    if not (settings.MVU_BROWSER_RUNTIME and final_state.get("persona_uses_mvu")):
        return None
    import copy
    base_local = (final_state.get("mvu_scope") or {}).get("local") or {}
    return {
        "base_stat": copy.deepcopy(base_local.get("stat_data") or {}),
        "raw_reply": final_state.get("assistant_reply") or "",
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
    # 账户级配置桶（ADR-4）：记忆调参 + token 预算账户默认。空 {} = 全部继承全局。
    account_config = dict(getattr(_user_row, "account_config", None) or {}) if _user_row else {}

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
            # ADR-2c 严格声明模式账户默认（此前缺失，导致 resolve 恒退全局 settings）。
            # _user_row 缺列（旧数据 refresh 前）时给 None → resolve 再回退全局。
            "output_contract_require_confirmed": (
                getattr(_user_row, "output_contract_require_confirmed", None)
                if _user_row else None
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
            # ADR-2c 严格声明模式（对话级覆盖 > 账户默认 > 全局 settings）。
            "output_contract_require_confirmed": _conv_cfg.get(
                "output_contract_require_confirmed"
            ),
        },
    }
    # ADR-2c：严格模式只影响契约**执行**（未确认草稿不强制），不影响 Prompt 锚定。
    _require_confirmed = resolve_require_confirmed(
        account_defaults=output_contract_config["account_defaults"],
        conversation_overrides=output_contract_config["overrides"],
    )

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
        "mvu_double_ai_ops": [],
        "enabled_blocks": enabled_blocks,
        "mvu_compat_enabled": mvu_compat_enabled,
        "output_contract_config": output_contract_config,
        "account_config": account_config,
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

    # ADR-0022b：MVU 卡的输出格式由卡自己定（内联标签 + 卡正则），EMIYA 输出契约对 MVU 卡冲突+冗余
    # （会把 [系统]/[事件] 逻辑条目误判成尾部模板、指挥 AI 复述）→ MVU 激活时喂空条目 = 整体关掉契约
    # （strict 判定 + 尾部执行都变 no-op；与 node_build_prompt 的锚定关闭一致）。
    _wi_for_contract = [] if final_state.get("persona_uses_mvu") else final_state.get("wi_activated")

    # ADR-1g：strict 模式在生成前判定。可用时草稿不作为 message_delta 流式下发（改发
    # contract_stage 阶段事件），最终由 node_post_process 的确定性渲染经 message_done 一次
    # 性提交。strict 永不自动开启——只有账户/对话显式设为 strict 且启用前提满足才为真。
    _strict_contract = compile_contract(
        _wi_for_contract, require_confirmed=_require_confirmed
    )
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

    # ADR-0022：MVU 更新策略元数据（仅供日志/诊断）。mode 由本轮 divert 标志决定：
    # double_ai（回复后独立 pass）或 inline（主模型内联 <UpdateVariable>，无第二 pass）。
    _is_double_ai = bool(final_state.get("mvu_divert_update"))
    wi_activated_for_tool = final_state.get("wi_activated") or []
    mvu_update_entry_count = sum(
        1
        for e in wi_activated_for_tool
        if "[mvu_update]" in str((e or {}).get("comment") or "").lower()
    )
    mvu_tool_meta = {
        "mode": "double_ai" if _is_double_ai else "inline",
        "persona_uses_mvu": bool(final_state.get("persona_uses_mvu")),
        "mvu_update_entries": mvu_update_entry_count,
        "tool_calls_received": 0,
        "tool_call_names": [],
        "double_ai": None,
    }
    final_state["mvu_tool_meta"] = mvu_tool_meta
    logger.info(
        "[MVU-UPDATE] gate conv=%s mode=%s persona_uses_mvu=%s mvu_update_entries=%s",
        conversation_id,
        mvu_tool_meta["mode"],
        mvu_tool_meta["persona_uses_mvu"],
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

    logger.info(
        "[MVU-UPDATE] stream done conv=%s content_chunks=%s content_chars=%s mode=%s",
        conversation_id,
        len(buffer),
        len("".join(buffer)),
        mvu_tool_meta["mode"],
    )

    final_state["assistant_reply"] = "".join(buffer)

    logger.info(f"LLM 原始回复 (conv={conversation_id}):\n{final_state['assistant_reply']}")

    if not buffer:
        yield f"event: message_delta\ndata: {json.dumps({'content': '[没有收到回复]'}, ensure_ascii=False)}\n\n"
        yield f"event: message_done\ndata: {json.dumps({'message_id': '', 'conversation_id': str(conversation_id), 'new_memories': 0}, ensure_ascii=False)}\n\n"
        return

    # 5.5 尾部模板续写通过输出契约执行器统一处理。
    final_state["assistant_reply"] = "".join(buffer)
    output_contract = compile_contract(
        _wi_for_contract,  # MVU 卡为空 → 契约整体关闭（ADR-0022b，见上）
        chat_config,
        require_confirmed=_require_confirmed,
    )
    _tail_policy = resolve_policy(
        output_contract,
        account_defaults=output_contract_config["account_defaults"],
        conversation_overrides=output_contract_config["overrides"],
    )
    tail_deltas: list[str] = []

    async def _continue_tail(reply: str) -> str:
        current = reply
        async for delta in continue_missing_tail_blocks(
            reply=reply,
            contract=output_contract,
            messages=messages,
            conversation_id=conversation_id,
            chat_config=chat_config,
            update_reply=lambda value: None,
        ):
            tail_deltas.append(delta)
            try:
                payload = json.loads(delta.split("data: ", 1)[1])
                current += str(payload.get("content") or "")
            except (IndexError, json.JSONDecodeError):
                continue
        return current

    tail_result = await enforce_visible_output_contract(
        content=final_state["assistant_reply"],
        display_content=final_state["assistant_reply"],
        contract=output_contract,
        messages=messages,
        policy=_tail_policy,
        tail_continuation=(
            _continue_tail if settings.WORLDBOOK_TAIL_CONTINUATION_ENABLED else None
        ),
    )
    final_state["assistant_reply"] = tail_result.content
    for delta in tail_deltas:
        yield delta

    # 6. 保存回复 + 后处理（情绪记录、关系更新、记忆提取）
    # ADR-0022：仅 double_ai 策略（mvu_divert_update）才跑独立更新 pass；inline 策略下
    # 更新是主模型正文里的 <UpdateVariable>，由内联解析处理，不跑第二 pass。
    if final_state.get("mvu_divert_update") and (final_state.get("assistant_reply") or "").strip():
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
            requested_mode=tail_result.requested_mode,
            effective_mode=tail_result.effective_mode,
            outcome=tail_result.outcome,
            coverage=tail_result.coverage,
            method=tail_result.method,
            initial=None,
            final=None,
            actions=tail_result.actions,
            latency_ms=tail_result.latency_ms,
            extra_calls=tail_result.extra_calls,
        )
        msg_done_data["output_contract"].update(tail_result.diagnostics)
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
