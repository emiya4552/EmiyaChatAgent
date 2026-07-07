# -*- coding: utf-8 -*-
"""关系查询 REST API。"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.conversation import Conversation
from app.models.relationship import Relationship, RELATIONSHIP_LEVELS
from app.models.user import User
from app.schemas.relationship import RelationshipResponse
from app.services.relationship_service import (
    assess_relationship,
    get_or_create_relationship,
)
from app.utils.exceptions import ForbiddenException, NotFoundException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["关系"])


@router.get("/relationships/{persona_id}", response_model=RelationshipResponse)
async def get_relationship(
    persona_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户与某个人设的关系状态。"""
    assessment = await assess_relationship(
        db, str(current_user.id), persona_id
    )

    # 获取里程碑信息
    rel = await get_or_create_relationship(
        db, str(current_user.id), persona_id
    )

    return RelationshipResponse(
        level=assessment["level"],
        level_name=assessment["level_name"],
        affinity_score=assessment["affinity_score"],
        total_messages=assessment["total_messages"],
        deep_talk_count=assessment["deep_talk_count"],
        first_interaction=assessment["first_interaction"],
        last_interaction=assessment["last_interaction"],
        days_span=assessment["days_span"],
        milestones=rel.milestones or [],
    )


@router.get(
    "/conversations/{conversation_id}/relationship",
    response_model=RelationshipResponse,
)
async def get_conversation_relationship(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前对话的关系状态。"""
    conv_uuid = UUID(conversation_id)

    result = await db.execute(
        select(Conversation).where(Conversation.id == conv_uuid)
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise NotFoundException("对话不存在")
    if conv.user_id != current_user.id:
        raise ForbiddenException("无权访问该对话")

    persona_id = str(conv.persona_id) if conv.persona_id else None
    user_persona_id = str(conv.user_persona_id) if conv.user_persona_id else None
    if persona_id is None:
        return RelationshipResponse(
            level=0,
            level_name="陌生人",
            affinity_score=0.0,
            total_messages=0,
        )

    assessment = await assess_relationship(
        db, str(current_user.id), persona_id,
        user_persona_id=user_persona_id,
        conversation_id=conversation_id,
    )

    rel = await get_or_create_relationship(
        db, str(current_user.id), persona_id,
        user_persona_id=user_persona_id,
    )

    return RelationshipResponse(
        level=assessment["level"],
        level_name=assessment["level_name"],
        affinity_score=assessment["affinity_score"],
        total_messages=assessment["total_messages"],
        deep_talk_count=assessment["deep_talk_count"],
        first_interaction=assessment["first_interaction"],
        last_interaction=assessment["last_interaction"],
        days_span=assessment["days_span"],
        milestones=rel.milestones or [],
    )
