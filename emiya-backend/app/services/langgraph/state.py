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
    # MVU 更新通道：double_ai 策略产出的 ops（chat_service 填），以及 post_process 的校验诊断
    # 与实际生效通道（供 mvu_runtime_view）。inline 策略更新走正文 <UpdateVariable> 内联解析。
    mvu_double_ai_ops: list[dict]
    mvu_update_diag: dict
    mvu_update_channel: str
    # ADR-0022：本轮 MVU 更新是否走 double_ai（True）/ inline（False）；chat_service 据此
    # 决定跑不跑 run_update_pass。node_build_prompt 写入。
    mvu_divert_update: bool

    # 用户画像
    profile: dict | None
    profile_section: str

    # 关系状态
    relationship: dict | None
    relationship_section: str
    relationship_level: int
    level_changed: bool
    new_milestone: str | None

    # 对话历史窗口（由 node_prepare_history 产出）
    recent_messages: list[dict]
    summary_context: str
    dialogue_message_count: int

    # Prompt 组装
    system_prompt: str
    messages: list[dict]
    token_budget_report: dict | None
    persona_name: str | None
    # MVU 标记：**有效** uses_mvu = persona.uses_mvu AND user.mvu_compat_enabled
    # （node_build_prompt 写入有效值，下游所有 MVU 门控读它 → 自动尊重兼容开关；CARD-0002）
    persona_uses_mvu: bool
    # MVU 兼容总开关（账户级，chat_service 从 User 载入；CARD-0002）
    # off 时 node_build_prompt 剔除 MVU 标签条目 + 跳过 EJS，并把 persona_uses_mvu 压成 False
    mvu_compat_enabled: bool
    # 可见输出契约聊天期执行配置（ADR-1f）：{account_defaults, overrides}。
    # chat_service 从 User + conversation.chat_config 载入，node_post_process 用它
    # 连同已编译契约 resolve_policy 出 executor 的运行策略。
    output_contract_config: dict | None
    # 账户级配置桶（配置系统 ADR-4）：User.account_config JSONB（记忆系统调参 + token 预算
    # 账户默认）。chat_service 从 User 载入；node_retrieve_memories / node_prepare_history /
    # node_post_process / node_build_prompt 经 config_registry 解析器读它（缺省回退全局）。
    account_config: dict | None
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
