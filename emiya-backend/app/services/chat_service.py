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
from app.services.langgraph.chat_graph import build_analysis_graph
from app.services.langgraph.nodes import (
    _build_template_scaffold,
    _extract_template_entries,
    _find_missing_templates,
    node_post_process,
)
from app.services.langgraph.state import ChatState
from app.services.llm_service import call_deepseek_stream, call_deepseek_stream_prefix
from app.services.prompt_renderer import DEFAULT_TEMPLATE_BLOCKS

logger = logging.getLogger(__name__)


async def _broadcast(conversation_id: UUID, event_type: str, data: dict) -> None:
    """向 Redis PubSub 广播聊天事件，供前端 live SSE 订阅。"""
    try:
        from app.services.redis_client import publish_token
        await publish_token(str(conversation_id), event_type, data)
    except Exception:
        pass  # Redis 不可用时静默降级


REPLY_LENGTH_MAX_TOKENS = {"short": 150, "medium": 500, "long": 2000}


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
        "profile_constraints": "",
        "profile_reminder": False,
        "relationship": None,
        "relationship_section": "",
        "relationship_level": 0,
        "level_changed": False,
        "new_milestone": None,
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
        "enabled_blocks": enabled_blocks,
    }

    # 4. 执行 graph（astream 逐节点推送中间状态，消除沉默期）
    # 必须用 initial_state 初始化 —— astream updates 模式只产出各节点的增量输出，
    # 不含 conversation_id / user_id 等初始字段，node_post_process 依赖这些字段。
    final_state: dict = dict(initial_state)
    try:
        async for chunk in graph.astream(initial_state, stream_mode="updates"):
            for node_name, node_output in chunk.items():
                final_state.update(node_output)

                if node_name == "analyze_emotion":
                    # 关闭情绪分析时 node 内部已 short-circuit 返回默认值，
                    # 这里同步不发 SSE（前端 emoji 也不会更新）
                    if conversation.analyze_emotion:
                        emotion_data = {
                            "emotion": node_output.get("emotion") or "平静",
                            "intensity": node_output.get("emotion_intensity", 5),
                            "confidence": node_output.get("emotion_confidence", 0.3),
                            "triggers": node_output.get("emotion_triggers", []),
                        }
                        yield f"event: emotion\ndata: {json.dumps(emotion_data, ensure_ascii=False)}\n\n"
                        await _broadcast(conversation_id, "emotion", emotion_data)

                elif node_name == "retrieve_memories":
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

                elif node_name == "build_prompt" and node_output.get("error"):
                    yield f"event: error\ndata: {json.dumps({'error': node_output['error']}, ensure_ascii=False)}\n\n"
                    return

    except Exception as e:
        logger.error(f"LangGraph 执行失败: {e}", exc_info=True)
        yield f"event: error\ndata: {json.dumps({'error': '回复生成失败，请稍后重试'}, ensure_ascii=False)}\n\n"
        return

    # Yield profile_reminder SSE 事件（无画像时提醒设置）
    if final_state.get("profile_reminder"):
        yield f"event: profile_reminder\ndata: {json.dumps({'message': '设置你的画像，让小暖更懂你', 'link': '/profile'}, ensure_ascii=False)}\n\n"

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

    # max_tokens：预设 openai_max_tokens 优先，否则按 reply_length 映射
    dynamic_max_tokens = chat_config.get("openai_max_tokens") or REPLY_LENGTH_MAX_TOKENS.get(
        final_state.get("reply_length", "medium"), 600
    )
    llm_temperature = chat_config.get("temperature", settings.CHAT_TEMPERATURE)
    llm_top_p = chat_config.get("top_p")
    llm_frequency_penalty = chat_config.get("frequency_penalty")
    llm_presence_penalty = chat_config.get("presence_penalty")
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

    if not buffer:
        yield f"event: message_delta\ndata: {json.dumps({'content': '[没有收到回复]'}, ensure_ascii=False)}\n\n"
        yield f"event: message_done\ndata: {json.dumps({'message_id': '', 'conversation_id': str(conversation_id), 'new_memories': 0}, ensure_ascii=False)}\n\n"
        return

    # 5.5 尾部模板兜底：检测缺失模板，prefix continuation 强制续写
    final_state["assistant_reply"] = "".join(buffer)
    if settings.WORLDBOOK_TAIL_CONTINUATION_ENABLED:
        async for delta in _continuation_loop(
            final_state=final_state,
            messages=messages,
            conversation_id=conversation_id,
            chat_config=chat_config,
        ):
            yield delta

    # 6. 保存回复 + 后处理（情绪记录、关系更新、记忆提取）
    logger.info(f"LLM 原始回复 (conv={conversation_id}):\n{final_state['assistant_reply']}")
    logger.debug(f"即将调用 node_post_process, conv_id={conversation_id}, "
                f"reply_len={len(final_state['assistant_reply'])}, "
                f"state_keys={sorted(final_state.keys())}")
    post_result: dict = {}
    try:
        post_result = await node_post_process(final_state)
        logger.debug(f"node_post_process 成功, new_memories={post_result.get('new_memories_count', 0)}")
    except Exception:
        logger.exception("post_process 失败，回复已生成但状态未更新")

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
        # 文本写回 final_state["assistant_reply"]，这里透传给前端覆盖累积版。
        # 若流式期间用户已看到未清洗版，message_done 时 UI 静默替换为最终版。
        "final_content": final_state.get("assistant_reply") or "",
    }
    if affinity_score is not None:
        msg_done_data["affinity_score"] = affinity_score
    # 把最新 conv 变量透出来，前端 ConfigPanel「对话状态变量」实时刷新
    # （MVU 写回后 conv.variables 已更新，不传则前端要等手动 refetch 才看到）
    mvu_scope = final_state.get("mvu_scope") or {}
    msg_done_data["variables"] = dict(mvu_scope.get("local") or {})
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


async def _continuation_loop(
    final_state: dict,
    messages: list[dict],
    conversation_id: UUID,
    chat_config: dict,
):
    """主回复结束后扫缺失模板，按 order 升序串行调 prefix continuation。

    每个续写的 token 直接 yield 为 SSE message_delta；前端无感知，看起来是"AI
    自然继续写"。失败时静默 fallback，不影响主回复保存。

    详见 grilling Q1=A / Q2=β / Q3=α / Q4=α-1 / Q5=K=3。
    """
    wi_activated = final_state.get("wi_activated") or []
    if not wi_activated:
        return

    template_entries = _extract_template_entries(wi_activated)
    if not template_entries:
        return

    current_reply = final_state["assistant_reply"]
    missing = _find_missing_templates(current_reply, template_entries)
    if not missing:
        return

    K = settings.WORLDBOOK_TAIL_CONTINUATION_MAX
    missing = missing[:K]
    logger.info(
        f"[尾部模板续写] 主回复缺 {len(missing)} 个模板，开始 prefix continuation: "
        f"{[e['marker'] for e in missing]}"
    )

    cont_temperature = chat_config.get("temperature", settings.CHAT_TEMPERATURE)
    cont_max_tokens = settings.WORLDBOOK_TAIL_CONTINUATION_MAX_TOKENS

    for entry in missing:
        try:
            scaffold = _build_template_scaffold(entry["content"])
            if not scaffold.strip():
                continue

            # 1. 先把 scaffold 作为可见 message_delta 推给前端（让用户看到结构开始浮现）
            scaffold_payload = "\n\n" + scaffold
            yield f"event: message_delta\ndata: {json.dumps({'content': scaffold_payload}, ensure_ascii=False)}\n\n"
            await _broadcast(conversation_id, "message_delta", {"content": scaffold_payload})
            current_reply += scaffold_payload

            # 2. DeepSeek 续写：从 scaffold 末尾接着填字段值
            prefix_text = current_reply
            try:
                async for token in call_deepseek_stream_prefix(
                    messages=messages,
                    prefix_text=prefix_text,
                    temperature=cont_temperature,
                    max_tokens=cont_max_tokens,
                    stop=["</details>"],
                ):
                    yield f"event: message_delta\ndata: {json.dumps({'content': token}, ensure_ascii=False)}\n\n"
                    await _broadcast(conversation_id, "message_delta", {"content": token})
                    current_reply += token
            except Exception as e:
                logger.warning(
                    f"[尾部模板续写] marker={entry['marker']} stream 失败，"
                    f"主回复保留 scaffold 但不闭合: {e}"
                )
                continue

            # 3. 续写不含 </details>（被 stop 截掉），自己补一个
            closing = "\n</details>"
            yield f"event: message_delta\ndata: {json.dumps({'content': closing}, ensure_ascii=False)}\n\n"
            await _broadcast(conversation_id, "message_delta", {"content": closing})
            current_reply += closing
        except Exception as e:
            logger.warning(
                f"[尾部模板续写] marker={entry['marker']} 失败，静默跳过: {e}"
            )
            continue

    # 更新 final_state.assistant_reply 让 post_process 写入完整版
    final_state["assistant_reply"] = current_reply
