# -*- coding: utf-8 -*-
"""对话相关的 Pydantic 请求/响应模型。"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ConversationCreateRequest(BaseModel):
    """新建对话请求。"""
    persona_id: UUID = Field(..., description="选择的 AI 人设 ID")
    user_persona_id: UUID | None = Field(None, description="选择的用户人设 ID（可选）")
    title: str | None = Field(None, max_length=100, description="对话标题")
    preset_id: UUID | None = Field(None, description="预设 ID（可选）")
    template_id: UUID | None = Field(None, description="Prompt 模板 ID（null=默认）")
    # 显式选择世界书 + 正则预设（前端创建对话弹窗的"统一配置"，详见 ADR-0014）
    # 给出 None = 走"关联预导入"兜底：worldbook→persona.default_worldbook_ids,
    # regex→preset.regex_preset_id → persona.default_regex_preset_id
    worldbook_ids: list[UUID] | None = Field(
        None,
        description="显式绑定的世界书 ID 列表；None=用 persona.default_worldbook_ids 兜底",
    )
    regex_preset_id: UUID | None = Field(
        None,
        description="显式选择的正则预设；None=按 preset > persona 优先级回退",
    )
    greeting_index: int | None = Field(
        None,
        ge=0,
        description="开场白索引。0 = first_message；>=1 = alternate_greetings[idx-1]。详见 docs/adr/0006",
    )


class PresetApplyRequest(BaseModel):
    """应用预设到对话请求。preset_id=None 表示取消预设（清 chat_config 派生项 + preset_id + regex_preset_id）。"""
    preset_id: UUID | None = Field(None, description="预设 ID；None = 取消预设")


class ConversationConfigUpdate(BaseModel):
    """更新对话配置请求。"""
    chat_config: dict = Field(..., description="对话配置（采样参数 + 上下文设置）")


class ConversationResponse(BaseModel):
    """对话响应。"""
    id: UUID
    persona_id: UUID | None = None
    persona_name: str | None = None
    title: str | None = None
    user_persona_id: UUID | None = None
    user_persona_name: str | None = None
    preset_id: UUID | None = None
    preset_name: str | None = None
    chat_config: dict | None = None
    # 用于配置面板回显：系统默认 ∪ chat_config，只覆盖后端真正会下发的字段
    effective_chat_config: dict | None = None
    template_id: UUID | None = None
    regex_preset_id: UUID | None = None
    # 世界书 + AN（详见 docs/adr/0002, 0003）
    worldbook_ids: list[str] = []
    author_note: str | None = None
    an_depth: int = 4
    an_role: str = "system"
    an_interval: int = 1
    # 情绪分析功能开关
    analyze_emotion: bool = True
    # 该 conv 的有效模板里 reply_length block 是否启用——derived 字段，前端 ChatMain
    # 的短/中/长按钮组据此 disable（详见 ADR-0014）
    reply_length_enabled: bool = True
    # MVU 对话级变量桶（详见 ADR-0007）；只读暴露给前端展示，写入由宏机制完成
    variables: dict = {}
    # MVU 初始化/重载状态摘要（详见 docs/mvu/adr/0002）
    mvu_state: dict | None = None
    # MVU 卡 UI 危险能力 per-conversation 开关（ADR-0008d）；{"dangerous": bool}，默认 {} = 全拒
    mvu_capabilities: dict = {}
    # 最后一条消息的预览文本（派生字段，非 DB 列）；仅列表接口填充，供首页最近对话卡片展示
    last_message_preview: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RegexPresetSwitchRequest(BaseModel):
    """切换对话正则预设请求。"""
    regex_preset_id: UUID | None = Field(
        None, description="正则预设 ID；None=取消正则",
    )


class GreetingSwitchRequest(BaseModel):
    """切换开场白请求。0 = first_message，>=1 = alternate_greetings[idx-1]。

    仅在对话尚未开始（首条 assistant 消息没被用户回复过）时允许。详见 ADR-0017。
    """
    greeting_index: int = Field(..., ge=0, description="开场白索引")
