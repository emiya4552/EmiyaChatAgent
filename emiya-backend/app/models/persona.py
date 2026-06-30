# -*- coding: utf-8 -*-
"""角色卡 ORM 模型。"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Persona(Base, TimestampMixin):
    """角色卡表。"""

    __tablename__ = "personas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    personality: Mapped[str] = mapped_column(Text, nullable=False, default="")
    background: Mapped[str | None] = mapped_column(Text)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)

    # === 角色卡核心字段 ===
    first_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    mes_example: Mapped[str | None] = mapped_column(Text, nullable=True)

    # === 展示/筛选 ===
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # === 原始角色卡 JSON（兜底 + 导出用） ===
    card_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # === 来源追踪 ===
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # === 世界书 / AN 默认推荐（建对话时复制到 Conversation） ===
    # 详见 docs/adr/0002-worldbook-binding-via-conversation-list.md
    default_worldbook_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    # 卡作者随卡分发的正则脚本：导入时拆到 RegexPreset，这里存其 ID；
    # 建对话时若 conv 没从 preset 拿到 regex_preset_id，就回退用这个
    default_regex_preset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regex_presets.id", ondelete="SET NULL"),
        nullable=True,
    )
    author_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # === v3 角色卡扩展（详见 docs/adr/0006） ===
    # 备用开场白（除 first_message 外的其他可选切入）
    alternate_greetings: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    # 当前情境（区别于 background 历史/出身）
    scenario: Mapped[str | None] = mapped_column(Text, nullable=True)

    # === 前端渲染：角色卡级 CSS 主题（详见 docs/adr/0008） ===
    # 卡作者自带的样式包，导入时从 extensions.css / extensions.style /
    # creator_notes 抽。User.css_theme 之后再注入（CSS cascade 覆盖）
    css_theme: Mapped[str | None] = mapped_column(Text, nullable=True)

    # === MVU 兼容标记（详见 docs/adr/0010） ===
    # 卡的 extensions.tavern_helper.scripts 含 MVU / MagVarUpdate 脚本时置 True；
    # EMIYA 据此显示「兼容模式」banner、提示用户已识别 MVU 卡
    uses_mvu: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped["User | None"] = relationship("User", backref="personas")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id) if self.user_id else None,
            "name": self.name,
            "personality": self.personality,
            "background": self.background,
            "is_template": self.is_template,
            "first_message": self.first_message,
            "mes_example": self.mes_example,
            "tags": self.tags,
            "avatar_url": self.avatar_url,
            "card_data": self.card_data,
            "source": self.source,
            "source_url": self.source_url,
            "imported_at": self.imported_at.isoformat() if self.imported_at else None,
            "default_worldbook_ids": [str(x) for x in (self.default_worldbook_ids or [])],
            "default_regex_preset_id": (
                str(self.default_regex_preset_id) if self.default_regex_preset_id else None
            ),
            "author_note": self.author_note,
            "alternate_greetings": list(self.alternate_greetings or []),
            "scenario": self.scenario,
            "css_theme": self.css_theme,
            "uses_mvu": self.uses_mvu,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<Persona(id={self.id}, name={self.name})>"
