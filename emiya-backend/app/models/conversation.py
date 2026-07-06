# -*- coding: utf-8 -*-
"""对话 ORM 模型。"""
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Conversation(Base, TimestampMixin):
    """对话表。"""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    persona_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("personas.id", ondelete="SET NULL"), nullable=True
    )
    user_persona_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("personas.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str | None] = mapped_column(String(200))
    current_mood: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mood_intensity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_count: Mapped[int] = mapped_column(Integer, default=0)
    last_extraction_msg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_summarized_count: Mapped[int] = mapped_column(Integer, default=0)
    chat_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    preset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("presets.id", ondelete="SET NULL"),
        nullable=True,
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    regex_preset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regex_presets.id", ondelete="SET NULL"),
        nullable=True,
    )

    # === 世界书绑定 + AN（详见 docs/adr/0002, 0003） ===
    # JSONB 数组而非 M2M：单对话挂书数量小、顺序敏感、与现有冻结模式一致
    worldbook_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    author_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    an_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    an_role: Mapped[str] = mapped_column(String(20), nullable=False, default="system")
    an_interval: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # === MVU 本地变量桶（详见 docs/adr/0007） ===
    # 由 {{setvar}}/{{getvar}}/{{incvar}}/{{decvar}} 宏读写，跨轮持久化
    variables: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # === 情感分析（感知）总开关（无 template block，独立 conv 级开关；ADR-0019） ===
    # 字段名沿用 analyze_emotion，但语义已扩为整套"情感感知系统"的开关：
    # 情绪 + 好感度合并为 node_post_process 里的一次 assess_turn 上下文感知调用。
    # 关闭后：跳过 assess_turn（省 LLM 调用），不写 EmotionRecord、不更新 mood、不更新好感度。
    # 注意：这是"写路径"开关；"读路径"（把关系状态注入 prompt）由 relationship
    # template block 另行 gate，与本开关正交（详见 ADR-0019 门控模型）。
    analyze_emotion: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    # === MVU 卡 UI 危险能力 per-conversation 限权（ADR-0008d D2） ===
    # 卡 UI（如飞讯手机终端）会调 generateRaw（卡触发 LLM=花 token）/ setChatMessages（卡改会话楼层）
    # 等 dangerous 能力，默认全拒；用户对某个会话显式开启（{"dangerous": true}）后才经后端端点执行。
    # read（getWorldbook 等）默认允许，local（本回合 stat_data）Host 内本地做，均不受此开关限制。
    mvu_capabilities: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    user: Mapped["User"] = relationship("User", backref="conversations")
    persona: Mapped["Persona | None"] = relationship("Persona", foreign_keys=[persona_id])
    user_persona: Mapped["Persona | None"] = relationship("Persona", foreign_keys=[user_persona_id])
    preset: Mapped["Preset | None"] = relationship("Preset", foreign_keys=[preset_id])
    regex_preset: Mapped["RegexPreset | None"] = relationship(
        "RegexPreset", foreign_keys=[regex_preset_id]
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", order_by="Message.created_at",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title={self.title})>"
