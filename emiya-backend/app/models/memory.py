# -*- coding: utf-8 -*-
"""长期记忆 ORM 模型。"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# 记忆分类常量
MEMORY_CATEGORIES = [
    "basic_info",       # 基本信息
    "preference",       # 喜好偏好
    "experience",       # 经历事件
    "habit",            # 生活习惯
    "emotion_pattern",  # 情绪模式
    "relationship",     # 人际关系
    "goal",             # 目标愿望
]

# 分类中文标签
MEMORY_CATEGORY_LABELS = {
    "basic_info": "基本信息",
    "preference": "喜好偏好",
    "experience": "经历事件",
    "habit": "生活习惯",
    "emotion_pattern": "情绪模式",
    "relationship": "人际关系",
    "goal": "目标愿望",
}


class Memory(Base):
    """长期记忆表，存储从对话中提取的用户事实。"""

    __tablename__ = "memories"

    # 记忆 ID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 所属用户
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # 记忆内容（自然语言）
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 类别（7 大类之一）
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    # 来源对话
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 重要性（0-1）
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    # 被引用次数
    reference_count: Mapped[int] = mapped_column(Integer, default=0)
    # 作用域（global / persona:{persona_id}）
    scope: Mapped[str] = mapped_column(String(50), default="global", nullable=False)
    # 记忆类型（fact / event / state）
    memory_type: Mapped[str] = mapped_column(String(20), default="fact", nullable=False)
    # 软删除标记
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    # 提取时间
    extracted_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )
    # 最后引用时间
    last_referenced_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # 关联
    user: Mapped["User"] = relationship("User", backref="memories")
    source_conversation: Mapped["Conversation | None"] = relationship("Conversation")

    def __repr__(self) -> str:
        return f"<Memory(id={self.id}, category={self.category}, importance={self.importance})>"
