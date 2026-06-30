# -*- coding: utf-8 -*-
"""Assistant 消息后处理管道（ADR-0015）。

把"对一条 assistant 文本要做的处理"集中到一个函数：
  1. MacroEngine 渲染（{{user}} / {{char}} / {{getvar}} 等卡作者宏）
  2. 后端 reply 类正则替换（promptOnly=false 的脚本，对应 ST AI_OUTPUT 阶段）
  3. MVU `<UpdateVariable>` 解析 → 写回 stat_data

开场白 (create_conversation) 和 LLM 真实输出 (node_post_process) 共用本管道。
本模块不写库、不副作用——只做文本处理 + 返回更新后的 mvu_scope。
"""
from __future__ import annotations

import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.services.macro_engine import MacroEngine
from app.services.regex_processor import RegexProcessor
from app.services.regex_preset_service import get_regex_preset

logger = logging.getLogger(__name__)


_UPDATE_VAR_RE = re.compile(
    r"<UpdateVariable>\s*<initvar>\s*(.+?)\s*</initvar>\s*</UpdateVariable>",
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
    try:
        import yaml
        parsed = yaml.safe_load(m.group(1))
    except Exception as e:
        logger.warning(f"MVU <UpdateVariable> YAML 解析失败: {e}")
        return None
    if not isinstance(parsed, dict):
        logger.warning(
            f"MVU <UpdateVariable> 解析结果非 dict (type={type(parsed).__name__})"
        )
        return None
    return parsed


async def _load_reply_scripts(db: AsyncSession, conv: Conversation) -> list[dict]:
    """加载该 conv 当前生效的 reply 阶段正则脚本 (promptOnly=false 部分)。

    优先级：conv.regex_preset_id > preset.regex_preset_id。fallback 为空。
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
    # 返回所有 promptOnly=false 的脚本；RegexProcessor.apply_reply_to_text 内部
    # 还会再过滤 disabled，这里不重复
    return [s for s in (rp.scripts or []) if not s.get("promptOnly", False)]


async def process_assistant_message_text(
    text: str,
    *,
    db: AsyncSession,
    conv: Conversation,
    mvu_scope: dict | None = None,
    macro_scope: dict | None = None,
    run_macro: bool = True,
) -> tuple[str, dict | None]:
    """对一条 assistant 文本做与 LLM 输出等价的后处理。

    Args:
        text: 原始文本（开场白 / LLM 输出）
        db: AsyncSession，用来查 RegexPreset
        conv: 当前对话（用来定位绑定的 regex_preset / preset）
        mvu_scope: 当前 MVU 三段桶 {local, global, names}；若内含
            `<UpdateVariable>` 解析会更新 local.stat_data
        macro_scope: MacroEngine 用的 scope，None 时跳过宏渲染
        run_macro: False 时即使给了 macro_scope 也跳过（如 LLM 真实输出，不带宏占位符）

    Returns:
        (processed_text, updated_mvu_scope)：scope 已就地修改，但也返回方便链式。
    """
    if not text:
        return text, mvu_scope

    processed = text

    # 1) MacroEngine
    if run_macro and macro_scope is not None:
        try:
            processed = MacroEngine.render(processed, macro_scope)
        except Exception:
            logger.exception("MacroEngine 渲染失败，保留原文")

    # 2) reply 阶段正则——把 macro_scope 透传给 RegexProcessor，让 substituteRegex
    #    字段下的 findRegex/replaceString 也能跑 {{user}}/{{char}} 等 ST 宏（ADR-0016）
    try:
        scripts = await _load_reply_scripts(db, conv)
        if scripts:
            processed = RegexProcessor.apply_reply_to_text(
                processed, scripts, macro_scope=macro_scope,
            )
    except Exception:
        logger.exception("reply 阶段正则跑挂，保留前一步结果")

    # 3) MVU <UpdateVariable> 解析（基于处理后的文本——正则可能已经把标签擦掉了）
    # 但要注意：正则若把 UpdateVariable 整块删掉，初始化就触发不了。
    # 卡作者如果同时写了 [杀八股] 类规则又依赖 UpdateVariable，这是他们要解决的——
    # 我们按"清洗后才是真相"的原则处理。
    new_stat_data = _parse_update_variable(processed)
    if new_stat_data is not None:
        if mvu_scope is None:
            mvu_scope = {"local": {}, "global": {}, "names": {}}
        local_bucket = mvu_scope.setdefault("local", {})
        local_bucket["stat_data"] = new_stat_data

    return processed, mvu_scope
