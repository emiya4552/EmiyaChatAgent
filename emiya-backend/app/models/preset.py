# -*- coding: utf-8 -*-
"""预设 ORM 模型。"""
import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Preset(Base, TimestampMixin):
    __tablename__ = "presets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sampling_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    context_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    prompts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    extensions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    regex_preset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regex_presets.id", ondelete="SET NULL"),
        nullable=True,
    )

    regex_preset: Mapped["RegexPreset | None"] = relationship(
        "RegexPreset", foreign_keys=[regex_preset_id]
    )
