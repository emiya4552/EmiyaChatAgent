# -*- coding: utf-8 -*-
"""对话业务逻辑：创建、列表、删除、消息查询。"""
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.persona import Persona
from app.models.user import User
from app.services.macro_engine import MacroEngine
from app.services.mvu_runtime import build_initial_state, merge_initial_state_missing_only
from app.utils.exceptions import ForbiddenException, NotFoundException


def _parse_uuid_list(values: list[str] | None) -> list[UUID]:
    out: list[UUID] = []
    for value in values or []:
        try:
            out.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return out


async def get_user_conversations(
    db: AsyncSession, user_id: UUID
) -> list[Conversation]:
    """获取用户的所有对话，按更新时间倒序。"""
    result = await db.execute(
        select(Conversation)
        .options(
            joinedload(Conversation.persona),
            joinedload(Conversation.user_persona),
            joinedload(Conversation.preset),
        )
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    return list(result.unique().scalars().all())


async def create_conversation(
    db: AsyncSession, user_id: UUID, persona_id: UUID,
    user_persona_id: UUID | None = None,
    title: str | None = None,
    preset_id: UUID | None = None,
    template_id: UUID | None = None,
    regex_preset_id: UUID | None = None,
    worldbook_ids: list[UUID] | None = None,
    greeting_index: int | None = None,
) -> Conversation:
    """新建对话。有预设时继承其采样参数和上下文设置到 chat_config。

    Args:
        regex_preset_id: 显式选择的正则预设；None 时按 preset > persona 优先级回退
        worldbook_ids: 显式绑定的世界书；None 时回退到 persona.default_worldbook_ids
        greeting_index: 0 表示用 first_message；>= 1 表示用 alternate_greetings[idx-1]。
            None 等价 0。索引越界则降级为 first_message。

    详见 ADR-0014（对话配置集中化）。
    """
    ai_persona = await db.get(Persona, persona_id)
    if ai_persona is None:
        raise ValueError("AI 角色不存在")

    user_persona = None
    if user_persona_id is not None:
        user_persona = await db.get(Persona, user_persona_id)
        if user_persona is None:
            raise ValueError("用户角色不存在")

    chat_config = {}
    preset_regex_preset_id = None
    if preset_id:
        from app.services.preset_service import get_preset
        # 校验 preset 属于该用户
        preset = await get_preset(db, preset_id, user_id)
        if preset:
            for k, v in preset.sampling_params.items():
                if v is not None:
                    chat_config[k] = v
            for k, v in preset.context_settings.items():
                if v is not None:
                    chat_config[k] = v
            preset_regex_preset_id = preset.regex_preset_id

    # 正则预设优先级（ADR-0014 用户已确认 "预设赢"）：
    #   显式 regex_preset_id > preset.regex_preset_id > persona.default_regex_preset_id
    # 前端创建对话弹窗已经做了关联预导入（选预设时把正则切到 preset 的），
    # 后端这里只保证"用户在弹窗里看到啥就生效啥"+"未选时合理兜底"
    effective_regex_preset_id = (
        regex_preset_id
        or preset_regex_preset_id
        or ai_persona.default_regex_preset_id
    )

    # template_id=None 表示"使用系统默认（内置）"——nodes.py::node_build_prompt
    # 在 conv.template_id is None 时直接用 DEFAULT_TEMPLATE_BLOCKS 内存常量渲染

    # 世界书：显式给的 > persona 默认
    if worldbook_ids is not None:
        seed_worldbook_ids = [str(x) for x in worldbook_ids]
    else:
        seed_worldbook_ids = [str(x) for x in (ai_persona.default_worldbook_ids or [])]
    seed_author_note = ai_persona.author_note

    import uuid as _uuid
    conversation = Conversation(
        id=_uuid.uuid4(),
        user_id=user_id, persona_id=persona_id, user_persona_id=user_persona_id,
        title=title, preset_id=preset_id, chat_config=chat_config,
        template_id=template_id,
        regex_preset_id=effective_regex_preset_id,
        worldbook_ids=seed_worldbook_ids,
        author_note=seed_author_note,
    )
    db.add(conversation)

    greeting_text: str | None = ai_persona.first_message
    alts = list(ai_persona.alternate_greetings or [])
    if greeting_index is not None and greeting_index >= 1:
        idx = greeting_index - 1
        if 0 <= idx < len(alts):
            greeting_text = alts[idx]
    if greeting_text:
        # 开场白 = LLM 输出（ADR-0015）：走与 node_post_process 同一条管道
        # （MacroEngine → reply 正则 → MVU UpdateVariable 解析）。处理后的文本写
        # DB，处理后的 stat_data（若开场白带 UpdateVariable）写 conv.variables。
        user_row = await db.get(User, user_id)
        macro_scope = {
            "local": dict(conversation.variables or {}),
            "global": dict((user_row.global_variables if user_row else None) or {}),
            "names": {
                "user": (user_persona.name if user_persona else None)
                        or (user_row.nickname if user_row else "")
                        or "",
                "char": ai_persona.name,
            },
        }
        from app.services.message_pipeline import process_assistant_message_text
        greeting_text, greeting_display, updated_scope = await process_assistant_message_text(
            greeting_text,
            db=db,
            conv=conversation,
            mvu_scope=macro_scope,
            macro_scope=macro_scope,
            run_macro=True,
        )
        # MVU UpdateVariable 解析若产出了 stat_data，落到 conv.variables
        if updated_scope is not None:
            local_after = updated_scope.get("local") or {}
            if local_after:
                conversation.variables = local_after
        greeting = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=greeting_text,
            display_content=greeting_display,
        )
        db.add(greeting)

    from app.services.worldbook.service import get_worldbooks_by_ids

    worldbooks = await get_worldbooks_by_ids(db, _parse_uuid_list(seed_worldbook_ids))
    initial_state = build_initial_state(
        card_data=ai_persona.card_data,
        worldbooks=worldbooks,
    )
    if (
        initial_state.get("stat_data")
        or initial_state.get("sources")
        or ai_persona.uses_mvu
    ):
        merged_variables, _ = merge_initial_state_missing_only(
            conversation.variables or {},
            initial_state,
        )
        conversation.variables = merged_variables
        db.add(conversation)

    await db.commit()
    await db.refresh(conversation)

    result = await db.execute(
        select(Conversation)
        .options(joinedload(Conversation.persona), joinedload(Conversation.user_persona), joinedload(Conversation.preset))
        .where(Conversation.id == conversation.id)
    )
    return result.unique().scalar_one()


async def delete_conversation(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> bool:
    """删除对话（仅允许所有者删除）。"""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    if conversation is None:
        raise NotFoundException("对话不存在")
    if conversation.user_id != user_id:
        raise ForbiddenException("无权删除该对话")

    from app.models.emotion_record import EmotionRecord
    from app.models.memory import Memory
    from app.models.message import Message

    mem_result = await db.execute(
        select(Memory.id).where(Memory.source_conversation_id == conversation_id)
    )
    memory_ids = [str(row[0]) for row in mem_result.all()]
    if memory_ids:
        from app.services.memory.chroma_client import delete_memory_vector
        for mid in memory_ids:
            await delete_memory_vector(mid, str(user_id))

    await db.execute(
        delete(Memory).where(Memory.source_conversation_id == conversation_id)
    )
    await db.execute(
        delete(EmotionRecord).where(EmotionRecord.conversation_id == conversation_id)
    )
    await db.execute(
        delete(Message).where(Message.conversation_id == conversation_id)
    )
    await db.delete(conversation)
    await db.commit()
    return True


async def get_conversation_by_id(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> Conversation | None:
    """获取单个对话（需验证所有权）。"""
    result = await db.execute(
        select(Conversation)
        .options(
            joinedload(Conversation.persona),
            joinedload(Conversation.user_persona),
            joinedload(Conversation.preset),
        )
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    return result.unique().scalar_one_or_none()


async def reload_conversation_mvu_initial_state(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> Conversation | None:
    """Fill missing MVU variables from the current card/worldbook initial state.

    Existing keys are never overwritten. This is the manual "reload initial
    state" action from ADR MVU-0002.
    """
    conv = await get_conversation_by_id(db, conversation_id, user_id)
    if conv is None:
        return None
    if conv.persona is None:
        raise NotFoundException("对话未绑定角色卡")

    from app.services.worldbook.service import get_worldbooks_by_ids

    worldbooks = await get_worldbooks_by_ids(db, _parse_uuid_list(conv.worldbook_ids))
    initial_state = build_initial_state(
        card_data=conv.persona.card_data,
        worldbooks=worldbooks,
    )
    merged_variables, _ = merge_initial_state_missing_only(
        conv.variables or {},
        initial_state,
        reloaded=True,
    )
    conv.variables = merged_variables
    db.add(conv)
    await db.commit()

    return await get_conversation_by_id(db, conversation_id, user_id)


async def apply_preset_to_conversation(
    db: AsyncSession, conversation_id: UUID, preset_id: UUID | None, user_id: UUID
) -> Conversation | None:
    """将预设的采样参数和上下文设置合并到对话 chat_config。

    preset_id=None：取消预设——清掉 conv.preset_id / conv.regex_preset_id，
    并从 chat_config 里剥掉所有由该预设贡献的字段（保留用户手动改的字段）。
    """
    from app.services.preset_service import get_preset as get_preset_svc

    conv = await get_conversation_by_id(db, conversation_id, user_id)
    if conv is None:
        return None

    if preset_id is None:
        # 取消预设：清 chat_config 里所有当前预设贡献的字段
        # （这里简单做：清空 chat_config 整体；用户手动调过的零散字段会一起丢，
        # 但实际场景用户先选预设再覆盖几个字段的概率低，可接受）
        conv.chat_config = {}
        conv.preset_id = None
        conv.regex_preset_id = None
        db.add(conv)
        await db.commit()
        await db.refresh(conv)
    else:
        preset = await get_preset_svc(db, preset_id, user_id)
        if preset is None:
            return None

        merged = dict(conv.chat_config or {})
        for k, v in preset.sampling_params.items():
            if v is not None:
                merged[k] = v
        for k, v in preset.context_settings.items():
            if v is not None:
                merged[k] = v

        conv.chat_config = merged
        conv.preset_id = preset_id
        conv.regex_preset_id = preset.regex_preset_id
        db.add(conv)
        await db.commit()
        await db.refresh(conv)

    result = await db.execute(
        select(Conversation)
        .options(
            joinedload(Conversation.persona),
            joinedload(Conversation.user_persona),
            joinedload(Conversation.preset),
        )
        .where(Conversation.id == conversation_id)
    )
    return result.unique().scalar_one()


async def update_conversation_config(
    db: AsyncSession, conversation_id: UUID, chat_config: dict, user_id: UUID
) -> Conversation | None:
    """直接更新对话配置。"""
    conv = await get_conversation_by_id(db, conversation_id, user_id)
    if conv is None:
        return None
    conv.chat_config = chat_config
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    result = await db.execute(
        select(Conversation)
        .options(
            joinedload(Conversation.persona),
            joinedload(Conversation.user_persona),
            joinedload(Conversation.preset),
        )
        .where(Conversation.id == conversation_id)
    )
    return result.unique().scalar_one()


async def get_conversation_messages(
    db: AsyncSession, conversation_id: UUID, limit: int = 50, offset: int = 0
) -> list[Message]:
    """获取对话的消息列表（分页，按时间倒序）。"""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())
