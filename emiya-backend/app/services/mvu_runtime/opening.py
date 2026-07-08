# -*- coding: utf-8 -*-
"""Opening-message MVU policy integration.

Conversation creation and greeting switching both treat the selected greeting as
an assistant message. This module keeps their MVU behavior aligned with the
chat-time policy.
"""
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.persona import Persona
from app.models.user import User
from app.services.message_pipeline import process_assistant_message_text
from app.services.mvu_runtime.initialization import merge_initial_state_missing_only
from app.services.mvu_runtime.policy import (
    MvuRuntimePolicy,
    build_mvu_policy_for_user_persona,
)
from app.services.mvu_runtime.scope import build_macro_scope


@dataclass(frozen=True)
class OpeningMessageResult:
    content: str
    display_content: str | None
    variables: dict | None = None


async def process_opening_message(
    text: str,
    *,
    db: AsyncSession,
    conversation: Conversation,
    persona: Persona,
    user: User | None,
    user_persona: Persona | None = None,
    policy: MvuRuntimePolicy | None = None,
) -> OpeningMessageResult:
    """Process a first/alternate greeting under the effective MVU policy.

    Name macros remain available even when MVU compatibility is disabled. The
    local/global variable buckets and `<UpdateVariable>` writes are only active
    when `policy.active` is true.
    """
    policy = policy or build_mvu_policy_for_user_persona(user=user, persona=persona)
    scope = build_macro_scope(
        policy=policy,
        conversation_variables=conversation.variables,
        user_global_variables=(user.global_variables if user else None),
        user_name=(user_persona.name if user_persona else None)
        or (user.nickname if user else "")
        or "",
        char_name=persona.name,
    )

    content, display_content, updated_scope = await process_assistant_message_text(
        text,
        db=db,
        conv=conversation,
        mvu_scope=scope if policy.active else None,
        macro_scope=scope,
        run_macro=True,
        apply_update_variable=policy.active,
    )

    variables = None
    if policy.active and updated_scope is not None:
        local_after = dict(updated_scope.get("local") or {})
        if local_after:
            variables = local_after

    return OpeningMessageResult(
        content=content,
        display_content=display_content,
        variables=variables,
    )


def merge_initial_state_for_opening(
    variables: dict | None,
    initial_state: dict,
    *,
    policy: MvuRuntimePolicy,
    reloaded: bool = False,
) -> tuple[dict, list[str]]:
    """Merge MVU initial state only when compatibility is active."""
    if not policy.active:
        return dict(variables or {}), []
    return merge_initial_state_missing_only(
        variables,
        initial_state,
        reloaded=reloaded,
    )
