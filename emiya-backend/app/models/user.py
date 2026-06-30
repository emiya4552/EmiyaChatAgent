# -*- coding: utf-8 -*-
"""用户 ORM 模型。"""
import uuid

from sqlalchemy import String, Text
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

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
