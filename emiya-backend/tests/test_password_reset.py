# -*- coding: utf-8 -*-
"""找回密码与密码安全回归测试。"""
from datetime import timedelta
from urllib.parse import parse_qs, urlparse
from datetime import datetime, timezone
import smtplib
import uuid

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.password_reset_token import PasswordResetToken
from app.models.user_session import UserSession
from app.services.email_service import send_password_reset_email
from app.utils.exceptions import AppException
from app.utils.security import create_access_token, verify_password


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


async def test_forgot_password_sends_reset_link_without_exposing_email(
    client,
    test_user,
    monkeypatch,
):
    sent: list[tuple[str, str]] = []

    async def fake_send(to_email: str, reset_url: str):
        sent.append((to_email, reset_url))

    monkeypatch.setattr(
        "app.services.password_reset_service.send_password_reset_email",
        fake_send,
    )

    missing_res = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "missing@example.com"},
    )
    existing_res = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": test_user.email},
    )

    assert missing_res.status_code == 200
    assert existing_res.status_code == 200
    assert missing_res.json() == existing_res.json()
    assert len(sent) == 1
    assert sent[0][0] == test_user.email
    assert "/reset-password?" in sent[0][1]


async def test_new_reset_link_invalidates_previous_link(client, test_user, monkeypatch):
    sent: list[str] = []

    async def fake_send(_to_email: str, reset_url: str):
        sent.append(reset_url)

    monkeypatch.setattr(
        "app.services.password_reset_service.send_password_reset_email",
        fake_send,
    )

    for _ in range(2):
        res = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": test_user.email},
        )
        assert res.status_code == 200

    first_token = parse_qs(urlparse(sent[0]).query)["token"][0]
    second_token = parse_qs(urlparse(sent[1]).query)["token"][0]

    old_res = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": first_token, "new_password": "new-password"},
    )
    new_res = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": second_token, "new_password": "new-password"},
    )

    assert old_res.status_code == 400
    assert new_res.status_code == 200


async def test_reset_password_is_one_time_and_revokes_sessions(
    client,
    test_user,
    monkeypatch,
):
    sent: list[str] = []

    async def fake_send(_to_email: str, reset_url: str):
        sent.append(reset_url)

    monkeypatch.setattr(
        "app.services.password_reset_service.send_password_reset_email",
        fake_send,
    )
    _session, old_token = await _create_session_token(test_user, "current")

    await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": test_user.email},
    )
    token = parse_qs(urlparse(sent[0]).query)["token"][0]

    reset_res = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "new-password"},
    )
    second_res = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "another-password"},
    )
    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {old_token}"},
    )

    assert reset_res.status_code == 200
    assert second_res.status_code == 400
    assert me_res.status_code == 401

    async with AsyncSessionLocal() as session:
        user = await session.get(type(test_user), test_user.id)
        assert user is not None
        assert verify_password("new-password", user.password_hash)


async def test_expired_reset_link_is_rejected(client, test_user, monkeypatch):
    sent: list[str] = []

    async def fake_send(_to_email: str, reset_url: str):
        sent.append(reset_url)

    monkeypatch.setattr(
        "app.services.password_reset_service.send_password_reset_email",
        fake_send,
    )

    await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": test_user.email},
    )
    token = parse_qs(urlparse(sent[0]).query)["token"][0]

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(PasswordResetToken))
        reset_token = result.scalar_one()
        reset_token.expires_at = reset_token.expires_at - timedelta(hours=1)
        session.add(reset_token)
        await session.commit()

    res = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "new-password"},
    )

    assert res.status_code == 400


async def test_change_password_revokes_all_sessions(client, test_user):
    _session, token = await _create_session_token(test_user, "current")

    change_res = await client.post(
        "/api/v1/users/me/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": "old-password", "new_password": "new-password"},
    )
    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert change_res.status_code == 204
    assert me_res.status_code == 401


async def test_smtp_connection_failure_returns_app_exception(monkeypatch):
    def fake_smtp(*_args, **_kwargs):
        raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed: timed out")

    monkeypatch.setattr("app.services.email_service.settings.SMTP_HOST", "smtp.163.com")
    monkeypatch.setattr("app.services.email_service.settings.SMTP_PORT", 587)
    monkeypatch.setattr("app.services.email_service.settings.SMTP_FROM_EMAIL", "sender@example.com")
    monkeypatch.setattr("app.services.email_service.settings.SMTP_USE_TLS", True)
    monkeypatch.setattr("app.services.email_service.settings.SMTP_USE_SSL", False)
    monkeypatch.setattr("smtplib.SMTP", fake_smtp)

    with pytest.raises(AppException) as exc:
        await send_password_reset_email("user@example.com", "http://localhost/reset-password?token=x")

    assert exc.value.status_code == 502
    assert "SMTP_HOST" in exc.value.message
