# -*- coding: utf-8 -*-
"""Prompt 模板服务：CRUD + 所有权过滤 + 复制。

PromptTemplate 同时支持用户私有（user_id 有值）与系统模板（user_id IS NULL）。
系统模板全员可读、不可写、不可删；仅后端脚本 / DB 直插创建（详见 ADR-0013）。
"""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt_template import PromptTemplate

logger = logging.getLogger(__name__)


def template_to_dict(t: PromptTemplate) -> dict:
    return {
        "id": str(t.id),
        "user_id": str(t.user_id) if t.user_id else None,
        "name": t.name,
        "description": t.description,
        "is_default": t.is_default,
        "is_system": t.user_id is None,
        "blocks": t.blocks or [],
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def template_to_list_item(t: PromptTemplate) -> dict:
    return {
        "id": str(t.id),
        "user_id": str(t.user_id) if t.user_id else None,
        "name": t.name,
        "description": t.description,
        "is_default": t.is_default,
        "is_system": t.user_id is None,
        "block_count": len(t.blocks or []),
    }


async def list_templates(db: AsyncSession, user_id: UUID) -> list[dict]:
    """列出当前用户的模板 + 所有系统模板。系统模板排在前面。"""
    result = await db.execute(
        select(PromptTemplate)
        .where(
            (PromptTemplate.user_id == user_id) | (PromptTemplate.user_id.is_(None))
        )
        .order_by(
            PromptTemplate.user_id.is_(None).desc(),
            PromptTemplate.is_default.desc(),
            PromptTemplate.name,
        )
    )
    items = result.scalars().all()
    return [template_to_list_item(t) for t in items]


async def get_template(
    db: AsyncSession, template_id: UUID, user_id: UUID
) -> PromptTemplate | None:
    """获取模板。仅返回自己的或系统模板。"""
    t = await db.get(PromptTemplate, template_id)
    if t is None:
        return None
    if t.user_id is not None and t.user_id != user_id:
        return None
    return t


async def create_template(
    db: AsyncSession,
    user_id: UUID,
    name: str,
    description: str | None,
    blocks: list[dict],
    is_default: bool,
) -> PromptTemplate:
    if is_default:
        await _clear_user_default(db, user_id)
    t = PromptTemplate(
        user_id=user_id,
        name=name,
        description=description,
        is_default=is_default,
        blocks=blocks,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def update_template(
    db: AsyncSession,
    template_id: UUID,
    user_id: UUID,
    name: str | None,
    description: str | None,
    blocks: list[dict] | None,
    is_default: bool | None,
) -> PromptTemplate | None:
    """更新模板。仅自己的可改；系统模板拒绝。"""
    t = await get_template(db, template_id, user_id)
    if t is None:
        return None
    if t.user_id is None:
        raise ValueError("系统模板不可修改")

    if name is not None:
        t.name = name
    if description is not None:
        t.description = description
    if blocks is not None:
        t.blocks = blocks
    if is_default is not None:
        if is_default is True:
            await _clear_user_default(db, user_id)
        t.is_default = is_default

    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def delete_template(
    db: AsyncSession, template_id: UUID, user_id: UUID
) -> bool:
    t = await get_template(db, template_id, user_id)
    if t is None:
        return False
    if t.user_id is None:
        raise ValueError("系统模板不可删除")
    if t.is_default:
        raise ValueError("不能删除默认模板")
    await db.delete(t)
    await db.commit()
    return True


async def duplicate_template(
    db: AsyncSession, template_id: UUID, user_id: UUID
) -> PromptTemplate | None:
    """复制模板（可复制系统模板或自己的）。副本归当前用户。"""
    src = await get_template(db, template_id, user_id)
    if src is None:
        return None
    dup = PromptTemplate(
        user_id=user_id,
        name=f"{src.name} (副本)",
        description=src.description,
        is_default=False,
        blocks=[dict(b) for b in (src.blocks or [])],
    )
    db.add(dup)
    await db.commit()
    await db.refresh(dup)
    return dup


async def _clear_user_default(db: AsyncSession, user_id: UUID) -> None:
    """把当前用户旗下其他 is_default=True 的模板清掉，保证 is_default 唯一性。"""
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.user_id == user_id,
            PromptTemplate.is_default == True,  # noqa: E712
        )
    )
    for t in result.scalars().all():
        t.is_default = False
        db.add(t)
