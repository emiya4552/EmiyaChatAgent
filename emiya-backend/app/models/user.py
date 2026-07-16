# -*- coding: utf-8 -*-
"""用户 ORM 模型。"""
import uuid

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """用户表。"""

    __tablename__ = "users"

    # 用户 ID，使用 UUID 主键
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 邮箱，唯一不可重复
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # 昵称
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    # bcrypt 密码哈希
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # 头像 URL，可选
    avatar_url: Mapped[str | None] = mapped_column(String(2048))

    # === MVU 全局变量桶（详见 docs/adr/0007） ===
    # 跨该用户所有对话与角色共享；{{setglobalvar}}/{{getglobalvar}} 读写
    global_variables: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    # === 用户级 CSS 主题（详见 docs/adr/0008） ===
    # 用户全局样式包，对该用户所有对话生效；Persona.css_theme 之后再注入
    css_theme: Mapped[str | None] = mapped_column(Text, nullable=True)

    # === 情感分析默认偏好（详见 docs/adr/0020） ===
    # 仅决定**新建对话**时 Conversation.analyze_emotion 的初始值（创建时快照）。
    # 默认 False → 感知系统 opt-in。改它不追溯已存在的对话、不覆盖手动选择。
    default_analyze_emotion: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )

    # === MVU 兼容总开关（详见 docs/card/0002） ===
    # 账户级、仅作用于**聊天时**。关闭后把 MVU 卡当普通卡：关整条 MVU 状态机器 +
    # 剔除 MVU 标签世界书条目 + 跳过 EJS + 隐藏卡 UI。不影响导入/检测/导出。默认开。
    mvu_compat_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )

    # === 输出契约 LLM 自动识别偏好（详见 docs/feat-adr/adr1-1） ===
    # 仅作用于世界书导入/编辑期。关闭时仍会运行本地启发式识别；用户也可在单条
    # entry 上手动触发 AI 识别。limit 控制每次批量导入最多送检多少条候选 entry。
    output_contract_llm_detection_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    output_contract_llm_detection_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="30", default=30
    )

    # === 可见输出契约聊天期执行默认（详见 docs/feat-adr/adr1f） ===
    # 账户默认执行模式，新对话继承；对话 chat_config 可覆盖。默认 auto：
    # tail→repair、full_document→guide、strict 永不自动开启。
    output_contract_default_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="auto", default="auto"
    )
    # 是否允许最后兜底的整篇 rewrite（独立许可，不因选 repair 自动开）。默认关。
    output_contract_allow_full_rewrite: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    # strict 不可用 / 预算不足时的降级模式：repair / guide / off。默认 repair。
    output_contract_strict_fallback: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="repair", default="repair"
    )
    # 严格声明模式账户默认（ADR-2c / 配置系统 ADR）：on 时聊天只**执行**已确认 / 声明
    # 的契约，未确认草稿降为仅 Prompt 引导。对话 chat_config 可覆盖。
    # **可空**是有意的：NULL=该账户未表态 → 继承全局 settings.OUTPUT_CONTRACT_REQUIRE_CONFIRMED；
    # 唯有此项同时存在全局 env 层，故不能像其余三个执行默认那样用非空列（否则全局层被永久遮蔽）。
    output_contract_require_confirmed: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=None
    )

    # === 账户级配置桶（配置系统 ADR-4）===
    # 单个 JSONB 承载「用户可见的账户级偏好」：记忆系统（总开关/频率/检索旋钮）+
    # token 预算账户默认。仿 chat_config，键/默认/钳制/白名单由 config_registry 统一管，
    # 读取时 account_config.get(key) 缺省回退全局 settings。空 {} = 全部继承全局默认。
    account_config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
