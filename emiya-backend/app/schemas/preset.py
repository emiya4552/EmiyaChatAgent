# -*- coding: utf-8 -*-
"""预设相关的 Pydantic 请求/响应模型。"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PresetCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: str | None = None
    sampling_params: dict = Field(default_factory=dict)
    context_settings: dict = Field(default_factory=dict)
    prompts: list = Field(default_factory=list)
    extensions: dict = Field(default_factory=dict)


class PresetUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = None
    sampling_params: dict | None = None
    context_settings: dict | None = None
    prompts: list | None = None
    extensions: dict | None = None


class PresetListItem(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    prompt_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PresetResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    sampling_params: dict
    context_settings: dict
    prompts: list
    extensions: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
