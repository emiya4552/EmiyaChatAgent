# -*- coding: utf-8 -*-
"""MVU 变量驱动扫描（ADR-0004，WuWa 档，默认关闭）。

把选定的 `stat_data` 点路径渲染成扫描文本，喂给世界书扫描器，让带关键词的条目能被
当前变量激活。这是对 ST 里 `calculateStoryLogic` 注入 `should_scan` 触发器的**尽力而为
替代**——EMIYA 不执行卡内 JS，只读已声明/已写入的变量，因此：
  - 只扫白名单里的路径，不把整棵 stat_data 转储进扫描缓冲区（噪声大、易误激活）；
  - 派生显示字段（ST 由 JS 算出的 剧情显示 等）EMIYA 没有，早期回合可能扫不出东西。
详见 docs/mvu/adr/0004。
"""
from __future__ import annotations

from typing import Any


def _stat_data(variables: dict | None) -> dict:
    v = variables or {}
    sd = v.get("stat_data")
    return sd if isinstance(sd, dict) else v


def _get_path(root: Any, path: str) -> tuple[bool, Any]:
    """按点路径取值。路径可带可不带 `stat_data.` 前缀。返回 (found, value)。"""
    segs = [s for s in path.replace("stat_data.", "", 1).split(".") if s]
    cur = root
    for seg in segs:
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        elif isinstance(cur, list) and seg.lstrip("-").isdigit():
            idx = int(seg)
            if -len(cur) <= idx < len(cur):
                cur = cur[idx]
            else:
                return False, None
        else:
            return False, None
    return True, cur


def _preview(value: Any, limit: int = 80) -> str:
    if isinstance(value, (dict, list)):
        import json
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def build_mvu_scan_text(
    variables: dict | None,
    paths: list[str] | None,
) -> tuple[str, list[dict]]:
    """渲染白名单路径为扫描文本。

    Returns:
        (scan_text, items)：
          scan_text 形如 "路径: 值\\n路径: 值"（喂给扫描器做关键词匹配）；
          items 为诊断项 [{path, found, value_preview}]。
    """
    if not paths:
        return "", []
    root = _stat_data(variables)
    lines: list[str] = []
    items: list[dict] = []
    for path in paths:
        if not isinstance(path, str) or not path.strip():
            continue
        found, value = _get_path(root, path.strip())
        preview = _preview(value) if found else ""
        items.append({"path": path.strip(), "found": found, "value_preview": preview})
        if found and preview:
            # 同时放"路径 值"和"值"，让关键词既能命中字段名也能命中值文本
            lines.append(f"{path.strip()}: {preview}")
    return "\n".join(lines), items
