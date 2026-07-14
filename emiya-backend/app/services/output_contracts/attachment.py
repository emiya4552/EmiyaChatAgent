# -*- coding: utf-8 -*-
"""Output Contract Attachment v2 的读取、规范化与生命周期操作。

世界书 entry 仍把契约存为 JSON dict；本模块负责把外部/旧版自由 JSON 收敛成
受控 v2 Attachment。运行时和写入路径都通过这里读取，避免 schema 解释散落。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.output_contracts.hashing import content_hash
from app.services.output_contracts.sections import get_canonical, match_canonical
from app.services.output_contracts.render_profiles import DEFAULT_RENDER_PROFILE, RENDER_PROFILES
from app.services.output_contracts.types import SectionKind, SpanStrategy


SCHEMA_VERSION = 2
DETECTOR_VERSION = "output-contract-detector-v2"
DOCUMENT_KINDS = {
    "none", "tail_html", "tail_markdown", "tail_json", "inline_section", "full_document", "unknown",
}
ACTIVE_DOCUMENT_KINDS = {"tail_html", "tail_markdown", "tail_json", "inline_section", "full_document"}
LIFECYCLE_STATUSES = {"active", "none", "unknown"}
REPAIR_POLICIES = {"deterministic", "fill_slot", "rewrite_slot", "diagnose_only"}
SPAN_STRATEGIES = {
    SpanStrategy.BALANCED_TAG,
    SpanStrategy.EXPLICIT_DELIMITERS,
    SpanStrategy.FIXED_LINE_SET,
    SpanStrategy.UNTIL_NEXT_ANCHOR,
    SpanStrategy.NONE,
}
SECTION_KINDS = {
    SectionKind.MARKDOWN_HEADING,
    SectionKind.NARRATIVE,
    SectionKind.CHOICE_SET,
    SectionKind.DETAILS_SUMMARY,
    SectionKind.HTML_BLOCK,
    SectionKind.LITERAL_BLOCK,
}


def _status_for(document_kind: str) -> str:
    if document_kind == "none":
        return "none"
    if document_kind == "unknown":
        return "unknown"
    return "active"


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _section_defaults(section_id: str) -> dict[str, Any]:
    canonical = get_canonical(section_id)
    if canonical is None:
        return {
            "id": section_id,
            "label": section_id,
            "kind": SectionKind.NARRATIVE,
            "marker": "",
            "order": 1000,
            "locator": {"type": "none"},
            "span_strategy": SpanStrategy.NONE,
            "content_policy": {"non_empty": False},
            "repair_policy": "diagnose_only",
            "capability": "diagnose_only",
        }

    locator: dict[str, Any]
    if canonical.kind == SectionKind.MARKDOWN_HEADING:
        locator = {"type": "markdown_heading"}
    elif canonical.kind == SectionKind.CHOICE_SET:
        locator = {"type": "choice_labels", "labels": ["A", "B", "C", "D"]}
    elif canonical.kind == SectionKind.DETAILS_SUMMARY:
        locator = {"type": "details_summary", "contains": canonical.summary_keyword}
    else:
        locator = {"type": "between_sections"}

    span = {
        SectionKind.MARKDOWN_HEADING: SpanStrategy.UNTIL_NEXT_ANCHOR,
        SectionKind.CHOICE_SET: SpanStrategy.FIXED_LINE_SET,
        SectionKind.DETAILS_SUMMARY: SpanStrategy.BALANCED_TAG,
    }.get(canonical.kind, SpanStrategy.NONE)
    repair = {
        SectionKind.CHOICE_SET: "fill_slot",
        SectionKind.DETAILS_SUMMARY: "deterministic",
    }.get(canonical.kind, "diagnose_only")
    return {
        "id": canonical.name,
        "label": canonical.label or canonical.name,
        "kind": canonical.kind,
        "marker": canonical.marker,
        "order": canonical.order,
        "locator": locator,
        "span_strategy": span,
        "content_policy": {
            "non_empty": True,
            **({"min_items": 4} if canonical.kind == SectionKind.CHOICE_SET else {}),
        },
        "repair_policy": repair,
        "capability": "compilable" if repair != "diagnose_only" else "diagnose_only",
    }


def canonicalize_sections(raw_sections: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """把自由 section 列表转换为受控 v2 定义，返回 (sections, warnings)。"""
    if not isinstance(raw_sections, list):
        return [], []

    sections: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_sections):
        if not isinstance(raw, dict):
            warnings.append(f"section[{index}] 不是对象，已忽略")
            continue
        raw_id = str(raw.get("id") or raw.get("name") or "").strip()
        marker = str(raw.get("marker") or "").strip()
        canonical = get_canonical(raw_id) or match_canonical(raw_id, marker)
        if canonical is None:
            section_id = f"unsupported_{index + 1}"
            item = _section_defaults(section_id)
            item["label"] = str(raw.get("label") or raw_id or marker or "未支持区块")[:120]
            item["marker"] = marker[:200]
            item["order"] = _as_int(raw.get("order"), 1000 + index * 10)
            item["required"] = bool(raw.get("required", True))
            sections.append(item)
            warnings.append(f"未支持区块“{item['label']}”仅用于诊断")
            continue

        if canonical.name in seen:
            warnings.append(f"重复区块“{canonical.name}”已忽略")
            continue
        seen.add(canonical.name)
        item = _section_defaults(canonical.name)
        item["label"] = str(raw.get("label") or canonical.label or canonical.name)[:120]
        item["required"] = bool(raw.get("required", True))
        item["order"] = _as_int(raw.get("order"), canonical.order)

        # 仅开放受控的内容配置；kind、定位和修复策略由注册表决定。
        policy = raw.get("content_policy")
        if isinstance(policy, dict):
            item["content_policy"]["non_empty"] = bool(
                policy.get("non_empty", item["content_policy"]["non_empty"])
            )
            if canonical.kind == SectionKind.CHOICE_SET:
                min_items = _as_int(policy.get("min_items"), item["content_policy"].get("min_items", 4))
                item["content_policy"]["min_items"] = max(1, min(26, min_items))
        locator = raw.get("locator")
        if isinstance(locator, dict):
            if canonical.kind == SectionKind.CHOICE_SET and isinstance(locator.get("labels"), list):
                labels = [str(value).strip()[:8] for value in locator["labels"] if str(value).strip()]
                if labels:
                    item["locator"]["labels"] = labels[:26]
            if canonical.kind == SectionKind.DETAILS_SUMMARY and locator.get("contains"):
                item["locator"]["contains"] = str(locator["contains"])[:120]
        sections.append(item)

    sections.sort(key=lambda section: section["order"])
    return sections, warnings


def _definition_from_proposal(proposal: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    document_kind = str(proposal.get("type") or proposal.get("document_kind") or "unknown")
    if document_kind not in DOCUMENT_KINDS:
        document_kind = "unknown"
    abstract = proposal.get("abstract") if isinstance(proposal.get("abstract"), dict) else {}
    sections, warnings = canonicalize_sections(abstract.get("sections"))
    definition = {
        "document_kind": document_kind,
        "placement": str(abstract.get("placement") or ("tail" if document_kind.startswith("tail_") else document_kind)),
        "once_per_reply": bool(abstract.get("once_per_reply", True)),
        "sections": sections,
        "markers": [str(marker)[:200] for marker in abstract.get("markers", []) if marker] if isinstance(abstract.get("markers"), list) else [],
        "variables": [],
        "template_span_hint": dict(abstract.get("template_span_hint") or {}),
        "forbidden_terms": [str(term)[:120] for term in proposal.get("forbidden_terms", []) if term]
        if isinstance(proposal.get("forbidden_terms"), list) else [],
        "render_profile": (
            str(abstract.get("render_profile") or DEFAULT_RENDER_PROFILE)
            if str(abstract.get("render_profile") or DEFAULT_RENDER_PROFILE) in RENDER_PROFILES
            else DEFAULT_RENDER_PROFILE
        ),
    }
    return definition, warnings


def _provenance(proposal: dict[str, Any], warnings: list[str], *, content: str) -> dict[str, Any]:
    confidence = proposal.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "source": str(proposal.get("source") or "heuristic"),
        "trigger": str(proposal.get("trigger") or "auto_import"),
        "confidence": confidence,
        "reason": str(proposal.get("reason") or "")[:500],
        "proposal": {
            "type": str(proposal.get("type") or proposal.get("document_kind") or "unknown"),
            "warnings": warnings,
        },
        "content_hash": content_hash(content),
    }


def _legacy_to_proposal(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": raw.get("type", "unknown"),
        "source": raw.get("source", "heuristic"),
        "trigger": raw.get("trigger", "auto_import"),
        "confidence": raw.get("confidence", 0.0),
        "reason": raw.get("reason", ""),
        "abstract": raw.get("abstract") if isinstance(raw.get("abstract"), dict) else {},
    }


def is_v2_attachment(raw: Any) -> bool:
    return isinstance(raw, dict) and raw.get("schema_version") == SCHEMA_VERSION and isinstance(raw.get("definition"), dict)


def canonicalize_attachment(raw: Any, entry: dict) -> dict[str, Any]:
    """读取 v1/v2 数据并返回完整受控 v2 Attachment，不修改传入对象。"""
    if not isinstance(raw, dict):
        return canonicalize_proposal(entry, {"type": "unknown", "source": "heuristic", "reason": "未识别"})

    if not is_v2_attachment(raw):
        migrated = canonicalize_proposal(entry, _legacy_to_proposal(raw), existing=None)
        legacy_type = str(raw.get("type") or "unknown")
        migrated["lifecycle"] = {
            "content_hash": str(raw.get("content_hash") or content_hash(str(entry.get("content") or ""))),
            "detector_version": str(raw.get("detector_version") or "output-contract-detector-v1"),
            "reviewed": bool(raw.get("reviewed")) or raw.get("source") == "manual",
            "status": _status_for(legacy_type),
        }
        migrated["provenance"]["source"] = str(raw.get("source") or "heuristic")
        migrated["provenance"]["trigger"] = str(raw.get("trigger") or "auto_import")
        return migrated

    source_definition = raw.get("definition") or {}
    proposal = {
        "type": source_definition.get("document_kind", "unknown"),
        "abstract": {
            "placement": source_definition.get("placement"),
            "once_per_reply": source_definition.get("once_per_reply", True),
            "sections": source_definition.get("sections", []),
            "markers": source_definition.get("markers", []),
            "template_span_hint": source_definition.get("template_span_hint", {}),
        },
        "forbidden_terms": source_definition.get("forbidden_terms", []),
        **(raw.get("provenance") if isinstance(raw.get("provenance"), dict) else {}),
    }
    definition, warnings = _definition_from_proposal(proposal)
    lifecycle_raw = raw.get("lifecycle") if isinstance(raw.get("lifecycle"), dict) else {}
    status = str(lifecycle_raw.get("status") or _status_for(definition["document_kind"]))
    if status not in LIFECYCLE_STATUSES:
        status = _status_for(definition["document_kind"])
    lifecycle = {
        "content_hash": str(lifecycle_raw.get("content_hash") or content_hash(str(entry.get("content") or ""))),
        "detector_version": str(lifecycle_raw.get("detector_version") or DETECTOR_VERSION),
        "reviewed": bool(lifecycle_raw.get("reviewed", False)),
        "status": status,
    }
    attachment = {
        "schema_version": SCHEMA_VERSION,
        "enabled": bool(raw.get("enabled", True)),
        "definition": definition,
        "provenance": _provenance(proposal, warnings, content=str(entry.get("content") or "")),
        "lifecycle": lifecycle,
    }
    if isinstance(raw.get("latest_auto_definition"), dict):
        auto_definition, auto_warnings = _definition_from_proposal({
            "type": raw["latest_auto_definition"].get("document_kind"),
            "abstract": raw["latest_auto_definition"],
        })
        attachment["latest_auto_definition"] = auto_definition
        attachment["latest_auto_provenance"] = dict(raw.get("latest_auto_provenance") or {})
        attachment["latest_auto_provenance"].setdefault("warnings", auto_warnings)
    return attachment


def canonicalize_proposal(
    entry: dict,
    proposal: dict[str, Any],
    *,
    existing: dict[str, Any] | None = None,
    preserve_reviewed: bool = False,
) -> dict[str, Any]:
    """把检测 Proposal 写成 v2 Attachment；可保留过期的人工 definition。"""
    content = str(entry.get("content") or "")
    definition, warnings = _definition_from_proposal(proposal)
    provenance = _provenance(proposal, warnings, content=content)
    existing_attachment = canonicalize_attachment(existing, entry) if isinstance(existing, dict) else None

    if existing_attachment and preserve_reviewed and existing_attachment["lifecycle"].get("reviewed"):
        preserved = deepcopy(existing_attachment)
        preserved["enabled"] = bool(existing_attachment.get("enabled", True))
        preserved["latest_auto_definition"] = definition
        preserved["latest_auto_provenance"] = provenance
        return preserved

    reviewed = bool(proposal.get("reviewed", False))
    attachment = {
        "schema_version": SCHEMA_VERSION,
        "enabled": bool(existing_attachment.get("enabled", True)) if existing_attachment else True,
        "definition": definition,
        "provenance": provenance,
        "lifecycle": {
            "content_hash": content_hash(content),
            "detector_version": DETECTOR_VERSION,
            "reviewed": reviewed,
            "status": _status_for(definition["document_kind"]),
        },
    }
    if existing_attachment and isinstance(existing_attachment.get("latest_auto_definition"), dict):
        attachment["latest_auto_definition"] = deepcopy(existing_attachment["latest_auto_definition"])
        attachment["latest_auto_provenance"] = deepcopy(existing_attachment.get("latest_auto_provenance") or {})
    return attachment


def attachment_is_stale(attachment: dict[str, Any], entry: dict) -> bool:
    lifecycle = attachment.get("lifecycle") if isinstance(attachment.get("lifecycle"), dict) else {}
    return lifecycle.get("content_hash") != content_hash(str(entry.get("content") or ""))


def attachment_is_compilable(attachment: dict[str, Any], entry: dict, *, require_confirmed: bool = False) -> bool:
    lifecycle = attachment.get("lifecycle") if isinstance(attachment.get("lifecycle"), dict) else {}
    if not attachment.get("enabled", True) or lifecycle.get("status") != "active":
        return False
    reviewed = bool(lifecycle.get("reviewed"))
    if require_confirmed and not reviewed:
        return False
    if attachment_is_stale(attachment, entry) and not reviewed:
        return False
    sections = (attachment.get("definition") or {}).get("sections") or []
    document_kind = (attachment.get("definition") or {}).get("document_kind")
    if document_kind in {"tail_html", "tail_markdown", "tail_json"}:
        return True
    # 即使所有区块都只能诊断，整篇/内联契约仍必须进入 Prompt 锚定与校验；
    # capability 只决定能否修复，不决定世界书作者的格式要求是否生效。
    if document_kind in {"full_document", "inline_section"}:
        return bool(sections)
    return any(section.get("capability") == "compilable" for section in sections if isinstance(section, dict))


def apply_manual_definition(
    entry: dict,
    definition: dict[str, Any],
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """保存人工 definition，保留最近自动候选以支持恢复自动定义。"""
    proposal = {
        "type": definition.get("document_kind", "unknown"),
        "abstract": definition,
        "forbidden_terms": definition.get("forbidden_terms", []),
        "source": "manual",
        "trigger": "manual",
        "confidence": 1.0,
        "reason": "用户编辑输出契约",
        "reviewed": True,
    }
    attachment = canonicalize_proposal(entry, proposal, existing=existing)
    if existing:
        prior = canonicalize_attachment(existing, entry)
        if prior["provenance"].get("source") != "manual":
            attachment["latest_auto_definition"] = deepcopy(prior["definition"])
            attachment["latest_auto_provenance"] = deepcopy(prior["provenance"])
        elif isinstance(prior.get("latest_auto_definition"), dict):
            attachment["latest_auto_definition"] = deepcopy(prior["latest_auto_definition"])
            attachment["latest_auto_provenance"] = deepcopy(prior.get("latest_auto_provenance") or {})
    return attachment


def accept_latest_auto_definition(entry: dict, attachment: dict[str, Any], *, reviewed: bool) -> dict[str, Any]:
    """把完整自动候选提升为当前 definition；reviewed 决定接受还是恢复自动。"""
    current = canonicalize_attachment(attachment, entry)
    definition = current.get("latest_auto_definition")
    auto_provenance = current.get("latest_auto_provenance") or {}
    if not isinstance(definition, dict):
        raise ValueError("没有可接受的自动识别候选")
    proposal = {
        "type": definition.get("document_kind"),
        "abstract": definition,
        "forbidden_terms": definition.get("forbidden_terms", []),
        "source": "manual" if reviewed else auto_provenance.get("source", "heuristic"),
        "trigger": "manual" if reviewed else auto_provenance.get("trigger", "auto_import"),
        "confidence": auto_provenance.get("confidence", 1.0),
        "reason": "用户接受自动候选" if reviewed else "恢复自动候选",
        "reviewed": reviewed,
    }
    upgraded = canonicalize_proposal(entry, proposal, existing=current)
    upgraded.pop("latest_auto_definition", None)
    upgraded.pop("latest_auto_provenance", None)
    return upgraded


def set_attachment_enabled(entry: dict, attachment: dict[str, Any], enabled: bool) -> dict[str, Any]:
    result = canonicalize_attachment(attachment, entry)
    result["enabled"] = bool(enabled)
    return result


def mark_attachment_reviewed(entry: dict, attachment: dict[str, Any]) -> dict[str, Any]:
    """确认当前 definition，不改变其来源或内容。"""
    result = canonicalize_attachment(attachment, entry)
    result["lifecycle"]["reviewed"] = True
    return result
