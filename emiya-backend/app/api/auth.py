# -*- coding: utf-8 -*-
"""认证相关 API 路由。"""
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.limiter import limiter
from app.schemas.auth import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import (
    authenticate_user,
    get_user_by_id,
    register_user,
)
from app.utils.exceptions import AuthException
from app.utils.security import decode_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    """依赖注入：从 JWT 令牌中获取当前用户。"""
    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        raise AuthException("无效的认证令牌")

    user_id = payload.get("sub")
    if user_id is None:
        raise AuthException("无效的认证令牌")

    try:
        UUID(user_id)
    except (ValueError, AttributeError):
        raise AuthException("无效的认证令牌")

    user = await get_user_by_id(db, user_id)
    if user is None:
        raise AuthException("用户不存在")
    return user


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register(
    request: Request,
    body: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """用户注册，成功后返回 JWT 令牌。"""
    user, token = await register_user(db, body.email, body.password, body.nickname)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """用户登录，返回 JWT 令牌。"""
    result = await authenticate_user(db, body.email, body.password)
    if result is None:
        raise AuthException("邮箱或密码错误")
    user, token = result
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user=Depends(get_current_user)):
    """获取当前登录用户信息。"""
    return UserResponse.model_validate(current_user)
