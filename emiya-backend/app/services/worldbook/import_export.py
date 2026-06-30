# -*- coding: utf-8 -*-
"""世界书导入 / 导出：ST native .json + 角色卡 character_book 字段。

参见 docs/adr/0001（extras 兼容字段）+ ADR-0003（position 全保真）。
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── 我们一等公民的 entry 字段集 ──
KNOWN_ENTRY_FIELDS = {
    "uid", "comment", "enabled", "content",
    "constant", "selective", "use_regex",
    "key", "keysecondary", "selective_logic",
    "scan_depth", "case_sensitive", "match_whole_words",
    "position", "depth", "order", "role",
    "ignore_budget", "outlet_name",
    "extras",
}


# ── v3 character_book.entries[].position 字符串 → 内部 int ──
_V3_POSITION_STR_TO_INT = {
    "before_char": 0,
    "after_char": 1,
}


def _resolve_v3_position(entry: dict, ext: dict) -> int:
    """v3 字符卡 position 解析：extensions.position(int) > 顶层 position > 0。

    顶层 position 在 v3 spec 里是字符串 "before_char" / "after_char"；
    某些卡也可能直接放 int。两者都要兼容。
    """
    ext_pos = ext.get("position")
    if isinstance(ext_pos, int):
        return ext_pos

    top = entry.get("position")
    if isinstance(top, int):
        return top
    if isinstance(top, str):
        return _V3_POSITION_STR_TO_INT.get(top, 0)

    return 0

# ST 字段 → 我们字段的映射（仅那些命名不同的；同名不列）
_ST_NAME_REMAP = {
    "selectiveLogic": "selective_logic",
    "scanDepth": "scan_depth",
    "caseSensitive": "case_sensitive",
    "matchWholeWords": "match_whole_words",
    "ignoreBudget": "ignore_budget",
    "outletName": "outlet_name",
}


def _normalize_role(v: Any) -> str:
    """ST 用 0/1/2 数字表示 system/user/assistant；我们用字符串。"""
    if isinstance(v, str):
        return v.lower() if v.lower() in ("system", "user", "assistant") else "system"
    if isinstance(v, int):
        return {0: "system", 1: "user", 2: "assistant"}.get(v, "system")
    return "system"


def from_st_entry(st_entry: dict) -> dict:
    """ST native entry → 我们的 entry 形式。未识别字段塞 extras。"""
    out: dict = {
        "uid": int(st_entry.get("uid", 0)),
        "comment": st_entry.get("comment", "") or "",
        "enabled": not bool(st_entry.get("disable", False)),
        "content": st_entry.get("content", "") or "",
        "constant": bool(st_entry.get("constant", False)),
        # ST native 这两字段：selective 历史默认 true（addMemo 之后才填的卡），useRegex 默认 false
        "selective": bool(st_entry.get("selective", False)),
        "use_regex": bool(st_entry.get("useRegex", False)),
        "key": list(st_entry.get("key", []) or []),
        "keysecondary": list(st_entry.get("keysecondary", []) or []),
        "selective_logic": int(st_entry.get("selectiveLogic", 0)),
        "scan_depth": st_entry.get("scanDepth"),
        "case_sensitive": st_entry.get("caseSensitive"),
        "match_whole_words": st_entry.get("matchWholeWords"),
        "position": int(st_entry.get("position", 0)),
        "depth": int(st_entry.get("depth", 4)),
        "order": int(st_entry.get("order", 100)),
        "role": _normalize_role(st_entry.get("role", 0)),
        "ignore_budget": bool(st_entry.get("ignoreBudget", False)),
        "outlet_name": st_entry.get("outletName") or None,
    }

    # extras：保留所有未识别字段（ST 高级语义如 sticky/cooldown/probability 等）
    consumed_st_keys = {
        "uid", "comment", "disable", "content", "constant", "selective", "useRegex",
        "key", "keysecondary",
        "selectiveLogic", "scanDepth", "caseSensitive", "matchWholeWords",
        "position", "depth", "order", "role", "ignoreBudget", "outletName",
    }
    extras = {k: v for k, v in st_entry.items() if k not in consumed_st_keys}
    if extras:
        out["extras"] = extras
    return out


def to_st_entry(entry: dict) -> dict:
    """我们的 entry → ST native entry。extras 字段原样合并回顶层。"""
    out: dict = {
        "uid": entry.get("uid", 0),
        "comment": entry.get("comment", ""),
        "disable": not bool(entry.get("enabled", True)),
        "content": entry.get("content", ""),
        "constant": bool(entry.get("constant", False)),
        "key": list(entry.get("key", []) or []),
        "keysecondary": list(entry.get("keysecondary", []) or []),
        "selectiveLogic": int(entry.get("selective_logic", 0)),
        "scanDepth": entry.get("scan_depth"),
        "caseSensitive": entry.get("case_sensitive"),
        "matchWholeWords": entry.get("match_whole_words"),
        "position": int(entry.get("position", 0)),
        "depth": int(entry.get("depth", 4)),
        "order": int(entry.get("order", 100)),
        "role": entry.get("role", "system"),
        "ignoreBudget": bool(entry.get("ignore_budget", False)),
        "outletName": entry.get("outlet_name") or "",
        # ST native 字段：selective 缺省回到导入前的值或 ST 默认 true；useRegex 同步导出
        "selective": bool(entry.get("selective", True)),
        "useRegex": bool(entry.get("use_regex", False)),
        "vectorized": False,
        "addMemo": bool(entry.get("comment")),
    }
    # extras 原样还原
    extras = entry.get("extras") or {}
    for k, v in extras.items():
        if k not in out:
            out[k] = v
    return out


# ─── ST native 整本互转 ───────────────────────────────────────


def import_st_worldbook(data: dict) -> dict:
    """ST native worldbook JSON → 我们的 Worldbook 字段 dict（不含 id/user_id）。"""
    entries_raw = data.get("entries", {})
    # ST 用 {uid_str: entry} 形式；少数旧版本可能用 list
    if isinstance(entries_raw, dict):
        entries_list = [from_st_entry(e) for e in entries_raw.values()]
    elif isinstance(entries_raw, list):
        entries_list = [from_st_entry(e) for e in entries_raw]
    else:
        raise ValueError("worldbook JSON 中 entries 字段非法")

    # name 字段保持 None / 空 透传，让调用方按 文件名 > 通用兜底 的顺序补
    raw_name = data.get("name")
    return {
        "name": raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else None,
        "description": data.get("description"),
        "scan_depth": int(data.get("scan_depth", data.get("scanDepth", 2))),
        "case_sensitive": bool(data.get("case_sensitive", False)),
        "match_whole_words": bool(data.get("match_whole_words", False)),
        "entries": entries_list,
        "extensions": data.get("extensions") or {},
    }


def export_st_worldbook(wb_dict: dict) -> dict:
    """Worldbook ORM 转 dict → ST native 格式 JSON。"""
    entries_list = wb_dict.get("entries", []) or []
    st_entries = {str(e.get("uid", i)): to_st_entry(e) for i, e in enumerate(entries_list)}
    return {
        "name": wb_dict.get("name", ""),
        "description": wb_dict.get("description"),
        "scan_depth": wb_dict.get("scan_depth", 2),
        "case_sensitive": wb_dict.get("case_sensitive", False),
        "match_whole_words": wb_dict.get("match_whole_words", False),
        "entries": st_entries,
        "extensions": wb_dict.get("extensions") or {},
    }


# ─── 角色卡 character_book 字段（v2/v3） ─────────────────────


def from_character_book(character_book: dict, persona_name: str = "") -> dict:
    """v2/v3 character_book → 我们的 Worldbook 字段 dict。

    character_book 是角色卡内嵌的子结构，entries 是 list[dict]，字段命名 snake_case。
    """
    raw_entries = character_book.get("entries") or []
    out_entries: list[dict] = []
    for idx, e in enumerate(raw_entries):
        ext = e.get("extensions") or {}
        out_entries.append({
            "uid": int(e.get("id", idx)),
            "comment": e.get("comment", "") or "",
            "enabled": bool(e.get("enabled", True)),
            "content": e.get("content", "") or "",
            "constant": bool(e.get("constant", False)),
            "selective": bool(e.get("selective", False)),
            "use_regex": bool(e.get("use_regex", False)),
            "key": list(e.get("keys", []) or []),
            "keysecondary": list(e.get("secondary_keys", []) or []),
            "selective_logic": int(ext.get("selectiveLogic", 0)),
            "scan_depth": ext.get("scan_depth"),
            "case_sensitive": ext.get("case_sensitive"),
            "match_whole_words": ext.get("match_whole_words"),
            "position": _resolve_v3_position(e, ext),
            "depth": int(ext.get("depth", 4)),
            "order": int(e.get("insertion_order", 100)),
            "role": _normalize_role(ext.get("role", 0)),
            "ignore_budget": bool(ext.get("ignore_budget", False)),
            "outlet_name": ext.get("outlet_name") or None,
            "extras": {
                k: v for k, v in ext.items() if k not in {
                    "selectiveLogic", "scan_depth", "case_sensitive",
                    "match_whole_words", "position", "depth", "role",
                    "ignore_budget", "outlet_name",
                }
            },
        })

    book_name = character_book.get("name") or (
        f"{persona_name} - 内嵌设定" if persona_name else "内嵌世界书"
    )
    return {
        "name": book_name,
        "description": character_book.get("description"),
        "scan_depth": int(character_book.get("scan_depth", 2)),
        "case_sensitive": bool(character_book.get("case_sensitive", False)),
        "match_whole_words": bool(character_book.get("match_whole_words", False)),
        "entries": out_entries,
        "extensions": character_book.get("extensions") or {},
    }
