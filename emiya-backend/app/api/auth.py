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
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
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
from app.services.session_service import (
    access_token_expires_at,
    create_user_session,
    get_active_session,
    touch_session,
)
from app.services.password_reset_service import request_password_reset, reset_password
from app.utils.exceptions import AuthException
from app.utils.security import create_access_token, decode_access_token

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
    session_id = payload.get("sid")
    if user_id is None or session_id is None:
        raise AuthException("无效的认证令牌")

    try:
        UUID(user_id)
    except (ValueError, AttributeError):
        raise AuthException("无效的认证令牌")

    user = await get_user_by_id(db, user_id)
    if user is None:
        raise AuthException("用户不存在")

    session = await get_active_session(db, session_id, user.id)
    if session is None:
        raise AuthException("登录已失效，请重新登录")

    await touch_session(db, session)
    setattr(user, "_current_session_id", session.id)
    return user


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register(
    request: Request,
    body: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """用户注册，成功后返回 JWT 令牌。"""
    user = await register_user(db, body.email, body.password, body.nickname)
    expires_at = access_token_expires_at()
    session = await create_user_session(db, user.id, request, expires_at)
    token = create_access_token(str(user.id), str(session.id))
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
    user = await authenticate_user(db, body.email, body.password)
    if user is None:
        raise AuthException("邮箱或密码错误")
    expires_at = access_token_expires_at()
    session = await create_user_session(db, user.id, request, expires_at)
    token = create_access_token(str(user.id), str(session.id))
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """发送找回密码邮件。响应不暴露邮箱是否存在。"""
    await request_password_reset(db, body.email)
    return MessageResponse(message="如果邮箱存在，重置邮件已发送")


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def reset_password_by_token(
    request: Request,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """使用邮件链接令牌重置密码。"""
    await reset_password(db, body.token, body.new_password)
    return MessageResponse(message="密码已重置，请重新登录")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user=Depends(get_current_user)):
    """获取当前登录用户信息。"""
    return UserResponse.model_validate(current_user)
