# -*- coding: utf-8 -*-
"""MVU runtime boundary.

This package owns MVU initialization and compatibility diagnostics so the chat
pipeline only consumes a stable variables bucket.
"""

from app.services.mvu_runtime.initialization import (
    MVU_META_KEY,
    analyze_card_compatibility,
    build_initial_state,
    describe_conversation_mvu_state,
    merge_initial_state_missing_only,
)
from app.services.mvu_runtime.runtime_view import (
    build_runtime_view,
    classify_mvu_comment,
)
from app.services.mvu_runtime.policy import (
    MvuRuntimePolicy,
    build_mvu_policy,
    build_mvu_policy_for_user_persona,
)
from app.services.mvu_runtime.scope import build_macro_scope
from app.services.mvu_runtime.worldbook import (
    filter_worldbook_entries_for_prompt,
    is_mvu_tagged_entry,
)
from app.services.mvu_runtime.constraints import extract_constraints_from_entries
from app.services.mvu_runtime.update_core import (
    merge_diag,
    validate_initvar_state,
    validate_ops,
)
from app.services.mvu_runtime.update_pass import run_update_pass

__all__ = [
    "MVU_META_KEY",
    "analyze_card_compatibility",
    "build_initial_state",
    "build_macro_scope",
    "build_mvu_policy",
    "build_mvu_policy_for_user_persona",
    "build_runtime_view",
    "classify_mvu_comment",
    "describe_conversation_mvu_state",
    "extract_constraints_from_entries",
    "filter_worldbook_entries_for_prompt",
    "is_mvu_tagged_entry",
    "merge_diag",
    "merge_initial_state_missing_only",
    "MvuRuntimePolicy",
    "run_update_pass",
    "validate_initvar_state",
    "validate_ops",
]
