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


def _render_content(content: str, scope: dict | None) -> str:
    """EJS → MacroEngine 二阶段渲染（MVU 兼容，详见 ADR-0010）。"""
    if not content:
        return content
    ejs_scope = (scope or {}).get("local") or {} if isinstance(scope, dict) else {}
    content = EJSEngine.render(content, ejs_scope)
    return MacroEngine.render(content, scope)


# ─── MVU 写回协议（详见 ADR-0010 决定 4） ───
# `_parse_update_variable` 已上移到 app.services.message_pipeline（ADR-0015）。
# 开场白与 LLM 输出共享同一条管道，本文件不再持有副本。

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
from app.services.langgraph.state import ChatState

logger = logging.getLogger(__name__)


def _should_retire_backend_apply(state: dict) -> bool:
    """ADR-0008c 阶段3：是否退役后端 MVU apply（交给前端 MVU Host）。

    三条件同时满足：全局开关 `MVU_RETIRE_BACKEND_APPLY` + `MVU_BROWSER_RUNTIME` +
    本对话 `persona_uses_mvu`。默认全 off → 恒 False → 后端照旧 apply。
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

    安全降级：state 里缺 enabled_blocks 时视为启用（兼容旧调用方）。
    """
    blocks = state.get("enabled_blocks")
    if blocks is None:
        return True
    return key in blocks


# ADR-0019：情绪分析已从"回复前独立节点"合并进 node_post_process 的感知段（与好感度
# 评估合一、上下文感知）。原 node_analyze_emotion 已删；情绪现由 assess_turn 在回复后产出，
# 随 message_done 透出给前端更新 emoji。感知总开关仍是 conv.analyze_emotion（现覆盖情绪+好感度）。


async def node_retrieve_memories(state: ChatState) -> dict:
    # 功能开关：memories block 关闭则跳过（连同 SSE memory_recall / reference_count）
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

            # 历史消息（旧 → 新顺序）
            msgs_result = await db.execute(
                select(Message)
                .where(Message.conversation_id == state["conversation_id"])
                .order_by(Message.created_at.asc())
            )
            history = [{"role": m.role, "content": m.content} for m in msgs_result.scalars().all()]

        # MVU 变量驱动扫描（ADR-0004，默认关闭）：白名单非空时把选定 stat_data 路径
        # 渲染成扫描文本，让当前变量驱动关键词激活。空 = 不做任何额外扫描。
        chat_cfg = conv.chat_config or {}
        activated = scan_worldbook(
            worldbooks=book_dicts,
            history_messages=history,
            chat_config=chat_cfg,
        )

        # 序列化成可放入 state 的 dict
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
    """产出"## 关于用户"段落 + profile_reminder（用户没设角色卡时给前端提醒）。

    功能开关：profile block 关闭 → 跳过；profile_reminder 也不发（无 user_persona 时
    用户主动关 profile block 表示不需要提醒）。
    """
    if not _block_enabled(state, "profile"):
        return {"profile": None, "profile_section": "", "profile_reminder": False}

    try:
        user_persona = await _load_user_persona(state)
        if user_persona is None:
            return {"profile": None, "profile_section": "", "profile_reminder": True}
        section = _build_user_persona_profile(user_persona)
        logger.info(f"画像解析: user_persona={user_persona.name}")
        return {"profile": None, "profile_section": section, "profile_reminder": False}
    except Exception as e:
        logger.warning(f"画像段落构建失败: {e}")
        return {"profile": None, "profile_section": "", "profile_reminder": False}


async def node_resolve_constraints(state: ChatState) -> dict:
    """产出"## 交互要求"段落（约束 + goal 派生指令）。

    功能开关：constraints block 关闭 → 跳过整段。
    """
    if not _block_enabled(state, "constraints"):
        return {"profile_constraints": ""}

    try:
        user_persona = await _load_user_persona(state)
        if user_persona is None:
            return {"profile_constraints": ""}
        return {"profile_constraints": _build_user_persona_constraints(user_persona)}
    except Exception as e:
        logger.warning(f"交互约束构建失败: {e}")
        return {"profile_constraints": ""}


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


def _build_user_persona_constraints(p: Persona) -> str:
    """构建"## 交互要求"段落（约束 + goal 派生指令）。"""
    lines: list[str] = []
    constraints = _cd(p, 'constraints')
    if constraints:
        lines.append(f"- {constraints}")

    goal = _cd(p, 'goal') or "陪伴"
    goal_map = {
        "陪伴": "",
        "倾诉": "- 用户来这里是倾诉的，请多倾听、共情，不要急于给建议",
        "解压": "- 用户的目的是放松解压，保持轻松愉快的氛围",
        "学习": "- 用户希望深入探讨某个话题，请认真对待每一个问题",
    }
    goal_instruction = goal_map.get(goal, "")
    if goal_instruction:
        lines.append(goal_instruction)

    return "## 交互要求\n" + "\n".join(lines) if lines else ""


async def node_assess_relationship(state: ChatState) -> dict:
    """读取好感度关系，生成 Prompt 段落（不调 LLM，纯 DB 读取 + 文本映射）。"""
    # 功能开关：relationship block 关闭 → 跳过整个关系评估（连 SSE 与 milestone 一起停）
    if not _block_enabled(state, "relationship"):
        return {
            "relationship": None,
            "relationship_level": 0,
            "relationship_section": "",
            "level_changed": False,
            "new_milestone": None,
        }

    persona_id = state.get("persona_id")
    if persona_id is None:
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


# mes_example 解析已迁至 prompt_renderer.py::parse_mes_example
# （随 type='mes_example' block 类型一起；详见 ADR-XXX 待后续）


# ─── Token 计数与预算 ─────────────────────────────────────────────

def _count_tokens(text: str) -> int:
    """估算文本 token 数。"""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return int(len(text) / 3.5)


def _count_message_tokens(messages: list[dict]) -> int:
    """计算消息列表的 token 总数（含 role 格式开销，每条 +4）。"""
    return sum(_count_tokens(m.get("content", "")) + 4 for m in messages)


def _truncate_history(history: list, budget: int) -> list:
    """从旧到新截断历史，丢弃超出 budget 的旧消息。

    始终保留最后一条（当前用户输入）。
    """
    if not history:
        return []

    filtered = [{"role": m.role, "content": m.content}
                for m in history if m.role in ("user", "assistant")]

    if not filtered:
        return []

    # 最后一条是当前用户输入，必须保留
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


# ─── Prompt 组装 ─────────────────────────────────────────────────

async def node_build_prompt(state: ChatState) -> dict:
    """组装完整的 messages 列表。"""
    from app.services.prompt_renderer import PromptRenderer, DEFAULT_TEMPLATE_BLOCKS, PromptBlock
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

        msgs_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == state["conversation_id"])
            .order_by(Message.created_at.asc())
        )
        all_messages = list(msgs_result.scalars().all())

        summary = None
        summary_enabled = _block_enabled(state, "summary")
        if len(all_messages) > settings.WINDOW_SIZE:
            overflow = all_messages[: len(all_messages) - settings.WINDOW_SIZE]
            recent = all_messages[len(all_messages) - settings.WINDOW_SIZE :]

            # summary 功能开关：block 关 → 不触发后台 LLM 摘要、不读 summary 字段进 prompt
            if summary_enabled:
                already_summarized = min(conv.last_summarized_count or 0, len(overflow))
                new_overflow = overflow[already_summarized:]

                if new_overflow:
                    summary = conv.summary
                    conv.last_summarized_count = len(overflow)
                    await db.commit()
                    _asyncio.create_task(_update_summary_background(
                        conv_id=conv.id,
                        messages=new_overflow,
                        existing_summary=conv.summary,
                    ))
                else:
                    summary = conv.summary
        else:
            recent = all_messages

        # ── Prompt 模板渲染 ──
        # 情绪不再注入 Prompt（详见 docs/adr/0005）：current_mood / emotion 仅用于
        # 聊天页 emoji + Dashboard + 关系系统的 deep_talk_count，不进 LLM 上下文

        # 构建记忆上下文
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
            "constraints_context": state.get("profile_constraints", ""),
            "summary_context": summary or "",
            "reply_length": state.get("reply_length", "medium"),
            "author_note": conv.author_note or "",
        }

        # ── MVU scope 加载（详见 docs/adr/0007） ──
        # local 桶来自 conversation.variables；global 桶来自 user.global_variables
        # names 用于 {{user}}/{{char}} 名字宏；user_persona.name 作为 {{user}}
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
        # 副本避免直接持有 ORM JSONB 引用；落库由 post_process 显式做
        scope = {
            "local": dict(conv.variables or {}),
            "global": dict((user_row.global_variables if user_row else None) or {}),
            "names": {
                "user": user_persona_name or (user_row.nickname if user_row else ""),
                "char": persona.name if persona else "",
            },
        }

        # 从 DB 加载对话关联的模板
        template = None
        if conv.template_id:
            t_result = await db.execute(
                select(PTModel).where(PTModel.id == conv.template_id)
            )
            template = t_result.scalar_one_or_none()

        if template and template.blocks:
            blocks = [PromptBlock(**b) for b in template.blocks]
        else:
            blocks = DEFAULT_TEMPLATE_BLOCKS
        wi_activated = state.get("wi_activated") or []
        rendered = PromptRenderer.render(
            blocks, context, wi_activated=wi_activated, scope=scope,
        )
        logger.info(
            f"使用模板: {template.name if template else '默认'} | "
            f"预设: {conv.preset_id or '无'} | "
            f"WI 激活: {len(wi_activated)}"
        )

        # 给 char_desc 块产出的消息打锚点（供 WorldbookInjector 定位 BEFORE/AFTER_CHAR）
        for m in rendered:
            if m.get("_block_id") == "char_desc":
                m[ANCHOR_KEY] = ANCHOR_CHAR_DESC

        # mes_example：优先用模板 mes_example block 产出的消息（render 时已注入），
        em_first = next(
            (m for m in rendered if m.get("_block_id") == "mes_example"), None,
        )
        if em_first is not None:
            em_first[ANCHOR_KEY] = ANCHOR_MES_EXAMPLE

        # Token Budget 截断历史
        cc = conv.chat_config or {}
        budget = _calc_history_budget(
            rendered,
            max_tokens=cc.get("openai_max_tokens"),
            max_context=cc.get("openai_max_context"),
        )
        truncated = _truncate_history(recent, max(budget, 100))
        # 对 history 中每条消息跑宏（开场白/历史消息里可能含 {{user}}/{{char}}/变量宏）
        # 与 ST 对齐：history 不持久化渲染结果，每轮按当时 scope 重渲
        for h in truncated:
            h["content"] = _render_content(h.get("content", ""), scope)
        history_start_idx = len(rendered)
        rendered.extend(truncated)

        # ── Author's Note 注入（历史末尾倒数 an_depth 条之前） ──
        if conv.author_note and conv.author_note.strip():
            an_msg_count = sum(1 for m in all_messages if m.role in ("user", "assistant"))
            interval = max(1, conv.an_interval or 1)
            # interval=1 等价每次必插；其余按消息计数取模
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
                    "content": _render_content(conv.author_note, scope),
                    ANCHOR_KEY: ANCHOR_AUTHOR_NOTE,
                })

        # ── ADR-0006：tool 模式下把 [mvu_update] 从 prompt 注入里摘掉 ──
        # 这些条目命令模型"在正文输出 <UpdateVariable> 文本"，会和 update_variables 工具
        # 竞争、让模型走文本通道。其内容已进 tool description，这里只从**注入**移除
        # （state["wi_activated"] 不动，工具描述/诊断仍拿全量），并追加一句"用工具"引导。
        # 注意：`persona_uses_mvu` 要到本节点 return 时才写进 state，这里 state.get 拿不到；
        # 直接读本节点已加载的 persona 对象（见上文 persona = ... 处）。
        mvu_update_divert_mode = bool(persona and getattr(persona, "uses_mvu", False))
        if mvu_update_divert_mode and wi_activated:
            from app.services.mvu_runtime.runtime_view import classify_mvu_comment
            wi_activated = [
                e for e in wi_activated
                if classify_mvu_comment(e.get("comment")) != "update"
            ]

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
                rendered, wi_as_active, history_start_idx, scope=scope,
            )
        else:
            # 没激活集也要剥掉锚点/_block_id
            rendered = WorldbookInjector.inject(
                rendered, [], history_start_idx, scope=scope,
            )

        # 剥掉残留的 _block_id 元字段
        rendered = [
            {k: v for k, v in m.items() if k != "_block_id"}
            for m in rendered
        ]

        # ── 预设注入 ──
        if conv.preset_id:
            preset = await get_preset_for_injection(db, conv.preset_id)
            if preset:
                rendered = PresetInjector.inject(rendered, preset, scope)

        # ── 正则后处理（独立于 preset_id；conv.regex_preset_id 来源可能是 preset
        #     或 persona.default_regex_preset_id 回退） ──
        # macro_scope 透传给 RegexProcessor，让 substituteRegex 字段下的
        # findRegex/replaceString 也能跑 {{user}}/{{char}}/getvar 等宏（ADR-0016）
        from app.services.regex_preset_service import get_prompt_only_scripts
        scripts = await get_prompt_only_scripts(
            db, conv.regex_preset_id, conv.preset_id,
        )
        if scripts:
            rendered = RegexProcessor.apply_prompt_only(
                rendered, scripts, macro_scope=scope,
            )

        # ── 尾部模板强制兜底（squash 前必须先注入，确保进末端 system 块） ──
        # 启发式识别 wi_activated 里"输出模板"型条目（含 <details>+占位符 或
        # 自定义 HTML 标签），追加一段强约束指令到 prompt 末端，对抗预设的
        # 严格输出格式（如 <content></content> 包裹）压制模板输出
        if settings.WORLDBOOK_TAIL_TEMPLATE_ENFORCEMENT and wi_activated:
            templates = _detect_output_templates(wi_activated)
            if templates:
                directive = _build_tail_template_directive(templates)
                rendered.append({"role": "system", "content": directive})
                logger.info(f"[尾部模板兜底] 注入约束：{templates}")

        # ── ADR-0006：tool 模式引导，替代被摘掉的 [mvu_update] 文本指令 ──
        if mvu_update_divert_mode:
            rendered.append({"role": "system", "content": _MVU_DOUBLE_AI_DIRECTIVE})

        # squash 策略：仅在有预设时合并连续 system 消息。
        # 理由：预设 position=0/1 注入会产生多块紧邻的 system，合并为单条以满足
        # OpenAI Chat Completion 单 system 约束（DeepSeek 容忍多 system 但合并更稳）；
        # 无预设时 system 块自然只有 1-2 条，无需合并。
        if conv.preset_id:
            rendered = _squash_system_messages(rendered)

        if truncated:
            _log_messages(rendered, persona.name if persona else "无角色")

        is_first = len(all_messages) <= 1

        return {
            "messages": rendered,
            "system_prompt": rendered[0]["content"][:200] if rendered else "",
            "persona_name": persona.name if persona else None,
            "persona_uses_mvu": bool(persona and getattr(persona, "uses_mvu", False)),
            "is_first_round": is_first,
            "error": None,
            "mvu_scope": scope,
        }


# ─── 辅助函数 ────────────────────────────────────────────────────

# 启发式：识别"输出模板"型 worldbook 条目
import re as _re

# (1) PascalCase 标签（StatusBlock、CharBox 等）：首字母大写 + 含至少 2 个大写字母或骆驼壳
# (2) 带数字后缀的小写标签（dp1~dp8、ce1~ce4 等）：纯小写字母开头 + 数字结尾
_CUSTOM_TAG_RE = _re.compile(
    r"<(?P<tag>(?:[A-Z][a-zA-Z]*[A-Z][a-zA-Z]*)|(?:[a-z]+\d+))\b"
)
# 含 <details> 容器 + 占位符（{xxx} 或 {{xxx}}）
_DETAILS_RE = _re.compile(r"<details\b", _re.IGNORECASE)
_SUMMARY_RE = _re.compile(r"<summary\b[^>]*>(.*?)</summary>", _re.IGNORECASE | _re.DOTALL)
# 单括号占位（{时间} {用户名与@ID} 这种）；用 lookaround 排除 {{user}} 之类宏
_PLACEHOLDER_RE = _re.compile(r"(?<!\{)\{[^{}\n]{1,80}\}(?!\})")
_TAG_STRIP_RE = _re.compile(r"<[^>]+>")


# 占位符识别（构造 scaffold 用）：删去 {xxx} 单括号和 {{xxx}} 双括号占位符
# 含 {{user}}/{{char}} 等宏也会被一并删（无碍——prefix 给 LLM 当字面文本看）
_TEMPLATE_DOUBLE_BRACE = _re.compile(r"\{\{[^{}\n]{1,100}\}\}")
_TEMPLATE_SINGLE_BRACE = _re.compile(r"\{[^{}\n]{1,100}\}")

# MVU 协议/指令族标签（comment 子串，大小写不敏感，对齐 MVU 的 includes 语义）。
# 这些条目是"教 LLM 输出 <UpdateVariable> 的指令"或"状态读数"，**不是**要 LLM 回填
# 追加的 HTML 显示模板——绝不能被尾部模板兜底/续写当成输出模板，否则会注入错误约束
# 文案并每轮空烧一次 prefix 续写。详见 docs/mvu/adr/0003（标签拦截）。
_MVU_TAG_RE = _re.compile(r"\[(?:mvu_update|mvu_plot|mvu_status|initvar|opening)\]", _re.I)

# ADR-0006：tool 模式下替代 [mvu_update] 文本指令的引导（[mvu_update] 已从注入摘除）
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


def _is_mvu_tagged_entry(entry: dict) -> bool:
    return bool(_MVU_TAG_RE.search(str(entry.get("comment") or "")))


def _extract_template_entries(wi_activated: list[dict]) -> list[dict]:
    """识别"输出模板"型条目，返回每个的 {marker, content, order}。

    marker: 用于检测 LLM 输出是否含此模板（从 <summary> 提取）
    content: 模板原文，用于构造续写 prefix scaffold
    order: worldbook 条目优先级，用于多模板时排序
    """
    entries: list[dict] = []
    seen_markers: set[str] = set()
    for entry in wi_activated:
        content = entry.get("content", "")
        if not content:
            continue

        # MVU 指令/状态族条目（[mvu_update]/[mvu_status]/[mvu_plot]/[initvar]/[opening]）
        # 不是输出模板：它们的 <UpdateVariable>/<Analysis>/<status_...> 等标签会误命中
        # has_custom_tag。跳过，避免尾部模板兜底注入错误约束 + 空烧续写（ADR-0003 拦截）。
        if _is_mvu_tagged_entry(entry):
            continue

        has_details = bool(_DETAILS_RE.search(content))
        has_placeholder = bool(_PLACEHOLDER_RE.search(content)) or bool(
            _TEMPLATE_DOUBLE_BRACE.search(content)
        )
        has_custom_tag = bool(_CUSTOM_TAG_RE.search(content))

        is_template = (has_details and has_placeholder) or has_custom_tag
        if not is_template:
            continue

        # 提取 marker：优先 <summary> 内文 → entry.comment → entry.uid 兜底
        marker = ""
        m = _SUMMARY_RE.search(content)
        if m:
            marker = _TAG_STRIP_RE.sub("", m.group(1)).strip()
        if not marker:
            marker = (entry.get("comment") or "").strip()
        if not marker:
            marker = f"条目#{entry.get('uid', '?')}"

        if marker in seen_markers:
            continue
        seen_markers.add(marker)
        entries.append({
            "marker": marker,
            "content": content,
            "order": entry.get("order", 100),
        })
    return entries


def _detect_output_templates(wi_activated: list[dict]) -> list[str]:
    """返回所有"输出模板"型条目的 marker 列表（用于 tail_template 强约束文案）。"""
    return [e["marker"] for e in _extract_template_entries(wi_activated)]


def _find_missing_templates(reply: str, entries: list[dict]) -> list[dict]:
    """扫 LLM 主回复，返回 marker 未出现的模板条目列表（按 order 升序）。"""
    missing = [e for e in entries if e["marker"] and e["marker"] not in reply]
    missing.sort(key=lambda e: e.get("order", 100))
    return missing


def _build_template_scaffold(content: str) -> str:
    """从模板 content 抽取**最小开头**作为续写 prefix：
    `<details><summary>【...】</summary>`（含一个紧邻的自定义开口标签如 <StatusBlock>）。

    设计原则（修正后的版本，详见 grilling Q2 复盘）：
    - 不带卡作者写给 LLM 的 # 指令注释（这些只该在 system context 里出现）
    - 不带字段名/占位符/闭合标签 —— 完整 schema 已经在 system 的世界书条目原文里，
      LLM 看到这个最小开头会"接着写字段值"，不会因为 prefix 已经完整而停手
    - 不带 `(女性角色全名)` 这种括号注解 —— 它们会让 LLM 误以为是 value

    例如：
      原始 content:
        # 此为'状态栏'，只允许输出在最底部...

        <details>
        <summary><b>【状态栏】</b></summary>
        <StatusBlock>
        👤姓名:{{char name}} (女性角色全名)
        ...
        </StatusBlock>
        </details>

      产出 scaffold:
        <details>
        <summary><b>【状态栏】</b></summary>
        <StatusBlock>
    """
    # 找第一个 <details> 开始
    details_match = _re.search(r"<details[^>]*>", content, _re.IGNORECASE)
    if not details_match:
        return ""  # 不是合法模板，跳过

    # 找紧接的 </summary>
    summary_end_idx = content.find("</summary>", details_match.end())
    if summary_end_idx == -1:
        # 没有 summary 直接截取 <details> 开头
        return content[details_match.start():details_match.end()]

    end = summary_end_idx + len("</summary>")

    # 把紧跟的自定义开口标签（如 <StatusBlock> / <body> / <dp1>）也一起含进来
    rest = content[end:]
    inner_match = _re.match(r"\s*<[A-Za-z][^/>]*>", rest)
    if inner_match:
        end = end + inner_match.end()

    return content[details_match.start():end]


def _build_tail_template_directive(templates: list[str]) -> str:
    """生成尾部模板强制约束的 system 文案。"""
    bullets = "\n".join(f"- {t}" for t in templates)
    return (
        "[输出尾部模板强制约束]\n"
        "本轮回复必须在正文之后追加以下世界书要求的 HTML 模板"
        "（按各模板内字段定义填空，模板原文见上文世界书条目）：\n"
        f"{bullets}\n"
        "即便上文 / 预设要求严格的输出格式（如 <content></content> 包裹、"
        "单一标签结构、思维链分段等），HTML 模板块**必须**追加输出，不得省略。"
        "如有 <content> 闭合标签，模板追加在标签之后。"
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


def _calc_history_budget(prefix_messages: list[dict], max_tokens: int | None = None, max_context: int | None = None) -> int:
    """计算对话历史可用的 token 预算。"""
    prefix_tokens = _count_message_tokens(prefix_messages)
    _max_tokens = max_tokens or settings.CHAT_MAX_TOKENS
    _max_context = max_context or settings.MAX_CONTEXT_TOKENS
    return (_max_context
            - prefix_tokens
            - _max_tokens
            - settings.TOKEN_BUDGET_SAFETY_MARGIN)


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
# 注：回复生成不在 graph 节点中。chat_service 直接调 call_deepseek_stream
# 实现逐 token 流式输出；流式完成后手动调 node_post_process。


async def node_post_process(state: ChatState) -> dict:
    """保存消息和情绪记录，触发后台记忆提取（含摘要注入）。

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

        # 拉 conv 用于 message_pipeline 决策 regex_preset / preset
        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == conv_id)
        )
        conv_for_pipeline = conv_result.scalar_one_or_none()

        # ── 把 LLM 输出走 ADR-0015 管道（与开场白共用）──
        # MacroEngine 对 LLM 实时输出意义不大（LLM 不会自己写 {{user}} 宏），
        # 但 reply 正则 + UpdateVariable 解析必跑。
        processed_reply = state.get("assistant_reply") or ""
        display_reply = processed_reply
        scope_before = state.get("mvu_scope")
        # ADR-0005：有界校验层的约束（来自本轮激活的 [mvu_update] 条目）+ 诊断收集
        from app.services.mvu_runtime import extract_constraints_from_entries
        mvu_constraints = extract_constraints_from_entries(state.get("wi_activated"))
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
            # 写回 state：assistant_reply=prompt 真相版，assistant_display=显示版
            # （chat_service 的 message_done 分别透出 final_content / final_display_content）
            state["assistant_reply"] = processed_reply
            state["assistant_display"] = display_reply
            if scope_after is not None:
                state["mvu_scope"] = scope_after
            if update_diag["applied"] or update_diag["dropped"]:
                update_channel = "text"

        # ── ADR-0008c 阶段3：退役后端 apply（gated）──
        # 开关 on 且浏览器运行时 on 且 uses_mvu 时，后端**不再 apply** —— ops 仍随 down-channel
        # 下推，由前端 MVU Host 应用+派生并 UP 回传（含派生字段，比后端版更全）。默认 off：后端
        # 照旧 apply（浏览器版经 UP 覆盖），保住无浏览器/关页时的兜底。ops 无论如何都留在 state 里。
        _retire_apply = _should_retire_backend_apply(state)

        # ── ADR-0005：tool-calling 更新通道（与文本通道汇到同一校验+应用核心）──
        tool_calls = state.get("mvu_tool_calls")
        if tool_calls and not _retire_apply:
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
        if double_ai_ops and not _retire_apply:
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

        # 退役模式下后端没 apply，但 ops 已下推给前端；诊断标注 channel=browser
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
            # 显式赋 id（SQLAlchemy 的 column default 在 flush 时才执行）
            assistant_message_id = str(msg_id)

            if state.get("is_first_round"):
                if conv_for_pipeline and conv_for_pipeline.title is None:
                    msg = state["user_message"]
                    conv_for_pipeline.title = msg[:30] + ("..." if len(msg) > 30 else "")
                    db.add(conv_for_pipeline)

        # ADR-0019：感知总开关，直接读已加载的 conv（省一次查询）；conv 缺失 → False（fail-safe）
        emotion_enabled = bool(conv_for_pipeline and conv_for_pipeline.analyze_emotion)

        # ── ADR-0019：情感感知（情绪 + 好感度合并为一次上下文感知调用）──
        # 写路径由 conv.analyze_emotion（"情感分析"感知总开关）gate：关则整段跳过——
        # 不写 EmotionRecord、好感度也不动。读路径（把关系注入 prompt）由 relationship
        # template block 另行 gate，与本段正交（详见 ADR-0019）。
        turn_delta: int = 0
        turn_reason: str = ""
        _perc_persona_id = state.get("persona_id")

        if emotion_enabled:
            _user_msg_text = (state.get("user_message") or "").strip()
            if len(_user_msg_text) <= settings.EMOTION_SKIP_TRIVIAL_CHARS:
                # 低信号轮（"嗯""哦"等填充消息）：不调 LLM，记"平静"、好感度不动（ADR-0019）
                state["emotion"] = "平静"
                state["emotion_intensity"] = 5
                state["emotion_confidence"] = 0.3
                state["emotion_triggers"] = []
                logger.info(
                    "情感感知：用户消息过短(%d<=%d)，跳过 assess_turn",
                    len(_user_msg_text), settings.EMOTION_SKIP_TRIVIAL_CHARS,
                )
            # 有用户消息且有 AI 回复时才调 LLM 感知（无用户消息或仅系统消息时不调）
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

                    # 好感度门槛为"有 AI 角色即评"（高版本卡人设在世界书里、
                    # personality/background 都可能空——assess_turn 会从回复推断角色态度）。
                    want_affinity = bool(_perc_persona_id)
                    cur_affinity = 0.0
                    if want_affinity:
                        # 读当前好感度
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
                        # state["emotion"] 初始为 None；assess_turn 未跑/失败时回退"平静"（ADR-0019）
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

        # MVU `<UpdateVariable>` 解析已上移到 message_pipeline（ADR-0015），
        # state["mvu_scope"] 此时已携带可能更新过的 stat_data。
        mvu_scope = state.get("mvu_scope")

        # ── MVU scope 落库（详见 docs/adr/0007 决策 3） ──
        # 在 post_process 成功路径写回，保证 incvar 幂等：若 build_prompt 后
        # LLM 调用失败，本节点不跑，counter 不会多增。
        if mvu_scope:
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

                # ADR-0019：好感度写入随"情感分析"感知开关一起 gate（不再仅看 persona.personality）。
                # delta/reason 来自本轮合并的 assess_turn（perception 段），不再单独调 assess_affinity。
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
                dynamic_interval = settings.MEMORY_EXTRACTION_AGGRESSIVE
            elif current_memories < 30:
                dynamic_interval = settings.MEMORY_EXTRACTION_MODERATE
            else:
                dynamic_interval = settings.MEMORY_EXTRACTION_SPARSE

            last_extraction = conv.last_extraction_msg or 0
            should_extract = msg_count - last_extraction >= dynamic_interval * 2

            if should_extract:
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
            # ADR-0019：情绪后置到本节点，随 message_done 透出给前端更新 emoji
            "emotion": state.get("emotion"),
            "emotion_intensity": state.get("emotion_intensity"),
            "emotion_confidence": state.get("emotion_confidence"),
            "emotion_triggers": state.get("emotion_triggers"),
        }


async def _update_summary_background(
    conv_id: UUID, messages: list[Message], existing_summary: str | None
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
                db.add(conv)
                await db.commit()
    except Exception:
        logger.exception("后台摘要更新失败")


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
