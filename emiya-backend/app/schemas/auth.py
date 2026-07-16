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


class ForgotPasswordRequest(BaseModel):
    """找回密码请求。"""
    email: EmailStr = Field(..., description="用户邮箱")


class ResetPasswordRequest(BaseModel):
    """重置密码请求。"""
    token: str = Field(..., min_length=20, description="邮件里的重置令牌")
    new_password: str = Field(..., min_length=6, max_length=72, description="新密码")

    @field_validator("new_password")
    @classmethod
    def password_byte_limit(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("密码过长，请使用72字符以内的密码")
        return v


class MessageResponse(BaseModel):
    """通用消息响应。"""
    message: str


class UserResponse(BaseModel):
    """用户信息响应。"""
    id: UUID
    email: str
    nickname: str
    avatar_url: str | None = None
    # 用户级 CSS 主题（详见 docs/adr/0008）
    css_theme: str | None = None
    # 情感分析默认偏好：新建对话时 analyze_emotion 的初始值（详见 docs/adr/0020）
    default_analyze_emotion: bool = False
    # MVU 兼容总开关（详见 docs/card/0002）：off 时聊天把 MVU 卡当普通卡
    mvu_compat_enabled: bool = True
    # 世界书导入/编辑期是否自动调用 LLM 识别可见输出契约（详见 docs/feat-adr/adr1-1）
    output_contract_llm_detection_enabled: bool = False
    # 每次批量识别最多送检多少条候选 entry
    output_contract_llm_detection_limit: int = 30
    # 聊天期可见输出契约执行默认（详见 docs/feat-adr/adr1f）
    output_contract_default_mode: str = "auto"
    output_contract_allow_full_rewrite: bool = False
    output_contract_strict_fallback: str = "repair"
    # 严格声明模式账户默认（详见 docs/feat-adr/adr2c + 配置系统 ADR）；
    # None = 该账户未表态，继承全局 settings.OUTPUT_CONTRACT_REQUIRE_CONFIRMED
    output_contract_require_confirmed: bool | None = None
    # 账户级配置桶（ADR-4）：记忆系统调参 + token 预算账户默认。空 {} = 全部继承全局。
    account_config: dict = {}
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """用户资料编辑请求（PATCH /users/me），所有字段可选。"""
    nickname: str | None = Field(None, min_length=1, max_length=50)
    avatar_url: str | None = Field(None)
    css_theme: str | None = Field(None, description="用户级 CSS 主题（None 清空，详见 ADR-0008）")
    default_analyze_emotion: bool | None = Field(
        None, description="情感分析默认偏好，仅影响新建对话（详见 ADR-0020）"
    )
    mvu_compat_enabled: bool | None = Field(
        None, description="MVU 兼容总开关，off 时聊天把 MVU 卡当普通卡（详见 CARD-0002）"
    )
    output_contract_llm_detection_enabled: bool | None = Field(
        None,
        description="世界书导入/编辑时是否自动调用 LLM 识别可见输出契约",
    )
    output_contract_llm_detection_limit: int | None = Field(
        None,
        ge=0,
        le=200,
        description="每次批量识别最多送检多少条候选世界书 entry",
    )
    output_contract_default_mode: str | None = Field(
        None,
        pattern="^(off|auto|guide|repair|strict)$",
        description="聊天期可见输出契约默认执行模式（详见 ADR-1f）",
    )
    output_contract_allow_full_rewrite: bool | None = Field(
        None,
        description="是否允许最后兜底的整篇 rewrite（独立许可，默认关）",
    )
    output_contract_strict_fallback: str | None = Field(
        None,
        pattern="^(repair|guide|off)$",
        description="strict 不可用时的降级模式",
    )
    output_contract_require_confirmed: bool | None = Field(
        None,
        description="严格声明模式账户默认：on 时聊天只执行已确认/声明的契约（详见 ADR-2c）",
    )
    account_config: dict | None = Field(
        None,
        description="账户级配置桶（ADR-4）：增量合并入现有 account_config，白名单+钳制；"
                    "键值为 null=清空该项回退全局。未知键丢弃",
    )


class UserSessionResponse(BaseModel):
    """用户会话响应。"""
    id: UUID
    device_label: str
    ip_address: str | None = None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    is_current: bool = False
    status: str


class TokenResponse(BaseModel):
    """JWT 令牌响应。"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
