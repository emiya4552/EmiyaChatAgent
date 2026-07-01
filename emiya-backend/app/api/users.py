# -*- coding: utf-8 -*-
"""用户资料 API 路由（profile patching、头像上传、改密码、注销账号）。

与 /api/v1/auth 分开：auth 处理认证（注册/登录/获取自己身份），
users 处理用户资料的所有写操作。

详见 ADR-0009 「Account Settings & MVU Local Inspector」。
"""
import logging
import os
import shutil
import uuid as _uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.user_session import UserSession
from app.schemas.auth import UserResponse, UserSessionResponse, UserUpdateRequest
from app.services.session_service import (
    list_user_sessions,
    revoke_all_sessions,
    revoke_current_session,
    revoke_other_sessions,
    revoke_user_session,
)
from app.utils.exceptions import AppException
from app.utils.security import hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/users", tags=["用户"])


# 用户级头像与 persona 头像分目录，避免误删彼此
_BACKEND_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
USER_AVATAR_DIR = os.path.join(_BACKEND_ROOT, "uploads", "avatars", "users")
PERSONA_AVATAR_DIR = os.path.join(_BACKEND_ROOT, "uploads", "avatars")

ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MB


def _current_session_id(current_user: User) -> UUID | None:
    return getattr(current_user, "_current_session_id", None)


def _session_status(session: UserSession) -> str:
    now = datetime.now(timezone.utc)
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if session.revoked_at is not None:
        return "revoked"
    if expires_at <= now:
        return "expired"
    return "active"


def _session_to_response(
    session: UserSession,
    current_session_id: UUID | None,
) -> UserSessionResponse:
    return UserSessionResponse(
        id=session.id,
        device_label=session.device_label,
        ip_address=session.ip_address,
        created_at=session.created_at,
        last_seen_at=session.last_seen_at,
        expires_at=session.expires_at,
        revoked_at=session.revoked_at,
        is_current=current_session_id == session.id,
        status=_session_status(session),
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    request: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """编辑当前用户的资料。仅支持本字段的列：nickname / avatar_url / css_theme。

    None 字段表示"不修改"；显式空字符串表示"清空"（仅对 css_theme 有意义；
    nickname 拒绝空字符串由 schema validator 处理）。
    """
    data = request.model_dump(exclude_unset=True)
    for field, value in data.items():
        # css_theme: 空字符串视为清空（写入 NULL）
        if field == "css_theme" and value == "":
            setattr(current_user, "css_theme", None)
        else:
            setattr(current_user, field, value)
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.post("/me/avatar", response_model=UserResponse)
async def upload_user_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传用户头像。

    存储：uploads/avatars/users/{user_id}/{uuid}.{ext}
    旧头像文件不主动清理（避免误删并发请求；体积可忽略）。
    """
    if file.content_type not in ALLOWED_AVATAR_TYPES:
        raise AppException("仅支持 jpg / png / webp 格式", status_code=400)

    content = await file.read()
    if len(content) > MAX_AVATAR_BYTES:
        raise AppException("头像不能超过 2MB", status_code=400)

    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
    ext = ext_map[file.content_type]
    user_dir = os.path.join(USER_AVATAR_DIR, str(current_user.id))
    os.makedirs(user_dir, exist_ok=True)
    filename = f"{_uuid.uuid4()}.{ext}"
    fullpath = os.path.join(user_dir, filename)
    with open(fullpath, "wb") as f:
        f.write(content)

    current_user.avatar_url = f"/static/avatars/users/{current_user.id}/{filename}"
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.get("/me/sessions", response_model=list[UserSessionResponse])
async def list_my_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出当前账号的登录会话。"""
    current_sid = _current_session_id(current_user)
    sessions = await list_user_sessions(db, current_user.id)
    return [_session_to_response(s, current_sid) for s in sessions]


@router.delete("/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """撤销一个其他登录会话。"""
    await revoke_user_session(db, current_user.id, session_id, _current_session_id(current_user))


class RevokeOtherSessionsResponse(BaseModel):
    revoked: int


@router.post("/me/sessions/revoke-others", response_model=RevokeOtherSessionsResponse)
async def revoke_my_other_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """撤销当前设备之外的所有有效登录会话。"""
    revoked = await revoke_other_sessions(db, current_user.id, _current_session_id(current_user))
    return RevokeOtherSessionsResponse(revoked=revoked)


@router.post("/me/sessions/revoke-current", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_current_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """撤销当前登录会话。"""
    await revoke_current_session(db, current_user.id, _current_session_id(current_user))


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., description="当前密码")
    new_password: str = Field(..., min_length=6, max_length=72, description="新密码")


@router.post("/me/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改密码。需校验旧密码，成功后撤销该账号所有登录会话。"""
    if not verify_password(request.old_password, current_user.password_hash):
        raise AppException("当前密码不正确", status_code=400)
    if len(request.new_password.encode("utf-8")) > 72:
        raise AppException("新密码过长（≤ 72 字节）", status_code=400)
    current_user.password_hash = hash_password(request.new_password)
    db.add(current_user)
    await revoke_all_sessions(db, current_user.id, commit=False)
    await db.commit()


class DeleteAccountRequest(BaseModel):
    password: str = Field(..., description="当前密码（确认）")


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    request: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """注销账号：硬删该用户所有数据。

    顺序：
    1. 校验密码
    2. 查所有 conversation 关联 memory.id 用于 Chroma 清理
    3. PG 级联删 — 显式 DELETE 每个表，避免依赖 ORM cascade 配置
    4. Chroma 删该 user_id 全部向量
    5. 删 uploads/avatars/users/{user_id}/ 与 uploads/avatars/{user_id}/ 两个目录
    """
    if not verify_password(request.password, current_user.password_hash):
        raise AppException("密码不正确", status_code=400)

    from app.models.conversation import Conversation
    from app.models.emotion_record import EmotionRecord
    from app.models.memory import Memory
    from app.models.message import Message
    from app.models.persona import Persona
    from app.models.preset import Preset
    from app.models.prompt_template import PromptTemplate
    from app.models.regex_preset import RegexPreset
    from app.models.relationship import Relationship
    from app.models.worldbook import Worldbook

    user_id = current_user.id

    # 1. 收集所有 memory id（Chroma 清理用）
    mem_q = await db.execute(
        select(Memory.id).where(Memory.user_id == user_id)
    )
    memory_ids = [str(row[0]) for row in mem_q.all()]

    # 2. PG 级联 — 子表先删，再删父表
    conv_q = await db.execute(
        select(Conversation.id).where(Conversation.user_id == user_id)
    )
    conv_ids = [row[0] for row in conv_q.all()]

    if conv_ids:
        await db.execute(
            sql_delete(Message).where(Message.conversation_id.in_(conv_ids))
        )
        await db.execute(
            sql_delete(EmotionRecord).where(EmotionRecord.conversation_id.in_(conv_ids))
        )

    await db.execute(sql_delete(Memory).where(Memory.user_id == user_id))
    await db.execute(sql_delete(Relationship).where(Relationship.user_id == user_id))
    await db.execute(sql_delete(Conversation).where(Conversation.user_id == user_id))
    await db.execute(sql_delete(Persona).where(Persona.user_id == user_id))
    await db.execute(sql_delete(Worldbook).where(Worldbook.user_id == user_id))
    await db.execute(sql_delete(Preset).where(Preset.user_id == user_id))
    await db.execute(sql_delete(RegexPreset).where(RegexPreset.user_id == user_id))
    # PromptTemplate.user_id IS NULL 表示系统模板，注销时不动；仅删该用户私有模板
    await db.execute(
        sql_delete(PromptTemplate).where(PromptTemplate.user_id == user_id)
    )
    await db.delete(current_user)
    await db.commit()

    # 3. Chroma 清向量（失败仅记 warning，PG 已 commit 无法回滚）
    if memory_ids:
        try:
            from app.services.memory.chroma_client import delete_memory_vector
            for mid in memory_ids:
                try:
                    await delete_memory_vector(mid, str(user_id))
                except Exception:
                    logger.warning(f"注销时 Chroma 清向量失败 mid={mid}")
        except Exception:
            logger.exception("注销时 Chroma 模块加载失败")

    # 4. 删两个头像目录
    for d in (
        os.path.join(USER_AVATAR_DIR, str(user_id)),
        os.path.join(PERSONA_AVATAR_DIR, str(user_id)),
    ):
        if os.path.isdir(d):
            try:
                shutil.rmtree(d)
            except Exception:
                logger.warning(f"注销时删头像目录失败：{d}")
