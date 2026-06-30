# -*- coding: utf-8 -*-
"""消息 ORM 模型。"""
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Message(Base):
    """消息表。"""

    __tablename__ = "messages"

    # 消息 ID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 所属对话
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 角色：user / assistant / system
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    # 消息内容
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 创建时间
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )

    # 关联对话
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role={self.role})>"
