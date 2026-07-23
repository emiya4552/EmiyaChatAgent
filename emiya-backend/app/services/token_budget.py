# -*- coding: utf-8 -*-
"""Centralized token budget calculations for chat prompt assembly."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.config import settings
from app.utils.token_counter import count_tokens


REPLY_LENGTH_MAX_TOKENS = {
    "short": 150,
    "medium": 500,
    "long": 2000,
}
DEFAULT_REPLY_MAX_TOKENS = 600


@dataclass(frozen=True)
class PromptBudgetPlan:
    max_context: int
    reserved_output: int
    safety_margin: int
    prompt_prefix_tokens: int
    history_available: int
    history_cap: int
    history_budget: int
    reply_length: str

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _non_negative_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def count_text_tokens(text: str | None) -> int:
    return count_tokens(text or "")


def count_message_tokens(messages: list[dict]) -> int:
    """Estimate chat message tokens, including a small per-message wrapper cost."""
    return sum(count_text_tokens(m.get("content") or "") + 4 for m in messages)


def resolve_max_context(chat_config: dict | None) -> int:
    config = chat_config or {}
    return _positive_int(config.get("openai_max_context"), settings.MAX_CONTEXT_TOKENS)


def resolve_reply_max_tokens(chat_config: dict | None, reply_length: str | None) -> int:
    """Resolve output token budget.

    An explicit `openai_max_tokens` overrides reply length. When it is absent,
    the UI reply-length selector controls the generated response cap.
    """
    config = chat_config or {}
    explicit = config.get("openai_max_tokens")
    if explicit not in (None, ""):
        return _positive_int(explicit, DEFAULT_REPLY_MAX_TOKENS)
    return REPLY_LENGTH_MAX_TOKENS.get(reply_length or "medium", DEFAULT_REPLY_MAX_TOKENS)


def resolve_safety_margin(chat_config: dict | None) -> int:
    config = chat_config or {}
    return _non_negative_int(
        config.get("token_budget_safety_margin"),
        settings.TOKEN_BUDGET_SAFETY_MARGIN,
    )


def resolve_history_budget_cap(chat_config: dict | None) -> int:
    config = chat_config or {}
    return _non_negative_int(config.get("history_budget_cap"), 0)


def resolve_worldbook_budget(chat_config: dict | None) -> dict[str, int | bool]:
    config = chat_config or {}
    max_context = resolve_max_context(config)
    pct = _non_negative_int(config.get("worldbook_budget_pct"), settings.WORLDBOOK_BUDGET_PCT)
    pct = max(0, min(100, pct))
    cap = _non_negative_int(config.get("worldbook_budget_cap"), settings.WORLDBOOK_BUDGET_CAP)

    budget = max(0, round(max_context * pct / 100))
    if cap > 0 and budget > cap:
        budget = cap

    return {
        "max_context": max_context,
        "pct": pct,
        "cap": cap,
        "budget": budget,
        "overflow_alert": bool(config.get(
            "worldbook_overflow_alert",
            settings.WORLDBOOK_OVERFLOW_ALERT,
        )),
    }


def build_prompt_budget_plan(
    *,
    prefix_messages: list[dict],
    chat_config: dict | None,
    reply_length: str | None,
    overhead_tokens: int = 0,
) -> PromptBudgetPlan:
    """规划历史预算。

    `overhead_tokens` 计入那些「不在 prefix_messages 里、但裁剪后才注入」的固定
    system 开销（当前用于预设：见 nodes.node_build_prompt）。不纳入的话
    history_available 会系统性高估、最终 prompt 超 max_context。
    """
    max_context = resolve_max_context(chat_config)
    reserved_output = resolve_reply_max_tokens(chat_config, reply_length)
    safety_margin = resolve_safety_margin(chat_config)
    history_cap = resolve_history_budget_cap(chat_config)
    prefix_tokens = count_message_tokens(prefix_messages) + max(0, overhead_tokens)
    history_available = max(0, max_context - reserved_output - safety_margin - prefix_tokens)
    history_budget = min(history_available, history_cap) if history_cap > 0 else history_available
    return PromptBudgetPlan(
        max_context=max_context,
        reserved_output=reserved_output,
        safety_margin=safety_margin,
        prompt_prefix_tokens=prefix_tokens,
        history_available=history_available,
        history_cap=history_cap,
        history_budget=history_budget,
        reply_length=reply_length or "medium",
    )


def build_token_budget_report(
    *,
    plan: PromptBudgetPlan,
    final_prompt_tokens: int,
    history_tokens: int,
    history_candidate_tokens: int,
    history_kept_messages: int,
    history_candidate_messages: int,
    worldbook_used_tokens: int,
    worldbook_budget: dict[str, int | bool],
) -> dict[str, Any]:
    dropped_tokens = max(0, history_candidate_tokens - history_tokens)
    projected_total = final_prompt_tokens + plan.reserved_output
    remaining_context = max(0, plan.max_context - projected_total)
    # 前置称重（预设 overhead）后仍越界，多因 system 前缀本身超预算（预设/世界书/persona
    # 过大，历史已裁至下限仍不足），或 squash/正则/depth 溢出的残差。供调用方兜底告警。
    budget_overflow_tokens = max(0, projected_total - plan.max_context)
    return {
        **plan.to_dict(),
        "history_tokens": history_tokens,
        "history_candidate_tokens": history_candidate_tokens,
        "history_dropped_tokens": dropped_tokens,
        "history_kept_messages": history_kept_messages,
        "history_candidate_messages": history_candidate_messages,
        "final_prompt_tokens": final_prompt_tokens,
        "remaining_context": remaining_context,
        "over_budget": budget_overflow_tokens > 0,
        "budget_overflow_tokens": budget_overflow_tokens,
        "worldbook": {
            "budget": int(worldbook_budget.get("budget") or 0),
            "used": worldbook_used_tokens,
            "remaining": max(0, int(worldbook_budget.get("budget") or 0) - worldbook_used_tokens),
            "pct": int(worldbook_budget.get("pct") or 0),
            "cap": int(worldbook_budget.get("cap") or 0),
        },
    }
