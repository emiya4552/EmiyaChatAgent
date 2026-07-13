# -*- coding: utf-8 -*-
"""LangGraph 聊天流水线 — 各节点实现。"""
import asyncio as _asyncio
import json
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.emotion_record import EmotionRecord
from app.models.memory import Memory
from app.models.message import Message
from app.models.persona import Persona
from app.models.relationship import Relationship, RELATIONSHIP_LEVELS
from app.models.user import User
from app.services.context_service import update_summary
from app.services.ejs_engine import EJSEngine
from app.services.macro_engine import MacroEngine


def _render_content(content: str, scope: dict | None, run_ejs: bool = True) -> str:
    """对可模板化文本执行 EJS 与宏两层渲染。

    EJS 用于处理角色卡 / 世界书里常见的条件与插值语法；MacroEngine
    用于处理 {{user}}、{{char}}、变量宏等 ST 风格宏。关闭 run_ejs
    时只保留宏渲染，适合把 MVU 模板语法隔离在兼容开关之后。
    """
    if not content:
        return content
    if run_ejs:
        ejs_scope = (scope or {}).get("local") or {} if isinstance(scope, dict) else {}
        content = EJSEngine.render(content, ejs_scope)
    return MacroEngine.render(content, scope)


from app.services.emotion_service import (
    MoodStateMachine,
    assess_turn,
)
from app.services.memory.chroma_client import search_memories
from app.services.memory.extraction import rewrite_query_for_retrieval
from app.services.relationship_service import (
    MILESTONE_DEFINITIONS,
    assess_relationship,
    detect_milestones,
    get_or_create_relationship,
)
from app.services.worldbook.injector import (
    ANCHOR_AUTHOR_NOTE,
    ANCHOR_CHAR_DESC,
    ANCHOR_KEY,
    ANCHOR_MES_EXAMPLE,
    WorldbookInjector,
)
from app.services.worldbook.scanner import ActiveEntry, scan_worldbook
from app.services.worldbook.service import get_worldbooks_by_ids
from app.services.mvu_runtime.policy import build_mvu_policy_for_user_persona
from app.services.mvu_runtime.scope import build_macro_scope
from app.services.mvu_runtime.worldbook import (
    filter_worldbook_entries_for_prompt,
)
from app.services.token_budget import (
    build_prompt_budget_plan,
    build_token_budget_report,
    count_message_tokens,
    count_text_tokens,
    resolve_worldbook_budget,
)
from app.services.langgraph.state import ChatState

logger = logging.getLogger(__name__)

_summary_tasks_inflight: set[UUID] = set()


def _should_retire_backend_apply(state: dict) -> bool:
    """判断本轮是否跳过后端 MVU 状态应用。

    三个条件同时满足时，后端只保留更新 ops 与诊断信息，不直接写 stat_data：
    全局退役开关打开、浏览器运行时打开、当前对话实际启用 MVU。
    """
    return bool(
        settings.MVU_RETIRE_BACKEND_APPLY
        and settings.MVU_BROWSER_RUNTIME
        and state.get("persona_uses_mvu")
    )


def _block_enabled(state: ChatState, key: str) -> bool:
    """检查当前 template 是否启用某个 block。

    key 通常是 dynamic_ref（"memories" / "relationship" / "profile" /
    "constraints" / "summary"）。enabled_blocks 由 chat_service 预加载。

    安全降级：state 里缺 enabled_blocks 时视为启用，保证非聊天链路复用节点时不误关功能。
    """
    blocks = state.get("enabled_blocks")
    if blocks is None:
        return True
    return key in blocks


async def node_retrieve_memories(state: ChatState) -> dict:
    # 记忆 block 关闭时，本轮不做向量检索，也不会产生 memory_recall 事件。
    if not _block_enabled(state, "memories"):
        return {"recalled_memories": []}
    try:
        retrieval_query = await rewrite_query_for_retrieval(state["user_message"])
        user_id_str = str(state["user_id"])
        conv_scope = f"conversation:{state['conversation_id']}"

        memories = await search_memories(
            user_id=user_id_str,
            query=retrieval_query,
            top_k=settings.MEMORY_TOP_K,
            threshold=settings.MEMORY_SIMILARITY_THRESHOLD,
            scope_filter=conv_scope,
        )

        if memories:
            _asyncio.create_task(_update_reference_counts(
                user_id_str, [m["memory_id"] for m in memories]
            ))

        logger.info(
            f"记忆检索: '{retrieval_query[:30]}' → {len(memories)} 条"
        )
        return {"recalled_memories": memories}
    except Exception as e:
        logger.warning(f"记忆检索失败，降级为空: {e}")
        return {"recalled_memories": []}


async def _update_reference_counts(user_id_str: str, memory_ids: list[str]) -> None:
    """后台异步：更新被引用记忆的 reference_count 和 last_referenced_at。"""
    from datetime import datetime
    try:
        async with AsyncSessionLocal() as db:
            for mid in memory_ids:
                from sqlalchemy import text
                await db.execute(
                    text("UPDATE memories SET reference_count = reference_count + 1, last_referenced_at = :now WHERE id = CAST(:id AS UUID)"),
                    {"now": datetime.utcnow(), "id": mid}
                )
            await db.commit()
        logger.debug(f"已更新 {len(memory_ids)} 条记忆引用计数")
    except Exception:
        logger.exception("更新引用计数失败")


async def node_activate_worldbook(state: ChatState) -> dict:
    """扫描对话绑定的所有世界书，产出激活集到 state.wi_activated。

    位置：retrieve_memories → activate_worldbook → resolve_profile
    输出：state["wi_activated"] = [dict(...ActiveEntry 字段)]
    SSE：上游 chat_service 读 wi_activated 发 worldinfo_activated 事件
    """
    try:
        async with AsyncSessionLocal() as db:
            conv_result = await db.execute(
                select(Conversation).where(Conversation.id == state["conversation_id"])
            )
            conv = conv_result.scalar_one_or_none()
            if conv is None:
                return {"wi_activated": []}
            # 对话只保存世界书 ID 列表；扫描前先过滤非法 UUID，再批量取书。
            wid_strs = list(conv.worldbook_ids or [])
            if not wid_strs:
                return {"wi_activated": []}

            from uuid import UUID as _UUID
            wid_uuids = []
            for x in wid_strs:
                try:
                    wid_uuids.append(_UUID(str(x)))
                except (TypeError, ValueError):
                    continue
            books = await get_worldbooks_by_ids(db, wid_uuids)

            book_dicts = [
                {
                    "id": str(b.id),
                    "name": b.name,
                    "scan_depth": b.scan_depth,
                    "case_sensitive": b.case_sensitive,
                    "match_whole_words": b.match_whole_words,
                    "entries": b.entries or [],
                    "extensions": b.extensions or {},
                }
                for b in books
            ]

            # 扫描器需要完整时间顺序历史，用于按 scan_depth 构造关键词缓冲区。
            msgs_result = await db.execute(
                select(Message)
                .where(Message.conversation_id == state["conversation_id"])
                .order_by(Message.created_at.asc())
            )
            history = [{"role": m.role, "content": m.content} for m in msgs_result.scalars().all()]

        chat_cfg = conv.chat_config or {}
        activated = scan_worldbook(
            worldbooks=book_dicts,
            history_messages=history,
            chat_config=chat_cfg,
        )

        # ActiveEntry 是运行时对象；LangGraph state 里只保留可序列化字段。
        wi_activated = [
            {
                "uid": ae.entry.get("uid"),
                "comment": ae.entry.get("comment", ""),
                "content": ae.content,
                "position": ae.position,
                "depth": ae.depth,
                "order": ae.order,
                "role": ae.role,
                "outlet_name": ae.outlet_name,
                "worldbook_id": ae.worldbook_id,
                "worldbook_name": ae.worldbook_name,
                "output_contract": ae.entry.get("output_contract"),
            }
            for ae in activated
        ]
        return {"wi_activated": wi_activated}
    except Exception:
        logger.exception("世界书扫描失败，本轮不注入")
        return {"wi_activated": []}


async def _load_user_persona(state: ChatState) -> Persona | None:
    """从 ChatState.conversation_id 加载 user_persona；None = 没设/不存在。"""
    async with AsyncSessionLocal() as db:
        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == state["conversation_id"])
        )
        conv = conv_result.scalar_one_or_none()
        user_persona_id = conv.user_persona_id if conv else None
        if user_persona_id is None:
            return None
        up_result = await db.execute(
            select(Persona).where(Persona.id == user_persona_id)
        )
        return up_result.scalar_one_or_none()


async def node_resolve_profile_section(state: ChatState) -> dict:
    """产出"## 关于用户"段落。

    功能开关：profile block 关闭 → 跳过。
    """
    if not _block_enabled(state, "profile"):
        return {"profile": None, "profile_section": ""}

    try:
        user_persona = await _load_user_persona(state)
        if user_persona is None:
            return {"profile": None, "profile_section": ""}
        section = _build_user_persona_profile(user_persona)
        logger.info(f"画像解析: user_persona={user_persona.name}")
        return {"profile": None, "profile_section": section}
    except Exception as e:
        logger.warning(f"画像段落构建失败: {e}")
        return {"profile": None, "profile_section": ""}


def _cd(persona: Persona, key: str, default=None):
    """从角色卡 card_data JSONB 读取辅助字段。"""
    if persona and persona.card_data and key in persona.card_data:
        val = persona.card_data[key]
        if isinstance(val, list):
            return val
        if val is not None and val != "":
            return val
    return default


def _build_user_persona_profile(p: Persona) -> str:
    """构建"## 关于用户"段落。"""
    lines = [f"姓名：{p.name}"]
    gender = _cd(p, 'gender')
    if gender:
        lines.append(f"性别：{gender}")
    age = _cd(p, 'age')
    if age:
        lines.append(f"年龄/身份：{age}")
    if p.personality:
        lines.append(f"性格：{p.personality}")
    if p.background:
        lines.append(f"背景：{p.background}")
    speaking = _cd(p, 'speaking_style')
    if speaking:
        lines.append(f"说话风格：{speaking}")
    interests = _cd(p, 'interests')
    if interests:
        lines.append(f"兴趣：{', '.join(interests)}")
    return "## 关于用户\n" + "\n".join(lines) if lines else ""


async def node_assess_relationship(state: ChatState) -> dict:
    """读取好感度关系，生成 Prompt 段落（不调 LLM，纯 DB 读取 + 文本映射）。"""
    # 关系 block 关闭或当前对话没有 AI 角色时，不生成关系提示，也不检测里程碑。
    persona_id = state.get("persona_id")
    if not _block_enabled(state, "relationship") or persona_id is None:
        return {
            "relationship": None,
            "relationship_level": 0,
            "relationship_section": "",
            "level_changed": False,
            "new_milestone": None,
        }

    try:
        async with AsyncSessionLocal() as db:
            user_id_str = str(state["user_id"])
            persona_id_str = str(persona_id)
            user_persona_id = state.get("user_persona_id")
            user_persona_id_str = str(user_persona_id) if user_persona_id else None

            assessment = await assess_relationship(
                db, user_id_str, persona_id_str,
                user_persona_id=user_persona_id_str,
                conversation_id=str(state["conversation_id"]),
            )

            rel = await get_or_create_relationship(
                db, user_id_str, persona_id_str,
                user_persona_id=user_persona_id_str,
            )
            new_milestones = await detect_milestones(
                db, rel,
                assessment["total_messages"],
                assessment["deep_talk_count"],
                assessment["days_span"],
            )
            new_milestone = new_milestones[0] if new_milestones else None

            section = _build_relationship_section(assessment)

            logger.info(
                f"关系评估完成: level={assessment['level']}({assessment['level_name']}), "
                f"affinity={assessment['affinity_score']}"
            )
            return {
                "relationship": assessment,
                "relationship_level": assessment["level"],
                "relationship_section": section,
                "level_changed": assessment["level"] > rel.level,
                "new_milestone": new_milestone,
            }
    except Exception as e:
        logger.warning(f"关系评估失败: {e}")
        return {
            "relationship": None,
            "relationship_level": 0,
            "relationship_section": "",
            "level_changed": False,
            "new_milestone": None,
        }


def _build_relationship_section(assessment: dict) -> str:
    """根据关系评估结果构建 Prompt 段落。"""
    level = assessment["level"]
    level_name = assessment["level_name"]
    total = assessment["total_messages"]
    days = assessment.get("days_span", 0)

    level_guidance = {
        0: "你们还不太熟，请保持礼貌和适度的距离感，先从轻松的话题开始建立信任",
        1: "你们已经认识一段时间了，可以适当聊一些个人话题，但不要过于深入",
        2: "你们是朋友了，语气可以放松自然，适当开一些无伤大雅的玩笑，展现真实的性格",
        3: "你们关系很亲密，回复可以更加随性和温柔，可以主动关心对方的状态",
        4: "你们是知己，可以无话不谈，分享内心真实的想法和感受，像老朋友一样自在",
    }

    lines = [
        "## 当前关系",
        f"- 你和用户已经是 **{level_name}** 了（等级 {level}/4）",
    ]
    if total > 0:
        lines.append(f"- 你们已经聊了 {total} 轮，持续了 {days} 天")
    lines.append(f"- {level_guidance.get(level, level_guidance[0])}")

    return "\n".join(lines)


# ─── Token 计数与预算 ─────────────────────────────────────────────

def _count_tokens(text: str) -> int:
    """估算文本 token 数。"""
    return count_text_tokens(text)


def _count_message_tokens(messages: list[dict]) -> int:
    """计算消息列表的 token 总数（含 role 格式开销，每条 +4）。"""
    return count_message_tokens(messages)


def _history_message_dict(message: Message) -> dict:
    """把 Message ORM 转为可跨 LangGraph 节点传递的普通 dict。"""
    return {
        "role": message.role,
        "content": message.content or "",
    }


def _truncate_history(history: list, budget: int) -> list:
    """从旧到新截断历史，丢弃超出 budget 的旧消息。

    始终保留最后一条（当前用户输入）。
    """
    if not history:
        return []

    filtered = []
    for m in history:
        if isinstance(m, dict):
            role = m.get("role")
            content = m.get("content")
        else:
            role = getattr(m, "role", None)
            content = getattr(m, "content", None)
        if role in ("user", "assistant"):
            filtered.append({"role": role, "content": content or ""})

    if not filtered:
        return []

    # 当前用户输入是本轮生成的核心输入，即使历史预算紧张也必须保留。
    current_input = filtered[-1]
    older = filtered[:-1]

    used = _count_tokens(current_input["content"]) + 4
    kept = []
    for msg in reversed(older):
        msg_tokens = _count_tokens(msg["content"]) + 4
        if used + msg_tokens > budget:
            break
        used += msg_tokens
        kept.insert(0, msg)

    kept.append(current_input)
    return kept


# ─── 历史消息处理 ─────────────────────────────────────────────

async def node_prepare_history(state: ChatState) -> dict:
    """准备对话历史窗口与 summary 上下文。

    该节点只负责消息读取、窗口切分、summary 调度与历史元数据产出。
    Token budget 截断仍留在 node_build_prompt，因为它依赖已经渲染好的 prompt prefix。
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == state["conversation_id"],
                Conversation.user_id == state["user_id"],
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            return {"error": "对话不存在"}

        msgs_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == state["conversation_id"])
            .order_by(Message.created_at.asc())
        )
        all_messages = list(msgs_result.scalars().all())

        summary = None
        summary_enabled = _block_enabled(state, "summary")
        if len(all_messages) > settings.WINDOW_SIZE:
            # 先按消息数量切窗口：旧消息进入摘要候选，最近消息进入 prompt 候选。
            overflow = all_messages[: len(all_messages) - settings.WINDOW_SIZE]
            recent = all_messages[len(all_messages) - settings.WINDOW_SIZE :]

            # 摘要 block 关闭时，不读取旧摘要，也不触发后台摘要任务。
            if summary_enabled:
                summary = conv.summary
                already_summarized = min(conv.last_summarized_count or 0, len(overflow))
                new_overflow = overflow[already_summarized:]

                batch_size = max(1, settings.SUMMARY_BATCH_MESSAGES)
                if len(new_overflow) >= batch_size:
                    if conv.id in _summary_tasks_inflight:
                        logger.debug(
                            f"摘要任务已在进行中，跳过重复触发: conv={conv.id}, "
                            f"pending={len(new_overflow)}"
                        )
                    else:
                        _summary_tasks_inflight.add(conv.id)
                        logger.info(
                            f"触发后台摘要: conv={conv.id}, "
                            f"pending={len(new_overflow)}, batch={batch_size}"
                        )
                        _asyncio.create_task(_update_summary_background(
                            conv_id=conv.id,
                            messages=new_overflow,
                            existing_summary=conv.summary,
                            summarized_count=len(overflow),
                        ))
                elif new_overflow:
                    logger.debug(
                        f"摘要待积累: conv={conv.id}, "
                        f"pending={len(new_overflow)}, batch={batch_size}"
                    )
        else:
            recent = all_messages

        dialogue_count = sum(
            1 for m in all_messages if m.role in ("user", "assistant")
        )

        return {
            "recent_messages": [_history_message_dict(m) for m in recent],
            "summary_context": summary or "",
            "dialogue_message_count": dialogue_count,
            "is_first_round": len(all_messages) <= 1,
            "error": None,
        }

# ─── Prompt 组装 ─────────────────────────────────────────────────

async def node_build_prompt(state: ChatState) -> dict:
    """组装发给聊天模型的完整 messages 列表。

    主流程分为：加载对话资源、构造运行时上下文、渲染模板骨架、
    截断并追加历史、插入 Author's Note、注入世界书和预设、执行
    promptOnly 正则，最后返回可直接发送给 LLM 的 messages。
    """
    from app.services.prompt_renderer import (
        PromptRenderer,
        DEFAULT_TEMPLATE_BLOCKS,
        prompt_block_from_dict,
    )
    from app.services.preset_injector import PresetInjector
    from app.services.regex_processor import RegexProcessor
    from app.services.preset_service import get_preset_for_injection
    from app.models.prompt_template import PromptTemplate as PTModel

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == state["conversation_id"],
                Conversation.user_id == state["user_id"],
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            return {"error": "对话不存在"}

        persona = None
        if conv.persona_id:
            p_result = await db.execute(
                select(Persona).where(Persona.id == conv.persona_id)
            )
            persona = p_result.scalar_one_or_none()

        recent = state.get("recent_messages") or []
        summary = state.get("summary_context", "")

        # 把召回记忆整理成一段 system 内容，交给模板里的 memories block 注入。
        recalled = state.get("recalled_memories", [])
        memory_ctx = ""
        if recalled:
            lines = ["[关于用户的关键信息 — 请自然引用]"]
            for m in recalled:
                lines.append(f"- {m['content']}")
            lines.append("请在合适的时机自然地引用这些信息，不要生硬列举。")
            memory_ctx = "\n".join(lines)

        context = {
            "persona": persona,
            "relationship_context": state.get("relationship_section", ""),
            "memory_context": memory_ctx,
            "profile_context": state.get("profile_section", ""),
            "summary_context": summary,
            "reply_length": state.get("reply_length", "medium"),
            "author_note": conv.author_note or "",
        }

        # ── 宏作用域与 MVU 运行策略 ──
        # names 提供 {{user}} / {{char}}；local/global 提供变量桶。
        # MVU 运行策略决定是否暴露变量桶、是否执行 EJS、是否过滤 MVU 条目。
        user_result = await db.execute(
            select(User).where(User.id == state["user_id"])
        )
        user_row = user_result.scalar_one_or_none()
        user_persona_name = ""
        if conv.user_persona_id:
            up_result = await db.execute(
                select(Persona.name).where(Persona.id == conv.user_persona_id)
            )
            user_persona_name = up_result.scalar_one_or_none() or ""
        mvu_policy = build_mvu_policy_for_user_persona(user=user_row, persona=persona)
        # scope 使用 JSON 副本，避免渲染阶段直接修改 ORM JSONB 引用。
        scope = build_macro_scope(
            policy=mvu_policy,
            conversation_variables=conv.variables,
            user_global_variables=(user_row.global_variables if user_row else None),
            user_name=user_persona_name or (user_row.nickname if user_row else ""),
            char_name=persona.name if persona else "",
        )

        # 对话可绑定自定义模板；未绑定时使用内置默认模板。
        template = None
        if conv.template_id:
            t_result = await db.execute(
                select(PTModel).where(PTModel.id == conv.template_id)
            )
            template = t_result.scalar_one_or_none()

        if template and template.blocks:
            blocks = [
                block for raw in template.blocks
                if (block := prompt_block_from_dict(raw)) is not None
            ]
        else:
            blocks = DEFAULT_TEMPLATE_BLOCKS
        wi_activated = state.get("wi_activated") or []
        rendered = PromptRenderer.render(
            blocks,
            context,
            wi_activated=wi_activated,
            scope=scope,
            run_ejs=mvu_policy.run_ejs,
        )
        logger.info(
            f"使用模板: {template.name if template else '默认'} | "
            f"预设: {conv.preset_id or '无'} | "
            f"WI 激活: {len(wi_activated)}"
        )

        # 模板渲染后先打临时锚点，后续世界书注入器靠这些锚点定位注入位置。
        for m in rendered:
            if m.get("_block_id") == "char_desc":
                m[ANCHOR_KEY] = ANCHOR_CHAR_DESC

        # 对话示例的第一条消息作为 EM 锚点，用于 EM_TOP / EM_BOTTOM 注入。
        em_first = next(
            (m for m in rendered if m.get("_block_id") == "mes_example"), None,
        )
        if em_first is not None:
            em_first[ANCHOR_KEY] = ANCHOR_MES_EXAMPLE

        # ── 历史预算与历史渲染 ──
        # 先用已渲染的 system 前缀估算剩余 token，再从最近窗口中保留尽量多的历史。
        cc = conv.chat_config or {}
        history_candidates = [
            {"role": m.get("role"), "content": m.get("content") or ""}
            for m in recent
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        ]
        wi_for_budget = filter_worldbook_entries_for_prompt(wi_activated, mvu_policy)
        wi_budget_messages = [
            {
                "role": str((entry or {}).get("role") or "system"),
                "content": (entry or {}).get("content") or "",
            }
            for entry in wi_for_budget
        ]
        budget_plan = build_prompt_budget_plan(
            prefix_messages=rendered + wi_budget_messages,
            chat_config=cc,
            reply_length=state.get("reply_length", "medium"),
        )
        truncated = _truncate_history(recent, max(budget_plan.history_budget, 100))
        # 历史消息只在本轮 prompt 中按当前 scope 渲染，不把渲染结果写回数据库。
        for h in truncated:
            h["content"] = _render_content(
                h.get("content", ""), scope, run_ejs=mvu_policy.run_ejs,
            )
        history_start_idx = len(rendered)
        rendered.extend(truncated)

        # ── Author's Note 注入 ──
        # Author's Note 作为可配置的提示块插入历史深处；an_depth 控制离末尾多远。
        if conv.author_note and conv.author_note.strip():
            an_msg_count = state.get("dialogue_message_count", 0)
            interval = max(1, conv.an_interval or 1)
            # interval=1 表示每轮注入；更大的 interval 表示每 N 条消息注入一次。
            if interval == 1 or (an_msg_count % interval == 0):
                an_role = conv.an_role or "system"
                an_depth = max(0, conv.an_depth or 0)
                history_length = len(rendered) - history_start_idx
                if an_depth >= history_length:
                    insert_idx = history_start_idx
                else:
                    insert_idx = len(rendered) - an_depth
                rendered.insert(insert_idx, {
                    "role": an_role,
                    "content": _render_content(
                        conv.author_note, scope, run_ejs=mvu_policy.run_ejs,
                    ),
                    ANCHOR_KEY: ANCHOR_AUTHOR_NOTE,
                })

        # ── MVU 世界书条目过滤 ──
        # 更新规则类条目不直接注入主回复 prompt，避免模型在可见正文中输出隐藏变量块。
        # 原始激活集仍保留在 state 里，供更新通道和诊断视图使用。
        wi_activated = filter_worldbook_entries_for_prompt(wi_activated, mvu_policy)

        # ── Worldbook 注入：按 8 个 position 分发 ──
        if wi_activated:
            wi_as_active = [
                ActiveEntry(
                    entry=e,
                    worldbook_id=e.get("worldbook_id", ""),
                    worldbook_name=e.get("worldbook_name", ""),
                    position=int(e.get("position", 0)),
                    depth=int(e.get("depth", 4)),
                    order=int(e.get("order", 100)),
                    role=str(e.get("role", "system")),
                    outlet_name=e.get("outlet_name"),
                    content=e.get("content", ""),
                )
                for e in wi_activated
            ]
            rendered = WorldbookInjector.inject(
                rendered,
                wi_as_active,
                history_start_idx,
                scope=scope,
                run_ejs=mvu_policy.run_ejs,
            )
        else:
            # 即使没有激活条目，也要通过注入器剥掉模板锚点。
            rendered = WorldbookInjector.inject(
                rendered,
                [],
                history_start_idx,
                scope=scope,
                run_ejs=mvu_policy.run_ejs,
            )

        # _block_id 只服务于本地注入定位，不能发送给 LLM。
        rendered = [
            {k: v for k, v in m.items() if k != "_block_id"}
            for m in rendered
        ]

        # ── 预设注入 ──
        if conv.preset_id:
            preset = await get_preset_for_injection(db, conv.preset_id)
            if preset:
                rendered = PresetInjector.inject(
                    rendered, preset, scope, run_ejs=mvu_policy.run_ejs,
                )

        # ── promptOnly 正则后处理 ──
        # 这里处理的是"发给 LLM 之前"的正则脚本，只会取 promptOnly=true 的脚本。
        # 脚本来源优先 conv.regex_preset_id；未显式选择时，可从当前 preset 绑定的
        # regex_preset_id 回退。拿到脚本后，对已经组装好的 messages 做一次最终改写。
        #
        # macro_scope 传给 RegexProcessor，是为了支持 ST 的 substituteRegex：
        # 当脚本允许宏替换时，findRegex / replaceString 里的 {{user}}、{{char}}、
        # getvar 等宏会按当前对话 scope 先渲染，再参与正则匹配/替换。
        from app.services.regex_preset_service import get_prompt_only_scripts
        scripts = await get_prompt_only_scripts(
            db, conv.regex_preset_id, conv.preset_id,
        )
        if scripts:
            rendered = RegexProcessor.apply_prompt_only(
                rendered, scripts, macro_scope=scope,
            )

        # ── 可见输出尾部契约提示 ──
        # 这段必须在 system 合并前追加，确保最终仍处于 prompt 末端的 system 区。
        # 世界书中的状态栏 / 日志栏等尾部模板由 output_contracts 统一识别；
        # 这里仅消费契约模块产出的提示文本。
        if settings.WORLDBOOK_TAIL_TEMPLATE_ENFORCEMENT and wi_activated:
            from app.services.output_contracts import (
                build_output_contract_prompt,
                build_tail_template_directive,
                build_visible_output_contract,
            )

            output_contract = build_visible_output_contract(wi_activated, cc)

            logger.info(
                "[提示词注入] 契约 active=%s mode=%s tail_blocks=%d",
                output_contract.active,
                output_contract.mode,
                len(output_contract.required_tail_blocks),
            )

            tail_blocks = output_contract.required_tail_blocks
            if tail_blocks:
                directive = build_tail_template_directive(tail_blocks)
                rendered.append({"role": "system", "content": directive})
                logger.info(
                    "[尾部模板兜底] 注入约束：%s",
                    [block.marker for block in tail_blocks],
                )

            # ADR-1e §2 生成前锚定：full_document 契约注入整篇结构约束。
            if output_contract.required_sections:
                fd_directive = build_output_contract_prompt(output_contract)
                if fd_directive:
                    rendered.append({"role": "system", "content": fd_directive})
                    logger.info(
                        "[整篇结构锚定] 注入 full_document 约束：%d sections",
                        len(output_contract.required_sections),
                    )

        # 主回复只写可见叙事；变量更新由回复后的独立更新通道处理。
        if mvu_policy.divert_update_entries:
            rendered.append({"role": "system", "content": _MVU_DOUBLE_AI_DIRECTIVE})

        # squash 策略：仅在有预设时合并连续 system 消息。
        # 理由：预设 position=0/1 注入会产生多块紧邻的 system，合并为单条以满足
        # OpenAI Chat Completion 单 system 约束（DeepSeek 容忍多 system 但合并更稳）；
        # 无预设时 system 块自然只有 1-2 条，无需合并。
        if conv.preset_id:
            rendered = _squash_system_messages(rendered)

        token_budget_report = build_token_budget_report(
            plan=budget_plan,
            final_prompt_tokens=_count_message_tokens(rendered),
            history_tokens=_count_message_tokens(truncated),
            history_candidate_tokens=_count_message_tokens(history_candidates),
            history_kept_messages=len(truncated),
            history_candidate_messages=len(history_candidates),
            worldbook_used_tokens=sum(
                _count_tokens((entry or {}).get("content") or "")
                for entry in wi_activated
            ),
            worldbook_budget=resolve_worldbook_budget(cc),
        )

        if truncated:
            _log_messages(rendered, persona.name if persona else "无角色")

        is_first = state.get("is_first_round", False)

        return {
            "messages": rendered,
            "system_prompt": rendered[0]["content"][:200] if rendered else "",
            "persona_name": persona.name if persona else None,
            # 下游只读取这个有效值，确保所有 MVU 更新、同步和落库路径使用同一套开关。
            "persona_uses_mvu": mvu_policy.active,
            "is_first_round": is_first,
            "error": None,
            "mvu_scope": scope,
            "token_budget_report": token_budget_report,
        }


# ─── 辅助函数 ────────────────────────────────────────────────────

# 主回复阶段的 MVU 提示：正文只负责叙事，变量更新交给独立更新通道。
_MVU_TOOL_DIRECTIVE = (
    "[状态更新 — 工具模式]\n"
    "本轮若剧情导致角色状态变量（stat_data）发生变化，请**调用 update_variables 工具**"
    "提交一组 JSON Patch 变更；**不要**在回复正文里输出 <UpdateVariable> / <JSONPatch> "
    "文本块。若本轮无任何变化，可以不调用该工具。变量字段、取值范围与更新规则见 "
    "update_variables 工具说明。"
)


_MVU_DOUBLE_AI_DIRECTIVE = (
    "[MVU state update - double-ai mode]\n"
    "Write only the visible narrative reply. Do not output <UpdateVariable>, "
    "<JSONPatch>, or any hidden state-update block in the reply body. If the "
    "scene changes character state, the system will run a separate update pass "
    "after your reply."
)


def _squash_system_messages(messages: list[dict]) -> list[dict]:
    """合并连续的 system-role 消息为一条。"""
    result = []
    buffer = []
    for msg in messages:
        if msg["role"] == "system":
            buffer.append(msg["content"])
        else:
            if buffer:
                result.append({"role": "system", "content": "\n\n".join(buffer)})
                buffer = []
            result.append(msg)
    if buffer:
        result.append({"role": "system", "content": "\n\n".join(buffer)})
    return result


def _log_messages(all_messages: list, persona_name: str) -> None:
    """输出发送给 LLM 的完整 messages 列表，便于查看生效的提示词。"""
    total_tokens = _count_message_tokens(all_messages)

    parts: list[str] = []
    for i, m in enumerate(all_messages):
        role = m["role"]
        if role == "system":
            tag = f"SYSTEM #{i}"
        elif role == "user":
            tag = f"用户 #{i}"
        elif role == "assistant":
            tag = f"{persona_name} #{i}"
        else:
            tag = f"{role} #{i}"

        content = m["content"]
        if role == "system":
            preview = content
        else:
            preview = content[:300] + ("..." if len(content) > 300 else "")

        parts.append(f"  [{tag}] ({_count_tokens(content)} tokens)\n    {preview}")

    separator = "─" * 60
    logger.info(
        f"{separator}\n"
        f"发送给 LLM — 共 {len(all_messages)} 条消息, {total_tokens} tokens (角色: {persona_name})\n"
        f"{separator}\n"
        + "\n\n".join(parts)
        + f"\n{separator}"
    )


# ─── 后处理 ──────────────────────────────────────────────────────
# 回复生成不在 graph 节点中。chat_service 负责逐 token 流式输出；
# 本节点在流式完成后统一处理落库、状态更新和后台任务。


async def node_post_process(state: ChatState) -> dict:
    """处理一次模型回复完成后的所有写路径。

    这里集中完成：回复文本管道处理、assistant 消息落库、MVU 变量更新、
    情绪与好感度感知、关系统计更新、后台记忆提取触发。

    返回 dict 会被 LangGraph 自动 merge 进 state；chat_service 手动调用本节点时
    也直接读返回 dict（不依赖 state merge）。
    """
    if state.get("error"):
        return {
            "new_memories_count": 0,
            "assistant_message_id": None,
            "affinity_delta": 0,
            "affinity_reason": "",
            "affinity_score": None,
        }

    assistant_message_id: str | None = None
    affinity_delta_out: int = 0
    affinity_reason_out: str = ""
    affinity_score_out: float | None = None

    async with AsyncSessionLocal() as db:
        conv_id = state["conversation_id"]
        user_id = state["user_id"]

        # 后处理管道需要对话配置来决定回复正则、显示版清理和 MVU 写入策略。
        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == conv_id)
        )
        conv_for_pipeline = conv_result.scalar_one_or_none()
        mvu_active = bool(state.get("persona_uses_mvu"))

        # ── 回复文本管道 ──
        # 同一条管道会产出两份文本：content 是进入历史的真相版，display_content
        # 是给前端渲染的显示版。这里不再跑宏，只处理回复正则、显示清理和变量块。
        processed_reply = state.get("assistant_reply") or ""
        display_reply = processed_reply
        scope_before = state.get("mvu_scope") if mvu_active else None
        # MVU 约束从本轮激活的更新规则条目提取，用于校验状态写入。
        from app.services.mvu_runtime import extract_constraints_from_entries
        mvu_constraints = (
            extract_constraints_from_entries(state.get("wi_activated"))
            if mvu_active
            else {}
        )
        update_diag = {"applied": 0, "dropped": [], "coerced": [], "clamped": []}
        update_channel = "none"
        if processed_reply and conv_for_pipeline is not None:
            from app.services.message_pipeline import process_assistant_message_text
            processed_reply, display_reply, scope_after = await process_assistant_message_text(
                processed_reply,
                db=db,
                conv=conv_for_pipeline,
                mvu_scope=scope_before,
                macro_scope=None,
                run_macro=False,
                apply_update_variable=False,
                constraints=mvu_constraints,
                update_diag=update_diag,
            )
            # 写回 state，供 message_done 分别透出 final_content / final_display_content。
            state["assistant_reply"] = processed_reply
            state["assistant_display"] = display_reply
            if scope_after is not None:
                state["mvu_scope"] = scope_after
            if update_diag["applied"] or update_diag["dropped"]:
                update_channel = "text"

        # ── ADR-1e 阶段5：可见输出契约执行（full_document 确定性修复）──
        # 必须在双视图（回复正则）之后、落库之前，让修复结果进入 content / display。
        # 只处理 full_document（有 required_sections）；append_tail 仍由 chat_service
        # 流式 continuation 处理。确定性修复不改语义内容，故 MVU ops 不受影响。
        output_contract_diag = None
        if processed_reply:
            try:
                from app.services.output_contracts import (
                    build_contract_sse,
                    compile_contract,
                    enforce_visible_output_contract,
                    resolve_policy,
                )

                _oc = compile_contract(state.get("wi_activated"))
                if _oc.required_sections:
                    _oc_cfg = state.get("output_contract_config") or {}
                    _oc_policy = resolve_policy(
                        _oc,
                        account_defaults=_oc_cfg.get("account_defaults"),
                        conversation_overrides=_oc_cfg.get("overrides"),
                    )
                    _oc_result = await enforce_visible_output_contract(
                        content=processed_reply,
                        display_content=display_reply,
                        contract=_oc,
                        messages=state.get("messages"),
                        policy=_oc_policy,
                    )
                    processed_reply = _oc_result.content
                    display_reply = _oc_result.display_content
                    state["assistant_reply"] = processed_reply
                    state["assistant_display"] = display_reply
                    _oc_diag = _oc_result.diagnostics
                    output_contract_diag = build_contract_sse(
                        contract=_oc,
                        contract_mode="full_document",
                        requested_mode=_oc_result.requested_mode,
                        effective_mode=_oc_result.effective_mode,
                        outcome=_oc_result.outcome,
                        coverage=_oc_result.coverage,
                        method=_oc_result.method,
                        initial=None,
                        final=None,
                        actions=_oc_result.actions,
                        latency_ms=_oc_result.latency_ms,
                        extra_calls=_oc_result.extra_calls,
                    )
                    # executor 已把 initial/final 压成 {ok, issues}，直接透传其结构。
                    output_contract_diag["initial"] = _oc_diag.get(
                        "initial", {"ok": True, "issues": []}
                    )
                    output_contract_diag["final"] = _oc_diag.get(
                        "final", {"ok": _oc_result.outcome == "passed", "issues": []}
                    )
                    logger.info(
                        "[输出契约] full_document outcome=%s coverage=%s method=%s actions=%d",
                        _oc_result.outcome,
                        _oc_result.coverage,
                        _oc_result.method,
                        len(_oc_result.actions),
                    )
            except Exception:
                logger.exception("[输出契约] full_document 执行失败，保留原回复")
        state["output_contract_diag"] = output_contract_diag

        # 浏览器运行时接管 MVU 时，后端只保留 ops 与诊断，不直接修改 stat_data。
        _retire_apply = _should_retire_backend_apply(state)

        # ── 主调用 tool 更新通道 ──
        # 如果主模型返回了 update_variables tool call，把 tool 参数解析成 JSON Patch
        # 并应用到同一个 stat_data 桶。
        tool_calls = state.get("mvu_tool_calls")
        if mvu_active and tool_calls and not _retire_apply:
            from app.services.mvu_runtime.tools import extract_update_ops_from_tool_calls
            from app.services.message_pipeline import _apply_json_patch_ops
            ops = extract_update_ops_from_tool_calls(tool_calls)
            if ops:
                scope_after = state.get("mvu_scope") or {"local": {}, "global": {}, "names": {}}
                local_bucket = scope_after.setdefault("local", {})
                stat_data = local_bucket.setdefault("stat_data", {})
                if not isinstance(stat_data, dict):
                    stat_data = {}
                    local_bucket["stat_data"] = stat_data
                _apply_json_patch_ops(stat_data, ops, mvu_constraints, update_diag)
                state["mvu_scope"] = scope_after
                update_channel = "tool"

        double_ai_ops = state.get("mvu_double_ai_ops")
        if mvu_active and double_ai_ops and not _retire_apply:
            # double-ai 更新通道已经在 chat_service 中产出 ops；这里统一应用到状态桶。
            from app.services.message_pipeline import _apply_json_patch_ops
            scope_after = state.get("mvu_scope") or {"local": {}, "global": {}, "names": {}}
            local_bucket = scope_after.setdefault("local", {})
            stat_data = local_bucket.setdefault("stat_data", {})
            if not isinstance(stat_data, dict):
                stat_data = {}
                local_bucket["stat_data"] = stat_data
            _apply_json_patch_ops(stat_data, double_ai_ops, mvu_constraints, update_diag)
            state["mvu_scope"] = scope_after
            update_channel = "double_ai"

        # 后端不 apply 时，诊断仍标记本轮更新交给浏览器运行时处理。
        if _retire_apply and (state.get("mvu_double_ai_ops") or state.get("mvu_tool_calls")):
            update_channel = "browser"

        state["mvu_update_diag"] = update_diag
        state["mvu_update_channel"] = update_channel

        if processed_reply:
            import uuid as _uuid
            msg_id = _uuid.uuid4()
            assistant_msg = Message(
                id=msg_id,
                conversation_id=conv_id, role="assistant", content=processed_reply,
                display_content=display_reply,
            )
            db.add(assistant_msg)
            # 立即把 UUID 返回给 SSE；不等 flush 后的 column default。
            assistant_message_id = str(msg_id)

            if state.get("is_first_round"):
                if conv_for_pipeline and conv_for_pipeline.title is None:
                    msg = state["user_message"]
                    conv_for_pipeline.title = msg[:30] + ("..." if len(msg) > 30 else "")
                    db.add(conv_for_pipeline)

        # 情感感知总开关：关闭时不写 EmotionRecord，也不更新好感度 delta。
        emotion_enabled = bool(conv_for_pipeline and conv_for_pipeline.analyze_emotion)

        # ── 情绪与好感度感知 ──
        # 本段在回复后运行，因为好感度变化需要结合"用户本轮输入 + AI 刚写出的回复"。
        # 关系提示词的读取在 graph 阶段完成；这里负责写入本轮感知结果。
        turn_delta: int = 0
        turn_reason: str = ""
        _perc_persona_id = state.get("persona_id")

        if emotion_enabled:
            _user_msg_text = (state.get("user_message") or "").strip()
            if len(_user_msg_text) <= settings.EMOTION_SKIP_TRIVIAL_CHARS:
                # 低信号短消息不调用感知模型，避免为"嗯""哦"这类填充轮消耗 token。
                state["emotion"] = "平静"
                state["emotion_intensity"] = 5
                state["emotion_confidence"] = 0.3
                state["emotion_triggers"] = []
                logger.info(
                    "情感感知：用户消息过短(%d<=%d)，跳过 assess_turn",
                    len(_user_msg_text), settings.EMOTION_SKIP_TRIVIAL_CHARS,
                )
            # 有用户消息且有 AI 回复时才调用感知模型。
            elif (state.get("assistant_reply") or "").strip():
                try:
                    from app.models.relationship import Relationship
                    per = None
                    if _perc_persona_id:
                        _per_result = await db.execute(
                            select(Persona).where(Persona.id == _perc_persona_id)
                        )
                        per = _per_result.scalar_one_or_none()

                    recent_result = await db.execute(
                        select(Message)
                        .where(
                            Message.conversation_id == conv_id,
                            Message.role.in_(("user", "assistant")),
                        )
                        .order_by(Message.created_at.desc())
                        .limit(settings.EMOTION_CONTEXT_MAX_MESSAGES)
                    )
                    recent_msgs = list(reversed(recent_result.scalars().all()))
                    recent_messages = [(m.role, m.content or "") for m in recent_msgs]

                    # 有 AI 角色时才评估好感度；没有显式人设时，感知模型会从回复推断态度。
                    want_affinity = bool(_perc_persona_id)
                    cur_affinity = 0.0
                    if want_affinity:
                        # 当前好感度作为本轮 delta 判断的基线。
                        _aff = await db.execute(
                            select(Relationship.affinity_score).where(
                                Relationship.user_id == user_id,
                                Relationship.persona_id == _perc_persona_id,
                                Relationship.user_persona_id == state.get("user_persona_id"),
                            )
                        )
                        cur_affinity = _aff.scalar_one_or_none() or 0.0

                    persona_desc = ""
                    if per:
                        _main = (per.personality or per.background or "").strip()
                        _style = (_cd(per, "speaking_style") or "").strip()
                        _dparts = []
                        if _main:
                            _dparts.append(_main)
                        if _style:
                            _dparts.append(f"说话风格：{_style}")
                        persona_desc = "\n".join(_dparts)

                    ta = await assess_turn(
                        recent_messages=recent_messages,
                        assistant_reply=state.get("assistant_reply") or "",
                        persona_name=(per.name if per else ""),
                        persona_desc=persona_desc,
                        scenario=((getattr(per, "scenario", None) if per else None) or ""),
                        affinity_score=cur_affinity,
                        assess_affinity=want_affinity,
                    )
                    state["emotion"] = ta.emotion
                    state["emotion_intensity"] = ta.intensity
                    state["emotion_confidence"] = ta.confidence
                    state["emotion_triggers"] = ta.triggers
                    turn_delta = ta.affinity_delta
                    turn_reason = ta.affinity_reason
                except Exception:
                    logger.exception("情感感知 assess_turn 失败，退化为默认值")

        if emotion_enabled:
            try:
                msg_result = await db.execute(
                    select(Message)
                    .where(Message.conversation_id == conv_id, Message.role == "user")
                    .order_by(Message.created_at.desc()).limit(1)
                )
                user_msg = msg_result.scalar_one_or_none()
                if user_msg:
                    emotion_record = EmotionRecord(
                        message_id=user_msg.id, conversation_id=conv_id,
                        # 感知未运行或失败时，用平静作为可落库的默认状态。
                        emotion=state.get("emotion") or "平静",
                        intensity=state.get("emotion_intensity") or 5,
                        confidence=state.get("emotion_confidence") or 0.3,
                        triggers=state.get("emotion_triggers") or [],
                    )
                    db.add(emotion_record)

                    conv_result = await db.execute(
                        select(Conversation).where(Conversation.id == conv_id)
                    )
                    conv = conv_result.scalar_one_or_none()
                    if conv:
                        sm = MoodStateMachine()
                        if conv.current_mood:
                            sm.current_mood = conv.current_mood
                            sm.current_intensity = conv.mood_intensity or 5
                        recent_records_result = await db.execute(
                            select(EmotionRecord)
                            .where(EmotionRecord.conversation_id == conv_id)
                            .order_by(EmotionRecord.created_at.desc()).limit(5)
                        )
                        recent_records = list(recent_records_result.scalars().all())
                        sm.recent_emotions = [
                            {"emotion": r.emotion, "confidence": r.confidence or 0.5}
                            for r in reversed(recent_records)
                        ]
                        new_mood, new_intensity = sm.update(
                            state.get("emotion") or "平静",
                            state.get("emotion_intensity") or 5,
                            state.get("emotion_confidence") or 0.3,
                        )
                        conv.current_mood = new_mood
                        conv.mood_intensity = new_intensity
                        db.add(conv)
            except Exception:
                logger.exception("情绪记录保存失败")

        mvu_scope = state.get("mvu_scope")

        # ── MVU scope 落库 ──
        # 只有回复后处理成功时才写回变量桶，避免生成失败后把本轮临时状态持久化。
        if mvu_active and mvu_scope:
            try:
                conv_result = await db.execute(
                    select(Conversation).where(Conversation.id == conv_id)
                )
                conv_for_vars = conv_result.scalar_one_or_none()
                if conv_for_vars is not None:
                    new_local = dict(mvu_scope.get("local") or {})
                    if (conv_for_vars.variables or {}) != new_local:
                        conv_for_vars.variables = new_local
                        db.add(conv_for_vars)

                user_result = await db.execute(
                    select(User).where(User.id == user_id)
                )
                user_for_vars = user_result.scalar_one_or_none()
                if user_for_vars is not None:
                    new_global = dict(mvu_scope.get("global") or {})
                    if (user_for_vars.global_variables or {}) != new_global:
                        user_for_vars.global_variables = new_global
                        db.add(user_for_vars)
            except Exception:
                logger.exception("MVU scope 落库失败")

        await db.commit()

        persona_id = state.get("persona_id")
        if persona_id and state.get("assistant_reply"):
            try:
                from datetime import datetime as dt
                from app.services.relationship_service import get_or_create_relationship, update_affinity

                user_persona_id = state.get("user_persona_id")

                rel = await get_or_create_relationship(
                    db, str(user_id), str(persona_id),
                    user_persona_id=str(user_persona_id) if user_persona_id else None,
                    for_update=True,
                )

                # 好感度 delta 来自本轮感知结果；delta 为 0 但有 reason 时也记录一次说明。
                delta, reason = turn_delta, turn_reason
                if delta != 0 or reason:
                    await update_affinity(db, rel, delta, reason)

                rel.total_messages = (rel.total_messages or 0) + 1
                rel.last_interaction = dt.utcnow()
                rel.deep_talk_count = state.get("relationship", {}).get("deep_talk_count", rel.deep_talk_count) if state.get("relationship") else rel.deep_talk_count

                new_ms = state.get("new_milestone")
                if new_ms:
                    existing_ms = set(rel.milestones or [])
                    if new_ms not in existing_ms:
                        existing_ms.add(new_ms)
                        rel.milestones = list(existing_ms)

                db.add(rel)
                await db.commit()

                affinity_delta_out = delta
                affinity_reason_out = reason
                affinity_score_out = rel.affinity_score

            except Exception as e:
                logger.warning(f"好感度/关系更新失败: {e}")

        new_count = 0
        try:
            # 记忆提取不阻塞本轮响应；这里只判断是否达到触发间隔并投递后台任务。
            count_result = await db.execute(
                select(Message).where(Message.conversation_id == conv_id)
            )
            msg_count = len(count_result.all())

            conv_result = await db.execute(
                select(Conversation).where(Conversation.id == conv_id)
            )
            conv = conv_result.scalar_one_or_none()
            if not conv:
                return {"new_memories_count": 0}
            extraction_count = conv.extraction_count

            mem_count_result = await db.execute(
                select(func.count()).where(
                    Memory.source_conversation_id == conv_id,
                    Memory.is_deleted == False,
                )
            )
            current_memories = mem_count_result.scalar()
            if current_memories < 10:
                # 记忆越少提取越频繁；记忆变多后降低提取频率，控制成本与重复。
                dynamic_interval = settings.MEMORY_EXTRACTION_AGGRESSIVE
            elif current_memories < 30:
                dynamic_interval = settings.MEMORY_EXTRACTION_MODERATE
            else:
                dynamic_interval = settings.MEMORY_EXTRACTION_SPARSE

            last_extraction = conv.last_extraction_msg or 0
            should_extract = msg_count - last_extraction >= dynamic_interval * 2

            if should_extract:
                # 给提取模型多带几条上次窗口之前的上下文，减少断章取义。
                context_start = max(0, last_extraction - 4)
                all_msgs_query = await db.execute(
                    select(Message)
                    .where(Message.conversation_id == conv_id)
                    .order_by(Message.created_at.asc())
                )
                all_msgs = list(all_msgs_query.scalars().all())
                window_msgs = all_msgs[context_start:]

                dialogues = [
                    {"role": m.role, "content": m.content}
                    for m in window_msgs if m.role in ("user", "assistant")
                ]

                if len(dialogues) >= 4:
                    existing_query = await db.execute(
                        select(Memory.content).where(
                            Memory.source_conversation_id == conv_id,
                            Memory.is_deleted == False,
                        ).order_by(Memory.extracted_at.desc()).limit(30)
                    )
                    existing_memories = [row[0] for row in existing_query.all()]

                    conv.extraction_count = extraction_count + 1
                    conv.last_extraction_msg = msg_count
                    db.add(conv)
                    await db.commit()

                    _asyncio.create_task(_extract_memories_delayed(
                        user_id=str(user_id), dialogues=dialogues,
                        conversation_id=conv_id, existing_memories=existing_memories,
                    ))
                    logger.info(
                        f"已触发后台记忆提取任务 (第 {extraction_count + 1} 次, "
                        f"窗口 {context_start}-{msg_count}, 已有记忆 {len(existing_memories)} 条)"
                    )
        except Exception as e:
            logger.warning(f"记忆提取后台任务触发失败: {e}")

        return {
            "new_memories_count": new_count,
            "assistant_message_id": assistant_message_id,
            "affinity_delta": affinity_delta_out,
            "affinity_reason": affinity_reason_out,
            "affinity_score": affinity_score_out,
            # 情绪结果随 message_done 返回，前端据此更新回合结束后的情绪展示。
            "emotion": state.get("emotion"),
            "emotion_intensity": state.get("emotion_intensity"),
            "emotion_confidence": state.get("emotion_confidence"),
            "emotion_triggers": state.get("emotion_triggers"),
            "output_contract": state.get("output_contract_diag"),
        }


async def _update_summary_background(
    conv_id: UUID,
    messages: list[Message],
    existing_summary: str | None,
    summarized_count: int | None = None,
) -> None:
    """后台异步更新摘要。"""
    try:
        async with AsyncSessionLocal() as db:
            summary = await update_summary(messages, existing_summary)
            result = await db.execute(
                select(Conversation).where(Conversation.id == conv_id)
            )
            conv = result.scalar_one_or_none()
            if conv:
                conv.summary = summary
                if summarized_count is not None:
                    conv.last_summarized_count = max(
                        conv.last_summarized_count or 0,
                        summarized_count,
                    )
                db.add(conv)
                await db.commit()
    except Exception:
        logger.exception("后台摘要更新失败")
    finally:
        _summary_tasks_inflight.discard(conv_id)


async def _extract_memories_delayed(
    user_id: str, dialogues: list[dict], conversation_id: UUID,
    existing_memories: list[str] | None = None,
) -> None:
    """带可选延迟的后台记忆提取入口。"""
    if settings.MEMORY_EXTRACTION_DELAY > 0:
        await _asyncio.sleep(settings.MEMORY_EXTRACTION_DELAY)
    await _extract_memories_background(
        user_id=user_id, dialogues=dialogues, conversation_id=conversation_id,
        existing_memories=existing_memories,
    )


async def _extract_memories_background(
    user_id: str, dialogues: list[dict], conversation_id: UUID,
    existing_memories: list[str] | None = None,
) -> None:
    """后台异步任务：从对话中提取长期记忆并存入 ChromaDB。"""
    try:
        from app.services.memory.extraction import (
            extract_memories_from_dialogues, deduplicate_and_save,
        )
        extracted = await extract_memories_from_dialogues(dialogues, existing_memories)
        if not extracted:
            return
        async with AsyncSessionLocal() as db:
            count = await deduplicate_and_save(
                user_id=user_id, extracted_memories=extracted, db=db,
                conversation_id=conversation_id,
            )
            if count > 0:
                logger.info(f"后台记忆提取完成: {count} 条新记忆（用户 {user_id}）")
    except Exception as e:
        logger.warning(f"后台记忆提取失败: {e}")
