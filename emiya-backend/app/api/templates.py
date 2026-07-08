# -*- coding: utf-8 -*-
"""Prompt 模板 CRUD API。"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.services import template_service

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])


class TemplateBlockSchema(BaseModel):
    id: str
    type: str
    label: str
    enabled: bool = True
    role: str = "system"
    content: str | None = None
    dynamic_ref: str | None = None
    reply_length_config: dict | None = None


class TemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None
    blocks: list[TemplateBlockSchema] = Field(default_factory=list)
    is_default: bool = False


class TemplateUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    blocks: list[TemplateBlockSchema] | None = None
    is_default: bool | None = None


@router.get("")
async def list_templates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await template_service.list_templates(db, user.id)


@router.post("")
async def create_template(
    req: TemplateCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    t = await template_service.create_template(
        db,
        user_id=user.id,
        name=req.name,
        description=req.description,
        blocks=[b.model_dump() for b in req.blocks],
        is_default=req.is_default,
    )
    return template_service.template_to_dict(t)


@router.get("/default-preview")
async def get_default_preview():
    """返回内置默认模板（代码常量）的序列化形式。"""
    from app.services.prompt_renderer import DEFAULT_TEMPLATE_BLOCKS, _block_to_dict
    return {
        "name": "系统默认（内置）",
        "description": "随版本更新；不可编辑；要个性化请复制为自己的模板",
        "is_builtin": True,
        "blocks": [_block_to_dict(b) for b in DEFAULT_TEMPLATE_BLOCKS],
    }


@router.get("/{template_id}")
async def get_template(
    template_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    t = await template_service.get_template(db, template_id, user.id)
    if t is None:
        raise HTTPException(404, "模板不存在")
    return template_service.template_to_dict(t)


@router.put("/{template_id}")
async def update_template(
    template_id: UUID,
    req: TemplateUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        t = await template_service.update_template(
            db,
            template_id=template_id,
            user_id=user.id,
            name=req.name,
            description=req.description,
            blocks=[b.model_dump() for b in req.blocks] if req.blocks is not None else None,
            is_default=req.is_default,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if t is None:
        raise HTTPException(404, "模板不存在")
    return template_service.template_to_dict(t)


@router.delete("/{template_id}")
async def delete_template(
    template_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        ok = await template_service.delete_template(db, template_id, user.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not ok:
        raise HTTPException(404, "模板不存在")
    return {"deleted": True}


@router.post("/{template_id}/duplicate")
async def duplicate_template(
    template_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dup = await template_service.duplicate_template(db, template_id, user.id)
    if dup is None:
        raise HTTPException(404, "模板不存在")
    return template_service.template_to_dict(dup)


@router.post("/import")
async def import_template(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导入模板 JSON。占位端点；导入请使用 POST /api/templates 创建并传入 blocks。"""
    raise HTTPException(400, "导入请使用 POST /api/templates 创建并传入 blocks")


