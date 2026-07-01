# -*- coding: utf-8 -*-
"""用户会话管理回归测试。"""
from datetime import datetime, timedelta, timezone
import uuid

from jose import jwt

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user_session import UserSession
from app.utils.security import create_access_token


async def _create_session_token(user, label: str) -> tuple[UserSession, str]:
    async with AsyncSessionLocal() as session:
        user_session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            user_agent=label,
            device_label=label,
            ip_address="127.0.0.1",
            last_seen_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        session.add(user_session)
        await session.commit()
    token = create_access_token(str(user.id), str(user_session.id), expires_delta=timedelta(days=1))
    return user_session, token


async def test_register_creates_current_user_session(client):
    res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"user-{uuid.uuid4().hex[:8]}@test.com",
            "password": "secret123",
            "nickname": "凛",
        },
    )

    assert res.status_code == 201
    token = res.json()["access_token"]

    sessions_res = await client.get(
        "/api/v1/users/me/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert sessions_res.status_code == 200
    sessions = sessions_res.json()
    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True
    assert sessions[0]["status"] == "active"


async def test_token_without_session_id_is_rejected(client, test_user):
    now = datetime.now(timezone.utc)
    legacy_token = jwt.encode(
        {
            "sub": str(test_user.id),
            "iat": now,
            "exp": now + timedelta(days=1),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {legacy_token}"},
    )

    assert res.status_code == 401


async def test_revoked_other_session_token_stops_working(client, test_user):
    current_session, current_token = await _create_session_token(test_user, "current")
    other_session, other_token = await _create_session_token(test_user, "other")

    revoke_res = await client.delete(
        f"/api/v1/users/me/sessions/{other_session.id}",
        headers={"Authorization": f"Bearer {current_token}"},
    )
    assert revoke_res.status_code == 204

    current_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {current_token}"},
    )
    other_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert current_res.status_code == 200
    assert other_res.status_code == 401
    assert current_session.id != other_session.id
