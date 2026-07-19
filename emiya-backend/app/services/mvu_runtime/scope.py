# -*- coding: utf-8 -*-
"""Macro scope construction under MVU runtime policy."""
from app.services.mvu_runtime.policy import MvuRuntimePolicy


def build_macro_scope(
    *,
    policy: MvuRuntimePolicy,
    conversation_variables: dict | None,
    user_global_variables: dict | None,
    user_name: str,
    char_name: str,
) -> dict:
    """Build the dual-bucket MacroEngine scope.

    Name macros are not MVU-specific, so `names` is always populated. The
    local/global variable buckets are part of the MVU state machine and are only
    exposed while MVU compatibility is active for this chat.
    """

    local = dict(conversation_variables or {}) if policy.use_variable_scope else {}
    if policy.use_variable_scope:
        # MVU 数据结构是 `{ stat_data, initialized_lorebooks }`。部分卡条目（如「[生成] 角色生成细节内容」
        # 创角模板）门控在 `getvar('initialized_lorebooks') !== undefined` 上——EMIYA 建对话时已跑
        # schema 播种初始态（= lorebook 已初始化），故补一个「已定义」的 `initialized_lorebooks`（缺省 `{}`），
        # 别让这类门控恒假、导致创角模板等条目永不渲染进 Prompt。已有值（前端 Host UP 回传）则保留。
        local.setdefault("initialized_lorebooks", {})

    return {
        "local": local,
        "global": dict(user_global_variables or {}) if policy.use_variable_scope else {},
        "names": {
            "user": user_name,
            "char": char_name,
        },
    }
