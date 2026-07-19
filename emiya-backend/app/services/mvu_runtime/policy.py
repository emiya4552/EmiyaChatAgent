# -*- coding: utf-8 -*-
"""MVU runtime policy for chat-time compatibility gates."""
from dataclasses import dataclass

# MVU 更新策略（ADR-0022）。inline = 默认；double_ai = 可选。未知值归一到 inline。
UPDATE_STRATEGY_INLINE = "inline"
UPDATE_STRATEGY_DOUBLE_AI = "double_ai"


def _normalize_update_strategy(value: str | None) -> str:
    return UPDATE_STRATEGY_DOUBLE_AI if str(value or "").strip().lower() == UPDATE_STRATEGY_DOUBLE_AI else UPDATE_STRATEGY_INLINE


@dataclass(frozen=True)
class MvuRuntimePolicy:
    """Centralized chat-time MVU behavior switches.

    `raw_uses_mvu` records the card import diagnosis. `active` is the effective
    runtime state after applying the user's account-level compatibility switch.
    `update_strategy` 选内联还是双 AI 更新（ADR-0022）。
    """

    raw_uses_mvu: bool
    compat_enabled: bool
    update_strategy: str = UPDATE_STRATEGY_INLINE

    @property
    def active(self) -> bool:
        return self.raw_uses_mvu and self.compat_enabled

    @property
    def run_ejs(self) -> bool:
        return self.active

    @property
    def use_variable_scope(self) -> bool:
        return self.active

    @property
    def divert_update_entries(self) -> bool:
        # ADR-0022：只有 double_ai 策略才把更新分流给回复后的独立 pass（并从 prompt 摘掉
        # [mvu_update] 条目、令主模型只写叙事）。inline 策略下更新留在正文，divert=False。
        return self.active and self.update_strategy == UPDATE_STRATEGY_DOUBLE_AI

    @property
    def strip_all_mvu_entries(self) -> bool:
        return self.raw_uses_mvu and not self.compat_enabled


def build_mvu_policy(
    *, persona_uses_mvu: bool, compat_enabled: bool, update_strategy: str | None = None
) -> MvuRuntimePolicy:
    return MvuRuntimePolicy(
        raw_uses_mvu=bool(persona_uses_mvu),
        compat_enabled=bool(compat_enabled),
        update_strategy=_normalize_update_strategy(update_strategy),
    )


def build_mvu_policy_for_user_persona(
    *, user, persona, update_strategy: str | None = None
) -> MvuRuntimePolicy:
    """Build policy from ORM-like user/persona rows.

    Missing user means "use the historical default": compatibility enabled.
    `update_strategy` 缺省时读全局 `settings.MVU_UPDATE_STRATEGY`（默认 inline）；调用方可传
    对话级覆盖。
    """
    if update_strategy is None:
        from app.config import settings

        update_strategy = getattr(settings, "MVU_UPDATE_STRATEGY", UPDATE_STRATEGY_INLINE)
    return build_mvu_policy(
        persona_uses_mvu=bool(persona and getattr(persona, "uses_mvu", False)),
        compat_enabled=bool(getattr(user, "mvu_compat_enabled", True)),
        update_strategy=update_strategy,
    )
