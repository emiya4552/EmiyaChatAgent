# -*- coding: utf-8 -*-
"""可见输出契约校验。"""
from __future__ import annotations

import re
from typing import Any, Callable

from app.services.output_contracts.types import (
    ContractDiagnostics,
    OutputContractMode,
    SectionContract,
    TailBlockContract,
    VisibleOutputContract,
)


_DETAILS_OPEN_RE = re.compile(r"<details\b", re.IGNORECASE)
_DETAILS_CLOSE_RE = re.compile(r"</details\s*>", re.IGNORECASE)
_DETAILS_BLOCK_RE = re.compile(r"<details\b.*?</details\s*>", re.IGNORECASE | re.DOTALL)
_SUMMARY_RE = re.compile(r"<summary\b[^>]*>(.*?)</summary>", re.IGNORECASE | re.DOTALL)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+\S")
_OPTION_RES = {
    letter: re.compile(r">\s*\*\*\s*%s\s*[.．]\s*\*\*" % letter)
    for letter in ("A", "B", "C", "D")
}

# 第一批只对这些区块每轮出现一次做硬约束（ADR-1d）。
_ONCE_SECTIONS = {"backend_log", "hidden_plot"}


def _strip_tags(text: str) -> str:
    return _TAG_STRIP_RE.sub("", text or "").strip()


# ── append_tail ────────────────────────────────────────────


def _missing_tail_reason(reply: str, block: TailBlockContract) -> dict[str, Any] | None:
    marker = block.marker
    marker_idx = reply.find(marker) if marker else -1
    if marker_idx == -1:
        return {
            "type": "tail_block",
            "marker": marker,
            "source": block.source.comment if block.source else "",
            "reason": "missing_marker",
        }

    # 该块原模板包含 <details> 时，只出现 summary/marker 还不够；
    # prefix continuation 失败可能留下半截结构，必须看到闭合标签才算通过。
    if _DETAILS_OPEN_RE.search(block.content or ""):
        tail_fragment = reply[marker_idx:]
        if not _DETAILS_CLOSE_RE.search(tail_fragment):
            return {
                "type": "tail_block",
                "marker": marker,
                "source": block.source.comment if block.source else "",
                "reason": "unclosed_details",
            }

    return None


def _validate_append_tail(reply: str, contract: VisibleOutputContract) -> ContractDiagnostics:
    missing: list[dict[str, Any]] = []
    for block in contract.required_tail_blocks:
        reason = _missing_tail_reason(reply, block)
        if reason is not None:
            missing.append(reason)

    return ContractDiagnostics(
        mode=contract.mode,
        ok=not missing,
        required=len(contract.required_tail_blocks),
        missing=missing,
    )


# ── full_document ─────────────────────────────────────────


def _locate_chapter(reply: str) -> tuple[int | None, int]:
    matches = list(_HEADING_RE.finditer(reply))
    if not matches:
        return None, 0
    return matches[0].start(), len(matches)


def _locate_options(reply: str) -> tuple[int | None, int]:
    positions = [m.start() for letter, rx in _OPTION_RES.items() if (m := rx.search(reply))]
    # 缺少 A/B/C/D 任一项即视为整个选项区块缺失。
    if len(positions) < len(_OPTION_RES):
        return None, 0
    return min(positions), 1


def _locate_summary(reply: str, keyword: str) -> tuple[int | None, int]:
    positions = [
        m.start()
        for m in _SUMMARY_RE.finditer(reply)
        if keyword in _strip_tags(m.group(1))
    ]
    if not positions:
        return None, 0
    return positions[0], len(positions)


# 可硬校验的整篇区块 detector；未列出的区块（如 body）视为软约束，跳过存在性校验。
_SECTION_DETECTORS: dict[str, Callable[[str], "tuple[int | None, int]"]] = {
    "chapter": _locate_chapter,
    "options": _locate_options,
    "backend_log": lambda reply: _locate_summary(reply, "后台日志"),
    "hidden_plot": lambda reply: _locate_summary(reply, "隐藏剧情"),
}


def _visible_text(reply: str) -> str:
    """玩家可见正文：剥掉所有 <details> 折叠块。"""
    return _DETAILS_BLOCK_RE.sub("", reply)


def _block_text(reply: str, keyword: str) -> str:
    """summary 命中 keyword 的折叠块正文拼接。"""
    texts: list[str] = []
    for m in _DETAILS_BLOCK_RE.finditer(reply):
        block = m.group(0)
        summary = _SUMMARY_RE.search(block)
        if summary and keyword in _strip_tags(summary.group(1)):
            texts.append(block)
    return "\n".join(texts)


def _scope_text(reply: str, scope: str) -> str:
    if scope in ("visible", "body", ""):
        return _visible_text(reply)
    if scope == "backend_log":
        return _block_text(reply, "后台日志")
    if scope == "hidden_plot":
        return _block_text(reply, "隐藏剧情")
    return reply


def _validate_full_document(reply: str, contract: VisibleOutputContract) -> ContractDiagnostics:
    missing: list[dict[str, Any]] = []
    invalid_order: list[dict[str, Any]] = []
    forbidden_hits: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    required = [s for s in contract.required_sections if s.required]

    # 只对有 detector 的硬校验区块定位；软区块（body 等）跳过。
    located: dict[str, int] = {}
    checkable: list[SectionContract] = []
    for section in required:
        detector = _SECTION_DETECTORS.get(section.name)
        if detector is None:
            continue
        checkable.append(section)
        pos, count = detector(reply)
        if pos is None:
            missing.append({"section": section.name})
            continue
        located[section.name] = pos
        if section.name in _ONCE_SECTIONS and count > 1:
            warnings.append({"code": "duplicate_section", "section": section.name})

    # 顺序：按契约 order 排列已定位区块，相邻逆序即报错。
    ordered = sorted(
        (s for s in checkable if s.name in located),
        key=lambda s: s.order,
    )
    for earlier, later in zip(ordered, ordered[1:]):
        if located[earlier.name] > located[later.name]:
            invalid_order.append({"before": later.name, "after": earlier.name})

    # 禁词：按规则作用范围检测。
    for rule in contract.forbidden_terms:
        if not rule.term:
            continue
        if rule.term in _scope_text(reply, rule.scope):
            forbidden_hits.append({"term": rule.term, "section": rule.scope})

    if len(_DETAILS_OPEN_RE.findall(reply)) != len(_DETAILS_CLOSE_RE.findall(reply)):
        warnings.append({"code": "unclosed_details"})

    ok = not (missing or invalid_order or forbidden_hits or warnings)
    return ContractDiagnostics(
        mode=contract.mode,
        ok=ok,
        required=len(required),
        missing=missing,
        invalid_order=invalid_order,
        forbidden_hits=forbidden_hits,
        warnings=warnings,
    )


def validate_visible_output(
    reply: str,
    contract: VisibleOutputContract,
) -> ContractDiagnostics:
    """按当前已支持的契约子集校验回复。"""
    if contract.mode == OutputContractMode.NONE:
        return ContractDiagnostics(mode=OutputContractMode.NONE, ok=True, required=0)

    if contract.mode == OutputContractMode.APPEND_TAIL:
        return _validate_append_tail(reply or "", contract)

    if contract.mode == OutputContractMode.FULL_DOCUMENT:
        return _validate_full_document(reply or "", contract)

    return ContractDiagnostics(
        mode=contract.mode,
        ok=False,
        required=0,
        warnings=[{"code": "unknown_contract_mode"}],
    )
