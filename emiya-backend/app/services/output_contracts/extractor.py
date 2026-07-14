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
from app.services.output_contracts.attachment import (
    attachment_is_compilable,
    canonicalize_attachment,
)
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


def _normalise_sections(raw_sections: Any, source: ContractSource) -> list[SectionContract]:
    """将 v2 definition 的受控区块转换为运行时数据结构。"""
    sections: list[SectionContract] = []
    for raw in raw_sections if isinstance(raw_sections, list) else []:
        if not isinstance(raw, dict):
            continue
        content_policy = raw.get("content_policy") if isinstance(raw.get("content_policy"), dict) else {}
        sections.append(
            SectionContract(
                name=str(raw.get("id") or ""),
                marker=str(raw.get("marker") or ""),
                required=bool(raw.get("required", True)),
                order=int(raw.get("order") or 0),
                kind=str(raw.get("kind") or "narrative"),
                span_strategy=str(raw.get("span_strategy") or "none"),
                content_policy=("non_empty" if content_policy.get("non_empty") else "allow_empty"),
                min_items=int(content_policy.get("min_items") or 0),
                repair_policy=str(raw.get("repair_policy") or "diagnose_only"),
                locator=dict(raw.get("locator") or {}),
                source=source,
            )
        )
    return sorted((section for section in sections if section.name), key=lambda section: section.order)


def _marker_from_contract(entry: dict, definition: dict[str, Any]) -> str:
    markers = definition.get("markers")
    if isinstance(markers, list):
        for marker in markers:
            if marker:
                return str(marker)
    sections = definition.get("sections")
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
    definition = oc.get("definition") if isinstance(oc.get("definition"), dict) else {}
    marker = _marker_from_contract(entry, definition)
    placement = str(definition.get("placement") or "tail")
    return TailBlockContract(
        marker=marker,
        content=str(entry.get("content") or ""),
        summary=marker,
        placement=placement,
        once=bool(definition.get("once_per_reply", True)),
        order=_order_from_entry(entry),
        template_type=str(definition.get("document_kind") or "tail_html"),
        abstract=definition,
        repairable=True,
        source=source,
    )


def _entry_contract(entry: dict) -> dict:
    return canonicalize_attachment(entry.get("output_contract"), entry)


def is_confirmed(oc: dict) -> bool:
    """契约是否已确认/声明（ADR-2c）：用户确认 reviewed=true 或用户来源 source=manual。

    未确认者即“自动识别草稿”（source=heuristic/llm 且 reviewed!=true）。
    """
    lifecycle = oc.get("lifecycle") if isinstance(oc.get("lifecycle"), dict) else {}
    provenance = oc.get("provenance") if isinstance(oc.get("provenance"), dict) else {}
    return bool(lifecycle.get("reviewed")) or provenance.get("source") == "manual"


def iter_contract_candidates(
    wi_activated: list[dict] | None,
    *,
    require_confirmed: bool = False,
) -> list[dict[str, Any]]:
    """按 entry 逐个产出候选契约片段，供 compiler 做权威性选主与冲突检测。

    每个候选保留来源 entry 的识别元数据（`oc`），因此 compiler 能按
    `source / trigger / reviewed / order / confidence` 计算权威性，而不必再回读 entry。
    契约类型：`tail` / `inline` / `full_document`。

    `require_confirmed=True`（ADR-2c 严格声明模式）时跳过未确认的自动识别草稿——
    调用方只在**执行**路径传 True，**锚定**路径仍传 False（草稿照旧进 Prompt 引导）。
    """
    candidates: list[dict[str, Any]] = []
    for entry in wi_activated or []:
        if not isinstance(entry, dict) or _is_disabled(entry):
            continue
        if is_mvu_tagged_entry(entry):
            continue

        oc = _entry_contract(entry)
        if not attachment_is_compilable(oc, entry, require_confirmed=require_confirmed):
            continue
        if require_confirmed and not is_confirmed(oc):
            continue  # ADR-2c：严格模式下未确认草稿不进入执行契约
        definition = oc.get("definition") if isinstance(oc.get("definition"), dict) else {}
        ctype = str(definition.get("document_kind") or "none")
        if ctype in {"none", "unknown"}:
            continue

        source = _source_from_entry(entry)
        order = _order_from_entry(entry)
        if ctype in {"tail_html", "tail_markdown", "tail_json"}:
            candidates.append({
                "kind": "tail",
                "tail": _tail_block_from_entry(entry, oc, source),
                "sections": [],
                "source": source,
                "oc": oc,
                "render_profile": definition.get("render_profile"),
                "order": order,
            })
        elif ctype == "inline_section":
            candidates.append({
                "kind": "inline",
                "tail": None,
                "sections": _normalise_sections(definition.get("sections"), source),
                "source": source,
                "oc": oc,
                "render_profile": definition.get("render_profile"),
                "order": order,
            })
        elif ctype == "full_document":
            configured = _normalise_sections(definition.get("sections"), source)
            candidates.append({
                "kind": "full_document",
                "tail": None,
                "sections": configured,
                "source": source,
                "oc": oc,
                "render_profile": definition.get("render_profile"),
                "order": order,
            })
    return candidates


def build_visible_output_contract(
    wi_activated: list[dict] | None,
    chat_config: dict | None = None,
    *,
    require_confirmed: bool = False,
) -> VisibleOutputContract:
    """从已激活条目的持久化 output_contract 构建运行时契约。

    `chat_config` 目前只用于保持接口稳定，后续可承接用户级契约配置。
    多候选权威性选主与冲突检测在 compiler 层做（ADR-1e）；此处沿用"全部 section
    并入"的合并策略，保证 tail-only / 单 full_document 场景行为不变。
    `require_confirmed`（ADR-2c）透传给候选枚举：执行路径传 True 只留已确认契约。
    """
    _ = chat_config
    tail_blocks: list[TailBlockContract] = []
    sections: list[SectionContract] = []
    sources: list[ContractSource] = []
    mode = OutputContractMode.NONE

    for cand in iter_contract_candidates(wi_activated, require_confirmed=require_confirmed):
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
