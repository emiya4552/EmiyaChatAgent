# -*- coding: utf-8 -*-
"""可见输出契约执行器（ADR-1e 深模块接口）。

聊天主流程只调用 `enforce_visible_output_contract`，拿回最终两个视图和诊断，
不需要知道 validate / reconstruct / 补写的内部编排。

当前实现覆盖执行链的前半段：初次校验 → 确定性修复 → 复校。槽位补写
（`slot_completed`）和整篇 rewrite（`rewritten`）在后续子步骤接入，接口和
诊断三元组（outcome / coverage / method）已按最终形态定义，接线时不再变形。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable
from typing import Any

from app.services.output_contracts.reconstructor import reconstruct
from app.services.output_contracts.rewrite import rewrite_document
from app.services.output_contracts.slotfill import (
    apply_slots,
    fillable_sections,
    request_slots,
)
from app.services.output_contracts.strict import run_strict, strict_available
from app.services.output_contracts.types import (
    ContractDiagnostics,
    VisibleOutputContract,
)
from app.services.output_contracts.validator import validate_visible_output


@dataclass
class EnforcementResult:
    """执行器返回值：两个最终视图 + 诊断三元组。"""

    content: str
    display_content: str
    outcome: str          # passed / failed / conflict / disabled
    coverage: str         # full / partial / none
    method: str           # initial / reconstructed / slot_completed / rewritten / strict_rendered
    requested_mode: str
    effective_mode: str
    diagnostics: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    # 本轮修复额外发起的 LLM 调用数（槽位补写 / rewrite）与总耗时（ADR-1f 诊断）。
    extra_calls: int = 0
    latency_ms: int = 0


def _issues(diag: ContractDiagnostics) -> list[dict[str, Any]]:
    return [
        *diag.missing,
        *diag.invalid_order,
        *diag.forbidden_hits,
        *diag.warnings,
    ]


def _diag_dict(
    initial: ContractDiagnostics,
    final: ContractDiagnostics,
    contract: VisibleOutputContract | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "initial": {"ok": initial.ok, "issues": _issues(initial)},
        "final": {"ok": final.ok, "issues": _issues(final)},
    }
    if contract is not None and contract.conflicts:
        data["conflicts"] = list(contract.conflicts)
    return data


def _coverage(contract: VisibleOutputContract) -> str:
    """契约被程序保证的覆盖率（静态，基于契约构成，不依赖本轮结果）。"""
    sections = contract.required_sections
    if not sections:
        # 纯 tail 契约的尾部块都可确定性保证。
        return "full" if contract.required_tail_blocks else "none"
    hard = [s for s in sections if s.repair_policy != "diagnose_only"]
    if not hard:
        return "none"
    if len(hard) == len(sections):
        return "full"
    return "partial"


async def enforce_visible_output_contract(
    *,
    content: str,
    display_content: str,
    contract: VisibleOutputContract,
    messages: list[dict] | None = None,
    policy: dict | None = None,
    tail_continuation: Callable[[str], Awaitable[str]] | None = None,
) -> EnforcementResult:
    """执行可见输出契约，返回最终两个视图与诊断。

    校验以 `display_content`（用户可见）为结构目标；确定性修复同时作用于两个
    视图，保证历史真相版与显示版结构一致。

    `policy.mode` 门控能力（ADR-1f/1g）：`off` 不校验不修复；`guide` 只校验不修复；
    `repair` 校验 + 确定性修复 + 缺失槽位补写；`strict` 在可用时走两阶段结构化槽位
    生成 + 确定性渲染（ADR-1g），不可用时按 `policy.strict_fallback` 降级并如实反映在
    `effective_mode`，不冒充 strict 成功。
    """
    policy = policy or {}
    # `mode` 是解析后的具体模式（auto 已在 policy.resolve_policy 分派）；`requested_mode`
    # 是报告用的原始标签（可能是 auto），缺省时回落到 mode。
    operative = policy.get("mode", "repair")
    requested_mode = policy.get("requested_mode", operative)
    # strict 可用性决定实际运行模式：可用→strict，否则→strict_fallback。
    if operative == "strict":
        available, _strict_reason = strict_available(contract, policy)
        run_mode = "strict" if available else policy.get("strict_fallback", "repair")
    else:
        run_mode = operative
    effective_mode = run_mode

    if not contract.active:
        return EnforcementResult(
            content=content,
            display_content=display_content,
            outcome="disabled",
            coverage="none",
            method="initial",
            requested_mode=requested_mode,
            effective_mode=effective_mode,
        )

    coverage = _coverage(contract)

    # off：不校验不修复，原样返回（ADR-1f）。
    if run_mode == "off":
        return EnforcementResult(
            content=content,
            display_content=display_content,
            outcome="disabled",
            coverage="none",
            method="initial",
            requested_mode=requested_mode,
            effective_mode="off",
        )

    initial = validate_visible_output(display_content, contract)

    # 契约冲突：≥2 个高权威 full_document 序列互斥，本轮只诊断不修复（ADR-1e）。
    if contract.has_conflict:
        return EnforcementResult(
            content=content,
            display_content=display_content,
            outcome="conflict",
            coverage=coverage,
            method="initial",
            requested_mode=requested_mode,
            effective_mode=effective_mode,
            diagnostics=_diag_dict(initial, initial, contract),
        )

    # strict：两阶段结构化槽位生成 + 确定性渲染（ADR-1g）。即便草稿已"看似"合格，也
    # 由 renderer 重新生成结构外壳以硬保证，narrative 固定为草稿正文。
    if run_mode == "strict":
        strict = await run_strict(
            display_content,
            contract,
            temperature=float(policy.get("slot_temperature") or 0.2),
        )
        return EnforcementResult(
            content=strict.content,
            display_content=strict.content,
            outcome="passed" if strict.ok else "failed",
            coverage=coverage,
            method=strict.method,
            requested_mode=requested_mode,
            effective_mode="strict",
            diagnostics=_diag_dict(initial, strict.diagnostics, contract),
            actions=[{"action": "strict_render", "stages": strict.stages}],
            extra_calls=strict.extra_calls,
            latency_ms=strict.latency_ms,
        )

    if initial.ok:
        return EnforcementResult(
            content=content,
            display_content=display_content,
            outcome="passed",
            coverage=coverage,
            method="initial",
            requested_mode=requested_mode,
            effective_mode=effective_mode,
            diagnostics=_diag_dict(initial, initial, contract),
        )

    # guide：校验暴露问题，但不做任何确定性修复（ADR-1f）。
    if run_mode == "guide":
        return EnforcementResult(
            content=content,
            display_content=display_content,
            outcome="failed",
            coverage=coverage,
            method="initial",
            requested_mode=requested_mode,
            effective_mode=effective_mode,
            diagnostics=_diag_dict(initial, initial, contract),
        )

    # repair：① 流式尾部续写 → ② 确定性修复 → ③ 缺失槽位补写 → ④ 整篇 rewrite。
    # 三步同时作用于 content 与 display_content 两个视图，逐步复校。
    started = time.monotonic()
    extra_calls = 0
    new_content = content
    new_display = display_content
    actions: list[dict[str, Any]] = []
    method = "initial"

    # 流式层只提供 continuation 回调；缺失判定、复校和诊断归执行器统一负责。
    if tail_continuation is not None and contract.required_tail_blocks and initial.missing:
        continued = await tail_continuation(new_display)
        if continued != new_display:
            new_display = continued
            new_content = continued
            actions.append({"action": "tail_continuation"})
            extra_calls += 1
            method = "continuation"

    new_display, disp_actions = reconstruct(new_display, contract)
    new_content, _ = reconstruct(new_content, contract)
    actions.extend(disp_actions)
    if disp_actions and method == "initial":
        method = "reconstructed"

    final = validate_visible_output(new_display, contract)

    # ② 缺失槽位补写（ADR-1e §5）：一次结构化调用补缺失/空槽，renderer 拼入再复校。
    if not final.ok:
        to_fill = fillable_sections(contract, final.missing)
        if to_fill:
            temperature = float((policy.get("slot_temperature") or 0.2))
            extra_calls += 1
            slots = await request_slots(to_fill, new_display, temperature=temperature)
            if slots:
                new_display, fill_actions = apply_slots(new_display, contract, slots)
                new_content, _ = apply_slots(new_content, contract, slots)
                actions.extend(fill_actions)
                method = "slot_completed"
                final = validate_visible_output(new_display, contract)

    # ③ 整篇 rewrite 兜底（ADR-1e §6）：仅显式授权时一次低温重写。rewrite 后仍不合格
    # 则保留 rewrite 前最佳版本，不冒充成功（只记动作）。
    if not final.ok and policy.get("allow_full_rewrite"):
        extra_calls += 1
        rewritten = await rewrite_document(new_display, contract)
        if rewritten:
            rw_display, _ = reconstruct(rewritten, contract)
            rw_diag = validate_visible_output(rw_display, contract)
            if rw_diag.ok:
                new_display = rw_display
                new_content = rw_display
                final = rw_diag
                method = "rewritten"
                actions.append({"action": "full_rewrite", "result": "passed"})
            else:
                actions.append({"action": "full_rewrite", "result": "still_invalid"})

    outcome = "passed" if final.ok else "failed"

    return EnforcementResult(
        content=new_content,
        display_content=new_display,
        outcome=outcome,
        coverage=coverage,
        method=method,
        requested_mode=requested_mode,
        effective_mode=effective_mode,
        diagnostics=_diag_dict(initial, final, contract),
        actions=actions,
        extra_calls=extra_calls,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
