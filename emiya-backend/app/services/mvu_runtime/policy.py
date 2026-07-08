# -*- coding: utf-8 -*-
"""MVU runtime policy for chat-time compatibility gates."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MvuRuntimePolicy:
    """Centralized chat-time MVU behavior switches.

    `raw_uses_mvu` records the card import diagnosis. `active` is the effective
    runtime state after applying the user's account-level compatibility switch.
    """

    raw_uses_mvu: bool
    compat_enabled: bool

    @property
    def active(self) -> bool:
        return self.raw_uses_mvu and self.compat_enabled

    @property
    def run_ejs(self) -> bool:
        return self.active

    @property
    def use_variable_scope(self) -> bool:
        return self.active

    @property
    def divert_update_entries(self) -> bool:
        return self.active

    @property
    def strip_all_mvu_entries(self) -> bool:
        return self.raw_uses_mvu and not self.compat_enabled


def build_mvu_policy(*, persona_uses_mvu: bool, compat_enabled: bool) -> MvuRuntimePolicy:
    return MvuRuntimePolicy(
        raw_uses_mvu=bool(persona_uses_mvu),
        compat_enabled=bool(compat_enabled),
    )


def build_mvu_policy_for_user_persona(*, user, persona) -> MvuRuntimePolicy:
    """Build policy from ORM-like user/persona rows.

    Missing user means "use the historical default": compatibility enabled.
    """
    return build_mvu_policy(
        persona_uses_mvu=bool(persona and getattr(persona, "uses_mvu", False)),
        compat_enabled=bool(getattr(user, "mvu_compat_enabled", True)),
    )
