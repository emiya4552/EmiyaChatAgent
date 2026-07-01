# -*- coding: utf-8 -*-
"""用户会话业务逻辑。"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user_session import UserSession
from app.utils.exceptions import AppException


def access_token_expires_at() -> datetime:
    """返回新 access token 对应的过期时间。"""
    return datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or None
    return request.client.host if request.client else None


def _device_label(user_agent: str | None) -> str:
    ua = user_agent or ""
    if not ua:
        return "未知设备"

    if "Edg/" in ua:
        browser = "Edge"
    elif "Chrome/" in ua and "Chromium" not in ua:
        browser = "Chrome"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Safari/" in ua and "Chrome/" not in ua:
        browser = "Safari"
    else:
        browser = "浏览器"

    if "Windows" in ua:
        os_name = "Windows"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        os_name = "macOS"
    elif "Android" in ua:
        os_name = "Android"
    elif "iPhone" in ua or "iPad" in ua:
        os_name = "iOS"
    elif "Linux" in ua:
        os_name = "Linux"
    else:
        os_name = "未知系统"

    return f"{browser} / {os_name}"


async def create_user_session(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
    expires_at: datetime,
) -> UserSession:
    """为一次登录创建可撤销用户会话。"""
    user_agent = request.headers.get("user-agent")
    session = UserSession(
        user_id=user_id,
        user_agent=user_agent[:512] if user_agent else None,
        device_label=_device_label(user_agent),
        ip_address=_client_ip(request),
        last_seen_at=datetime.now(timezone.utc),
        expires_at=expires_at,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_active_session(
    db: AsyncSession,
    session_id: str,
    user_id: UUID,
) -> UserSession | None:
    """读取当前用户的有效会话。"""
    try:
        sid = UUID(session_id)
    except (TypeError, ValueError):
        return None

    result = await db.execute(
        select(UserSession).where(
            UserSession.id == sid,
            UserSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None
    now = datetime.now(timezone.utc)
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if session.revoked_at is not None or expires_at <= now:
        return None
    return session


async def touch_session(db: AsyncSession, session: UserSession) -> None:
    """刷新会话最近活跃时间。"""
    session.last_seen_at = datetime.now(timezone.utc)
    db.add(session)
    await db.commit()


async def list_user_sessions(
    db: AsyncSession,
    user_id: UUID,
) -> list[UserSession]:
    """列出当前用户的所有会话，最近活跃优先。"""
    result = await db.execute(
        select(UserSession)
        .where(UserSession.user_id == user_id)
        .order_by(UserSession.last_seen_at.desc())
    )
    return list(result.scalars().all())


async def revoke_user_session(
    db: AsyncSession,
    user_id: UUID,
    session_id: UUID,
    current_session_id: UUID | None,
) -> None:
    """撤销当前用户的一个其他会话。"""
    if current_session_id and session_id == current_session_id:
        raise AppException("当前登录请使用退出登录", status_code=400)

    result = await db.execute(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise AppException("会话不存在", status_code=404)
    if session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        db.add(session)
        await db.commit()


async def revoke_current_session(
    db: AsyncSession,
    user_id: UUID,
    current_session_id: UUID | None,
) -> None:
    """撤销当前登录会话。"""
    if current_session_id is None:
        return
    result = await db.execute(
        select(UserSession).where(
            UserSession.id == current_session_id,
            UserSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if session and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        db.add(session)
        await db.commit()


async def revoke_other_sessions(
    db: AsyncSession,
    user_id: UUID,
    current_session_id: UUID | None,
) -> int:
    """撤销当前会话之外的所有有效会话。"""
    sessions = await list_user_sessions(db, user_id)
    now = datetime.now(timezone.utc)
    count = 0
    for session in sessions:
        if current_session_id and session.id == current_session_id:
            continue
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if session.revoked_at is None and expires_at > now:
            session.revoked_at = now
            db.add(session)
            count += 1
    if count:
        await db.commit()
    return count


async def revoke_all_sessions(
    db: AsyncSession,
    user_id: UUID,
    *,
    commit: bool = True,
) -> int:
    """撤销某个用户的所有有效会话。"""
    sessions = await list_user_sessions(db, user_id)
    now = datetime.now(timezone.utc)
    count = 0
    for session in sessions:
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if session.revoked_at is None and expires_at > now:
            session.revoked_at = now
            db.add(session)
            count += 1
    if commit and count:
        await db.commit()
    return count
