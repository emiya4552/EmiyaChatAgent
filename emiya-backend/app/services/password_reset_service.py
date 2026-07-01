# -*- coding: utf-8 -*-
"""找回密码业务逻辑。"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services.email_service import send_password_reset_email
from app.services.session_service import revoke_all_sessions
from app.utils.exceptions import AppException
from app.utils.security import hash_password


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _reset_url(token: str) -> str:
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/reset-password?{urlencode({'token': token})}"


async def request_password_reset(db: AsyncSession, email: str) -> None:
    """创建找回密码链接并发送邮件。

    调用方始终返回相同响应文案，避免暴露邮箱是否存在。
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return

    now = datetime.now(timezone.utc)
    await _invalidate_unused_tokens(db, user.id, now)

    raw_token = secrets.token_urlsafe(32)
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
    )
    db.add(token)
    await db.commit()

    await send_password_reset_email(user.email, _reset_url(raw_token))


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    """校验一次性链接并重置密码。"""
    if len(new_password.encode("utf-8")) > 72:
        raise AppException("新密码过长（≤ 72 字节）", status_code=400)

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == _hash_token(token),
        )
    )
    reset_token = result.scalar_one_or_none()
    if reset_token is None or reset_token.used_at is not None:
        raise AppException("重置链接无效或已过期", status_code=400)

    expires_at = reset_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise AppException("重置链接无效或已过期", status_code=400)

    user = await db.get(User, reset_token.user_id)
    if user is None:
        raise AppException("重置链接无效或已过期", status_code=400)

    user.password_hash = hash_password(new_password)
    reset_token.used_at = now
    db.add(user)
    db.add(reset_token)
    await revoke_all_sessions(db, user.id, commit=False)
    await db.commit()


async def _invalidate_unused_tokens(
    db: AsyncSession,
    user_id: UUID,
    used_at: datetime,
) -> None:
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
    )
    for token in result.scalars().all():
        token.used_at = used_at
        db.add(token)
