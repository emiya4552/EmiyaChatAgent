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

__all__ = [
    "MVU_META_KEY",
    "analyze_card_compatibility",
    "build_initial_state",
    "describe_conversation_mvu_state",
    "merge_initial_state_missing_only",
]
