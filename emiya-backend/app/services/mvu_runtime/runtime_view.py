# -*- coding: utf-8 -*-
"""MVU 诊断运行时视图（ADR-0003 §3）。

`mvu_runtime_view` 是一个**只读诊断对象**：把本轮激活的世界书条目里带 MVU 标签的
那些识别、分类出来，说明它们各自是什么角色、是否作为 prompt 注入。它**不持久化**、
不进列表响应，只在 message_done SSE 与按需诊断端点里派生（详见 docs/mvu/adr/0003）。

核心版（本 ADR）不改动注入：`[mvu_status]`/`[mvu_plot]` 仍走普通世界书注入
（对 伶伶 这类卡，`[mvu_status]` 作为"状态读数"进 prompt 是正确的 ST 行为）。真正把
它们从 prompt 里改道属默认关闭的 ADR-0004。
"""
from __future__ import annotations

import re

# comment 子串匹配，大小写不敏感，对齐 MVU bundle 的 `.toLowerCase().includes('[tag]')`
_TAG_TO_ROLE = {
    "mvu_update": "update",
    "mvu_status": "status",
    "mvu_plot": "plot",
    "initvar": "initvar",
    "opening": "opening",
}
_ROLE_RE = re.compile(r"\[(mvu_update|mvu_plot|mvu_status|initvar|opening)\]", re.I)

_ROLE_LABEL = {
    "update": "变量更新指令（教 LLM 输出 <UpdateVariable>）",
    "status": "状态读数（当前变量注入 prompt 供模型参考）",
    "plot": "剧情/扮演正文",
    "initvar": "初始变量种子",
    "opening": "开场初始化",
}


def classify_mvu_comment(comment: str | None) -> str | None:
    """按 comment 里的 `[tag]` 子串返回 MVU 角色；非 MVU 条目返回 None。"""
    m = _ROLE_RE.search(str(comment or ""))
    if not m:
        return None
    return _TAG_TO_ROLE[m.group(1).lower()]


def build_runtime_view(
    wi_activated: list[dict] | None,
    scan_items: list[dict] | None = None,
    update_diag: dict | None = None,
    update_channel: str | None = None,
    update_meta: dict | None = None,
) -> dict:
    """从本轮激活集派生 MVU 诊断视图。

    Args:
        wi_activated: node_activate_worldbook 产出的激活条目 dict 列表
            （含 comment / content / worldbook_id / worldbook_name 等）。
        scan_items: MVU 变量驱动扫描（ADR-0004）参与匹配的路径诊断
            [{path, found, value_preview}]；默认关闭时为空。
        update_diag: ADR-0005 更新校验诊断 {applied, dropped, coerced, clamped}。
        update_channel: 本轮实际生效的更新通道 tool/text/none。

    Returns:
        {
          "is_mvu": bool,
          "counts": {role: n},
          "entries": [...],
          "scan_items": [...],
          "update": {"channel", "applied", "dropped", "coerced", "clamped"},
          "diagnostics": [str, ...],
        }
    """
    entries: list[dict] = []
    counts: dict[str, int] = {}
    for e in wi_activated or []:
        role = classify_mvu_comment(e.get("comment"))
        if role is None:
            continue
        counts[role] = counts.get(role, 0) + 1
        entries.append({
            "role": role,
            "role_label": _ROLE_LABEL.get(role, role),
            "comment": str(e.get("comment") or ""),
            "worldbook_id": e.get("worldbook_id"),
            "worldbook_name": e.get("worldbook_name"),
            "chars": len(str(e.get("content") or "")),
            # 核心版：MVU 标签条目仍走普通注入 → 都作为 prompt 注入。ADR-0004 才 rerouting。
            "injected_as_prompt": True,
        })

    diagnostics: list[str] = []
    if counts.get("update"):
        diagnostics.append(
            f"{counts['update']} 条 [mvu_update] 指令已作为 prompt 注入；"
            "已从尾部模板兜底/续写中排除（不会被误当 HTML 输出模板）。"
        )
    if counts.get("status"):
        diagnostics.append(
            f"{counts['status']} 条 [mvu_status] 状态读数注入 prompt 供模型参考；"
            "可视状态栏由显示层 regex→HTML 出（ADR-0003 双管线），非此条目。"
        )
    if counts.get("plot"):
        diagnostics.append(
            f"{counts['plot']} 条 [mvu_plot] 作为剧情/扮演正文注入（非只扫描）。"
        )

    scan_items = scan_items or []
    if scan_items:
        hit = [s for s in scan_items if s.get("found")]
        diagnostics.append(
            f"变量驱动扫描（ADR-0004）：{len(scan_items)} 条路径参与，"
            f"{len(hit)} 条有值渲染进扫描缓冲区。"
        )

    update_diag = update_diag or {}
    update_meta = update_meta or {}
    update = {
        "channel": update_channel or "none",
        "applied": update_diag.get("applied", 0),
        "dropped": update_diag.get("dropped", []),
        "coerced": update_diag.get("coerced", []),
        "clamped": update_diag.get("clamped", []),
        "meta": update_meta,
    }
    if update_meta:
        diagnostics.append(
            "ADR-0005 tool: "
            f"enabled={bool(update_meta.get('enabled_flag'))}, "
            f"persona_uses_mvu={bool(update_meta.get('persona_uses_mvu'))}, "
            f"tools_sent={bool(update_meta.get('tools_sent'))}, "
            f"tool_calls={int(update_meta.get('tool_calls_received') or 0)}"
        )
    if update["applied"] or update["dropped"] or update["coerced"] or update["clamped"]:
        parts = [f"更新通道={update['channel']}", f"应用 {update['applied']} 个 op（ADR-0005）"]
        if update["coerced"]:
            parts.append(f"强转 {len(update['coerced'])}")
        if update["clamped"]:
            parts.append(f"限幅 {len(update['clamped'])}")
        if update["dropped"]:
            parts.append(f"丢弃 {len(update['dropped'])}")
        diagnostics.append("；".join(parts) + "。")

    return {
        "is_mvu": bool(entries) or bool(scan_items),
        "counts": counts,
        "entries": entries,
        "scan_items": scan_items,
        "update": update,
        "diagnostics": diagnostics,
    }
