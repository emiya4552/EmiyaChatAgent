# -*- coding: utf-8 -*-
"""记忆管理业务逻辑 — CRUD + 查询。"""
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.services.memory.chroma_client import (
    delete_memory_vector,
    update_memory_vector,
)
from app.utils.exceptions import ForbiddenException, NotFoundException


async def list_memories(
    db: AsyncSession,
    user_id: UUID,
    category: str | None = None,
    scope: str | None = None,
    memory_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Memory], int]:
    """分页获取用户的记忆列表，可按分类、作用域、类型筛选。"""
    conditions = [Memory.user_id == user_id, Memory.is_deleted == False]
    if category:
        conditions.append(Memory.category == category)
    if scope:
        # 支持前缀匹配：scope=conversation: 匹配所有 conversation:{id}
        if scope.endswith(":"):
            conditions.append(Memory.scope.like(f"{scope}%"))
        else:
            conditions.append(Memory.scope == scope)
    if memory_type:
        conditions.append(Memory.memory_type == memory_type)

    count_query = select(func.count()).where(*conditions)
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    items_query = (
        select(Memory)
        .where(*conditions)
        .order_by(Memory.extracted_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items_result = await db.execute(items_query)
    items = list(items_result.scalars().all())

    return items, total


async def get_memory(db: AsyncSession, memory_id: UUID, user_id: UUID) -> Memory:
    """获取单条记忆详情（需权限校验）。"""
    result = await db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.is_deleted == False)
    )
    memory = result.scalar_one_or_none()
    if memory is None:
        raise NotFoundException("记忆不存在")
    if memory.user_id != user_id:
        raise ForbiddenException("无权查看该记忆")
    return memory


async def update_memory_content(
    db: AsyncSession,
    memory_id: UUID,
    user_id: UUID,
    content: str | None = None,
    category: str | None = None,
    scope: str | None = None,
    memory_type: str | None = None,
) -> Memory:
    """编辑记忆内容，同步更新 ChromaDB。"""
    memory = await get_memory(db, memory_id, user_id)

    if content is not None:
        memory.content = content
    if category is not None:
        memory.category = category
    if scope is not None:
        memory.scope = scope
    if memory_type is not None:
        memory.memory_type = memory_type

    db.add(memory)
    await db.commit()
    await db.refresh(memory)

    # 同步 ChromaDB
    await update_memory_vector(
        memory_id=str(memory.id),
        user_id=str(user_id),
        content=memory.content,
        metadata={
            "category": memory.category,
            "importance": memory.importance,
            "scope": memory.scope,
            "memory_type": memory.memory_type,
        },
    )

    return memory


async def soft_delete_memory(db: AsyncSession, memory_id: UUID, user_id: UUID) -> bool:
    """软删除记忆（设置 is_deleted=True），同步删除 ChromaDB 向量。"""
    memory = await get_memory(db, memory_id, user_id)

    memory.is_deleted = True
    db.add(memory)
    await db.commit()

    await delete_memory_vector(str(memory.id), str(user_id))

    return True


async def clear_all_memories(db: AsyncSession, user_id: UUID) -> int:
    """批量清空用户的所有记忆（PG 软删除 + ChromaDB 硬删除）。"""
    from sqlalchemy import update

    result = await db.execute(
        select(Memory.id).where(
            Memory.user_id == user_id,
            Memory.is_deleted == False,
        )
    )
    memory_ids = [str(row[0]) for row in result.all()]
    if not memory_ids:
        return 0

    # PG 批量软删除
    await db.execute(
        update(Memory)
        .where(Memory.user_id == user_id, Memory.is_deleted == False)
        .values(is_deleted=True)
    )

    # ChromaDB 逐条删除向量
    for mid in memory_ids:
        await delete_memory_vector(mid, str(user_id))

    await db.commit()
    return len(memory_ids)
