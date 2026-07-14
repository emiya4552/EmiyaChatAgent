# -*- coding: utf-8 -*-
"""世界书 entry 的可见输出契约识别。

识别发生在世界书导入/编辑期，结果写回 entry.output_contract。聊天运行时只消费
保存好的契约，不再对未识别条目做临时扫描。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.llm_service import call_deepseek_non_stream
from app.services.mvu_runtime.worldbook import is_mvu_tagged_entry
from app.services.output_contracts.attachment import (
    apply_manual_definition,
    attachment_is_stale,
    canonicalize_attachment,
    canonicalize_proposal,
)
from app.services.output_contracts.hashing import content_hash
from app.services.output_contracts.sections import get_canonical

logger = logging.getLogger(__name__)

DETECTOR_VERSION = "output-contract-detector-v1"
CONTRACT_TYPES = {
    "none",
    "tail_html",
    "tail_markdown",
    "tail_json",
    "inline_section",
    "full_document",
    "unknown",
}

_DETAILS_RE = re.compile(r"<details\b", re.IGNORECASE)
_SUMMARY_RE = re.compile(r"<summary\b[^>]*>(.*?)</summary>", re.IGNORECASE | re.DOTALL)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_CUSTOM_TAG_RE = re.compile(
    r"<(?P<tag>(?:[A-Z][a-zA-Z]*[A-Z][a-zA-Z]*)|(?:[a-z]+\d+))\b"
)
_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{[^{}\n]{1,80}\}(?!\})")
_DOUBLE_BRACE_RE = re.compile(r"\{\{[^{}\n]{1,100}\}\}")
_JSON_FENCE_RE = re.compile(r"```json\b", re.IGNORECASE)
_MARKDOWN_TABLE_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
_HTML_RE = re.compile(r"<[a-zA-Z][^>]*>")

_FORMAT_HINTS = (
    "格式要求",
    "输出格式",
    "状态栏",
    "后台日志",
    "隐藏剧情",
    "选项区块",
    "章节号",
    "必须严格按照以下顺序",
)


def _strip_tags(text: str) -> str:
    return _TAG_STRIP_RE.sub("", text or "").strip()


def _entry_order(entry: dict) -> int:
    try:
        return int(entry.get("order", 100) or 100)
    except (TypeError, ValueError):
        return 100


def _log_entry_contract(
    entry: dict,
    contract: dict[str, Any],
    *,
    phase: str,
) -> None:
    """记录 entry 的最终识别结果，不输出世界书原文。"""
    definition = contract.get("definition") if isinstance(contract.get("definition"), dict) else {}
    provenance = contract.get("provenance") if isinstance(contract.get("provenance"), dict) else {}
    lifecycle = contract.get("lifecycle") if isinstance(contract.get("lifecycle"), dict) else {}
    try:
        definition_text = json.dumps(
            definition,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
    except (TypeError, ValueError):
        definition_text = repr(definition)

    if len(definition_text) > 4000:
        definition_text = f"{definition_text[:4000]}...(truncated)"

    logger.info(
        "[输出契约识别] phase=%s uid=%s comment=%r kind=%s enabled=%s "
        "status=%s reviewed=%s source=%s trigger=%s confidence=%.2f reason=%r definition=%s",
        phase,
        entry.get("uid"),
        str(entry.get("comment") or "")[:120],
        definition.get("document_kind"),
        contract.get("enabled", True),
        lifecycle.get("status"),
        lifecycle.get("reviewed", False),
        provenance.get("source"),
        provenance.get("trigger"),
        float(provenance.get("confidence") or 0),
        provenance.get("reason"),
        definition_text,
    )


def _base_contract(
    *,
    ctype: str,
    status: str,
    source: str,
    confidence: float,
    entry: dict,
    abstract: dict[str, Any] | None,
    reason: str = "",
    trigger: str = "auto_import",
) -> dict[str, Any]:
    return {
        "type": ctype,
        "status": status,
        "source": source,
        # trigger 区分识别触发来源：auto_import（导入/编辑期自动）/ manual（用户主动）/
        # edit（内容改动重扫）。用于 ADR-1e 主契约权威性优先级，与识别手段 source 正交。
        "trigger": trigger,
        "confidence": float(confidence),
        "content_hash": content_hash(str(entry.get("content") or "")),
        "detector_version": DETECTOR_VERSION,
        "reviewed": False,
        "reason": reason,
        "abstract": abstract,
    }


def _none_contract(
    entry: dict, *, source: str = "heuristic", trigger: str = "auto_import"
) -> dict[str, Any]:
    return _base_contract(
        ctype="none",
        status="none",
        source=source,
        confidence=1.0 if source == "heuristic" else 0.0,
        entry=entry,
        abstract=None,
        reason="未发现输出格式模板特征",
        trigger=trigger,
    )


def _unknown_contract(
    entry: dict, reason: str, *, trigger: str = "auto_import"
) -> dict[str, Any]:
    return _base_contract(
        ctype="unknown",
        status="unknown",
        source="llm",
        confidence=0.0,
        entry=entry,
        abstract=None,
        reason=reason[:80],
        trigger=trigger,
    )


def _marker_from_entry(entry: dict, fallback: str = "") -> str:
    content = str(entry.get("content") or "")
    match = _SUMMARY_RE.search(content)
    if match:
        marker = _strip_tags(match.group(1))
        if marker:
            return marker
    return str(entry.get("comment") or "").strip() or fallback or f"条目#{entry.get('uid', '?')}"


def _tail_abstract(
    entry: dict,
    marker: str,
    *,
    placement: str = "tail",
    span_hint: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "placement": placement,
        "once_per_reply": True,
        "markers": [marker] if marker else [],
        "sections": [{
            "name": marker or "尾部模板",
            "marker": marker,
            "required": True,
            "order": _entry_order(entry),
        }],
        "variables": [],
        "template_span_hint": span_hint or {},
    }


def _detect_entry_heuristic_proposal(entry: dict) -> dict[str, Any]:
    """用高置信度规则识别单条 entry 的输出契约。"""
    if not isinstance(entry, dict):
        return _unknown_contract({}, "entry 非对象")

    content = str(entry.get("content") or "")
    comment = str(entry.get("comment") or "")
    text = f"{comment}\n{content}"
    if not content.strip() or is_mvu_tagged_entry(entry):
        return _none_contract(entry)

    marker = _marker_from_entry(entry)
    has_details = bool(_DETAILS_RE.search(content))
    has_summary = bool(_SUMMARY_RE.search(content))
    has_placeholder = bool(_PLACEHOLDER_RE.search(content) or _DOUBLE_BRACE_RE.search(content))
    has_custom_tag = bool(_CUSTOM_TAG_RE.search(content))
    has_format_hint = any(hint in text for hint in _FORMAT_HINTS)

    if "必须严格按照以下顺序" in text or (
        "格式要求" in text and all(hint in text for hint in ("选项", "后台日志", "隐藏剧情"))
    ):
        return _base_contract(
            ctype="full_document",
            status="detected",
            source="heuristic",
            confidence=0.88,
            entry=entry,
            reason="检测到整篇结构格式要求",
            abstract={
                "placement": "full_document",
                "once_per_reply": True,
                "markers": [],
                "sections": [
                    {"name": "chapter", "marker": "#", "required": True, "order": 10},
                    {"name": "body", "marker": "", "required": True, "order": 20},
                    {"name": "options", "marker": "> **A.**", "required": True, "order": 30},
                    {"name": "backend_log", "marker": "后台日志", "required": True, "order": 40},
                    {"name": "hidden_plot", "marker": "隐藏剧情", "required": True, "order": 50},
                ],
                "variables": [],
                "template_span_hint": {},
            },
        )

    if has_details and (has_summary or has_placeholder or has_format_hint):
        return _base_contract(
            ctype="tail_html",
            status="detected",
            source="heuristic",
            confidence=0.92,
            entry=entry,
            reason="检测到 details 尾部模板",
            abstract=_tail_abstract(
                entry,
                marker,
                span_hint={
                    "start_marker": "<details",
                    "summary_text": marker,
                    "end_marker": "</summary>",
                },
            ),
        )

    if has_custom_tag and (has_placeholder or has_format_hint):
        return _base_contract(
            ctype="tail_html",
            status="detected",
            source="heuristic",
            confidence=0.82,
            entry=entry,
            reason="检测到自定义 HTML 标签模板",
            abstract=_tail_abstract(entry, marker, span_hint={"start_marker": "<"}),
        )

    if _JSON_FENCE_RE.search(content) and has_format_hint:
        return _base_contract(
            ctype="tail_json",
            status="detected",
            source="heuristic",
            confidence=0.78,
            entry=entry,
            reason="检测到 JSON 尾部模板",
            abstract=_tail_abstract(entry, marker or "JSON 状态"),
        )

    if _MARKDOWN_TABLE_RE.search(content) and has_format_hint:
        return _base_contract(
            ctype="tail_markdown",
            status="detected",
            source="heuristic",
            confidence=0.76,
            entry=entry,
            reason="检测到 Markdown 表格模板",
            abstract=_tail_abstract(entry, marker or "当前状态"),
        )

    if has_format_hint and any(hint in text for hint in ("选项", "后台日志", "隐藏剧情")):
        return _base_contract(
            ctype="inline_section",
            status="detected",
            source="heuristic",
            confidence=0.68,
            entry=entry,
            reason="检测到内联章节格式要求",
            abstract={
                "placement": "inline",
                "once_per_reply": True,
                "markers": [],
                "sections": [],
                "variables": [],
                "template_span_hint": {},
            },
        )

    return _none_contract(entry)


def _is_llm_candidate(entry: dict) -> bool:
    content = str(entry.get("content") or "")
    comment = str(entry.get("comment") or "")
    if not content.strip() or is_mvu_tagged_entry(entry):
        return False
    attachment = canonicalize_attachment(entry.get("output_contract"), entry)
    if attachment.get("lifecycle", {}).get("status") == "active":
        return True
    text = f"{comment}\n{content}"
    return (
        any(hint in text for hint in _FORMAT_HINTS)
        or bool(_HTML_RE.search(content))
        or bool(_MARKDOWN_TABLE_RE.search(content))
        or bool(_JSON_FENCE_RE.search(content))
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    """从 LLM 文本中尽力提取第一个 JSON 对象。"""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start:end + 1])
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _normalise_llm_contract(
    entry: dict, data: dict[str, Any], *, trigger: str = "auto_import"
) -> dict[str, Any]:
    ctype = str(data.get("type") or data.get("template_type") or "unknown")
    if ctype not in CONTRACT_TYPES:
        ctype = "unknown"
    confidence = data.get("confidence", 0.0)
    if not isinstance(confidence, (int, float)):
        confidence = 0.0
    confidence = max(0.0, min(1.0, float(confidence)))
    # 只产 LLM proposal；section 的 canonical 规范化（中文 name→英文、乱 marker→标准
    # marker）由下游 attachment.canonicalize_proposal → canonicalize_sections 统一完成
    # （ADR-2a 逻辑已收敛到 v2 Attachment 层），此处不再重复规范化。
    abstract = data.get("abstract")
    if not isinstance(abstract, dict):
        abstract = None
    reason = str(data.get("reason") or "")
    status = "none" if ctype == "none" else ("unknown" if ctype == "unknown" else "detected")
    return _base_contract(
        ctype=ctype,
        status=status,
        source="llm",
        confidence=confidence,
        entry=entry,
        abstract=abstract,
        reason=reason,
        trigger=trigger,
    )


async def _detect_entry_llm_proposal(entry: dict, *, trigger: str = "auto_import") -> dict[str, Any]:
    """调用 LLM 识别单条 entry 的输出契约。失败时返回 unknown。"""
    content = str(entry.get("content") or "")
    comment = str(entry.get("comment") or "")
    if not content.strip():
        return _none_contract(entry, source="llm", trigger=trigger)

    prompt = f"""你是一个世界书输出格式模板分析器。请判断下面 entry 是否要求 assistant 按固定用户可见格式输出。

只返回 JSON，不要解释。

类型：
- none: 普通设定/剧情/lore，不要求固定输出格式
- tail_html: 回复尾部追加 HTML 结构，如 details、div、table、自定义标签状态栏
- tail_markdown: 回复尾部追加 Markdown 表格/列表/状态栏
- tail_json: 回复尾部追加 JSON 代码块
- inline_section: 回复正文中必须包含若干章节或选项
- full_document: 整篇回复必须按固定顺序组织
- unknown: 无法可靠判断

要求：
- 不要编造变量
- 不要改写模板
- 不要返回 scaffold 正文，只返回原文定位线索
- 不能确定就返回 unknown

entry comment:
{comment}

entry content:
{content[:5000]}

返回 JSON schema:
{{
  "type": "none|tail_html|tail_markdown|tail_json|inline_section|full_document|unknown",
  "confidence": 0.0,
  "reason": "15字内原因",
  "abstract": {{
    "placement": "tail|inline|full_document|none",
    "once_per_reply": true,
    "markers": ["..."],
    "sections": [{{"name": "...", "marker": "...", "required": true, "order": 10}}],
    "variables": [{{"name": "...", "kind": "placeholder|macro|natural_language"}}],
    "template_span_hint": {{"start_marker": "...", "summary_text": "...", "end_marker": "..."}}
  }}
}}"""
    try:
        response = await call_deepseek_non_stream(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=900,
        )
        data = _extract_json_object(response)
        if not data:
            return _unknown_contract(entry, "LLM 返回非 JSON", trigger=trigger)
        return _normalise_llm_contract(entry, data, trigger=trigger)
    except Exception as exc:
        logger.warning("[输出契约识别] LLM 识别失败 uid=%s: %s", entry.get("uid"), exc)
        return _unknown_contract(entry, f"LLM 失败: {exc}", trigger=trigger)


def detect_entry_heuristic(entry: dict) -> dict[str, Any]:
    """用启发式生成 Proposal 并规范化为 v2 Attachment。"""
    proposal = _detect_entry_heuristic_proposal(entry)
    return canonicalize_proposal(entry, proposal, existing=entry.get("output_contract"))


async def detect_entry_llm(entry: dict, *, trigger: str = "auto_import") -> dict[str, Any]:
    """用 LLM 生成 Proposal 并规范化为 v2 Attachment。"""
    proposal = await _detect_entry_llm_proposal(entry, trigger=trigger)
    return canonicalize_proposal(entry, proposal, existing=entry.get("output_contract"))


def _existing_contract_fresh(entry: dict) -> bool:
    raw = entry.get("output_contract")
    if not isinstance(raw, dict):
        return False
    attachment = canonicalize_attachment(raw, entry)
    return not attachment_is_stale(attachment, entry)


async def annotate_entries(
    entries: list[dict] | None,
    *,
    llm_enabled: bool = False,
    llm_limit: int = 30,
) -> list[dict]:
    """为一批 entry 写入 output_contract。"""
    updated: list[dict] = []
    for raw in entries or []:
        entry = dict(raw or {})
        raw_contract = entry.get("output_contract")
        existing = canonicalize_attachment(raw_contract, entry) if isinstance(raw_contract, dict) else None
        if existing is not None and not attachment_is_stale(existing, entry):
            entry["output_contract"] = existing
            _log_entry_contract(
                entry,
                existing,
                phase="reuse",
            )
            updated.append(entry)
            continue
        proposal = _detect_entry_heuristic_proposal(entry)
        contract = canonicalize_proposal(
            entry,
            proposal,
            existing=existing,
            preserve_reviewed=bool(existing and existing.get("lifecycle", {}).get("reviewed")),
        )
        entry["output_contract"] = contract
        _log_entry_contract(
            entry,
            contract,
            phase="manual_override_preserved" if existing and existing.get("lifecycle", {}).get("reviewed") else "heuristic",
        )
        updated.append(entry)

    if not llm_enabled or llm_limit <= 0:
        return updated

    candidate_indexes = [
        idx for idx, entry in enumerate(updated)
        if _is_llm_candidate(entry)
    ][:llm_limit]
    for idx in candidate_indexes:
        entry = updated[idx]
        existing = canonicalize_attachment(entry.get("output_contract"), entry)
        proposal = await _detect_entry_llm_proposal(entry)
        contract = canonicalize_proposal(
            entry,
            proposal,
            existing=existing,
            preserve_reviewed=bool(existing.get("lifecycle", {}).get("reviewed")),
        )
        updated[idx]["output_contract"] = contract
        _log_entry_contract(updated[idx], contract, phase="llm")
    return updated


async def detect_single_entry(entry: dict) -> dict:
    """用户主动触发单条 entry AI 识别。"""
    updated = dict(entry or {})
    existing = canonicalize_attachment(updated.get("output_contract"), updated) if isinstance(updated.get("output_contract"), dict) else None
    proposal = await _detect_entry_llm_proposal(updated, trigger="manual")
    contract = canonicalize_proposal(
        updated,
        proposal,
        existing=existing,
        preserve_reviewed=bool(existing and existing.get("lifecycle", {}).get("reviewed")),
    )
    updated["output_contract"] = contract
    _log_entry_contract(updated, contract, phase="manual_llm")
    return updated


def build_manual_contract(
    entry: dict,
    *,
    mode: str = "full_document",
    section_names: list[str] | None = None,
) -> dict[str, Any]:
    """用户显式声明的输出模板 → source=manual、reviewed=true 契约（ADR-2b）。

    与识别（推断）相反：这是用户在编辑器里直接声明的结果，权威性最高
    （compiler._authority_key 里 reviewed / source=manual 为 level 4），运行时优先于
    任何启发式 / LLM 识别。支持三种 `mode`：
    - `full_document`：勾选 canonical section 组成整篇结构；
    - `append_tail`（ADR-2e）：声明本 entry.content 为尾部模板，marker / span_hint 从
      原文确定性提取（复用启发式 `_marker_from_entry` / `_tail_abstract`），运行时在回复
      尾部续写；
    - `none` 或空 full_document 选择：记为“用户声明无模板”（status=none，运行时不激活，
      且 _existing_contract_fresh 视为新鲜，不再被自动重识别覆盖）。
    """
    if mode == "append_tail":
        marker = _marker_from_entry(entry)
        abstract = _tail_abstract(
            entry,
            marker,
            span_hint={
                "start_marker": "<details",
                "summary_text": marker,
                "end_marker": "</summary>",
            },
        )
        return apply_manual_definition(
            entry,
            {
                "document_kind": "tail_html",
                **abstract,
            },
            existing=entry.get("output_contract"),
        )

    names = [n for n in (section_names or []) if get_canonical(n) is not None]
    if mode != "full_document" or not names:
        return apply_manual_definition(
            entry,
            {"document_kind": "none", "sections": []},
            existing=entry.get("output_contract"),
        )

    sections = []
    seen: set[str] = set()
    for name in names:
        cs = get_canonical(name)
        if cs.name in seen:
            continue
        seen.add(cs.name)
        sections.append({
            "name": cs.name,
            "marker": cs.marker,
            "required": True,
            "order": cs.order,
        })
    abstract = {
        "placement": "full_document",
        "once_per_reply": True,
        "markers": [],
        "sections": sections,
        "variables": [],
        "template_span_hint": {},
    }
    return apply_manual_definition(
        entry,
        {"document_kind": "full_document", **abstract},
        existing=entry.get("output_contract"),
    )
