# -*- coding: utf-8 -*-
import uuid

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.message import Message
from app.models.persona import Persona
from app.models.user import User
from app.services.conversation_service import create_conversation


OPENING_WITH_UPDATE = """你好 {{user}}，我是 {{char}}。
<UpdateVariable>
<initvar>
伶伶:
  hp: 1
</initvar>
</UpdateVariable>
"""


@pytest.mark.asyncio
async def test_opening_update_variable_is_ignored_when_mvu_compat_disabled(test_user):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, test_user.id)
        user.mvu_compat_enabled = False
        persona = Persona(
            id=uuid.uuid4(),
            name="伶伶",
            uses_mvu=True,
            first_message=OPENING_WITH_UPDATE,
            is_template=False,
        )
        session.add(persona)
        await session.commit()

        conv = await create_conversation(session, test_user.id, persona.id)

        assert conv.variables == {}
        result = await session.execute(
            select(Message).where(Message.conversation_id == conv.id)
        )
        msg = result.scalar_one()
        assert "测试用户" in msg.content
        assert "伶伶" in msg.content


@pytest.mark.asyncio
async def test_opening_update_variable_applies_when_mvu_compat_enabled(test_user):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, test_user.id)
        user.mvu_compat_enabled = True
        persona = Persona(
            id=uuid.uuid4(),
            name="伶伶",
            uses_mvu=True,
            first_message=OPENING_WITH_UPDATE,
            is_template=False,
        )
        session.add(persona)
        await session.commit()

        conv = await create_conversation(session, test_user.id, persona.id)

        assert conv.variables["stat_data"]["伶伶"]["hp"] == 1
