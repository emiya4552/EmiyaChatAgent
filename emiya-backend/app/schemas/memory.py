# -*- coding: utf-8 -*-
"""记忆相关的 Pydantic 模型。"""
from pydantic import BaseModel, Field


class MemoryResponse(BaseModel):
    """记忆记录响应。"""
    id: str
    content: str
    category: str
    importance: float
    reference_count: int
    scope: str = "global"
    memory_type: str = "fact"
    source_conversation_id: str | None = None
    extracted_at: str
    last_referenced_at: str | None = None


class MemoryListResponse(BaseModel):
    """记忆分页响应。"""
    items: list[MemoryResponse]
    total: int


class MemoryUpdateRequest(BaseModel):
    """编辑记忆请求。"""
    content: str | None = Field(None, description="新的记忆内容")
    category: str | None = Field(None, description="新的分类")
    scope: str | None = Field(None, description="作用域 global / persona:{id}")
    memory_type: str | None = Field(None, description="记忆类型 fact / event / state")


class MemoryExtractionResult(BaseModel):
    """LLM 记忆提取的原始输出。"""
    content: str = Field(..., description="提取的记忆内容（自然语言）")
    category: str = Field(..., description="类别")
    importance: float = Field(..., ge=0.0, le=1.0, description="重要性 0-1")
    memory_type: str = Field(default="fact", description="记忆类型 fact / event / state")
