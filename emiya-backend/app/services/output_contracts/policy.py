# -*- coding: utf-8 -*-
"""可见输出契约聊天期执行策略解析（ADR-1f）。

把"账户默认"与"对话覆盖"合并成 executor 消费的 policy dict，并解析 `auto` 的按类型
分派。导入/编辑期识别设置（`output_contract_llm_detection_*`）与本模块无关，两类配置
不得混淆：识别决定 entry 是否有契约，执行模式决定聊天时如何处理已识别契约。
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.output_contracts.types import VisibleOutputContract

# 聊天期执行模式全集。
EXECUTION_MODES = {"off", "auto", "guide", "repair", "strict"}
STRICT_FALLBACKS = {"repair", "guide", "off"}

DEFAULT_MODE = "auto"
DEFAULT_STRICT_FALLBACK = "repair"

# 对话覆盖里表示"继承账户默认"的取值。
_INHERIT = {None, "", "inherit"}


def _pick(override: Any, account: Any, fallback: Any) -> Any:
    if override not in _INHERIT:
        return override
    if account not in _INHERIT and account is not None:
        return account
    return fallback


def resolve_require_confirmed(
    *,
    account_defaults: dict | None = None,
    conversation_overrides: dict | None = None,
) -> bool:
    """解析「严格声明模式」开关（ADR-2c）：对话覆盖 > 账户默认 > 全局 settings 默认。

    只影响契约的**执行**（未确认草稿是否强制），不影响 Prompt 锚定。与 resolve_policy
    的执行模式（off/guide/repair/strict）正交——一个决定“哪些契约参与执行”，一个决定
    “参与执行的契约处理到什么程度”。
    """
    conv = conversation_overrides or {}
    v = conv.get("output_contract_require_confirmed")
    if v is not None:
        return bool(v)
    acc = (account_defaults or {}).get("output_contract_require_confirmed")
    if acc is not None:
        return bool(acc)
    return bool(settings.OUTPUT_CONTRACT_REQUIRE_CONFIRMED)


def _dispatch_auto(contract: VisibleOutputContract) -> str:
    """`auto` 按契约类型分派：full_document→guide、tail→repair。

    strict 永不由 auto 触发；full_document 默认只锚定 + 诊断，不自动改回复，避免旧
    对话行为突变（ADR-1f）。
    """
    if contract.required_sections:
        return "guide"
    return "repair"


def resolve_policy(
    contract: VisibleOutputContract,
    *,
    account_defaults: dict | None = None,
    conversation_overrides: dict | None = None,
) -> dict[str, Any]:
    """解析成 executor policy：{mode, requested_mode, allow_full_rewrite, strict_fallback}。

    - `mode`：已解析的具体运行模式（off/guide/repair/strict），auto 已按类型分派。
    - `requested_mode`：用户/账户请求的原始标签（可能是 auto），仅用于诊断展示。
    - `allow_full_rewrite`：是否允许整篇 rewrite 兜底（独立许可）。
    - `strict_fallback`：strict 不可用时的降级模式。
    """
    acc = account_defaults or {}
    conv = conversation_overrides or {}

    requested = _pick(
        conv.get("output_contract_mode"),
        acc.get("output_contract_default_mode"),
        DEFAULT_MODE,
    )
    if requested not in EXECUTION_MODES:
        requested = DEFAULT_MODE

    allow_rewrite = _pick(
        conv.get("output_contract_allow_full_rewrite"),
        acc.get("output_contract_allow_full_rewrite"),
        False,
    )
    strict_fallback = _pick(
        conv.get("output_contract_strict_fallback"),
        acc.get("output_contract_strict_fallback"),
        DEFAULT_STRICT_FALLBACK,
    )
    if strict_fallback not in STRICT_FALLBACKS:
        strict_fallback = DEFAULT_STRICT_FALLBACK

    mode = _dispatch_auto(contract) if requested == "auto" else requested

    return {
        "mode": mode,
        "requested_mode": requested,
        "allow_full_rewrite": bool(allow_rewrite),
        "strict_fallback": strict_fallback,
    }
