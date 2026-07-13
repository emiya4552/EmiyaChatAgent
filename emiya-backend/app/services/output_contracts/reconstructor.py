# -*- coding: utf-8 -*-
"""确定性结构修复（ADR-1e §4）。

不调用 LLM，只做无损结构修复：选项标签规范化、重复空壳去重、相邻自界定块按契约
顺序重排、`<details>` 闭合补齐。只有块边界无歧义（自界定块、仅空白分隔）才允许移动；
`narrative` 永不被切割，正文边界不明确时禁止重排，转交上层诊断 / 槽位补写。
"""
from __future__ import annotations

import re

from app.services.output_contracts.types import (
    SectionKind,
    VisibleOutputContract,
)

_DETAILS_OPEN_RE = re.compile(r"<details\b", re.IGNORECASE)
_DETAILS_CLOSE_RE = re.compile(r"</details\s*>", re.IGNORECASE)
_DETAILS_BLOCK_RE = re.compile(r"<details\b.*?</details\s*>", re.IGNORECASE | re.DOTALL)
_SUMMARY_RE = re.compile(r"<summary\b[^>]*>(.*?)</summary>", re.IGNORECASE | re.DOTALL)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
# 选项行近似匹配：必须有 **字母** 粗体标记，narrative 极少以此开头，误伤概率低。
_OPTION_LINE_RE = re.compile(r"(?m)^\s*>?\s*\*\*\s*([A-Da-d])\s*[.．、)]?\s*\*\*\s*(.*)$")


def _strip_tags(text: str) -> str:
    return _TAG_STRIP_RE.sub("", text or "").strip()


def _has_kind(contract: VisibleOutputContract, kind: str) -> bool:
    return any(s.kind == kind for s in contract.required_sections)


# ── 选项标签规范化 ─────────────────────────────────────────


def _normalize_choice_labels(text: str, contract: VisibleOutputContract):
    """把近似选项行规范成 `> **A.** 描述`；仅契约含 choice_set 时启用。"""
    if not _has_kind(contract, SectionKind.CHOICE_SET):
        return text, None
    changed = False

    def repl(m: re.Match) -> str:
        nonlocal changed
        letter = m.group(1).upper()
        rest = m.group(2).strip()
        canon = f"> **{letter}.** {rest}".rstrip()
        if canon != m.group(0):
            changed = True
        return canon

    new = _OPTION_LINE_RE.sub(repl, text)
    if changed:
        return new, {"action": "normalize_choices"}
    return text, None


# ── 重复空壳去重 ───────────────────────────────────────────


def _is_empty_shell(block: str) -> bool:
    inner = _SUMMARY_RE.sub("", block)
    return not _strip_tags(inner).strip()


def _dedup_empty_details(text: str):
    """删除完全相同的重复空 `<details>` 壳，保留首个。"""
    seen: set[str] = set()
    spans: list[tuple[int, int]] = []
    for m in _DETAILS_BLOCK_RE.finditer(text):
        block = m.group(0)
        if not _is_empty_shell(block):
            continue
        if block in seen:
            spans.append(m.span())
        else:
            seen.add(block)
    if not spans:
        return text, None
    for start, end in sorted(spans, reverse=True):
        tail = text[end:]
        # 连带吃掉紧邻的一个换行，避免留下空行。
        if tail.startswith("\n"):
            tail = tail[1:]
        text = text[:start] + tail
    return text, {"action": "dedup_empty_details", "count": len(spans)}


# ── 相邻自界定块按契约顺序重排 ─────────────────────────────


def _details_order_map(contract: VisibleOutputContract) -> dict[str, int]:
    return {
        s.marker: s.order
        for s in contract.required_sections
        if s.kind == SectionKind.DETAILS_SUMMARY and s.marker
    }


def _block_keyword(block: str, order_map: dict[str, int]) -> str | None:
    summ = _SUMMARY_RE.search(block)
    if not summ:
        return None
    stext = _strip_tags(summ.group(1))
    for kw in order_map:
        if kw in stext:
            return kw
    return None


def _reorder_adjacent_details(text: str, contract: VisibleOutputContract):
    """仅对"只由空白分隔的连续 details 块" run 按契约顺序重排。

    run 内全为自界定 `<details>` 块、无 narrative 夹杂，边界无歧义才排；任一块无法
    映射到契约 order 则跳过该 run（归属不明不猜测）。
    """
    order_map = _details_order_map(contract)
    if len(order_map) < 2:
        return text, None
    blocks = list(_DETAILS_BLOCK_RE.finditer(text))
    if len(blocks) < 2:
        return text, None

    runs: list[list[re.Match]] = []
    cur: list[re.Match] = []
    for m in blocks:
        if cur and text[cur[-1].end():m.start()].strip() == "":
            cur.append(m)
        else:
            if cur:
                runs.append(cur)
            cur = [m]
    if cur:
        runs.append(cur)

    changed = False
    for run in reversed(runs):
        if len(run) < 2:
            continue
        keyed = [(_block_keyword(m.group(0), order_map), m) for m in run]
        if any(kw is None for kw, _ in keyed):
            continue  # 有块归属不明，整段不动
        ordered = sorted(keyed, key=lambda t: order_map[t[0]])
        if [id(m) for _, m in keyed] == [id(m) for _, m in ordered]:
            continue  # 已有序
        start, end = run[0].start(), run[-1].end()
        text = text[:start] + "\n".join(m.group(0) for _, m in ordered) + text[end:]
        changed = True

    if changed:
        return text, {"action": "reorder_details"}
    return text, None


# ── details 闭合补齐 ───────────────────────────────────────


def _close_unbalanced_details(text: str):
    """开标签多于闭标签时，在末尾补足缺失的 </details>。纯追加，不删内容。"""
    opens = len(_DETAILS_OPEN_RE.findall(text))
    closes = len(_DETAILS_CLOSE_RE.findall(text))
    if opens <= closes:
        return text, None
    missing = opens - closes
    fixed = text.rstrip() + "\n" + "\n".join(["</details>"] * missing)
    return fixed, {"action": "close_details", "count": missing}


def reconstruct(text: str, contract: VisibleOutputContract) -> tuple[str, list[dict]]:
    """对文本做确定性无损修复，返回 (修复后文本, 动作列表)。

    只在契约激活时执行；不改变正文内容，只规范结构外壳。冲突契约不修复（由 executor
    在调用前短路，这里对冲突也保持保守，不重排）。
    """
    actions: list[dict] = []
    if not contract.active or not text or contract.has_conflict:
        return text, actions

    # 顺序：规范选项 → 去重空壳 → 相邻块重排 → 闭合补齐。前三步作用于自界定块，
    # 不改 narrative；闭合放最后，基于最终 open/close 计数补齐。
    text, action = _normalize_choice_labels(text, contract)
    if action:
        actions.append(action)
    text, action = _dedup_empty_details(text)
    if action:
        actions.append(action)
    text, action = _reorder_adjacent_details(text, contract)
    if action:
        actions.append(action)
    text, action = _close_unbalanced_details(text)
    if action:
        actions.append(action)

    return text, actions
