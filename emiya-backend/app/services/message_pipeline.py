# -*- coding: utf-8 -*-
"""Assistant 消息后处理管道（ADR-0015）。

把"对一条 assistant 文本要做的处理"集中到一个函数：
  1. MacroEngine 渲染（{{user}} / {{char}} / {{getvar}} 等卡作者宏）
  2. MVU `<UpdateVariable>` 解析 → 写回 stat_data
  3. 后端 reply 类正则替换（promptOnly=false 的脚本，对应 ST AI_OUTPUT 阶段）

开场白 (create_conversation) 和 LLM 真实输出 (node_post_process) 共用本管道。
本模块不写库、不副作用——只做文本处理 + 返回更新后的 mvu_scope。
"""
from __future__ import annotations

import copy
import json
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.services.macro_engine import MacroEngine
from app.services.mvu_runtime.json_safe import make_json_safe
from app.services.regex_processor import RegexProcessor
from app.services.regex_preset_service import get_regex_preset

logger = logging.getLogger(__name__)


_UPDATE_VAR_RE = re.compile(
    r"<UpdateVariable\b[^>]*>(.*?)</UpdateVariable>",
    re.DOTALL | re.IGNORECASE,
)
_INITVAR_RE = re.compile(r"<initvar\b[^>]*>(.*?)</initvar>", re.DOTALL | re.IGNORECASE)
_JSON_PATCH_RE = re.compile(
    r"<(?:JSONPatch|json_patch)\b[^>]*>(.*?)</(?:JSONPatch|json_patch)>",
    re.DOTALL | re.IGNORECASE,
)


def _parse_update_variable(text: str) -> dict | None:
    """提取 `<UpdateVariable><initvar>YAML</initvar></UpdateVariable>` 内的 YAML 树。

    解析失败 / 非 dict 一律返回 None（不阻断主流程）。详见 ADR-0010 决策 4。
    """
    if not text or "<UpdateVariable" not in text:
        return None
    m = _UPDATE_VAR_RE.search(text)
    if not m:
        return None
    initvar = _INITVAR_RE.search(m.group(1))
    if not initvar:
        return None
    try:
        import yaml
        parsed = yaml.safe_load(initvar.group(1))
    except Exception as e:
        logger.warning(f"MVU <UpdateVariable> YAML 解析失败: {e}")
        return None
    if not isinstance(parsed, dict):
        logger.warning(
            f"MVU <UpdateVariable> 解析结果非 dict (type={type(parsed).__name__})"
        )
        return None
    return make_json_safe(parsed)


def _decode_json_pointer(path: str) -> list[str]:
    """Decode JSON Pointer syntax and treat `/stat_data/...` as stat_data-rooted."""
    if not path:
        return []
    if not path.startswith("/"):
        path = "/" + path
    parts = [p.replace("~1", "/").replace("~0", "~") for p in path.split("/")[1:]]
    return parts[1:] if parts and parts[0] == "stat_data" else parts


def _container_for(next_seg: str | None):
    return [] if next_seg is not None and (next_seg.isdigit() or next_seg == "-") else {}


def _list_index(seg: str, length: int, *, append_allowed: bool = False) -> int:
    if seg == "-":
        return length if append_allowed else max(length - 1, 0)
    try:
        idx = int(seg)
    except (TypeError, ValueError):
        idx = length if append_allowed else max(length - 1, 0)
    if idx < 0:
        idx = max(length + idx, 0)
    return idx


def _resolve_parent(root, path: list[str], *, create: bool):
    cur = root
    for i, seg in enumerate(path[:-1]):
        next_seg = path[i + 1] if i + 1 < len(path) else None
        if isinstance(cur, dict):
            if seg not in cur or cur[seg] is None:
                if not create:
                    return None, None
                cur[seg] = _container_for(next_seg)
            cur = cur[seg]
            continue
        if isinstance(cur, list):
            idx = _list_index(seg, len(cur), append_allowed=create)
            if idx >= len(cur):
                if not create:
                    return None, None
                while len(cur) <= idx:
                    cur.append(None)
                cur[idx] = _container_for(next_seg)
            if cur[idx] is None and create:
                cur[idx] = _container_for(next_seg)
            cur = cur[idx]
            continue
        return None, None
    return cur, path[-1] if path else None


def _get_path(root, path: list[str]):
    cur = root
    for seg in path:
        if isinstance(cur, dict):
            cur = cur.get(seg)
        elif isinstance(cur, list):
            idx = _list_index(seg, len(cur))
            cur = cur[idx] if 0 <= idx < len(cur) else None
        else:
            return None
    return cur


def _set_path(root, path: list[str], value, *, insert: bool = False):
    if not path:
        if isinstance(value, dict):
            root.clear()
            root.update(value)
        return
    parent, key = _resolve_parent(root, path, create=True)
    if parent is None or key is None:
        return
    if isinstance(parent, dict):
        parent[key] = value
    elif isinstance(parent, list):
        idx = _list_index(key, len(parent), append_allowed=True)
        if insert or key == "-":
            parent.insert(min(idx, len(parent)), value)
        else:
            while len(parent) <= idx:
                parent.append(None)
            parent[idx] = value


def _remove_path(root, path: list[str]):
    if not path:
        old = copy.deepcopy(root)
        root.clear()
        return old
    parent, key = _resolve_parent(root, path, create=False)
    if parent is None or key is None:
        return None
    if isinstance(parent, dict):
        return parent.pop(key, None)
    if isinstance(parent, list):
        idx = _list_index(key, len(parent))
        if 0 <= idx < len(parent):
            return parent.pop(idx)
    return None


def _apply_json_patch_ops(
    stat_data: dict,
    ops: list[dict],
    constraints: dict | None = None,
    diag: dict | None = None,
) -> None:
    # ADR-0005：先过有界校验层（_ 只读保护 / 类型强转 / range clamp / enum），
    # 只应用 accepted 的 op；诊断累加到 diag（供 mvu_runtime_view）。
    from app.services.mvu_runtime.update_core import merge_diag, validate_ops
    ops, op_diag = validate_ops(stat_data, ops, constraints)
    if diag is not None:
        merge_diag(diag, op_diag)

    for op in ops:
        if not isinstance(op, dict):
            continue
        kind = str(op.get("op") or "").lower()
        path = _decode_json_pointer(str(op.get("path") or ""))
        try:
            if kind in ("add", "replace", "assign", "set"):
                _set_path(stat_data, path, make_json_safe(copy.deepcopy(op.get("value"))))
            elif kind == "insert":
                _set_path(
                    stat_data,
                    path,
                    make_json_safe(copy.deepcopy(op.get("value"))),
                    insert=True,
                )
            elif kind in ("remove", "delete", "unset"):
                _remove_path(stat_data, path)
            elif kind == "delta":
                current = _get_path(stat_data, path) or 0
                _set_path(stat_data, path, current + op.get("value", 0))
            elif kind in ("move", "copy"):
                source = _decode_json_pointer(str(op.get("from") or op.get("source") or ""))
                value = copy.deepcopy(_get_path(stat_data, source))
                if kind == "move":
                    value = _remove_path(stat_data, source)
                _set_path(stat_data, path, value)
        except Exception as e:
            logger.warning(f"MVU JSONPatch op 应用失败 op={op!r}: {e}")


def _apply_update_variable_to_scope(
    text: str,
    mvu_scope: dict | None,
    constraints: dict | None = None,
    diag: dict | None = None,
) -> dict | None:
    """Apply supported `<UpdateVariable>` blocks to `local.stat_data`."""
    if not text or "<UpdateVariable" not in text:
        return mvu_scope
    blocks = _UPDATE_VAR_RE.findall(text)
    if not blocks:
        return mvu_scope
    blocks = [
        block for block in blocks
        if _INITVAR_RE.search(block) or _JSON_PATCH_RE.search(block)
    ]
    if not blocks:
        return mvu_scope

    if mvu_scope is None:
        mvu_scope = {"local": {}, "global": {}, "names": {}}
    local_bucket = mvu_scope.setdefault("local", {})
    stat_data = local_bucket.setdefault("stat_data", {})
    if not isinstance(stat_data, dict):
        stat_data = {}
        local_bucket["stat_data"] = stat_data

    for block in blocks:
        initvar = _INITVAR_RE.search(block)
        if initvar:
            parsed = _parse_update_variable(f"<UpdateVariable>{block}</UpdateVariable>")
            if parsed is not None:
                from app.services.mvu_runtime.update_core import (
                    merge_diag,
                    validate_initvar_state,
                )
                parsed, init_diag = validate_initvar_state(stat_data, parsed, constraints)
                if diag is not None:
                    merge_diag(diag, init_diag)
                local_bucket["stat_data"] = parsed
                stat_data = parsed
            continue

        patch = _JSON_PATCH_RE.search(block)
        if not patch:
            continue
        try:
            ops = json.loads(patch.group(1))
        except Exception as e:
            logger.warning(f"MVU <JSONPatch> 解析失败: {e}")
            continue
        if not isinstance(ops, list):
            logger.warning(f"MVU <JSONPatch> 解析结果非 list (type={type(ops).__name__})")
            continue
        _apply_json_patch_ops(stat_data, ops, constraints, diag)

    return mvu_scope


async def _load_reply_scripts(db: AsyncSession, conv: Conversation) -> list[dict]:
    """加载该 conv 当前生效的全部 AI_OUTPUT 阶段正则脚本（不按视图过滤）。

    优先级：conv.regex_preset_id > preset.regex_preset_id。fallback 为空。
    视图划分（promptOnly / markdownOnly）由 process_assistant_message_text 完成：
      - prompt 真相版：not markdownOnly（promptOnly + neither）
      - 显示版：      not promptOnly（markdownOnly + neither）
    详见 docs/mvu/adr/0003 双管线。
    """
    regex_preset_id = conv.regex_preset_id
    if regex_preset_id is None and conv.preset_id:
        from app.models.preset import Preset
        from sqlalchemy import select
        result = await db.execute(select(Preset).where(Preset.id == conv.preset_id))
        preset = result.scalar_one_or_none()
        if preset:
            regex_preset_id = preset.regex_preset_id

    if regex_preset_id is None:
        return []

    rp = await get_regex_preset(db, regex_preset_id)
    if rp is None:
        return []
    # disabled 由 RegexProcessor.apply_reply_to_text 过滤，这里全量返回
    return list(rp.scripts or [])


async def process_assistant_message_text(
    text: str,
    *,
    db: AsyncSession,
    conv: Conversation,
    mvu_scope: dict | None = None,
    macro_scope: dict | None = None,
    run_macro: bool = True,
    constraints: dict | None = None,
    update_diag: dict | None = None,
) -> tuple[str, str, dict | None]:
    """对一条 assistant 文本做与 LLM 输出等价的后处理，产出双管线两个视图。

    ADR-0005：`constraints` 传入时，文本 `<UpdateVariable>` 的 JSONPatch 会过有界校验层
    （_ 只读 / 类型强转 / range/enum）；校验诊断累加到 `update_diag`（供 runtime_view）。

    Args:
        text: 原始文本（开场白 / LLM 输出）
        db: AsyncSession，用来查 RegexPreset
        conv: 当前对话（用来定位绑定的 regex_preset / preset）
        mvu_scope: 当前 MVU 三段桶 {local, global, names}；若内含
            `<UpdateVariable>` 解析会更新 local.stat_data
        macro_scope: MacroEngine 用的 scope，None 时跳过宏渲染
        run_macro: False 时即使给了 macro_scope 也跳过（如 LLM 真实输出，不带宏占位符）

    Returns:
        (content, display_content, updated_mvu_scope)，详见 docs/mvu/adr/0003：
          - content: **prompt 真相版**（进 history）。只烘"两边都生效"（既非
            promptOnly 也非 markdownOnly）的 AI_OUTPUT 脚本。markdownOnly 美化不进来
            （history 不膨胀）；promptOnly 脚本**不在此烘**——它们按楼层深度生效，
            交给 prompt 组装阶段的 `RegexProcessor.apply_prompt_only`（node_build_prompt，
            depth-aware）处理，若在这里按单串烘会让 minDepth/maxDepth 失效。
          - display_content: **显示版**（前端渲染）。跑 not promptOnly 的脚本
            （markdownOnly + 两边都生效）→ 含状态栏 HTML / UpdateVariable 折叠等美化。
        两者从同一 precursor（宏渲染 + MVU 提取后）分叉，无法互相反推。
    """
    if not text:
        return text, text, mvu_scope

    precursor = text

    # 1) MacroEngine
    if run_macro and macro_scope is not None:
        try:
            precursor = MacroEngine.render(precursor, macro_scope)
        except Exception:
            logger.exception("MacroEngine 渲染失败，保留原文")

    # 2) MVU state extraction must run before display/reply regex rewrites can
    # mutate or remove the machine-readable `<UpdateVariable>` block.
    mvu_scope = _apply_update_variable_to_scope(
        precursor, mvu_scope, constraints, update_diag
    )

    # 3) reply 阶段正则，按视图分两批跑（ADR-0003 双管线）。macro_scope 透传给
    #    RegexProcessor，让 substituteRegex 字段下的 findRegex/replaceString 也能
    #    跑 {{user}}/{{char}} 等 ST 宏（ADR-0016）。
    content = precursor
    display_content = precursor
    try:
        scripts = await _load_reply_scripts(db, conv)
        if scripts:
            # content 只烘"两边都生效"的脚本；promptOnly 留给 build 阶段（depth-aware）
            prompt_scripts = [
                s for s in scripts
                if not s.get("markdownOnly", False) and not s.get("promptOnly", False)
            ]
            display_scripts = [s for s in scripts if not s.get("promptOnly", False)]
            content = RegexProcessor.apply_reply_to_text(
                precursor, prompt_scripts, macro_scope=macro_scope,
            )
            display_content = RegexProcessor.apply_reply_to_text(
                precursor, display_scripts, macro_scope=macro_scope,
            )
    except Exception:
        logger.exception("reply 阶段正则跑挂，保留前一步结果")

    return content, display_content, mvu_scope
