# -*- coding: utf-8 -*-
"""安全工具：密码哈希和 JWT 令牌管理。"""
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import settings


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希。

    Args:
        password: 明文密码。

    Returns:
        哈希后的密码字符串。
    """
    # bcrypt 要求密码不超过 72 bytes
    password_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """验证明文密码是否与哈希匹配。

    Args:
        password: 明文密码。
        hashed: bcrypt 哈希值。

    Returns:
        匹配返回 True，否则返回 False。
    """
    password_bytes = password.encode("utf-8")[:72]
    return bcrypt.checkpw(password_bytes, hashed.encode("utf-8"))


def create_access_token(
    user_id: str,
    session_id: str,
    expires_delta: timedelta | None = None,
) -> str:
    """创建 JWT 访问令牌。

    Args:
        user_id: 用户 ID。
        session_id: 用户会话 ID。
        expires_delta: 过期时间增量，默认使用配置的 ACCESS_TOKEN_EXPIRE_MINUTES。

    Returns:
        编码后的 JWT 字符串。
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": user_id,
        "sid": session_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """解码并验证 JWT 令牌。

    Args:
        token: JWT 字符串。

    Returns:
        解码后的 payload 字典。

    Raises:
        JWTError: 令牌无效或已过期。
    """
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
