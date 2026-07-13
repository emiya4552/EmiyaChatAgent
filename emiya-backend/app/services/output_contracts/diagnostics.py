# -*- coding: utf-8 -*-
"""把可见输出契约诊断压缩成 SSE 稳定结构（ADR-1f）。

该结构取代 ADR-1c 的扁平诊断：三个维度分开——`outcome`（可检查规则是否满足）、
`coverage`（契约被程序保证的覆盖率）、`method`（达成手段）——并明确区分
`guaranteed_rules`（程序保证的硬结构）与 `soft_rules`（只能 Prompt 引导的软内容）。
前端只依赖本结构，不解析后端内部 dataclass。
"""
from __future__ import annotations

from typing import Any

from app.services.output_contracts.types import (
    ContractDiagnostics,
    SectionContract,
    VisibleOutputContract,
)

_SECTION_LABELS = {
    "chapter": "章节标题",
    "body": "正文",
    "options": "选项区块",
    "backend_log": "后台日志",
    "hidden_plot": "隐藏剧情",
}


def _section_label(section: SectionContract) -> str:
    return _SECTION_LABELS.get(section.name, section.marker or section.name)


def _diag_side(diag: ContractDiagnostics | None) -> dict[str, Any]:
    if diag is None:
        return {"ok": True, "issues": []}
    issues = [*diag.missing, *diag.invalid_order, *diag.forbidden_hits, *diag.warnings]
    return {"ok": bool(diag.ok), "issues": issues}


def split_rules(contract: VisibleOutputContract) -> tuple[list[str], list[str]]:
    """把契约规则分成程序保证的硬结构与只能 Prompt 引导的软内容（ADR-1e/1f）。"""
    guaranteed: list[str] = []
    soft: list[str] = []
    for section in contract.required_sections:
        label = _section_label(section)
        if section.repair_policy == "diagnose_only":
            soft.append(f"{label}（仅 Prompt 引导）")
        else:
            guaranteed.append(label)
    for block in contract.required_tail_blocks:
        if block.marker:
            guaranteed.append(f"尾部块 {block.marker}")
    for rule in contract.forbidden_terms:
        if rule.term:
            guaranteed.append(f"禁词不出现于{rule.scope}：{rule.term}")
    return guaranteed, soft


def build_contract_sse(
    *,
    contract: VisibleOutputContract,
    contract_mode: str,
    requested_mode: str,
    effective_mode: str,
    outcome: str,
    coverage: str,
    method: str,
    initial: ContractDiagnostics | None,
    final: ContractDiagnostics | None,
    actions: list[dict[str, Any]] | None = None,
    latency_ms: int = 0,
    extra_calls: int = 0,
    token_usage: int = 0,
) -> dict[str, Any]:
    """产出 `message_done.output_contract` 稳定结构。"""
    guaranteed, soft = split_rules(contract)
    return {
        "contract_mode": contract_mode,
        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        "outcome": outcome,
        "coverage": coverage,
        "method": method,
        "initial": _diag_side(initial),
        "actions": list(actions or []),
        "final": _diag_side(final),
        "guaranteed_rules": guaranteed,
        "soft_rules": soft,
        "conflicts": list(contract.conflicts),
        "latency_ms": int(latency_ms or 0),
        "extra_calls": int(extra_calls or 0),
        "token_usage": int(token_usage or 0),
    }


def diagnostics_to_dict(diag: ContractDiagnostics) -> dict[str, Any]:
    """兼容保留：把单侧诊断压成 issues 列表，供内部日志 / 调试使用。

    正式 SSE 一律走 `build_contract_sse`；本函数不再作为 message_done 的外部协议。
    """
    return {
        "mode": diag.mode,
        "ok": bool(diag.ok),
        "required": int(diag.required or 0),
        "issues": [
            *diag.missing,
            *diag.invalid_order,
            *diag.forbidden_hits,
            *diag.warnings,
        ],
    }
