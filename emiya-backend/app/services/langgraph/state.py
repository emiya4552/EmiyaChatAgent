# -*- coding: utf-8 -*-
"""LangGraph 聊天流水线 — State 定义。"""
from typing import TypedDict
from uuid import UUID


class ChatState(TypedDict):
    """聊天流水线的状态对象。

    LangGraph 的 State 是所有节点共享的字典，每个节点可以读取和修改。
    """

    # 输入参数
    conversation_id: UUID
    user_id: UUID
    persona_id: UUID | None
    user_persona_id: UUID | None
    user_message: str
    reply_length: str

    # 中间结果 — 情绪
    emotion: str | None
    emotion_intensity: int
    emotion_confidence: float
    emotion_triggers: list[str]
    current_mood: str | None
    mood_intensity: int | None

    # 中间结果 — 记忆
    recalled_memories: list[dict]

    # 世界书激活集（由 node_activate_worldbook 产出）
    # 每元素是 dataclass ActiveEntry 的 dict 化（uid/comment/content/position/depth/role/outlet_name/worldbook_id/worldbook_name）
    wi_activated: list[dict]
    # MVU 变量驱动扫描（ADR-0004，默认关闭）参与匹配的路径诊断 [{path,found,value_preview}]
    mvu_scan_items: list[dict]

    # 用户画像
    profile: dict | None
    profile_section: str
    profile_constraints: str  # 硬约束（避讳话题、沟通风格等 → 行为指令）
    profile_reminder: bool  # 无画像时提醒用户设置

    # 关系状态
    relationship: dict | None
    relationship_section: str
    relationship_level: int
    level_changed: bool
    new_milestone: str | None

    # Prompt 组装
    system_prompt: str
    messages: list[dict]
    persona_name: str | None
    # MVU 标记：persona.uses_mvu 透传，chat_service 据此触发 <UpdateVariable> 续写兜底
    persona_uses_mvu: bool
    # MVU 变量作用域 — dual-bucket {"local","global","names"}（详见 docs/adr/0007）
    # 由 node_build_prompt 加载/产出，node_post_process 成功时写回 DB（幂等）
    mvu_scope: dict

    # 当前 template 启用的 block 集合（key 为 dynamic_ref / static-block-id / mes_example 等）
    # 由 chat_service 预加载；各分析节点入口按此 gate，关功能 = 关 block
    # 关键 dynamic_ref 值：relationship / memories / profile / constraints / summary
    enabled_blocks: set[str]

    # 输出
    assistant_reply: str          # prompt 真相版（进 history）
    assistant_display: str        # 显示版（markdownOnly 美化后，前端渲染；ADR-0003 双管线）
    new_memories_count: int
    is_first_round: bool

    # post_process 写回（供 chat_service 拼装 SSE）
    assistant_message_id: str | None
    affinity_delta: int
    affinity_reason: str
    affinity_score: float | None

    # 错误
    error: str | None
