# -*- coding: utf-8 -*-
"""消息 ORM 模型。"""
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    # 消息内容 = **prompt 真相版**（发给 LLM / 进 history 的干净文本，
    # markdownOnly 美化不烘进来；详见 docs/mvu/adr/0003 双管线）
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 显示版：markdownOnly 美化（状态栏 HTML / UpdateVariable 折叠等）后的文本。
    # 由后端在持久化时派生，前端优先渲染它；NULL 时回退用 content。
    # 无法从 content 反推（两者从同一 precursor 分叉），故必须落库。
    display_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 每条消息的变量袋（TavernHelper `data`，ADR-0008d）。卡 UI（如 WuWa 飞讯手机终端）
    # 用 setChatMessages/createChatMessages 往消息上挂结构化状态；不参与 prompt/显示，
    # 仅供卡 UI 经能力端点读写。NULL = 无。
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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
