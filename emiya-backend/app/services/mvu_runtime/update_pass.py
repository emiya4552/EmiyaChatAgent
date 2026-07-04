# -*- coding: utf-8 -*-
"""Dedicated MVU variable update pass.

The visible chat call should focus on narrative text.  For MVU personas this
module runs a second, non-streaming call whose only job is to emit
`update_variables` JSON Patch ops.  The returned ops are still validated and
applied by `message_pipeline._apply_json_patch_ops`.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings
from app.services.llm_service import call_deepseek_tools_non_stream
from app.services.mvu_runtime.tools import (
    build_update_variables_tool,
    extract_update_ops_from_tool_calls,
)

logger = logging.getLogger(__name__)

_SYSTEM = """You are the MVU state update pass.

Given the current stat_data and the assistant's just-written narrative reply,
decide whether stat_data changed in this turn. Use the update_variables tool to
return JSON Patch ops rooted at stat_data.

Rules:
- Do not write narrative prose.
- Do not update readonly fields whose path segment starts with "_".
- Use only facts implied by the latest assistant reply and active MVU rules.
- If nothing changed, return no tool call.
"""


def _render_state(stat_data: dict[str, Any] | None) -> str:
    try:
        import yaml

        return yaml.safe_dump(
            stat_data or {},
            allow_unicode=True,
            sort_keys=False,
        )
    except Exception:
        return json.dumps(stat_data or {}, ensure_ascii=False, indent=2)


def _ops_from_text(content: str) -> list[dict]:
    """Best-effort fallback when a model returns bare JSON instead of a tool call."""
    if not content:
        return []
    try:
        parsed = json.loads(content)
    except Exception:
        try:
            from app.services.message_pipeline import _find_balanced_array

            raw = _find_balanced_array(content)
            parsed = json.loads(raw) if raw else None
        except Exception:
            logger.warning("MVU double-ai text fallback could not parse JSON ops")
            return []
    if isinstance(parsed, dict):
        parsed = parsed.get("patch")
    if isinstance(parsed, list):
        return [op for op in parsed if isinstance(op, dict)]
    return []


async def run_update_pass(
    *,
    reply: str,
    wi_activated: list[dict] | None,
    stat_data: dict[str, Any] | None,
) -> tuple[list[dict], dict]:
    """Run the second-pass MVU updater and return `(ops, meta)`."""
    meta: dict[str, Any] = {
        "mode": "double_ai",
        "forced": bool(settings.MVU_UPDATE_FORCE_TOOL),
        "tool_calls": 0,
        "ops": 0,
        "fallback": None,
        "error": None,
    }
    if not reply.strip():
        return [], meta

    tool = build_update_variables_tool(wi_activated)
    tool_choice: str | dict = "auto"
    if settings.MVU_UPDATE_FORCE_TOOL:
        tool_choice = {
            "type": "function",
            "function": {"name": "update_variables"},
        }

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                "Current stat_data:\n"
                f"```yaml\n{_render_state(stat_data)}\n```\n\n"
                "Latest assistant reply:\n"
                f"{reply}"
            ),
        },
    ]

    try:
        content, tool_calls = await call_deepseek_tools_non_stream(
            messages=messages,
            tools=[tool],
            tool_choice=tool_choice,
            model=settings.MVU_UPDATE_MODEL or settings.DEEPSEEK_MODEL,
            temperature=settings.MVU_UPDATE_TEMPERATURE,
            max_tokens=settings.MVU_UPDATE_MAX_TOKENS,
        )
    except Exception as exc:
        logger.exception("MVU double-ai update pass failed")
        meta["error"] = str(exc)
        return [], meta

    meta["tool_calls"] = len(tool_calls)
    ops = extract_update_ops_from_tool_calls(tool_calls)
    if not ops and content:
        ops = _ops_from_text(content)
        if ops:
            meta["fallback"] = "text"
    meta["ops"] = len(ops)
    return ops, meta
