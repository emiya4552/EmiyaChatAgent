# -*- coding: utf-8 -*-
"""从已激活世界书条目中提取可见输出契约。"""
from __future__ import annotations

from typing import Any

from app.services.output_contracts.types import (
    ContractSource,
    OutputContractMode,
    SectionContract,
    TailBlockContract,
    VisibleOutputContract,
)
from app.services.mvu_runtime.worldbook import is_mvu_tagged_entry
import logging

logger = logging.getLogger(__name__)


def _source_from_entry(entry: dict) -> ContractSource:
    return ContractSource(
        uid=entry.get("uid"),
        comment=str(entry.get("comment") or ""),
        worldbook_id=(
            str(entry.get("worldbook_id"))
            if entry.get("worldbook_id") is not None
            else None
        ),
        worldbook_name=str(entry.get("worldbook_name") or ""),
    )


def _is_disabled(entry: dict) -> bool:
    return entry.get("enabled", True) is False or entry.get("disable") is True


def _full_document_sections(source: ContractSource) -> list[SectionContract]:
    return [
        SectionContract("chapter", marker="#", order=10, source=source),
        SectionContract("body", marker="", order=20, source=source),
        SectionContract("options", marker="> **A.**", order=30, source=source),
        SectionContract("backend_log", marker="后台日志", order=40, source=source),
        SectionContract("hidden_plot", marker="隐藏剧情", order=50, source=source),
    ]


def _normalise_sections(raw_sections: Any, source: ContractSource) -> list[SectionContract]:
    sections: list[SectionContract] = []
    if not isinstance(raw_sections, list):
        return sections
    for idx, raw in enumerate(raw_sections):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or raw.get("marker") or f"section_{idx}")
        sections.append(
            SectionContract(
                name=name,
                marker=str(raw.get("marker") or ""),
                required=bool(raw.get("required", True)),
                order=int(raw.get("order", idx * 10)),
                source=source,
            )
        )
    return sections


def _marker_from_contract(entry: dict, abstract: dict[str, Any]) -> str:
    markers = abstract.get("markers")
    if isinstance(markers, list):
        for marker in markers:
            if marker:
                return str(marker)
    sections = abstract.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if isinstance(section, dict) and section.get("marker"):
                return str(section["marker"])
    return str(entry.get("comment") or "").strip() or f"条目#{entry.get('uid', '?')}"


def _order_from_entry(entry: dict) -> int:
    try:
        return int(entry.get("order", 100) or 100)
    except (TypeError, ValueError):
        return 100


def _tail_block_from_entry(entry: dict, oc: dict, source: ContractSource) -> TailBlockContract:
    abstract = oc.get("abstract") if isinstance(oc.get("abstract"), dict) else {}
    marker = _marker_from_contract(entry, abstract)
    placement = str(abstract.get("placement") or "tail")
    return TailBlockContract(
        marker=marker,
        content=str(entry.get("content") or ""),
        summary=marker,
        placement=placement,
        once=bool(abstract.get("once_per_reply", True)),
        order=_order_from_entry(entry),
        template_type=str(oc.get("type") or "tail_html"),
        abstract=abstract,
        repairable=True,
        source=source,
    )


def _entry_contract(entry: dict) -> dict:
    oc = entry.get("output_contract")
    return oc if isinstance(oc, dict) else {}


def iter_contract_candidates(wi_activated: list[dict] | None) -> list[dict[str, Any]]:
    """按 entry 逐个产出候选契约片段，供 compiler 做权威性选主与冲突检测。

    每个候选保留来源 entry 的识别元数据（`oc`），因此 compiler 能按
    `source / trigger / reviewed / order / confidence` 计算权威性，而不必再回读 entry。
    契约类型：`tail` / `inline` / `full_document`。
    """
    candidates: list[dict[str, Any]] = []
    for entry in wi_activated or []:
        if not isinstance(entry, dict) or _is_disabled(entry):
            continue
        if is_mvu_tagged_entry(entry):
            continue

        oc = _entry_contract(entry)
        if oc.get("status") not in {"detected", "manual"}:
            continue
        ctype = str(oc.get("type") or "none")
        if ctype in {"none", "unknown"}:
            continue

        source = _source_from_entry(entry)
        abstract = oc.get("abstract") if isinstance(oc.get("abstract"), dict) else {}
        order = _order_from_entry(entry)
        if ctype in {"tail_html", "tail_markdown", "tail_json"}:
            candidates.append({
                "kind": "tail",
                "tail": _tail_block_from_entry(entry, oc, source),
                "sections": [],
                "source": source,
                "oc": oc,
                "order": order,
            })
        elif ctype == "inline_section":
            candidates.append({
                "kind": "inline",
                "tail": None,
                "sections": _normalise_sections(abstract.get("sections"), source),
                "source": source,
                "oc": oc,
                "order": order,
            })
        elif ctype == "full_document":
            configured = _normalise_sections(abstract.get("sections"), source)
            candidates.append({
                "kind": "full_document",
                "tail": None,
                "sections": configured or _full_document_sections(source),
                "source": source,
                "oc": oc,
                "order": order,
            })
    return candidates


def build_visible_output_contract(
    wi_activated: list[dict] | None,
    chat_config: dict | None = None,
) -> VisibleOutputContract:
    """从已激活条目的持久化 output_contract 构建运行时契约。

    `chat_config` 目前只用于保持接口稳定，后续可承接用户级契约配置。
    多候选权威性选主与冲突检测在 compiler 层做（ADR-1e）；此处沿用"全部 section
    并入"的合并策略，保证 tail-only / 单 full_document 场景行为不变。
    """
    _ = chat_config
    tail_blocks: list[TailBlockContract] = []
    sections: list[SectionContract] = []
    sources: list[ContractSource] = []
    mode = OutputContractMode.NONE

    for cand in iter_contract_candidates(wi_activated):
        sources.append(cand["source"])
        if cand["kind"] == "tail":
            tail_blocks.append(cand["tail"])
        else:
            sections.extend(cand["sections"])

    if sections:
        mode = OutputContractMode.FULL_DOCUMENT
    elif tail_blocks:
        mode = OutputContractMode.APPEND_TAIL

    deduped_sources: list[ContractSource] = []
    seen_sources: set[tuple] = set()
    for source in sources:
        key = (source.uid, source.comment, source.worldbook_id)
        if key in seen_sources:
            continue
        seen_sources.add(key)
        deduped_sources.append(source)

    logger.info(
        "[输出契约] mode=%s active=%s tail_blocks=%d sections=%d sources=%d wi_count=%d",
        mode,
        mode != OutputContractMode.NONE,
        len(tail_blocks),
        len(sections),
        len(deduped_sources),
        len(wi_activated or []),
    )

    return VisibleOutputContract(
        mode=mode,
        required_tail_blocks=tail_blocks,
        required_sections=sections,
        source_entries=deduped_sources,
    )
