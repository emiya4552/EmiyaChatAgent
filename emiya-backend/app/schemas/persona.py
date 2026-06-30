# -*- coding: utf-8 -*-
"""角色卡 Pydantic 请求/响应模型。"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PersonaCreateRequest(BaseModel):
    """创建角色卡请求。"""
    name: str = Field(..., min_length=1, description="角色名称")
    personality: str = Field(default="", description="性格描述")
    background: str | None = Field(None, description="背景故事")
    first_message: str | None = Field(None, description="开场白")
    mes_example: str | None = Field(None, description="对话示例")
    tags: list[str] | None = Field(None, description="标签")
    avatar_url: str | None = Field(None, description="头像路径")
    scenario: str | None = Field(None, description="当前情境")
    alternate_greetings: list[str] | None = Field(None, description="备用开场白列表")
    css_theme: str | None = Field(None, description="角色卡级 CSS 主题")


class PersonaUpdateRequest(BaseModel):
    """编辑角色卡请求（所有字段可选）。"""
    name: str | None = Field(None)
    personality: str | None = Field(None)
    background: str | None = Field(None)
    first_message: str | None = Field(None)
    mes_example: str | None = Field(None)
    tags: list[str] | None = Field(None)
    avatar_url: str | None = Field(None)
    card_data: dict | None = Field(None, description="手动编辑原始 JSON")
    default_worldbook_ids: list[str] | None = Field(None, description="默认携带的世界书 ID 列表")
    default_regex_preset_id: UUID | None = Field(None, description="默认携带的正则预设 ID（卡内嵌 regex_scripts 拆来的）")
    author_note: str | None = Field(None, description="默认 Author's Note 文本")
    scenario: str | None = Field(None, description="当前情境")
    alternate_greetings: list[str] | None = Field(None, description="备用开场白列表")
    css_theme: str | None = Field(None, description="角色卡级 CSS 主题")


class PersonaResponse(BaseModel):
    """角色卡详情响应。"""
    id: UUID
    user_id: UUID | None = None
    name: str
    personality: str
    background: str | None = None
    is_template: bool = False
    first_message: str | None = None
    mes_example: str | None = None
    tags: list[str] | None = None
    avatar_url: str | None = None
    card_data: dict | None = None
    source: str = "manual"
    source_url: str | None = None
    imported_at: datetime | None = None
    default_worldbook_ids: list[str] = []
    default_regex_preset_id: UUID | None = None
    author_note: str | None = None
    scenario: str | None = None
    alternate_greetings: list[str] = []
    css_theme: str | None = None
    # MVU 兼容标记（详见 ADR-0010）
    uses_mvu: bool = False
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class PersonaListItem(BaseModel):
    """角色卡列表项。"""
    id: UUID
    name: str
    personality: str
    is_template: bool = False
    is_owner: bool = False
    tags: list[str] | None = None
    avatar_url: str | None = None
    source: str = "manual"

    class Config:
        from_attributes = True
