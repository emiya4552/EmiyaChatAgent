# -*- coding: utf-8 -*-
"""预设 API 路由：CRUD + 导入/导出。"""
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.preset import PresetCreate, PresetUpdate, PresetListItem, PresetResponse
from app.services import preset_service
from app.utils.exceptions import AppException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/presets", tags=["预设"])


def _preset_to_response(p: preset_service.Preset) -> PresetResponse:
    return PresetResponse(
        id=p.id,
        name=p.name,
        description=p.description,
        sampling_params=p.sampling_params or {},
        context_settings=p.context_settings or {},
        prompts=p.prompts or [],
        extensions=p.extensions or {},
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("", response_model=list[PresetListItem])
async def list_presets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await preset_service.list_presets(db, current_user.id)


@router.post("", response_model=PresetResponse, status_code=201)
async def create_preset(
    data: PresetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        preset = await preset_service.create_preset(db, current_user.id, data)
    except ValueError as e:
        raise AppException(str(e), status_code=400)
    return _preset_to_response(preset)


@router.post("/import", response_model=PresetResponse, status_code=201)
async def import_preset(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError:
        raise AppException("无效的 JSON 文件", status_code=400)

    preset = await preset_service.import_preset_json(
        db, current_user.id, data, source_filename=file.filename or "unnamed.json"
    )
    return _preset_to_response(preset)


@router.get("/{preset_id}", response_model=PresetResponse)
async def get_preset(
    preset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    preset = await preset_service.get_preset(db, preset_id, current_user.id)
    if preset is None:
        raise AppException("预设不存在", status_code=404)
    return _preset_to_response(preset)


@router.put("/{preset_id}", response_model=PresetResponse)
async def update_preset(
    preset_id: UUID,
    data: PresetUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        preset = await preset_service.update_preset(db, preset_id, current_user.id, data)
    except ValueError as e:
        raise AppException(str(e), status_code=400)
    if preset is None:
        raise AppException("预设不存在", status_code=404)
    return _preset_to_response(preset)


@router.delete("/{preset_id}")
async def delete_preset(
    preset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await preset_service.delete_preset(db, preset_id, current_user.id)
    if not ok:
        raise AppException("预设不存在", status_code=404)
    return {"deleted": True}


@router.get("/{preset_id}/export")
async def export_preset(
    preset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await preset_service.export_preset(db, preset_id, current_user.id)
    if data is None:
        raise AppException("预设不存在", status_code=404)
    return JSONResponse(content=data)
