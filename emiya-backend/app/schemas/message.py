# -*- coding: utf-8 -*-
"""消息相关的 Pydantic 请求/响应模型。"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MessageResponse(BaseModel):
    """消息响应。"""
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True
