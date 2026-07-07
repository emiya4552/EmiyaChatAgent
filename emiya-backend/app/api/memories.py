# -*- coding: utf-8 -*-
"""记忆管理 API 路由。"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.memory import MemoryListResponse, MemoryResponse, MemoryUpdateRequest
from app.services.memory import service as memory_service
from app.utils.exceptions import AppException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["记忆"])


@router.get("/memories", response_model=MemoryListResponse)
async def list_memories(
    category: str | None = Query(None, description="记忆分类筛选"),
    scope: str | None = Query(None, description="作用域筛选 global / persona:{id}"),
    memory_type: str | None = Query(None, description="类型筛选 fact / event / state"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取记忆列表，支持分类、作用域、类型筛选和分页。"""
    items, total = await memory_service.list_memories(
        db, current_user.id, category, scope, memory_type, limit, offset
    )
    return MemoryListResponse(
        items=[
            MemoryResponse(
                id=str(m.id),
                content=m.content,
                category=m.category,
                importance=m.importance,
                reference_count=m.reference_count,
                scope=m.scope,
                memory_type=m.memory_type,
                source_conversation_id=str(m.source_conversation_id) if m.source_conversation_id else None,
                extracted_at=m.extracted_at.isoformat(),
                last_referenced_at=m.last_referenced_at.isoformat() if m.last_referenced_at else None,
            )
            for m in items
        ],
        total=total,
    )


@router.put("/memories/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: UUID,
    request: MemoryUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """编辑记忆内容。"""
    m = await memory_service.update_memory_content(
        db, memory_id, current_user.id,
        content=request.content,
        category=request.category,
        scope=request.scope,
        memory_type=request.memory_type,
    )
    return MemoryResponse(
        id=str(m.id), content=m.content, category=m.category,
        importance=m.importance, reference_count=m.reference_count,
        scope=m.scope, memory_type=m.memory_type,
        source_conversation_id=str(m.source_conversation_id) if m.source_conversation_id else None,
        extracted_at=m.extracted_at.isoformat(),
        last_referenced_at=m.last_referenced_at.isoformat() if m.last_referenced_at else None,
    )


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除记忆（软删除）。"""
    await memory_service.soft_delete_memory(db, memory_id, current_user.id)


@router.delete("/memories", status_code=status.HTTP_200_OK)
async def clear_all_memories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量清空当前用户的所有记忆（软删除 + 清除 ChromaDB 向量）。"""
    count = await memory_service.clear_all_memories(db, current_user.id)
    return {"deleted": count}
