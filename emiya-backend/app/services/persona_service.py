# -*- coding: utf-8 -*-
"""角色卡业务逻辑：模板查询、CRUD。"""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.persona import Persona

MAX_CUSTOM_PERSONAS = 50


async def get_persona_templates(db: AsyncSession) -> list[Persona]:
    """获取系统角色卡模板。"""
    result = await db.execute(
        select(Persona).where(Persona.is_template == True)
    )
    return list(result.scalars().all())


async def get_persona_by_id(db: AsyncSession, persona_id: UUID) -> Persona | None:
    """根据 ID 获取角色卡。"""
    result = await db.execute(select(Persona).where(Persona.id == persona_id))
    return result.scalar_one_or_none()


async def get_custom_personas(db: AsyncSession, user_id: UUID) -> list[Persona]:
    """获取当前用户的自定义角色卡。"""
    result = await db.execute(
        select(Persona).where(
            Persona.user_id == user_id,
            Persona.is_template == False,
        ).order_by(Persona.created_at.desc())
    )
    return list(result.scalars().all())


async def create_persona(db: AsyncSession, user_id: UUID, data: dict) -> Persona:
    """创建自定义角色卡，最多 50 个。"""
    count_result = await db.execute(
        select(func.count()).where(
            Persona.user_id == user_id,
            Persona.is_template == False,
        )
    )
    if count_result.scalar() >= MAX_CUSTOM_PERSONAS:
        raise ValueError(f"最多创建 {MAX_CUSTOM_PERSONAS} 个自定义角色")

    persona = Persona(user_id=user_id, is_template=False, **data)
    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return persona


async def update_persona(
    db: AsyncSession, persona_id: UUID, user_id: UUID, data: dict,
) -> Persona:
    """编辑自定义角色卡。"""
    persona = await get_persona_by_id(db, persona_id)
    if persona is None:
        raise ValueError("角色卡不存在")
    if persona.user_id != user_id and persona.user_id is not None:
        raise ValueError("无权编辑该角色卡")

    for field, value in data.items():
        if value is not None:
            setattr(persona, field, value)

    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return persona


async def delete_persona(db: AsyncSession, persona_id: UUID, user_id: UUID) -> dict:
    """删除角色卡，级联删除关联对话、消息、情绪记录、记忆。"""
    from app.models.conversation import Conversation
    from app.models.emotion_record import EmotionRecord
    from app.models.memory import Memory
    from app.models.message import Message
    from sqlalchemy import delete, or_

    persona = await get_persona_by_id(db, persona_id)
    if persona is None:
        raise ValueError("角色卡不存在")
    if persona.user_id != user_id and persona.user_id is not None:
        raise ValueError("无权删除该角色卡")

    conv_result = await db.execute(
        select(Conversation.id).where(
            or_(
                Conversation.persona_id == persona_id,
                Conversation.user_persona_id == persona_id,
            ),
            Conversation.user_id == user_id,
        )
    )
    affected_conv_ids = [row[0] for row in conv_result.all()]

    total_memories = 0
    if affected_conv_ids:
        mem_result = await db.execute(
            select(Memory.id).where(Memory.source_conversation_id.in_(affected_conv_ids))
        )
        memory_ids = [str(row[0]) for row in mem_result.all()]
        if memory_ids:
            from app.services.memory.chroma_client import delete_memory_vector
            for mid in memory_ids:
                await delete_memory_vector(mid, str(user_id))
            await db.execute(
                delete(Memory).where(Memory.id.in_([UUID(mid) for mid in memory_ids]))
            )
            total_memories = len(memory_ids)

        await db.execute(
            delete(EmotionRecord).where(EmotionRecord.conversation_id.in_(affected_conv_ids))
        )
        await db.execute(
            delete(Message).where(Message.conversation_id.in_(affected_conv_ids))
        )
        await db.execute(
            delete(Conversation).where(Conversation.id.in_(affected_conv_ids))
        )

    await db.delete(persona)
    await db.commit()

    return {
        "deleted": True,
        "affected_conversations": len(affected_conv_ids),
        "affected_memories": total_memories,
    }


async def cleanup_orphans(db: AsyncSession) -> dict:
    """自检并清理孤儿记录。"""
    from app.models.conversation import Conversation
    from app.models.emotion_record import EmotionRecord
    from app.models.memory import Memory
    from app.models.message import Message
    from sqlalchemy import delete

    result = {"orphan_conversations": 0, "orphan_memories": 0}

    orphan_conv_query = select(Conversation.id).outerjoin(
        Persona, Conversation.persona_id == Persona.id
    ).where(
        Conversation.persona_id.isnot(None),
        Persona.id.is_(None),
    )
    orphan_conv_result = await db.execute(orphan_conv_query)
    orphan_conv_ids_1 = [row[0] for row in orphan_conv_result.all()]

    orphan_conv_query2 = select(Conversation.id).outerjoin(
        Persona, Conversation.user_persona_id == Persona.id
    ).where(
        Conversation.user_persona_id.isnot(None),
        Persona.id.is_(None),
    )
    orphan_conv_result2 = await db.execute(orphan_conv_query2)
    orphan_conv_ids_2 = [row[0] for row in orphan_conv_result2.all()]

    all_orphan_conv_ids = list(set(orphan_conv_ids_1 + orphan_conv_ids_2))

    if all_orphan_conv_ids:
        result["orphan_conversations"] = len(all_orphan_conv_ids)
        await db.execute(delete(EmotionRecord).where(
            EmotionRecord.conversation_id.in_(all_orphan_conv_ids)))
        await db.execute(delete(Message).where(
            Message.conversation_id.in_(all_orphan_conv_ids)))
        await db.execute(delete(Conversation).where(
            Conversation.id.in_(all_orphan_conv_ids)))

    orphan_mem_query = select(Memory.id).outerjoin(
        Conversation, Memory.source_conversation_id == Conversation.id
    ).where(
        Memory.source_conversation_id.isnot(None),
        Conversation.id.is_(None),
    )
    orphan_mem_result = await db.execute(orphan_mem_query)
    orphan_mem_ids = [str(row[0]) for row in orphan_mem_result.all()]

    if orphan_mem_ids:
        result["orphan_memories"] = len(orphan_mem_ids)
        from app.services.memory.chroma_client import delete_memory_vector
        for mid in orphan_mem_ids:
            try:
                mem_result = await db.execute(
                    select(Memory.user_id).where(Memory.id == UUID(mid))
                )
                mem_user = mem_result.scalar_one_or_none()
                if mem_user:
                    await delete_memory_vector(mid, str(mem_user))
            except Exception:
                pass
        await db.execute(delete(Memory).where(Memory.id.in_(
            [UUID(mid) for mid in orphan_mem_ids])))

    if result["orphan_conversations"] > 0 or result["orphan_memories"] > 0:
        await db.commit()

    return result
