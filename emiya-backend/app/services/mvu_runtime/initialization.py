# -*- coding: utf-8 -*-
"""MVU initialization sources and compatibility diagnostics.

ADR MVU-0002 intentionally keeps this module conservative: it reads explicit
state declarations and statically obvious defaults, but it never evaluates card
JavaScript.
"""
from __future__ import annotations

import ast
import copy
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.mvu_runtime.json_safe import make_json_safe

MVU_META_KEY = "_mvu"

_ENTRY_TAG_RE = re.compile(r"\[(initvar|opening)\]", re.IGNORECASE)
_CODE_FENCE_RE = re.compile(
    r"```(?:json|yaml|yml)?\s*(.*?)```",
    re.IGNORECASE | re.DOTALL,
)
_SCRIPT_IMPORT_RE = re.compile(r"\b(?:import\s*\(|fetch\s*\(|XMLHttpRequest)\b")
_DYNAMIC_DEFAULT_RE = re.compile(r"\.default\s*\(\s*(?:\(\s*\)\s*=>|function\b)")
_STATIC_DEFAULT_RE = re.compile(
    r"""^\s*["']?([^"':{}(),]+)["']?\s*:\s*z\.[\w.()]+(?:\([^)]*\))?[^;\n]*?\.default\s*\((.+)\)\s*,?\s*$"""
)
_OBJECT_START_RE = re.compile(
    r"""^\s*["']?([^"':{}(),]+)["']?\s*:\s*z\.object\s*\(\s*\{\s*$"""
)


@dataclass
class InitialSource:
    """One parsed MVU initialization source."""

    kind: str
    label: str
    stat_data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _card_data_root(card_data: dict | None) -> dict:
    if not isinstance(card_data, dict):
        return {}
    data = card_data.get("data")
    return data if isinstance(data, dict) else card_data


def _iter_character_book_entries(card_data: dict | None) -> list[dict]:
    root = _card_data_root(card_data)
    book = root.get("character_book")
    if not isinstance(book, dict):
        return []
    entries = book.get("entries") or []
    return [e for e in entries if isinstance(e, dict)]


def _worldbook_entries(worldbooks: list[Any] | None) -> list[dict]:
    out: list[dict] = []
    for wb in worldbooks or []:
        for entry in getattr(wb, "entries", None) or []:
            if isinstance(entry, dict):
                out.append(entry)
    return out


def _entry_tags(entry: dict) -> set[str]:
    haystacks = [
        str(entry.get("comment") or ""),
        " ".join(str(x) for x in (entry.get("key") or []) if x is not None),
    ]
    tags: set[str] = set()
    for text in haystacks:
        for match in _ENTRY_TAG_RE.findall(text):
            tags.add(match.lower())
    return tags


def _parse_structured_text(text: str) -> tuple[dict | None, list[str]]:
    """Parse JSON/YAML text or the first JSON/YAML code fence."""
    warnings: list[str] = []
    payload = text.strip()
    fence = _CODE_FENCE_RE.search(payload)
    if fence:
        payload = fence.group(1).strip()
    if not payload:
        return None, warnings

    try:
        parsed = json.loads(payload)
    except Exception:
        try:
            import yaml
            parsed = yaml.safe_load(payload)
        except Exception as exc:
            warnings.append(f"初始化内容无法解析为 JSON/YAML: {exc}")
            return None, warnings

    if not isinstance(parsed, dict):
        warnings.append(f"初始化内容不是对象: {type(parsed).__name__}")
        return None, warnings
    return parsed, warnings


def _normalize_stat_data(parsed: dict) -> dict:
    if isinstance(parsed.get("stat_data"), dict):
        return make_json_safe(copy.deepcopy(parsed["stat_data"]))
    return make_json_safe(copy.deepcopy(parsed))


def _source_from_entry(kind: str, entry: dict, label: str) -> InitialSource | None:
    from app.services.message_pipeline import _parse_update_variable

    content = str(entry.get("content") or "")
    warnings: list[str] = []
    parsed: dict | None = None

    if "<UpdateVariable" in content:
        parsed = _parse_update_variable(content)
        if parsed is None:
            warnings.append("UpdateVariable 存在但没有可解析的 initvar")
    elif "<initvar" in content:
        parsed = _parse_update_variable(f"<UpdateVariable>{content}</UpdateVariable>")
        if parsed is None:
            warnings.append("initvar 存在但 YAML 解析失败")
    else:
        parsed, warnings = _parse_structured_text(content)

    if parsed is None and not warnings:
        return None
    return InitialSource(
        kind=kind,
        label=label,
        stat_data=_normalize_stat_data(parsed or {}),
        warnings=warnings,
    )


def _safe_literal(value_text: str):
    value_text = value_text.strip()
    if "=>" in value_text or "function" in value_text:
        raise ValueError("dynamic default")
    value_text = re.sub(r"\btrue\b", "True", value_text)
    value_text = re.sub(r"\bfalse\b", "False", value_text)
    value_text = re.sub(r"\bnull\b", "None", value_text)
    return ast.literal_eval(value_text)


def _set_deep(root: dict, path: list[str], value: Any) -> None:
    cur = root
    for seg in path[:-1]:
        nxt = cur.get(seg)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[seg] = nxt
        cur = nxt
    if path:
        cur[path[-1]] = value


def _extract_static_schema_defaults(script: str) -> tuple[dict, list[str]]:
    """Extract a tiny safe subset of Zod defaults from `stat_data` schemas.

    Supported shape:
        stat_data: z.object({
          user: z.object({
            wounded: z.boolean().default(false),
          }),
        })

    Anything dynamic is reported, not evaluated.
    """
    defaults: dict[str, Any] = {}
    warnings: list[str] = []
    if not isinstance(script, str):
        return defaults, warnings
    if _DYNAMIC_DEFAULT_RE.search(script):
        warnings.append("检测到动态 Zod default，已跳过执行")

    stack: list[str] = []
    in_stat_data = False
    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        obj = _OBJECT_START_RE.match(line)
        if obj:
            key = obj.group(1).strip()
            if key == "stat_data":
                in_stat_data = True
                stack = []
            elif in_stat_data:
                stack.append(key)
            continue

        match = _STATIC_DEFAULT_RE.match(line)
        if match and in_stat_data:
            key = match.group(1).strip()
            try:
                value = _safe_literal(match.group(2))
            except Exception:
                warnings.append(f"跳过非静态默认值: {'.'.join(stack + [key])}")
            else:
                _set_deep(defaults, stack + [key], value)
            continue

        if line.startswith("})") or line.startswith("}),") or line.startswith("});"):
            if stack:
                stack.pop()
            elif in_stat_data:
                in_stat_data = False

    return defaults, warnings


def _tavern_helper_scripts(card_data: dict | None) -> list[dict]:
    root = _card_data_root(card_data)
    ext = root.get("extensions") or {}
    if not isinstance(ext, dict):
        return []
    th = ext.get("tavern_helper") or {}
    if not isinstance(th, dict):
        return []
    scripts = th.get("scripts") or []
    return [s for s in scripts if isinstance(s, dict)]


def _regex_scripts(card_data: dict | None) -> list[dict]:
    root = _card_data_root(card_data)
    ext = root.get("extensions") or {}
    if not isinstance(ext, dict):
        return []
    scripts = ext.get("regex_scripts") or []
    return [s for s in scripts if isinstance(s, dict)]


def _looks_like_html_fragment(text: str) -> bool:
    return bool(re.search(r"<(?:details|summary|style|script|div|span)\b", text or "", re.I))


def _merge_override(base: dict, overlay: dict) -> dict:
    merged = copy.deepcopy(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _merge_override(merged[k], v)
        else:
            merged[k] = copy.deepcopy(v)
    return merged


def _merge_missing(dst: dict, src: dict, path: list[str], filled: list[str]) -> None:
    for k, v in (src or {}).items():
        key_path = path + [str(k)]
        if k not in dst:
            dst[k] = copy.deepcopy(v)
            filled.append(".".join(key_path))
            continue
        if isinstance(dst[k], dict) and isinstance(v, dict):
            _merge_missing(dst[k], v, key_path, filled)


def build_initial_state(
    *,
    card_data: dict | None,
    worldbooks: list[Any] | None = None,
) -> dict:
    """Build the combined MVU initial stat_data with ADR-0002 priority.

    Returned keys:
        stat_data: merged initial stat data
        sources: parsed source summaries
        warnings: parse/diagnostic warnings
        compatibility: card-level report
    """
    warnings: list[str] = []
    schema_defaults: dict[str, Any] = {}
    for script in _tavern_helper_scripts(card_data):
        content = script.get("content") or ""
        defaults, script_warnings = _extract_static_schema_defaults(content)
        schema_defaults = _merge_override(schema_defaults, defaults)
        warnings.extend(script_warnings)

    entry_sources: list[InitialSource] = []
    entries = _iter_character_book_entries(card_data) + _worldbook_entries(worldbooks)
    for idx, entry in enumerate(entries):
        tags = _entry_tags(entry)
        label = str(entry.get("comment") or f"entry#{idx + 1}")
        for kind in ("initvar", "opening"):
            if kind in tags:
                src = _source_from_entry(kind, entry, label)
                if src:
                    entry_sources.append(src)
                    warnings.extend(src.warnings)

    # Lower priority first, higher priority overrides it inside the seed.
    stat_data = copy.deepcopy(schema_defaults)
    for src in [s for s in entry_sources if s.kind == "initvar"]:
        stat_data = _merge_override(stat_data, src.stat_data)
    for src in [s for s in entry_sources if s.kind == "opening"]:
        stat_data = _merge_override(stat_data, src.stat_data)

    return {
        "stat_data": stat_data,
        "sources": [
            {
                "kind": s.kind,
                "label": s.label,
                "keys": sorted(str(k) for k in s.stat_data.keys()),
                "warnings": s.warnings,
            }
            for s in entry_sources
        ],
        "warnings": warnings,
        "compatibility": analyze_card_compatibility(
            card_data, worldbooks=worldbooks, extra_warnings=warnings,
        ),
    }


def merge_initial_state_missing_only(
    variables: dict | None,
    initial_state: dict,
    *,
    reloaded: bool = False,
) -> tuple[dict, list[str]]:
    """Merge `initial_state.stat_data` into Conversation.variables without overwrite."""
    merged = copy.deepcopy(variables or {})
    stat_data = merged.get("stat_data")
    if not isinstance(stat_data, dict):
        stat_data = {}
        merged["stat_data"] = stat_data

    filled: list[str] = []
    _merge_missing(stat_data, initial_state.get("stat_data") or {}, ["stat_data"], filled)

    now = datetime.now(timezone.utc).isoformat()
    meta = merged.get(MVU_META_KEY)
    if not isinstance(meta, dict):
        meta = {}
    meta.setdefault("initialized_at", now)
    if reloaded:
        meta["reloaded_at"] = now
    meta["seeded_keys"] = sorted(set((meta.get("seeded_keys") or []) + filled))
    meta["source_count"] = len(initial_state.get("sources") or [])
    meta["warnings"] = list(initial_state.get("warnings") or [])
    merged[MVU_META_KEY] = meta
    return make_json_safe(merged), filled


def describe_conversation_mvu_state(variables: dict | None) -> dict:
    variables = variables or {}
    stat_data = variables.get("stat_data")
    if not isinstance(stat_data, dict):
        stat_data = {}
    meta = variables.get(MVU_META_KEY)
    if not isinstance(meta, dict):
        meta = {}
    return {
        "initialized": bool(meta or stat_data),
        "stat_data_keys": sorted(str(k) for k in stat_data.keys()),
        "field_count": len(stat_data),
        "initialized_at": meta.get("initialized_at"),
        "last_reload_at": meta.get("reloaded_at") or meta.get("initialized_at"),
        "seeded_keys": meta.get("seeded_keys") or [],
        "source_count": meta.get("source_count") or 0,
        "warnings": meta.get("warnings") or [],
    }


def analyze_card_compatibility(
    card_data: dict | None,
    *,
    worldbooks: list[Any] | None = None,
    extra_warnings: list[str] | None = None,
) -> dict:
    """Return compact card-level MVU compatibility diagnostics."""
    entries = _iter_character_book_entries(card_data) + _worldbook_entries(worldbooks)
    scripts = _tavern_helper_scripts(card_data)
    regex_scripts = _regex_scripts(card_data)

    initvar_entries = 0
    opening_entries = 0
    html_fragments = 0
    initvar_labels: list[str] = []
    opening_labels: list[str] = []
    html_labels: list[str] = []
    for entry in entries:
        tags = _entry_tags(entry)
        label = str(entry.get("comment") or entry.get("name") or entry.get("uid") or "未命名条目")
        if "initvar" in tags:
            initvar_entries += 1
            initvar_labels.append(label)
        if "opening" in tags:
            opening_entries += 1
            opening_labels.append(label)
        if _looks_like_html_fragment(str(entry.get("content") or "")):
            html_fragments += 1
            html_labels.append(label)

    remote_scripts = 0
    schema_defaults = 0
    dynamic_defaults = 0
    remote_script_names: list[str] = []
    dynamic_default_script_names: list[str] = []
    for script in scripts:
        content = str(script.get("content") or "")
        name = str(script.get("name") or script.get("scriptName") or "未命名脚本")
        if _SCRIPT_IMPORT_RE.search(content):
            remote_scripts += 1
            remote_script_names.append(name)
        schema_defaults += content.count(".default(")
        dynamic_count = len(_DYNAMIC_DEFAULT_RE.findall(content))
        dynamic_defaults += dynamic_count
        if dynamic_count:
            dynamic_default_script_names.append(name)

    script_names = [
        str(s.get("name") or s.get("scriptName") or "未命名脚本")
        for s in scripts
    ]
    regex_script_names = [
        str(s.get("scriptName") or s.get("name") or s.get("id") or "未命名正则")
        for s in regex_scripts
    ]

    is_mvu = bool(scripts or initvar_entries or opening_entries or regex_scripts)
    unsupported: list[str] = []
    warnings = list(extra_warnings or [])
    if remote_scripts:
        unsupported.append("remote_script_import")
        warnings.append("检测到远程脚本/网络访问，本系统不会执行")
    if dynamic_defaults:
        unsupported.append("dynamic_zod_default")
    if scripts:
        unsupported.append("tavern_helper_runtime_js")
        warnings.append("Tavern Helper 脚本仅做静态诊断，不作为前端插件执行")

    supported: list[str] = []
    if initvar_entries:
        supported.append("initvar_worldbook_seed")
    if opening_entries:
        supported.append("opening_worldbook_seed")
    if schema_defaults:
        supported.append("static_schema_default_detection")
    if regex_scripts:
        supported.append("regex_scripts_import")
    if html_fragments:
        supported.append("sanitized_html_fragments")

    details: list[dict] = []

    def add_detail(
        *,
        code: str,
        status: str,
        title: str,
        summary: str,
        detail: str,
        count: int = 0,
        evidence: list[str] | None = None,
    ) -> None:
        details.append({
            "code": code,
            "status": status,
            "title": title,
            "summary": summary,
            "detail": detail,
            "count": count,
            "evidence": (evidence or [])[:20],
        })

    if initvar_entries:
        add_detail(
            code="initvar_worldbook_seed",
            status="supported",
            title="[initvar] 初始变量",
            summary=f"识别到 {initvar_entries} 条 [initvar] 初始化条目。",
            detail="创建对话和手动补全时会读取这些条目作为初始化数据源；它们不会因为 disabled 而被当作普通世界书注入 Prompt。",
            count=initvar_entries,
            evidence=initvar_labels,
        )
    if opening_entries:
        add_detail(
            code="opening_worldbook_seed",
            status="supported",
            title="[opening] 开场初始化",
            summary=f"识别到 {opening_entries} 条 [opening] 初始化条目。",
            detail="这些条目优先级高于 [initvar]，用于补齐开场阶段需要存在的 stat_data 字段；已有字段不会被覆盖。",
            count=opening_entries,
            evidence=opening_labels,
        )
    if schema_defaults:
        add_detail(
            code="static_schema_default_detection",
            status="supported",
            title="静态 Schema 默认值",
            summary=f"检测到 {schema_defaults} 个 .default(...) 声明。",
            detail="系统只读取字面量默认值，例如字符串、数字、布尔值和 null；不会执行函数、表达式或 transform/refine。",
            count=schema_defaults,
            evidence=script_names,
        )
    if regex_scripts:
        add_detail(
            code="regex_scripts_import",
            status="supported",
            title="卡内正则脚本",
            summary=f"识别到 {len(regex_scripts)} 条 regex_scripts。",
            detail="导入确认时会拆成独立 RegexPreset 并挂到角色卡默认正则；运行时通过后端 JS 正则兼容层处理 prompt/reply 阶段。",
            count=len(regex_scripts),
            evidence=regex_script_names,
        )
    if html_fragments:
        add_detail(
            code="sanitized_html_fragments",
            status="supported",
            title="HTML 美化片段",
            summary=f"检测到 {html_fragments} 个可能的 HTML 美化片段。",
            detail="聊天渲染会用 DOMPurify 清洗后展示 HTML 片段；整页 HTML 代码块走 iframe 渲染。",
            count=html_fragments,
            evidence=html_labels,
        )
    if scripts:
        add_detail(
            code="tavern_helper_runtime_js",
            status="unsupported",
            title="Tavern Helper 运行时脚本",
            summary=f"检测到 {len(scripts)} 个助手脚本，但不会作为前端插件执行。",
            detail="EMIYA 当前采用后端兼容层重写 MVU 协议，不加载第三方前端插件，也不执行卡内任意 JS。已知协议会逐步在后端边界内实现。",
            count=len(scripts),
            evidence=script_names,
        )
    if remote_scripts:
        add_detail(
            code="remote_script_import",
            status="unsupported",
            title="远程脚本 / 网络访问",
            summary=f"检测到 {remote_scripts} 处 import/fetch/XMLHttpRequest。",
            detail="为了避免角色卡执行任意网络访问或加载未知代码，系统不会执行这类脚本；相关效果需要在受控兼容层中单独实现。",
            count=remote_scripts,
            evidence=remote_script_names,
        )
    if dynamic_defaults:
        add_detail(
            code="dynamic_zod_default",
            status="unsupported",
            title="动态 Zod 默认值",
            summary=f"检测到 {dynamic_defaults} 个动态 default。",
            detail="`.default(() => ...)` 或函数式默认值需要执行 JS 才能得到结果，当前只报告并跳过，避免隐式运行卡内代码。",
            count=dynamic_defaults,
            evidence=dynamic_default_script_names,
        )

    level = "none"
    if is_mvu:
        level = "partial" if unsupported else "supported"

    return {
        "is_mvu_card": is_mvu,
        "level": level,
        "features": {
            "initvar_entries": initvar_entries,
            "opening_entries": opening_entries,
            "tavern_helper_scripts": len(scripts),
            "remote_scripts": remote_scripts,
            "regex_scripts": len(regex_scripts),
            "html_fragments": html_fragments,
            "schema_defaults": schema_defaults,
        },
        "supported": supported,
        "unsupported": unsupported,
        "details": details,
        "warnings": sorted(set(warnings)),
    }
