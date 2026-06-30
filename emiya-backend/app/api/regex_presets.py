# -*- coding: utf-8 -*-
"""正则预设 API 路由：CRUD + 导入。"""
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.regex_preset import (
    RegexPresetCreate,
    RegexPresetUpdate,
    RegexPresetListItem,
    RegexPresetResponse,
)
from app.services import regex_preset_service
from app.utils.exceptions import AppException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/regex-presets", tags=["正则预设"])


def _rp_to_response(rp) -> RegexPresetResponse:
    return RegexPresetResponse(
        id=rp.id,
        name=rp.name,
        description=rp.description,
        scripts=rp.scripts or [],
        created_at=rp.created_at,
        updated_at=rp.updated_at,
    )


@router.get("", response_model=list[RegexPresetListItem])
async def list_regex_presets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await regex_preset_service.list_regex_presets(db, current_user.id)


@router.post("", response_model=RegexPresetResponse, status_code=201)
async def create_regex_preset(
    data: RegexPresetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        rp = await regex_preset_service.create_regex_preset(db, current_user.id, data)
    except ValueError as e:
        raise AppException(str(e), status_code=400)
    return _rp_to_response(rp)


@router.post("/import", response_model=RegexPresetResponse, status_code=201)
async def import_regex_preset(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError:
        raise AppException("无效的 JSON 文件", status_code=400)

    try:
        rp = await regex_preset_service.import_regex_preset_json(
            db, current_user.id, data,
            source_name=file.filename or "unnamed.json",
        )
    except ValueError as e:
        raise AppException(str(e), status_code=400)
    return _rp_to_response(rp)


@router.get("/{rp_id}", response_model=RegexPresetResponse)
async def get_regex_preset(
    rp_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rp = await regex_preset_service.get_regex_preset(db, rp_id, current_user.id)
    if rp is None:
        raise AppException("正则预设不存在", status_code=404)
    return _rp_to_response(rp)


@router.put("/{rp_id}", response_model=RegexPresetResponse)
async def update_regex_preset(
    rp_id: UUID,
    data: RegexPresetUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        rp = await regex_preset_service.update_regex_preset(db, rp_id, current_user.id, data)
    except ValueError as e:
        raise AppException(str(e), status_code=400)
    if rp is None:
        raise AppException("正则预设不存在", status_code=404)
    return _rp_to_response(rp)


@router.delete("/{rp_id}")
async def delete_regex_preset(
    rp_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await regex_preset_service.delete_regex_preset(db, rp_id, current_user.id)
    if not ok:
        raise AppException("正则预设不存在", status_code=404)
    return {"deleted": True}


@router.get("/{rp_id}/export")
async def export_regex_preset(
    rp_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rp = await regex_preset_service.get_regex_preset(db, rp_id, current_user.id)
    if rp is None:
        raise AppException("正则预设不存在", status_code=404)
    return JSONResponse(content={
        "name": rp.name,
        "description": rp.description,
        "scripts": rp.scripts,
    })
