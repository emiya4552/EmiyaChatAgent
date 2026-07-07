# -*- coding: utf-8 -*-
"""用户与 AI 人设的关系 ORM 模型。"""
import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# 关系等级常量
RELATIONSHIP_LEVELS = {
    0: "陌生人",
    1: "熟人",
    2: "朋友",
    3: "密友",
    4: "知己",
}

# affinity_score → level 阈值映射
AFFINITY_LEVEL_THRESHOLDS = [
    (0, 0),
    (15, 1),
    (35, 2),
    (60, 3),
    (85, 4),
]


def affinity_to_level(score: float) -> int:
    for threshold, lv in reversed(AFFINITY_LEVEL_THRESHOLDS):
        if score >= threshold:
            return lv
    return 0


class Relationship(Base):
    """用户与 AI persona 的好感度关系（user_persona × ai_persona 维度）。"""

    __tablename__ = "relationships"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 用户人设（NULL = 用户未选择人设，退化为 user_id × persona_id）
    user_persona_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("personas.id", ondelete="SET NULL"),
        nullable=True,
    )
    # AI 人设
    persona_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("personas.id", ondelete="CASCADE"),
        nullable=True,
    )
    # 关系等级 0-4
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 好感度分数 0.0-100.0（LLM 驱动，可升可降）
    affinity_score: Mapped[float] = mapped_column(Float, default=0.0)
    # 好感度变动历史（最近 20 条）
    affinity_history: Mapped[list | None] = mapped_column(
        JSONB, default=list, nullable=True
    )
    # 消息总数
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    # 深度对话次数
    deep_talk_count: Mapped[int] = mapped_column(Integer, default=0)
    # 首次交流时间
    first_interaction: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )
    # 最后交流时间
    last_interaction: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )
    # 已达成的里程碑列表
    milestones: Mapped[list | None] = mapped_column(
        JSONB, default=list, nullable=True
    )
    # 创建时间
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )
    # 更新时间
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # 唯一约束：同一用户-用户人设-AI人设组合唯一
    __table_args__ = (
        UniqueConstraint(
            "user_id", "user_persona_id", "persona_id",
            name="uq_relationship_user_upersona_persona",
        ),
        Index("ix_relationship_user_persona", "user_id", "persona_id"),
    )

    # 关联
    user: Mapped["User"] = relationship("User", backref="relationships")
    user_persona: Mapped["Persona | None"] = relationship(
        "Persona", foreign_keys=[user_persona_id]
    )
    persona: Mapped["Persona | None"] = relationship(
        "Persona", foreign_keys=[persona_id]
    )

    def __repr__(self) -> str:
        level_name = RELATIONSHIP_LEVELS.get(self.level, "未知")
        return f"<Relationship(id={self.id}, level={self.level}({level_name}), affinity={self.affinity_score})>"
