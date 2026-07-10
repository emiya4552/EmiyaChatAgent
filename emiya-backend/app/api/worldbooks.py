# -*- coding: utf-8 -*-
"""世界书 API 路由：CRUD + ST native 导入/导出。"""
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.worldbook import Worldbook
from app.schemas.worldbook import (
    WorldbookCreateRequest,
    WorldbookListItem,
    WorldbookResponse,
    WorldbookUpdateRequest,
)
from app.services.worldbook import service as wb_service
from app.services.worldbook.import_export import (
    export_st_worldbook,
    import_st_worldbook,
)
from app.utils.exceptions import NotFoundException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/worldbooks", tags=["世界书"])


def _wb_to_response(wb: Worldbook) -> WorldbookResponse:
    return WorldbookResponse(
        id=wb.id,
        user_id=wb.user_id,
        name=wb.name,
        description=wb.description,
        scan_depth=wb.scan_depth,
        case_sensitive=wb.case_sensitive,
        match_whole_words=wb.match_whole_words,
        entries=wb.entries or [],
        extensions=wb.extensions or {},
        created_at=wb.created_at,
        updated_at=wb.updated_at,
    )


def _wb_to_list_item(wb: Worldbook) -> WorldbookListItem:
    return WorldbookListItem(
        id=wb.id,
        user_id=wb.user_id,
        name=wb.name,
        description=wb.description,
        entry_count=len(wb.entries or []),
        is_template=wb.user_id is None,
        created_at=wb.created_at,
        updated_at=wb.updated_at,
    )


@router.get("", response_model=list[WorldbookListItem])
async def list_worldbooks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await wb_service.list_worldbooks(db, current_user.id)
    return [_wb_to_list_item(wb) for wb in items]


@router.get("/{worldbook_id}", response_model=WorldbookResponse)
async def get_worldbook_detail(
    worldbook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wb = await wb_service.get_worldbook(db, worldbook_id, current_user.id)
    if wb is None:
        raise NotFoundException("世界书不存在")
    return _wb_to_response(wb)


@router.post("", response_model=WorldbookResponse, status_code=status.HTTP_201_CREATED)
async def create_new_worldbook(
    data: WorldbookCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wb = await wb_service.create_worldbook(
        db,
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        entries=[e.model_dump() for e in data.entries],
        scan_depth=data.scan_depth,
        case_sensitive=data.case_sensitive,
        match_whole_words=data.match_whole_words,
        extensions=data.extensions,
        llm_detection_enabled=current_user.output_contract_llm_detection_enabled,
        llm_detection_limit=current_user.output_contract_llm_detection_limit,
    )
    return _wb_to_response(wb)


@router.put("/{worldbook_id}", response_model=WorldbookResponse)
async def update_existing_worldbook(
    worldbook_id: UUID,
    data: WorldbookUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    update_data = data.model_dump(exclude_none=True)
    # Pydantic 嵌套：entries 序列化成 dict 列表
    if "entries" in update_data and update_data["entries"] is not None:
        update_data["entries"] = [
            e.model_dump() if hasattr(e, "model_dump") else e
            for e in update_data["entries"]
        ]
        update_data["_llm_detection_enabled"] = current_user.output_contract_llm_detection_enabled
        update_data["_llm_detection_limit"] = current_user.output_contract_llm_detection_limit
    wb = await wb_service.update_worldbook(db, worldbook_id, current_user.id, update_data)
    if wb is None:
        raise NotFoundException("世界书不存在")
    return _wb_to_response(wb)


@router.delete("/{worldbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_worldbook(
    worldbook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await wb_service.delete_worldbook(db, worldbook_id, current_user.id)


@router.post("/{worldbook_id}/entries/{entry_uid}/detect-output-contract", response_model=WorldbookResponse)
async def detect_entry_output_contract(
    worldbook_id: UUID,
    entry_uid: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """用户主动对单条世界书 entry 执行 AI 输出契约识别。"""
    wb = await wb_service.detect_worldbook_entry_output_contract(
        db,
        worldbook_id,
        current_user.id,
        entry_uid,
    )
    return _wb_to_response(wb)


# ─── 导入 / 导出 ──────────────────────────────────────────


@router.post("/import", response_model=WorldbookResponse, status_code=201)
async def import_worldbook(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导入 ST native 格式的 .json 文件。"""
    content = await file.read()
    try:
        data = json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        from app.utils.exceptions import AppException

        raise AppException(f"JSON 解析失败: {e}", status_code=400)

    wb_fields = import_st_worldbook(data)
    # name 解析顺序：JSON 显式 name > 文件名(去扩展名) > 通用兜底
    if not wb_fields.get("name"):
        wb_fields["name"] = _name_from_filename(file.filename) or "导入的世界书"

    wb = await wb_service.create_worldbook(
        db,
        user_id=current_user.id,
        llm_detection_enabled=current_user.output_contract_llm_detection_enabled,
        llm_detection_limit=current_user.output_contract_llm_detection_limit,
        **wb_fields,
    )
    return _wb_to_response(wb)


def _name_from_filename(filename: str | None) -> str:
    """从上传文件名提取一个合理的世界书名称：去路径、去扩展名、trim 空白。
    若无可用片段返回空串，让调用方走通用兜底。
    """
    if not filename:
        return ""
    # 去掉路径片段（部分浏览器会带）
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    # 去扩展名：rsplit 取剩下部分；若以点开头（.gitignore 之类）保留原名
    if "." in base and not base.startswith("."):
        base = base.rsplit(".", 1)[0]
    return base.strip()


@router.get("/{worldbook_id}/export")
async def export_worldbook(
    worldbook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出为 ST native 格式 JSON。返回 {filename, data}。"""
    wb = await wb_service.get_worldbook(db, worldbook_id, current_user.id)
    if wb is None:
        raise NotFoundException("世界书不存在")

    wb_dict = {
        "name": wb.name,
        "description": wb.description,
        "scan_depth": wb.scan_depth,
        "case_sensitive": wb.case_sensitive,
        "match_whole_words": wb.match_whole_words,
        "entries": wb.entries or [],
        "extensions": wb.extensions or {},
    }
    st_format = export_st_worldbook(wb_dict)
    return JSONResponse(
        content={
            "filename": f"{wb.name}.json",
            "data": st_format,
        }
    )
