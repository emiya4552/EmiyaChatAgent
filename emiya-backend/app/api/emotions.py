# -*- coding: utf-8 -*-
"""情绪查询 API 路由。

设计原则（详见 docs/adr/0005）：
- 情绪数据不参与 Prompt 注入，本路由产出仅服务 Dashboard 与 deep_talk_count
- 5 个查询端点统一接受 persona_id / conversation_id 可选过滤
- 聚合在 PostgreSQL GROUP BY 端完成，不再 Python 后处理
- trend 在单 conversation scope 下返回 message-indexed 数据（"情绪弧线"）
"""
import logging
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.conversation import Conversation
from app.models.emotion_record import EmotionRecord
from app.models.message import Message
from app.models.persona import Persona
from app.models.user import User
from app.schemas.emotion import EmotionRecordResponse, MoodStateResponse
from app.utils.exceptions import ForbiddenException, NotFoundException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["情绪"])


# ─── 内部辅助：解析 + 校验 scope ──────────────────────────────────


async def _resolve_scope_conv_ids(
    db: AsyncSession,
    user_id: UUID,
    persona_id: UUID | None,
    conversation_id: UUID | None,
) -> tuple[list[UUID], Conversation | None]:
    """根据过滤参数解析出 conversation_id 列表 + 可选的单 conv 对象。

    校验：persona_id / conversation_id 必须属于当前 user_id。
    返回 (conv_ids, single_conv)：
      - single_conv 仅当过滤到唯一 conversation 时非 None（用于弧线模式判定）
    """
    if conversation_id is not None:
        conv = await db.get(Conversation, conversation_id)
        if conv is None:
            raise NotFoundException("对话不存在")
        if conv.user_id != user_id:
            raise ForbiddenException("无权访问该对话")
        if persona_id is not None and conv.persona_id != persona_id:
            raise NotFoundException("对话与所选角色不匹配")
        return [conv.id], conv

    base_q = select(Conversation.id).where(Conversation.user_id == user_id)
    if persona_id is not None:
        base_q = base_q.where(Conversation.persona_id == persona_id)
    result = await db.execute(base_q)
    conv_ids = [row[0] for row in result.all()]
    return conv_ids, None


# ─── 端点：当前情绪氛围（单 conv） ────────────────────────────────


@router.get("/conversations/{conversation_id}/mood", response_model=MoodStateResponse)
async def get_conversation_mood(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前对话的情绪氛围。"""
    result = await db.execute(
        select(Conversation).where(Conversation.id == UUID(conversation_id))
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise NotFoundException("对话不存在")
    if conv.user_id != current_user.id:
        raise ForbiddenException("无权访问该对话")

    return MoodStateResponse(
        current_mood=conv.current_mood,
        mood_intensity=conv.mood_intensity,
    )


# ─── 端点：对话情绪记录历史 ──────────────────────────────────────


@router.get(
    "/conversations/{conversation_id}/emotions",
    response_model=list[EmotionRecordResponse],
)
async def get_conversation_emotions(
    conversation_id: str,
    limit: int = Query(20, ge=1, le=50, description="返回数量"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取对话的情绪记录历史，按时间降序。"""
    result = await db.execute(
        select(Conversation).where(Conversation.id == UUID(conversation_id))
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise NotFoundException("对话不存在")
    if conv.user_id != current_user.id:
        raise ForbiddenException("无权访问该对话")

    records_result = await db.execute(
        select(EmotionRecord)
        .where(EmotionRecord.conversation_id == UUID(conversation_id))
        .order_by(EmotionRecord.created_at.desc())
        .limit(limit)
    )
    records = list(records_result.scalars().all())

    return [
        EmotionRecordResponse(
            id=str(r.id),
            emotion=r.emotion,
            intensity=r.intensity,
            confidence=r.confidence,
            triggers=r.triggers or [],
            created_at=r.created_at.isoformat(),
        )
        for r in records
    ]


# ─── 辅助端点：Dashboard filter 用 ───────────────────────────────


@router.get("/emotions/scope/personas")
async def list_filter_personas(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出用户参与过对话的所有 persona，供 Dashboard filter dropdown 使用。

    只返回"实际有过情绪记录"的 persona，避免 dropdown 出现空 persona。
    """
    result = await db.execute(
        select(Persona.id, Persona.name)
        .join(Conversation, Conversation.persona_id == Persona.id)
        .where(Conversation.user_id == current_user.id)
        .where(
            Conversation.id.in_(
                select(EmotionRecord.conversation_id).distinct()
            )
        )
        .distinct()
        .order_by(Persona.name)
    )
    return [{"id": str(row[0]), "name": row[1]} for row in result.all()]


@router.get("/emotions/scope/conversations")
async def list_filter_conversations(
    persona_id: str = Query(..., description="必填，按角色筛选对话"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出某 persona 下该用户所有有情绪记录的对话。"""
    pid = UUID(persona_id)
    result = await db.execute(
        select(Conversation.id, Conversation.title, Conversation.created_at)
        .where(Conversation.user_id == current_user.id)
        .where(Conversation.persona_id == pid)
        .where(
            Conversation.id.in_(
                select(EmotionRecord.conversation_id).distinct()
            )
        )
        .order_by(Conversation.updated_at.desc())
    )
    return [
        {
            "id": str(row[0]),
            "title": row[1] or "未命名对话",
            "created_at": row[2].isoformat() if row[2] else None,
        }
        for row in result.all()
    ]


# ─── 端点：情绪趋势（变形：单 conv 时改为消息序号弧线） ─────────────


@router.get("/emotions/trend")
async def get_emotion_trend(
    days: int = Query(7, ge=1, le=30, description="统计天数（多对话模式生效）"),
    persona_id: str | None = Query(None),
    conversation_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """情绪趋势。

    - 多对话模式（无 conversation_id）：按天聚合，返回 [{date, dominant_emotion, avg_intensity}, ...]
    - 单对话模式（有 conversation_id）：按消息序号返回弧线，
      返回 [{idx, emotion, intensity, confidence, triggers, created_at}, ...]
    """
    pid = UUID(persona_id) if persona_id else None
    cid = UUID(conversation_id) if conversation_id else None

    conv_ids, single_conv = await _resolve_scope_conv_ids(
        db, current_user.id, pid, cid
    )
    if not conv_ids:
        return []

    # ── 单对话模式：直接按消息序返回弧线 ──
    if single_conv is not None:
        result = await db.execute(
            select(
                EmotionRecord.emotion,
                EmotionRecord.intensity,
                EmotionRecord.confidence,
                EmotionRecord.triggers,
                EmotionRecord.created_at,
                EmotionRecord.message_id,
            )
            .where(EmotionRecord.conversation_id == single_conv.id)
            .order_by(EmotionRecord.created_at.asc())
        )
        arc = []
        for idx, row in enumerate(result.all(), start=1):
            arc.append({
                "idx": idx,
                "emotion": row.emotion,
                "intensity": row.intensity,
                "confidence": row.confidence,
                "triggers": row.triggers or [],
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })
        return arc

    # ── 多对话模式：按 (date, emotion) GROUP BY，挑每天主导 ──
    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(
            sa_func.date(EmotionRecord.created_at).label("date"),
            EmotionRecord.emotion,
            sa_func.avg(EmotionRecord.intensity).label("avg_intensity"),
            sa_func.count().label("cnt"),
        )
        .where(
            EmotionRecord.conversation_id.in_(conv_ids),
            EmotionRecord.created_at >= since,
        )
        .group_by(sa_func.date(EmotionRecord.created_at), EmotionRecord.emotion)
        .order_by(sa_func.date(EmotionRecord.created_at))
    )
    date_map: dict[str, dict] = {}
    for row in result.all():
        d = str(row.date)
        if d not in date_map:
            date_map[d] = {"emotions": {}, "total_intensity": 0.0, "total_count": 0}
        date_map[d]["emotions"][row.emotion] = row.cnt
        date_map[d]["total_intensity"] += float(row.avg_intensity) * row.cnt
        date_map[d]["total_count"] += row.cnt

    trend = []
    for d in sorted(date_map.keys()):
        info = date_map[d]
        dominant = max(info["emotions"], key=info["emotions"].get)
        avg = round(info["total_intensity"] / info["total_count"], 1) if info["total_count"] > 0 else 0
        trend.append({"date": d, "dominant_emotion": dominant, "avg_intensity": avg})
    return trend


# ─── 端点：情绪分布 ──────────────────────────────────────────────


@router.get("/emotions/distribution")
async def get_emotion_distribution(
    days: int = Query(30, ge=1, le=90, description="统计天数"),
    persona_id: str | None = Query(None),
    conversation_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """情绪标签分布饼图数据。"""
    pid = UUID(persona_id) if persona_id else None
    cid = UUID(conversation_id) if conversation_id else None

    conv_ids, single_conv = await _resolve_scope_conv_ids(
        db, current_user.id, pid, cid
    )
    if not conv_ids:
        return []

    # 单对话模式不限时间；多对话模式按 days 截断
    where_clauses = [EmotionRecord.conversation_id.in_(conv_ids)]
    if single_conv is None:
        since = datetime.utcnow() - timedelta(days=days)
        where_clauses.append(EmotionRecord.created_at >= since)

    result = await db.execute(
        select(
            EmotionRecord.emotion,
            sa_func.count().label("cnt"),
        )
        .where(and_(*where_clauses))
        .group_by(EmotionRecord.emotion)
    )
    rows = result.all()
    total = sum(row.cnt for row in rows)

    return [
        {
            "emotion": row.emotion,
            "count": row.cnt,
            "percentage": round(row.cnt / total * 100, 1) if total > 0 else 0,
        }
        for row in rows
    ]


# ─── 端点：情绪日历 ──────────────────────────────────────────────


@router.get("/emotions/calendar")
async def get_emotion_calendar(
    month: str = Query(..., description="月份，格式 YYYY-MM"),
    persona_id: str | None = Query(None),
    conversation_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """情绪日历数据。"""
    try:
        year, mon = map(int, month.split("-"))
    except ValueError:
        return []

    pid = UUID(persona_id) if persona_id else None
    cid = UUID(conversation_id) if conversation_id else None

    conv_ids, _ = await _resolve_scope_conv_ids(db, current_user.id, pid, cid)
    if not conv_ids:
        return []

    result = await db.execute(
        select(
            sa_func.date(EmotionRecord.created_at).label("date"),
            EmotionRecord.emotion,
            sa_func.count().label("cnt"),
            sa_func.avg(EmotionRecord.intensity).label("avg_intensity"),
        )
        .where(
            EmotionRecord.conversation_id.in_(conv_ids),
            sa_func.extract("year", EmotionRecord.created_at) == year,
            sa_func.extract("month", EmotionRecord.created_at) == mon,
        )
        .group_by(sa_func.date(EmotionRecord.created_at), EmotionRecord.emotion)
    )
    rows = result.all()

    date_map: dict[str, dict] = {}
    for row in rows:
        d = str(row.date)
        if d not in date_map:
            date_map[d] = {"emotions": {}, "total_intensity": 0.0, "total_count": 0}
        date_map[d]["emotions"][row.emotion] = row.cnt
        date_map[d]["total_intensity"] += float(row.avg_intensity) * row.cnt
        date_map[d]["total_count"] += row.cnt

    calendar = []
    for d in sorted(date_map.keys()):
        info = date_map[d]
        dominant = max(info["emotions"], key=info["emotions"].get)
        avg = round(info["total_intensity"] / info["total_count"], 1) if info["total_count"] > 0 else None
        calendar.append({
            "date": d,
            "dominant_emotion": dominant,
            "avg_intensity": avg,
        })
    return calendar
