# -*- coding: utf-8 -*-
"""关系服务 — 评估用户与 AI 人设的关系阶段与进展。"""
import logging
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.relationship import Relationship, RELATIONSHIP_LEVELS, affinity_to_level
from app.models.emotion_record import EmotionRecord
from app.models.message import Message

logger = logging.getLogger(__name__)

# 关系等级阈值
RELATIONSHIP_THRESHOLDS = [
    {"level": 0, "name": "陌生人", "min_score": 0, "messages": 0, "memories": 0},
    {"level": 1, "name": "熟人",   "min_score": 15, "messages": 20, "memories": 3},
    {"level": 2, "name": "朋友",   "min_score": 35, "messages": 80, "memories": 10},
    {"level": 3, "name": "密友",   "min_score": 60, "messages": 200, "memories": 30},
    {"level": 4, "name": "知己",   "min_score": 85, "messages": 500, "memories": 80},
]

# 里程碑定义
MILESTONE_DEFINITIONS = {
    "first_deep_talk": "第一次深度对话",
    "first_vulnerability": "第一次袒露心事",
    "first_joke": "第一次开玩笑",
    "consecutive_days_7": "连续聊了 7 天",
    "message_100": "第 100 条消息",
    "message_500": "第 500 条消息",
    "penetration_30": "深度对话达 30 次",
}


async def assess_relationship(
    db: AsyncSession,
    user_id: str,
    persona_id: str,
    user_persona_id: str | None = None,
    conversation_id: str | None = None,
) -> dict:
    """评估用户与某个人设的关系状态（纯读取，不做数学计算）。

    等级由 affinity_score 阈值映射，不再使用旧的时间/消息/情绪公式。

    Args:
        db: 数据库会话
        user_id: 用户 ID
        persona_id: AI 人设 ID
        user_persona_id: 用户人设 ID（可选）
        conversation_id: 对话 ID（用于统计消息和情绪范围）

    Returns:
        dict: 关系评估结果
    """
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    persona_uuid = UUID(persona_id) if isinstance(persona_id, str) else persona_id
    user_persona_uuid = UUID(user_persona_id) if user_persona_id and isinstance(user_persona_id, str) else user_persona_id
    conv_uuid = UUID(conversation_id) if conversation_id and isinstance(conversation_id, str) else conversation_id

    # 获取或创建关系记录（用新 key）
    rel = await get_or_create_relationship(db, user_id, persona_id, user_persona_id)

    # 查询消息和情绪统计（按对话范围）
    conv_ids_select = select(Conversation.id).where(Conversation.user_id == user_uuid)
    if persona_uuid:
        conv_ids_select = conv_ids_select.where(Conversation.persona_id == persona_uuid)
    if conv_uuid:
        conv_ids_select = conv_ids_select.where(Conversation.id == conv_uuid)

    msg_conditions = [Message.conversation_id.in_(conv_ids_select)]
    msg_count_result = await db.execute(
        select(sa_func.count()).where(*msg_conditions)
    )
    total_messages = msg_count_result.scalar() or 0

    first_msg_result = await db.execute(
        select(Message.created_at).where(*msg_conditions).order_by(Message.created_at.asc()).limit(1)
    )
    first_msg = first_msg_result.scalar_one_or_none()

    last_msg_result = await db.execute(
        select(Message.created_at).where(*msg_conditions).order_by(Message.created_at.desc()).limit(1)
    )
    last_msg = last_msg_result.scalar_one_or_none()

    days_span = 0
    if first_msg and last_msg:
        days_span = (last_msg - first_msg).days

    # 深度对话次数
    emotion_conditions = [EmotionRecord.conversation_id.in_(conv_ids_select)]
    deep_result = await db.execute(
        select(sa_func.count()).where(
            *emotion_conditions,
            EmotionRecord.confidence > 0.6,
            EmotionRecord.intensity >= 6,
        )
    )
    deep_talk_count = deep_result.scalar() or 0

    # 等级由 affinity_score 映射
    level = affinity_to_level(rel.affinity_score)

    return {
        "level": level,
        "level_name": RELATIONSHIP_LEVELS.get(level, "未知"),
        "affinity_score": rel.affinity_score,
        "total_messages": total_messages,
        "deep_talk_count": deep_talk_count,
        "first_interaction": first_msg.isoformat() if first_msg else None,
        "last_interaction": last_msg.isoformat() if last_msg else None,
        "days_span": days_span,
    }


async def detect_milestones(
    db: AsyncSession,
    relationship: Relationship,
    total_messages: int,
    deep_talk_count: int,
    days_span: int,
) -> list[str]:
    """检测新达成的里程碑，只返回本轮新达成的。

    Args:
        db: 数据库会话
        relationship: 现有关系记录
        total_messages: 当前消息总数
        deep_talk_count: 当前深度对话次数
        days_span: 当前对话天数跨度

    Returns:
        list[str]: 新达成的里程碑 key 列表
    """
    existing = set(relationship.milestones or [])
    new_milestones = []

    checks = {
        "first_deep_talk": deep_talk_count >= 1,
        "message_100": total_messages >= 100,
        "message_500": total_messages >= 500,
        "consecutive_days_7": days_span >= 7,
        "penetration_30": deep_talk_count >= 30,
    }

    for key, achieved in checks.items():
        if achieved and key not in existing:
            new_milestones.append(key)

    return new_milestones


async def get_or_create_relationship(
    db: AsyncSession,
    user_id: str,
    persona_id: str,
    user_persona_id: str | None = None,
    for_update: bool = False,
) -> Relationship:
    """获取或创建关系记录（key: user_id × user_persona_id × persona_id）。

    Args:
        db: 数据库会话
        user_id: 用户 ID
        persona_id: AI 人设 ID
        user_persona_id: 用户人设 ID（可选，NULL = 用户未选人设）
        for_update: 是否加行锁（FOR UPDATE），用于并发安全的 affinity 读写

    Returns:
        Relationship: 现有或新建的关系记录
    """
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    persona_uuid = UUID(persona_id) if isinstance(persona_id, str) else persona_id
    up_uuid = UUID(user_persona_id) if user_persona_id and isinstance(user_persona_id, str) else None

    stmt = select(Relationship).where(
        Relationship.user_id == user_uuid,
        Relationship.persona_id == persona_uuid,
        Relationship.user_persona_id == up_uuid,
    )
    if for_update:
        stmt = stmt.with_for_update()

    result = await db.execute(stmt)
    rel = result.scalar_one_or_none()

    if rel is None:
        rel = Relationship(
            user_id=user_uuid,
            persona_id=persona_uuid,
            user_persona_id=up_uuid,
        )
        db.add(rel)
        await db.flush()

    return rel


async def update_affinity(
    db: AsyncSession,
    rel: Relationship,
    delta: int,
    reason: str,
) -> None:
    """更新好感度分数和历史记录。

    Args:
        db: 数据库会话
        rel: 已加锁的关系记录
        delta: 好感变动（-3 ~ +3）
        reason: 变动原因简述
    """
    old_score = rel.affinity_score
    new_score = max(0.0, min(100.0, old_score + delta))
    rel.affinity_score = new_score

    # 更新等级
    from app.models.relationship import affinity_to_level
    rel.level = affinity_to_level(new_score)

    # 追加历史（保持最近 20 条，超出裁剪为首 10 + 尾 10）
    history = list(rel.affinity_history or [])
    from datetime import datetime as dt
    history.append({
        "delta": delta,
        "reason": reason,
        "score": round(new_score, 1),
        "timestamp": dt.utcnow().isoformat(),
    })
    if len(history) > 20:
        history = history[:10] + history[-10:]
    rel.affinity_history = history

    db.add(rel)
    await db.flush()
    logger.info(f"好感度更新: {old_score:.0f} → {new_score:.0f} (delta={delta:+d}, reason={reason})")
