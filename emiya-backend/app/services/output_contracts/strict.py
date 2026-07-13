# -*- coding: utf-8 -*-
"""严格整篇模板的槽位生成与确定性渲染（ADR-1g）。

strict 不要求主模型一次写出最终文档：主模型草稿只当叙事正文（narrative 槽位），代码
对其余受控区块做一次结构化槽位 pass，再按契约顺序确定性渲染最终文档，最后校验并最多
一次定向 refill。结构外壳、顺序、选项标签、`<details>` 闭合由 renderer 层硬保证；模型
不拼最终标签，从机制上杜绝正文被二次改写。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.services.output_contracts.renderer import render_section
from app.services.output_contracts.slotfill import fillable_sections, request_slots
from app.services.output_contracts.types import (
    ContractDiagnostics,
    SectionKind,
    VisibleOutputContract,
)
from app.services.output_contracts.validator import validate_visible_output

_DETAILS_BLOCK_RE = re.compile(r"<details\b.*?</details\s*>", re.IGNORECASE | re.DOTALL)
_OPTION_LINE_RE = re.compile(r"(?m)^\s*>?\s*\*\*\s*[A-Da-d]\s*[.．、)]?\s*\*\*.*$")
_HEADING_LINE_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+.*$")

# strict 阶段状态（SSE contract_stage）。
STRICT_STAGES = ("drafting", "structuring", "rendering", "validating", "refilling", "done")


@dataclass
class StrictResult:
    content: str
    ok: bool
    diagnostics: ContractDiagnostics
    method: str = "strict_rendered"
    extra_calls: int = 0
    latency_ms: int = 0
    stages: list[str] = field(default_factory=list)


def strict_available(
    contract: VisibleOutputContract,
    policy: dict | None = None,
) -> tuple[bool, str]:
    """判断 strict 启用前提（ADR-1g）。返回 (可用, 不可用原因)。"""
    policy = policy or {}
    if not contract.required_sections:
        return False, "no_full_document"
    if contract.has_conflict:
        return False, "contract_conflict"
    if not policy.get("strict_budget_ok", True):
        return False, "insufficient_budget"
    return True, ""


def _draft_narrative(draft: str) -> str:
    """把草稿里的结构块剥掉，只留纯叙事，作为 narrative 槽位。

    strict 从机制上不信任草稿结构：`<details>`、选项行、markdown 标题都由 renderer
    重新生成，草稿只贡献正文，避免结构重复。
    """
    text = _DETAILS_BLOCK_RE.sub("", draft or "")
    text = _OPTION_LINE_RE.sub("", text)
    text = _HEADING_LINE_RE.sub("", text)
    # 压掉剥离后残留的多余空行。
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def render_document(
    draft: str,
    contract: VisibleOutputContract,
    slots: dict[str, Any],
) -> str:
    """按契约 order 确定性渲染整篇文档：narrative=草稿正文，其余区块由 renderer 生成。"""
    narrative = _draft_narrative(draft)
    parts: list[str] = []
    for section in sorted(contract.required_sections, key=lambda s: s.order):
        if section.kind == SectionKind.NARRATIVE:
            if narrative:
                parts.append(narrative)
            continue
        value = slots.get(section.name)
        if section.kind == SectionKind.CHOICE_SET:
            choices = value if isinstance(value, list) else ([value] if value else [])
            parts.append(render_section(section, choices=[str(c) for c in choices]))
        else:
            parts.append(render_section(section, text=str(value) if value else ""))
    return "\n\n".join(p for p in parts if p)


async def run_strict(
    draft: str,
    contract: VisibleOutputContract,
    *,
    temperature: float = 0.2,
    max_refills: int = 1,
) -> StrictResult:
    """执行 strict 两阶段：结构化槽位 pass → 确定性渲染 → 校验 → 最多一次 refill。"""
    started = time.monotonic()
    stages: list[str] = ["structuring"]

    slot_sections = [
        s for s in contract.required_sections if s.kind != SectionKind.NARRATIVE
    ]
    extra_calls = 1
    slots = await request_slots(slot_sections, draft, temperature=temperature)

    stages.append("rendering")
    doc = render_document(draft, contract, slots)

    stages.append("validating")
    diag = validate_visible_output(doc, contract)

    # 阶段四：仅缺内容槽位时最多一次定向 refill，禁止无限重试。
    if not diag.ok and max_refills > 0:
        missing = fillable_sections(contract, diag.missing)
        missing = [s for s in missing if s.kind != SectionKind.NARRATIVE]
        if missing:
            stages.append("refilling")
            extra_calls += 1
            more = await request_slots(missing, draft, temperature=temperature)
            if more:
                slots.update(more)
                doc = render_document(draft, contract, slots)
                diag = validate_visible_output(doc, contract)

    stages.append("done")
    return StrictResult(
        content=doc,
        ok=diag.ok,
        diagnostics=diag,
        method="strict_rendered",
        extra_calls=extra_calls,
        latency_ms=int((time.monotonic() - started) * 1000),
        stages=stages,
    )
