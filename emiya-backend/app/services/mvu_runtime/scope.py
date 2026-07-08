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

    return {
        "local": dict(conversation_variables or {}) if policy.use_variable_scope else {},
        "global": dict(user_global_variables or {}) if policy.use_variable_scope else {},
        "names": {
            "user": user_name,
            "char": char_name,
        },
    }
