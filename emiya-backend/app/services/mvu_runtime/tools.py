# -*- coding: utf-8 -*-
"""MVU `update_variables` 工具定义 + tool_call 抽取。

原为 ADR-0005 的单调用 tool 更新策略；该策略已随 ADR-0022 移除。本模块现**仅服务
double_ai 更新策略**（`mvu_runtime.update_pass.run_update_pass` 用它构造工具、抽取 patch）。
inline 策略（ADR-0022 默认）不经这里——更新是主模型正文里的 `<UpdateVariable>`，由
`message_pipeline` 内联解析。

`update_variables` 工具：参数是**通用 JSON Patch 数组**（op/path/value），卡专属的
路径/取值规则放进 tool description（由本轮激活的 `[mvu_update]` 条目内容拼成）。
这样工具定义与卡无关，约束/校验交给 update_core。
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_TOOL_NAME = "update_variables"
_DESC_BUDGET = 6000  # description 里 [mvu_update] 原文的最大字符数，避免过长

_BASE_DESC = (
    "在本轮回复末尾根据剧情更新角色状态变量 stat_data。参数 patch 是一组 JSON Patch "
    "操作（RFC6902 风格）：op ∈ replace/add/insert/remove/delta/move；path 用 "
    "`/字段/子字段` 形式，以 stat_data 为根；delta 用于数值增减。"
    "不要更新以 `_` 开头的只读字段。以下是本卡的变量规则：\n"
)


def build_update_variables_tool(wi_activated: list[dict] | None) -> dict:
    """构造 OpenAI 风格的 update_variables 工具定义（description 来自 [mvu_update] 条目）。"""
    from app.services.mvu_runtime.runtime_view import classify_mvu_comment

    parts: list[str] = []
    used = 0
    for entry in wi_activated or []:
        if classify_mvu_comment(entry.get("comment")) != "update":
            continue
        content = str(entry.get("content") or "").strip()
        if not content:
            continue
        if used + len(content) > _DESC_BUDGET:
            content = content[: max(0, _DESC_BUDGET - used)]
        parts.append(content)
        used += len(content)
        if used >= _DESC_BUDGET:
            break

    description = _BASE_DESC + ("\n\n".join(parts) if parts else "（本卡未提供额外规则）")

    return {
        "type": "function",
        "function": {
            "name": _TOOL_NAME,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "patch": {
                        "type": "array",
                        "description": "JSON Patch 操作数组",
                        "items": {
                            "type": "object",
                            "properties": {
                                "op": {
                                    "type": "string",
                                    "enum": ["replace", "add", "insert", "remove", "delta", "move"],
                                },
                                "path": {"type": "string"},
                                "value": {},
                                "from": {"type": "string"},
                            },
                            "required": ["op", "path"],
                        },
                    }
                },
                "required": ["patch"],
            },
        },
    }


def extract_update_ops_from_tool_calls(tool_calls: list[dict] | None) -> list[dict]:
    """从累积好的 tool_calls 里抽出所有 update_variables 的 patch，拼成一个 op 列表。"""
    ops: list[dict] = []
    for tc in tool_calls or []:
        fn = (tc or {}).get("function") or {}
        if fn.get("name") != _TOOL_NAME:
            continue
        raw = fn.get("arguments")
        if not raw:
            continue
        try:
            args = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            logger.warning(f"MVU tool_call 参数解析失败: {e}; raw={raw!r:.200}")
            continue
        patch = args.get("patch") if isinstance(args, dict) else None
        if isinstance(patch, list):
            ops.extend(o for o in patch if isinstance(o, dict))
    return ops
