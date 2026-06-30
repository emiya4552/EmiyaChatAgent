# -*- coding: utf-8 -*-
"""世界书 ORM 模型。

参见 docs/adr/0001-worldbook-as-independent-module.md
   docs/adr/0004-worldbook-entries-as-jsonb-array.md
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


# ─── Position 枚举（对齐 ST 数值；详见 ADR-0003） ───
WI_POSITION_BEFORE_CHAR = 0
WI_POSITION_AFTER_CHAR = 1
WI_POSITION_AN_TOP = 2
WI_POSITION_AN_BOTTOM = 3
WI_POSITION_AT_DEPTH = 4
WI_POSITION_EM_TOP = 5
WI_POSITION_EM_BOTTOM = 6
WI_POSITION_OUTLET = 7

# ─── Selective Logic 枚举（对齐 ST） ───
WI_LOGIC_AND_ANY = 0
WI_LOGIC_NOT_ALL = 1
WI_LOGIC_NOT_ANY = 2
WI_LOGIC_AND_ALL = 3


class Worldbook(Base, TimestampMixin):
    """世界书表 — 顶层资源，user_id NULL 表示系统模板。

    `entries` 是 list[dict]，每个 dict 即一条 WorldbookEntry。
    完整字段约定见 schemas/worldbook.py::WorldbookEntry。
    """

    __tablename__ = "worldbooks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 书级默认（被 entry 覆盖时优先 entry） ──
    scan_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    match_whole_words: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # ── 条目数组（ADR-0004：单表 JSONB） ──
    entries: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # ── ST extensions 兜底字段（导入时无识别字段塞此处，导出时原样吐回） ──
    extensions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    user: Mapped["User | None"] = relationship("User", backref="worldbooks")

    def __repr__(self) -> str:
        return f"<Worldbook(id={self.id}, name={self.name}, entries={len(self.entries or [])})>"
