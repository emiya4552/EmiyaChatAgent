# -*- coding: utf-8 -*-
"""情绪记录 ORM 模型。"""
import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EmotionRecord(Base):
    """情绪记录表，存储每条用户消息的情绪分析结果。"""

    __tablename__ = "emotion_records"

    # 记录 ID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 关联的用户消息
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 所属对话
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 情绪标签（10 种之一）
    emotion: Mapped[str] = mapped_column(String(20), nullable=False)
    # 情绪强度（0-10）
    intensity: Mapped[int] = mapped_column(Integer, nullable=False)
    # 置信度（0-1）
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    # 触发词/短语列表
    triggers: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # 分析时间
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )

    # 关联（passive_deletes=True 让 DB CASCADE 处理，避免 ORM 先置空 FK）
    message: Mapped["Message"] = relationship(
        "Message", backref="emotion_record", passive_deletes=True,
    )
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", backref="emotion_records", passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<EmotionRecord(id={self.id}, emotion={self.emotion}, intensity={self.intensity})>"
