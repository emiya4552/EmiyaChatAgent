# -*- coding: utf-8 -*-
"""Worldbook filtering decisions for chat-time MVU compatibility."""
import re

from app.services.mvu_runtime.policy import MvuRuntimePolicy
from app.services.mvu_runtime.runtime_view import classify_mvu_comment


MVU_TAG_RE = re.compile(r"\[(?:mvu_update|mvu_plot|mvu_status|initvar|opening)\]", re.I)


def is_mvu_tagged_entry(entry: dict) -> bool:
    return bool(MVU_TAG_RE.search(str(entry.get("comment") or "")))


def filter_worldbook_entries_for_prompt(
    entries: list[dict] | None,
    policy: MvuRuntimePolicy,
) -> list[dict]:
    """Return the entries that may be injected into the visible LLM prompt.

    - MVU active: keep MVU status/plot/etc. but remove `[mvu_update]`, because
      variable updates are handled by the dedicated update pass.
    - MVU disabled for an MVU card: strip all MVU-tagged entries so the card is
      treated as a normal card during chat.
    """

    current = list(entries or [])
    if policy.divert_update_entries:
        return [
            entry for entry in current
            if classify_mvu_comment(entry.get("comment")) != "update"
        ]
    if policy.strip_all_mvu_entries:
        return [entry for entry in current if not is_mvu_tagged_entry(entry)]
    return current
