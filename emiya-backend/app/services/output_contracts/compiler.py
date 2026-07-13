# -*- coding: utf-8 -*-
"""编译运行时契约（ADR-1e）。

把 extractor 产出的基础契约编译成受控契约：为每个 section 填充 `kind`、
`span_strategy`、`content_policy`、`repair_policy`。识别期（detector）已给出的
`kind` 优先；缺失时用确定性 `name → kind` 映射后备，映射不出的 section 归
`narrative` 并走 per-section 降级（`repair_policy=diagnose_only`）。

compiler 不调用 LLM，只做确定性映射与编译，保持“运行时不做模板发现”原则。
多候选权威性选主与冲突检测将在后续子步骤接入，当前沿用 extractor 的合并结果。
"""
from __future__ import annotations

import dataclasses

from app.services.output_contracts.extractor import (
    build_visible_output_contract,
    iter_contract_candidates,
)
from app.services.output_contracts.types import (
    SectionContract,
    SectionKind,
    SpanStrategy,
    VisibleOutputContract,
)

# 过渡期 name → kind 确定性映射（与 ADR-1d validator 的按 name 硬编码对齐）。
_NAME_TO_KIND = {
    "chapter": SectionKind.MARKDOWN_HEADING,
    "body": SectionKind.NARRATIVE,
    "options": SectionKind.CHOICE_SET,
    "backend_log": SectionKind.DETAILS_SUMMARY,
    "hidden_plot": SectionKind.DETAILS_SUMMARY,
}

# kind → 默认 span_strategy（能否安全提取/移动）。
_KIND_TO_SPAN = {
    SectionKind.MARKDOWN_HEADING: SpanStrategy.UNTIL_NEXT_ANCHOR,
    SectionKind.NARRATIVE: SpanStrategy.NONE,
    SectionKind.CHOICE_SET: SpanStrategy.FIXED_LINE_SET,
    SectionKind.DETAILS_SUMMARY: SpanStrategy.BALANCED_TAG,
    SectionKind.HTML_BLOCK: SpanStrategy.BALANCED_TAG,
    SectionKind.LITERAL_BLOCK: SpanStrategy.EXPLICIT_DELIMITERS,
}

# kind → (content_policy, min_items)
_KIND_CONTENT_POLICY = {
    SectionKind.CHOICE_SET: ("non_empty", 4),
    SectionKind.DETAILS_SUMMARY: ("non_empty", 0),
    SectionKind.MARKDOWN_HEADING: ("non_empty", 0),
    SectionKind.NARRATIVE: ("non_empty", 0),
    SectionKind.HTML_BLOCK: ("non_empty", 0),
    SectionKind.LITERAL_BLOCK: ("non_empty", 0),
}

# kind → repair_policy
_KIND_REPAIR_POLICY = {
    SectionKind.DETAILS_SUMMARY: "deterministic",   # 可闭合 / 外壳修复
    SectionKind.CHOICE_SET: "fill_slot",            # 缺内容靠槽位补写
    SectionKind.HTML_BLOCK: "deterministic",
    SectionKind.LITERAL_BLOCK: "deterministic",
    SectionKind.MARKDOWN_HEADING: "diagnose_only",
    SectionKind.NARRATIVE: "diagnose_only",
}


def _resolve_kind(section: SectionContract) -> str:
    # 识别期已给出非默认 kind 时优先采用。
    if section.kind and section.kind != SectionKind.NARRATIVE:
        return section.kind
    mapped = _NAME_TO_KIND.get(section.name)
    if mapped:
        return mapped
    # body 本就是叙事；其余映射不出的自定义区块也归 narrative → diagnose_only 降级。
    return SectionKind.NARRATIVE


def _compile_section(section: SectionContract) -> SectionContract:
    kind = _resolve_kind(section)
    span = _KIND_TO_SPAN.get(kind, SpanStrategy.NONE)
    content_policy, min_items = _KIND_CONTENT_POLICY.get(kind, ("allow_empty", 0))
    repair_policy = _KIND_REPAIR_POLICY.get(kind, "diagnose_only")
    return dataclasses.replace(
        section,
        kind=kind,
        span_strategy=span,
        content_policy=content_policy,
        min_items=min_items,
        repair_policy=repair_policy,
    )


# ── 多候选权威性选主与冲突检测（ADR-1e §多候选合并与冲突）────────────


def _authority_key(candidate: dict) -> tuple:
    """主 full_document 契约的权威性排序键（越大越权威）。

    `confidence` 只表示识别确定性，不代表规则权威性，仅作同级 tie-break。
    优先级：reviewed/manual > trigger=manual > 自动 LLM > 启发式 > entry order > confidence。
    """
    oc = candidate.get("oc") or {}
    source = str(oc.get("source") or "")
    trigger = str(oc.get("trigger") or "")
    reviewed = bool(oc.get("reviewed"))
    if reviewed or source == "manual":
        level = 4
    elif trigger == "manual":
        level = 3
    elif source == "llm":
        level = 2
    elif source == "heuristic":
        level = 1
    else:
        level = 0
    confidence = float(oc.get("confidence") or 0.0)
    return (level, candidate.get("order", 100), confidence)


def _seq_names(candidate: dict) -> list[str]:
    return [s.name for s in sorted(candidate["sections"], key=lambda s: s.order)]


def _order_contradiction(a_names: list[str], b_names: list[str]) -> bool:
    """两条 section 序列在共有 section 上是否存在相对顺序矛盾。"""
    a_pos = {n: i for i, n in enumerate(a_names)}
    b_pos = {n: i for i, n in enumerate(b_names)}
    common = [n for n in a_names if n in b_pos]
    for i in range(len(common)):
        for j in range(i + 1, len(common)):
            x, y = common[i], common[j]
            if (a_pos[x] - a_pos[y]) * (b_pos[x] - b_pos[y]) < 0:
                return True
    return False


def _detect_fd_conflicts(fd_candidates: list[dict], main: dict) -> list[dict]:
    """主契约与其它 full_document 候选序列互斥时记冲突（只诊断，不猜测拼接）。"""
    conflicts: list[dict] = []
    main_names = _seq_names(main)
    for cand in fd_candidates:
        if cand is main:
            continue
        if _order_contradiction(main_names, _seq_names(cand)):
            conflicts.append({
                "code": "contract_conflict",
                "main": main["source"].comment if main.get("source") else "",
                "other": cand["source"].comment if cand.get("source") else "",
            })
    return conflicts


def _merge_sections(
    main_sections: list[SectionContract],
    inline_sections: list[SectionContract],
) -> list[SectionContract]:
    """主契约 sections 决定整篇顺序；inline 候选按 name 去重并入。"""
    seen = {s.name for s in main_sections}
    merged = list(main_sections)
    for s in inline_sections:
        if s.name not in seen:
            seen.add(s.name)
            merged.append(s)
    return merged


def compile_contract(
    wi_activated: list[dict] | None,
    chat_config: dict | None = None,
) -> VisibleOutputContract:
    """从激活条目编译受控运行时契约。

    补充受控 `kind` / `span_strategy` / `content_policy` / `repair_policy`；当存在
    ≥2 个 full_document 候选时，按权威性选主、检测序列冲突，取主契约 sections 决定
    整篇顺序（inline 候选并入），而不是把多份 full_document sections 直接堆叠。
    compiler 不调用 LLM，只做确定性映射与编译。
    """
    base = build_visible_output_contract(wi_activated, chat_config)
    if not base.required_sections:
        return base

    candidates = iter_contract_candidates(wi_activated)
    fd_candidates = [c for c in candidates if c["kind"] == "full_document"]

    sections = base.required_sections
    conflicts: list[dict] = []
    if len(fd_candidates) >= 2:
        main = max(fd_candidates, key=_authority_key)
        conflicts = _detect_fd_conflicts(fd_candidates, main)
        inline_sections = [
            s for c in candidates if c["kind"] == "inline" for s in c["sections"]
        ]
        sections = _merge_sections(main["sections"], inline_sections)

    compiled = [_compile_section(s) for s in sections]
    return dataclasses.replace(base, required_sections=compiled, conflicts=conflicts)
