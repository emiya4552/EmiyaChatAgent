# -*- coding: utf-8 -*-
"""认证业务逻辑：注册、登录、用户查询。"""
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.utils.exceptions import AuthException
from app.utils.security import (
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)


async def register_user(
    db: AsyncSession, email: str, password: str, nickname: str
) -> User:
    """注册新用户，检查邮箱唯一性后创建用户。

    Args:
        db: 数据库会话。
        email: 用户邮箱。
        password: 明文密码。
        nickname: 用户昵称。

    Returns:
        用户对象。

    Raises:
        AuthException: 邮箱已被注册。
    """
    # 检查邮箱是否已存在
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none() is not None:
        raise AuthException("该邮箱已被注册")

    user = User(
        email=email,
        nickname=nickname,
        password_hash=hash_password(password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise AuthException("该邮箱已被注册")

    await db.refresh(user)

    return user


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> User | None:
    """验证用户登录凭据。

    Args:
        db: 数据库会话。
        email: 用户邮箱。
        password: 明文密码。

    Returns:
        验证成功返回 User，失败返回 None。
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        return None

    return user


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    """根据用户 ID 获取用户。

    Args:
        db: 数据库会话。
        user_id: 用户 UUID 字符串。

    Returns:
        User 对象或 None。
    """
    from uuid import UUID

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    return result.scalar_one_or_none()
