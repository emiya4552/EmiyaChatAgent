# -*- coding: utf-8 -*-
"""缺失槽位补写（ADR-1e §5）。

确定性修复后仍缺内容时，调用一次低温结构化补写，只请求缺失 / 空槽位，不重写已合格
正文。模型只返回槽位数据（文本 / 选项数组），最终结构外壳由 renderer 确定性拼入，
再交回 validator 复校。一次调用返回多个槽位，避免按槽位重复请求。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.llm_service import call_deepseek_non_stream
from app.services.output_contracts.renderer import render_section
from app.services.output_contracts.types import (
    SectionContract,
    SectionKind,
    VisibleOutputContract,
)
from app.services.output_contracts.validator import locate_section_positions

logger = logging.getLogger(__name__)

_DETAILS_BLOCK_RE = re.compile(r"<details\b.*?</details\s*>", re.IGNORECASE | re.DOTALL)
_SUMMARY_RE = re.compile(r"<summary\b[^>]*>(.*?)</summary>", re.IGNORECASE | re.DOTALL)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_OPTION_LINE_RE = re.compile(r"(?m)^\s*>?\s*\*\*\s*[A-Da-d]\s*[.．、)]?\s*\*\*.*$")

_KIND_LABEL = {
    SectionKind.CHOICE_SET: "选项区块（A/B/C/D 描述数组）",
    SectionKind.DETAILS_SUMMARY: "折叠块正文（details 内部内容）",
    SectionKind.MARKDOWN_HEADING: "章节标题文本",
    SectionKind.HTML_BLOCK: "HTML 区块内容",
    SectionKind.LITERAL_BLOCK: "固定区块内容",
    SectionKind.NARRATIVE: "叙事段落",
}


def fillable_sections(
    contract: VisibleOutputContract,
    missing: list[dict[str, Any]],
) -> list[SectionContract]:
    """从校验 missing 里挑出可槽位补写的 section（排除 diagnose_only）。"""
    by_name = {s.name: s for s in contract.required_sections}
    names: list[str] = []
    for item in missing:
        name = item.get("section")
        if name and name not in names:
            names.append(name)
    out: list[SectionContract] = []
    for name in names:
        section = by_name.get(name)
        if section is not None and section.repair_policy != "diagnose_only":
            out.append(section)
    return out


def _strip_tags(text: str) -> str:
    return _TAG_STRIP_RE.sub("", text or "").strip()


def _section_summary(section: SectionContract) -> str:
    return section.marker or section.name


def _build_prompt(sections: list[SectionContract], reply: str) -> str:
    lines = [
        "你在为一段已生成的回复补齐缺失的结构化区块。",
        "只输出 JSON，不要解释。只补下列缺失槽位，不要改动或复述已有正文。",
        "",
        "缺失槽位：",
    ]
    for s in sections:
        label = _KIND_LABEL.get(s.kind, s.kind)
        hint = f"，世界书要求：{s.source.comment}" if s.source and s.source.comment else ""
        extra = f"（至少 {s.min_items} 项）" if s.kind == SectionKind.CHOICE_SET else ""
        lines.append(f"- {s.name}：{label}{extra}{hint}")
    lines += [
        "",
        "已生成回复（供理解上下文，不要重复它）：",
        reply[:4000],
        "",
        "返回 JSON：{\"slots\": {\"<name>\": <字符串或字符串数组>}}。",
        "choice_set 用字符串数组，其余用字符串。内容必须与上文事实一致。",
    ]
    return "\n".join(lines)


def _parse_slots(response: str) -> dict[str, Any]:
    raw = (response or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    data: Any = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                data = None
    if not isinstance(data, dict):
        return {}
    slots = data.get("slots")
    return slots if isinstance(slots, dict) else {}


async def request_slots(
    sections: list[SectionContract],
    reply: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 900,
) -> dict[str, Any]:
    """一次结构化调用补写缺失槽位，返回 {name: 文本 | 数组}。失败返回空 dict。"""
    if not sections:
        return {}
    prompt = _build_prompt(sections, reply)
    try:
        response = await call_deepseek_non_stream(
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 — 补写失败不阻断落库
        logger.warning("[输出契约] 槽位补写 LLM 调用失败：%s", exc)
        return {}
    slots = _parse_slots(response)
    wanted = {s.name for s in sections}
    return {k: v for k, v in slots.items() if k in wanted}


# ── 把补出的槽位渲染并拼入文档 ─────────────────────────────


def _find_details_span(text: str, keyword: str) -> tuple[int, int] | None:
    for m in _DETAILS_BLOCK_RE.finditer(text):
        summ = _SUMMARY_RE.search(m.group(0))
        if summ and keyword in _strip_tags(summ.group(1)):
            return m.span()
    return None


def _find_option_span(text: str) -> tuple[int, int] | None:
    """连续选项行的整体跨度；非连续（中间夹非选项行）时返回 None，不冒险替换。"""
    matches = list(_OPTION_LINE_RE.finditer(text))
    if not matches:
        return None
    start, end = matches[0].start(), matches[0].end()
    for m in matches[1:]:
        if text[end:m.start()].strip() != "":
            return None  # 中间夹了非选项内容，边界不安全
        end = m.end()
    return start, end


def _insert_by_order(
    text: str,
    contract: VisibleOutputContract,
    section: SectionContract,
    rendered: str,
) -> str:
    """按契约 order 把渲染块插到首个更高 order 的已定位 section 之前，否则追加末尾。"""
    positions = locate_section_positions(text, contract)
    order_by_name = {s.name: s.order for s in contract.required_sections}
    after_positions = [
        pos for name, pos in positions.items()
        if order_by_name.get(name, 0) > section.order
    ]
    if after_positions:
        at = min(after_positions)
        return text[:at] + rendered + "\n" + text[at:]
    sep = "" if text.endswith("\n") or not text else "\n"
    return text.rstrip("\n") + "\n" + rendered + "\n" if text else rendered


def _render_slot(section: SectionContract, value: Any) -> str:
    if section.kind == SectionKind.CHOICE_SET:
        choices = value if isinstance(value, list) else [value]
        return render_section(section, choices=[str(c) for c in choices])
    return render_section(section, text=str(value))


def apply_slots(
    text: str,
    contract: VisibleOutputContract,
    slots: dict[str, Any],
) -> tuple[str, list[dict]]:
    """把补出的槽位渲染并拼入文本：空壳替换、缺失按序插入。返回 (文本, 动作)。"""
    by_name = {s.name: s for s in contract.required_sections}
    actions: list[dict] = []
    for name, value in slots.items():
        section = by_name.get(name)
        if section is None or value in (None, "", []):
            continue
        rendered = _render_slot(section, value)

        if section.kind == SectionKind.DETAILS_SUMMARY:
            span = _find_details_span(text, _section_summary(section))
        elif section.kind == SectionKind.CHOICE_SET:
            span = _find_option_span(text)
        else:
            span = None

        if span is not None:
            text = text[:span[0]] + rendered + text[span[1]:]
            actions.append({"action": "fill_slot", "section": name, "mode": "replace"})
        else:
            text = _insert_by_order(text, contract, section, rendered)
            actions.append({"action": "fill_slot", "section": name, "mode": "insert"})
    return text, actions
