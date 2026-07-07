# -*- coding: utf-8 -*-
"""用户 ORM 模型。"""
import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """用户表。"""

    __tablename__ = "users"

    # 用户 ID，使用 UUID 主键
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 邮箱，唯一不可重复
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # 昵称
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    # bcrypt 密码哈希
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # 头像 URL，可选
    avatar_url: Mapped[str | None] = mapped_column(String(2048))

    # === MVU 全局变量桶（详见 docs/adr/0007） ===
    # 跨该用户所有对话与角色共享；{{setglobalvar}}/{{getglobalvar}} 读写
    global_variables: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    # === 用户级 CSS 主题（详见 docs/adr/0008） ===
    # 用户全局样式包，对该用户所有对话生效；Persona.css_theme 之后再注入
    css_theme: Mapped[str | None] = mapped_column(Text, nullable=True)

    # === 情感分析默认偏好（详见 docs/adr/0020） ===
    # 仅决定**新建对话**时 Conversation.analyze_emotion 的初始值（创建时快照）。
    # 默认 False → 感知系统 opt-in。改它不追溯已存在的对话、不覆盖手动选择。
    default_analyze_emotion: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )

    # === MVU 兼容总开关（详见 docs/card/0002） ===
    # 账户级、仅作用于**聊天时**。关闭后把 MVU 卡当普通卡：关整条 MVU 状态机器 +
    # 剔除 MVU 标签世界书条目 + 跳过 EJS + 隐藏卡 UI。不影响导入/检测/导出。默认开。
    mvu_compat_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
