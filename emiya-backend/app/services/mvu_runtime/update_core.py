# -*- coding: utf-8 -*-
"""MVU 更新通道核心：校验 + 应用（ADR-0005）。

文本 `<UpdateVariable>` 通道和 tool_call 通道都把更新规范化成一批 JSON Patch op，
经过**同一个有界校验层**后再写 stat_data：

- 恒开（无需 schema）：拒绝写 `_` 前缀只读路径；按当前值类型强转 value。
- 尽力而为（有约束才做）：range clamp / enum 校验（约束来自 `constraints.py`）。
- 无效 op 丢弃、绝不写坏 state，全部进诊断。

本模块只做"校验/规范化 op 列表"，真正的写入沿用 message_pipeline 的 JSON Patch 原语
（懒 import 规避循环依赖）。
"""
from __future__ import annotations

from typing import Any


def _decode(path: str) -> list[str]:
    from app.services.message_pipeline import _decode_json_pointer
    return _decode_json_pointer(str(path or ""))


def _current_value(stat_data: dict, segs: list[str]) -> tuple[bool, Any]:
    from app.services.message_pipeline import _get_path
    if not segs:
        return False, None
    val = _get_path(stat_data, segs)
    return (val is not None), val


_TRUE = {"true", "1", "yes", "y", "是", "真", "on"}
_FALSE = {"false", "0", "no", "n", "否", "假", "off"}


def _coerce(value: Any, cur_found: bool, cur_value: Any, ctype: str | None) -> tuple[Any, bool]:
    """把 value 强转成"当前值类型"（无当前值时看约束 type）。返回 (new, changed)。"""
    target = None
    if cur_found and cur_value is not None:
        if isinstance(cur_value, bool):
            target = "boolean"
        elif isinstance(cur_value, (int, float)):
            target = "number"
        elif isinstance(cur_value, str):
            target = "string"
    if target is None:
        target = ctype
    if target is None or value is None:
        return value, False

    try:
        if target == "boolean":
            if isinstance(value, bool):
                return value, False
            s = str(value).strip().lower()
            if s in _TRUE:
                return True, True
            if s in _FALSE:
                return False, True
            return value, False
        if target == "number":
            if isinstance(value, bool):
                return value, False
            if isinstance(value, (int, float)):
                return value, False
            s = str(value).strip()
            num = float(s)
            num = int(num) if num.is_integer() else num
            return num, True
        if target == "string":
            if isinstance(value, str):
                return value, False
            return str(value), True
    except (ValueError, TypeError):
        return value, False
    return value, False


def _apply_range_enum(value: Any, constraint: dict | None) -> tuple[Any, str | None]:
    """对 value 应用 min/max clamp 与 enum 校验。返回 (new_value, note)。

    note ∈ {None, "clamped", "enum-drop"}。
    """
    if not constraint:
        return value, None
    enum = constraint.get("enum")
    if enum and isinstance(value, str):
        if value not in enum:
            return value, "enum-drop"
    lo, hi = constraint.get("min"), constraint.get("max")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        clamped = value
        if lo is not None and clamped < lo:
            clamped = lo
        if hi is not None and clamped > hi:
            clamped = hi
        if clamped != value:
            if isinstance(value, int) and isinstance(clamped, float) and clamped.is_integer():
                clamped = int(clamped)
            return clamped, "clamped"
    return value, None


_VALUE_OPS = {"add", "replace", "assign", "set", "insert", "delta"}


def _has_readonly_segment(segs: list[str]) -> bool:
    return any(str(s).startswith("_") for s in segs)


def _json_pointer(segs: list[str]) -> str:
    if not segs:
        return ""
    escaped = [
        str(s).replace("~", "~0").replace("/", "~1")
        for s in segs
    ]
    return "/" + "/".join(escaped)


def _iter_init_values(value: Any, path: list[str] | None = None):
    path = path or []
    if isinstance(value, dict):
        if not value:
            yield path, {}
            return
        for key, child in value.items():
            yield from _iter_init_values(child, path + [str(key)])
        return
    if isinstance(value, list):
        if not value:
            yield path, []
            return
        for idx, child in enumerate(value):
            yield from _iter_init_values(child, path + [str(idx)])
        return
    yield path, value


def _new_container(next_seg: str | None) -> Any:
    return [] if next_seg is not None and str(next_seg).isdigit() else {}


def _set_init_path(root: dict, segs: list[str], value: Any) -> None:
    if not segs:
        return
    cur: Any = root
    for idx, seg in enumerate(segs[:-1]):
        nxt = segs[idx + 1] if idx + 1 < len(segs) else None
        if isinstance(cur, dict):
            if seg not in cur or not isinstance(cur[seg], (dict, list)):
                cur[seg] = _new_container(nxt)
            cur = cur[seg]
        elif isinstance(cur, list):
            list_idx = int(seg)
            while len(cur) <= list_idx:
                cur.append(_new_container(nxt))
            if not isinstance(cur[list_idx], (dict, list)):
                cur[list_idx] = _new_container(nxt)
            cur = cur[list_idx]
        else:
            return

    last = segs[-1]
    if isinstance(cur, dict):
        cur[last] = value
    elif isinstance(cur, list) and last.isdigit():
        list_idx = int(last)
        while len(cur) <= list_idx:
            cur.append(None)
        cur[list_idx] = value


def validate_ops(
    stat_data: dict,
    ops: list[dict],
    constraints: dict[str, dict] | None = None,
) -> tuple[list[dict], dict]:
    """校验 + 规范化一批 JSON Patch op（不写库）。

    Returns:
        (accepted_ops, diagnostics)
        diagnostics = {applied, dropped:[{path,reason}], coerced:[...], clamped:[...]}
    """
    constraints = constraints or {}
    accepted: list[dict] = []
    diag: dict = {"applied": 0, "dropped": [], "coerced": [], "clamped": []}

    for op in ops or []:
        if not isinstance(op, dict):
            diag["dropped"].append({"path": None, "reason": "op 非对象"})
            continue
        kind = str(op.get("op") or "").lower()
        raw_path = str(op.get("path") or "")
        segs = _decode(raw_path)

        # 恒开：`_` 前缀只读保护（含 move 的目标路径）
        if _has_readonly_segment(segs):
            diag["dropped"].append({"path": raw_path, "reason": "只读 `_` 路径"})
            continue

        if kind in ("move", "copy"):
            raw_from = str(op.get("from") or op.get("source") or "")
            from_segs = _decode(raw_from)
            if _has_readonly_segment(from_segs):
                diag["dropped"].append({"path": raw_from, "reason": "readonly `_` source path"})
                continue

        if kind in _VALUE_OPS and "value" in op:
            dot = ".".join(str(s) for s in segs)
            constraint = constraints.get(dot)
            ctype = (constraint or {}).get("type")
            cur_found, cur_value = _current_value(stat_data, segs)
            value = op.get("value")

            new_value, coerced = _coerce(value, cur_found, cur_value, ctype)
            if coerced:
                diag["coerced"].append({"path": raw_path, "from": value, "to": new_value})

            # delta 是增量，不做 range clamp（结果 clamp 交给未来）；只做 enum-drop 无意义 → 跳过
            if kind == "delta":
                current_number = (
                    cur_value
                    if isinstance(cur_value, (int, float)) and not isinstance(cur_value, bool)
                    else 0
                )
                if isinstance(new_value, (int, float)) and not isinstance(new_value, bool):
                    result_value, note = _apply_range_enum(current_number + new_value, constraint)
                    if note == "clamped":
                        diag["clamped"].append({"path": raw_path, "to": result_value})
                        new_value = result_value - current_number
            else:
                new_value, note = _apply_range_enum(new_value, constraint)
                if note == "enum-drop":
                    diag["dropped"].append({"path": raw_path, "reason": f"枚举外值: {value}"})
                    continue
                if note == "clamped":
                    diag["clamped"].append({"path": raw_path, "to": new_value})

            op = {**op, "value": new_value}

        accepted.append(op)

    diag["applied"] = len(accepted)
    return accepted, diag


def validate_initvar_state(
    stat_data: dict,
    new_state: dict,
    constraints: dict[str, dict] | None = None,
) -> tuple[dict, dict]:
    diag: dict = {"applied": 0, "dropped": [], "coerced": [], "clamped": []}
    if not isinstance(new_state, dict):
        diag["dropped"].append({"path": "", "reason": "initvar not object"})
        return {}, diag

    sanitized: dict = {}
    for path, value in _iter_init_values(new_state):
        if not path:
            continue
        op = {"op": "replace", "path": _json_pointer(path), "value": value}
        accepted, op_diag = validate_ops(stat_data or {}, [op], constraints)
        merge_diag(diag, op_diag)
        for accepted_op in accepted:
            _set_init_path(
                sanitized,
                _decode(accepted_op["path"]),
                accepted_op.get("value"),
            )
    return sanitized, diag


def merge_diag(dst: dict | None, src: dict | None) -> dict:
    """合并两个 diag（多通道/多块累加）。"""
    dst = dst or {"applied": 0, "dropped": [], "coerced": [], "clamped": []}
    if not src:
        return dst
    dst["applied"] += src.get("applied", 0)
    for k in ("dropped", "coerced", "clamped"):
        dst[k] = (dst.get(k) or []) + (src.get(k) or [])
    return dst
