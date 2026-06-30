# -*- coding: utf-8 -*-
"""正则预设 Pydantic Schema。"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RegexPresetCreate(BaseModel):
    name: str
    description: str | None = None
    scripts: list[dict] = []


class RegexPresetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    scripts: list[dict] | None = None


class RegexPresetListItem(BaseModel):
    id: UUID
    name: str
    description: str | None
    script_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RegexPresetResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    scripts: list[dict]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
