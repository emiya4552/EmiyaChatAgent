# -*- coding: utf-8 -*-
"""关系相关的 Pydantic 请求/响应模型。"""
from pydantic import BaseModel, Field


class RelationshipResponse(BaseModel):
    """关系状态响应。"""
    level: int = Field(..., description="关系等级 0-4")
    level_name: str = Field(..., description="陌生人/熟人/朋友/密友/知己")
    affinity_score: float = Field(0.0, description="好感度分数 0-100（LLM 驱动，可升可降）")
    total_messages: int = Field(..., description="消息总数")
    deep_talk_count: int = Field(0, description="深度对话次数")
    first_interaction: str | None = Field(None, description="首次交流时间")
    last_interaction: str | None = Field(None, description="最后交流时间")
    days_span: int = Field(0, description="交流天数跨度")
    milestones: list[str] = Field(default_factory=list, description="已达成的里程碑")
    new_milestone: str | None = Field(None, description="本轮新达成的里程碑")
    level_changed: bool = Field(False, description="本轮是否升级")
