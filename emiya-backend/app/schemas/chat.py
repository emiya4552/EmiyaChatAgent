# -*- coding: utf-8 -*-
"""聊天相关的 Pydantic 请求/响应模型。"""
from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    """发送聊天消息请求。"""
    content: str = Field(..., min_length=1, max_length=4000, description="用户消息内容")
    reply_length: str | None = Field(None, description="回复长度偏好: short / medium / long")
