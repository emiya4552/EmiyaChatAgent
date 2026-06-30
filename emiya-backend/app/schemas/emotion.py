# -*- coding: utf-8 -*-
"""情绪分析相关的 Pydantic 模型。"""
from pydantic import BaseModel, Field


class EmotionAnalysisResult(BaseModel):
    """LLM 情绪分析的原始输出。"""
    emotion: str = Field(..., description="情绪标签：开心/平静/低落/焦虑/愤怒/兴奋/疲惫/困惑/感动/思念")
    intensity: int = Field(..., ge=0, le=10, description="情绪强度 0-10")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度 0-1")
    triggers: list[str] = Field(default_factory=list, description="触发词列表")


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
