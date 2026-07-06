# -*- coding: utf-8 -*-
"""情绪分析相关的 Pydantic 模型。"""
from pydantic import BaseModel, Field


class EmotionRecordResponse(BaseModel):
    """情绪记录响应。"""
    id: str
    emotion: str
    intensity: int
    confidence: float
    triggers: list[str]
    created_at: str


class MoodStateResponse(BaseModel):
    """当前对话情绪氛围响应。"""
    current_mood: str | None
    mood_intensity: int | None
