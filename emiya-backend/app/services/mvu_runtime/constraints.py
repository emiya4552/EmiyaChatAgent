# -*- coding: utf-8 -*-
"""MVU 约束提取（ADR-0005，有界 / 尽力而为）。

约束用于 update_core 的 range clamp / enum 校验。来源是本轮激活的 `[mvu_update]`
世界书条目内容——很多卡（如伶伶）把变量规则写成 YAML-ish 结构：

    变量更新规则:
      伶伶:
        当前好感度:
          type: number
          range: 0~100
        当前情绪:
          type: string
          check:
            - 必须且只能从以下7个词汇中选择一个：开心、平静、伤心、发情、生气、害羞、诱惑

我们只提取能干净解析出来的：type / range(min,max) / enum。解析不了就跳过（best-effort），
绝不猜。keys 用点路径，与 stat_data 根对齐（`伶伶.当前好感度`）。
"""
from __future__ import annotations

import re

_RANGE_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*~\s*(-?\d+(?:\.\d+)?)")
# "……：开心、平静、伤心" —— 取最后一个中/英文冒号后的顿号列表
_ENUM_RE = re.compile(r"[:：]\s*([^\n:：]+)$")
_LEAF_KEYS = {"type", "range", "check", "enum"}


def _num(s: str):
    f = float(s)
    return int(f) if f.is_integer() else f


def _parse_enum_from_check(check) -> list[str] | None:
    items = check if isinstance(check, list) else [check]
    for raw in items:
        text = str(raw or "")
        if "从以下" not in text and "只能" not in text and "以下" not in text:
            continue
        m = _ENUM_RE.search(text.strip())
        if not m:
            continue
        parts = re.split(r"[、,，/|]", m.group(1).strip())
        vals = [p.strip() for p in parts if p.strip()]
        if len(vals) >= 2:
            return vals
    return None


def _leaf_constraint(node: dict) -> dict | None:
    c: dict = {}
    t = node.get("type")
    if isinstance(t, str):
        t = t.strip().lower()
        if t in ("number", "int", "integer", "float", "boolean", "bool", "string", "str"):
            c["type"] = {"int": "number", "integer": "number", "float": "number",
                         "bool": "boolean", "str": "string"}.get(t, t)
    rng = node.get("range")
    if rng is not None:
        m = _RANGE_RE.search(str(rng))
        if m:
            lo, hi = _num(m.group(1)), _num(m.group(2))
            c["min"], c["max"] = min(lo, hi), max(lo, hi)
    if "check" in node:
        enum = _parse_enum_from_check(node.get("check"))
        if enum:
            c["enum"] = enum
            c.setdefault("type", "string")
    return c or None


def _walk(node, path: list[str], out: dict) -> None:
    if not isinstance(node, dict):
        return
    if _LEAF_KEYS & set(node.keys()):
        c = _leaf_constraint(node)
        if c and path:
            out[".".join(path)] = c
        return
    for k, v in node.items():
        if isinstance(v, dict):
            _walk(v, path + [str(k)], out)


def extract_constraints_from_entries(wi_activated: list[dict] | None) -> dict[str, dict]:
    """从激活的 `[mvu_update]` 条目内容里提取约束表 {dot_path: {type,min,max,enum}}。"""
    from app.services.mvu_runtime.runtime_view import classify_mvu_comment

    out: dict[str, dict] = {}
    for entry in wi_activated or []:
        if classify_mvu_comment(entry.get("comment")) != "update":
            continue
        content = str(entry.get("content") or "")
        if not content.strip():
            continue
        try:
            import yaml
            parsed = yaml.safe_load(content)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        # 顶层可能是 {变量更新规则: {...}} 或直接就是字段树；两种都走 _walk
        roots = list(parsed.values()) if len(parsed) == 1 and all(
            isinstance(v, dict) for v in parsed.values()
        ) else [parsed]
        for root in roots:
            _walk(root, [], out)
    return out
