# -*- coding: utf-8 -*-
"""认证相关的 Pydantic 请求/响应模型。"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegisterRequest(BaseModel):
    """用户注册请求。"""
    email: EmailStr = Field(..., description="用户邮箱")
    password: str = Field(..., min_length=6, max_length=72, description="密码（最长72字符）")
    nickname: str = Field(..., min_length=1, max_length=50, description="昵称")

    @field_validator("password")
    @classmethod
    def password_byte_limit(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("密码过长，请使用72字符以内的密码")
        return v


class UserLoginRequest(BaseModel):
    """用户登录请求。"""
    email: EmailStr = Field(..., description="用户邮箱")
    password: str = Field(..., description="密码")


class UserResponse(BaseModel):
    """用户信息响应。"""
    id: UUID
    email: str
    nickname: str
    avatar_url: str | None = None
    # 用户级 CSS 主题（详见 docs/adr/0008）
    css_theme: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """用户资料编辑请求（PATCH /users/me），所有字段可选。"""
    nickname: str | None = Field(None, min_length=1, max_length=50)
    avatar_url: str | None = Field(None)
    css_theme: str | None = Field(None, description="用户级 CSS 主题（None 清空，详见 ADR-0008）")


class TokenResponse(BaseModel):
    """JWT 令牌响应。"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
