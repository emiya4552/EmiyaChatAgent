# -*- coding: utf-8 -*-
"""角色卡相关 API 路由：模板查询 + CRUD + 导入/导出。"""
import logging

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.persona import Persona
from app.models.user import User
from app.schemas.persona import (
    PersonaCreateRequest,
    PersonaListItem,
    PersonaResponse,
    PersonaUpdateRequest,
)
from app.services import persona_service
from app.services.mvu_runtime import analyze_card_compatibility
from app.utils.exceptions import AppException, ForbiddenException, NotFoundException
from app.utils.security import decode_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/personas", tags=["角色卡"])


async def _try_get_user_fixed(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        token = authorization[7:]
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        from uuid import UUID
        result = await db.execute(
            select(User).where(User.id == UUID(user_id))
        )
        return result.scalar_one_or_none()
    except Exception:
        return None


@router.get("", response_model=list[PersonaListItem])
async def list_personas(
    source: str | None = Query(None, alias="source", description="template / user / all"),
    current_user: User | None = Depends(_try_get_user_fixed),
    db: AsyncSession = Depends(get_db),
):
    """获取角色卡列表。"""
    if source == "template":
        personas = await persona_service.get_persona_templates(db)
        return _to_list_items(personas, is_owner=False)

    if source == "user":
        if current_user is None:
            raise AppException("需要登录", status_code=401)
        personas = await persona_service.get_custom_personas(db, current_user.id)
        return _to_list_items(personas, is_owner=True)

    templates = await persona_service.get_persona_templates(db)
    result = _to_list_items(templates, is_owner=False)

    if current_user is not None:
        user_personas = await persona_service.get_custom_personas(db, current_user.id)
        result.extend(_to_list_items(user_personas, is_owner=True))

    return result


def _to_list_items(personas: list[Persona], is_owner: bool) -> list[PersonaListItem]:
    return [
        PersonaListItem(
            id=p.id, name=p.name, personality=p.personality,
            is_template=p.is_template, is_owner=is_owner,
            tags=p.tags, avatar_url=p.avatar_url, source=p.source,
        )
        for p in personas
    ]


def _parse_uuid_list(values: list[str] | None):
    from uuid import UUID

    out: list[UUID] = []
    for value in values or []:
        try:
            out.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return out


async def _persona_response_with_mvu(
    db: AsyncSession,
    persona: Persona,
) -> PersonaResponse:
    from app.services.worldbook.service import get_worldbooks_by_ids

    worldbooks = await get_worldbooks_by_ids(
        db, _parse_uuid_list(persona.default_worldbook_ids),
    )
    report = analyze_card_compatibility(
        persona.card_data,
        worldbooks=worldbooks,
    )
    return PersonaResponse.model_validate(persona).model_copy(
        update={"mvu_compatibility": report},
    )


@router.post("", response_model=PersonaResponse, status_code=status.HTTP_201_CREATED)
async def create_persona(
    request: PersonaCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建自定义角色卡。"""
    try:
        data = request.model_dump(exclude_unset=True)
        persona = await persona_service.create_persona(db, current_user.id, data)
        return await _persona_response_with_mvu(db, persona)
    except ValueError as e:
        raise AppException(str(e), status_code=400)


@router.get("/{persona_id}", response_model=PersonaResponse)
async def get_persona_detail(
    persona_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取角色卡详情。仅自己拥有的或系统模板可读。"""
    from uuid import UUID

    persona = await persona_service.get_persona_by_id(db, UUID(persona_id))
    if persona is None:
        raise NotFoundException("角色卡不存在")
    if persona.user_id is not None and persona.user_id != current_user.id:
        raise NotFoundException("角色卡不存在")
    return await _persona_response_with_mvu(db, persona)


@router.put("/{persona_id}", response_model=PersonaResponse)
async def update_persona(
    persona_id: str,
    request: PersonaUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """编辑自定义角色卡。"""
    from uuid import UUID

    try:
        persona = await persona_service.update_persona(
            db,
            UUID(persona_id),
            current_user.id,
            request.model_dump(exclude_unset=True),
        )
        return await _persona_response_with_mvu(db, persona)
    except ValueError as e:
        msg = str(e)
        if "不存在" in msg:
            raise NotFoundException(msg)
        if "无权" in msg:
            raise ForbiddenException(msg)
        raise AppException(msg, status_code=400)


@router.delete("/{persona_id}")
async def remove_persona(
    persona_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除角色卡，级联删除关联的对话、消息、情绪记录、记忆。"""
    from uuid import UUID

    try:
        result = await persona_service.delete_persona(db, UUID(persona_id), current_user.id)
        return result
    except ValueError as e:
        msg = str(e)
        if "不存在" in msg:
            raise NotFoundException(msg)
        if "无权" in msg:
            raise ForbiddenException(msg)
        raise AppException(msg, status_code=400)


@router.post("/cleanup-orphans")
async def cleanup_orphan_records(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await persona_service.cleanup_orphans(db)
    return result


@router.get("/{persona_id}/relationship")
async def get_persona_relationship(
    persona_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取该角色卡与当前用户的关系摘要。"""
    from uuid import UUID
    from app.schemas.relationship import RelationshipResponse
    from app.services.relationship_service import (
        assess_relationship,
        get_or_create_relationship,
    )

    result = await db.execute(
        select(Persona).where(Persona.id == UUID(persona_id))
    )
    persona = result.scalar_one_or_none()
    if persona is None:
        raise NotFoundException("角色卡不存在")

    assessment = await assess_relationship(
        db, str(current_user.id), persona_id
    )
    rel = await get_or_create_relationship(
        db, str(current_user.id), persona_id
    )

    return RelationshipResponse(
        level=assessment["level"],
        level_name=assessment["level_name"],
        affinity_score=assessment["affinity_score"],
        total_messages=assessment["total_messages"],
        deep_talk_count=assessment["deep_talk_count"],
        first_interaction=assessment["first_interaction"],
        last_interaction=assessment["last_interaction"],
        days_span=assessment["days_span"],
        milestones=rel.milestones or [],
    )


# ─── 导入/导出 ───

import base64
import json
import os
import uuid as _uuid
from datetime import datetime

from fastapi import File, Form, Response, UploadFile
from fastapi.responses import JSONResponse

AVATAR_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "avatars")


@router.post("/import/parse")
async def import_parse(
    file: UploadFile | None = File(None),
    json_data: str | None = Form(None),
    url: str | None = Form(None),
    current_user: User = Depends(get_current_user),
):
    """解析角色卡，不入库，返回预览数据。"""
    from app.services.persona_import_service import CardParser

    raw_card: dict | None = None
    avatar_bytes: bytes | None = None
    source_filename: str | None = None

    try:
        if file is not None:
            source_filename = file.filename
            content = await file.read()
            if source_filename and source_filename.lower().endswith('.json'):
                raw_card = json.loads(content.decode('utf-8'))
            else:
                avatar_bytes = content
                raw_card = CardParser.parse_png(content)

        elif json_data:
            raw_card = json.loads(json_data)

        elif url:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.content
                content_type = resp.headers.get('content-type', '')
                if 'application/json' in content_type:
                    raw_card = resp.json()
                else:
                    avatar_bytes = content
                    raw_card = CardParser.parse_png(content)
            source_filename = url.rsplit('/', 1)[-1] if '/' in url else url

        else:
            raise AppException("请提供 PNG 文件、JSON 数据或 URL", status_code=400)

    except json.JSONDecodeError:
        raise AppException("无效的 JSON 格式", status_code=400)
    except ValueError as e:
        raise AppException(str(e), status_code=400)

    version = CardParser.detect_version(raw_card)
    data = CardParser.extract_data(raw_card, version)
    preview = CardParser.to_persona_fields(data, raw_card)
    # 注：character_book 不再塞 preview（456 条 entries 可达 MB 级，会击穿 form 体积）。
    # 改为：confirm 端凭 cache_key 从缓存的 raw_card 中重新派生。
    # Redis 缓存失效时退化为"该卡 worldbook 未挂载"（用户重新导入一次即可）。

    # 头像预览 base64
    avatar_preview = None
    if avatar_bytes:
        avatar_preview = "data:image/png;base64," + base64.b64encode(avatar_bytes).decode('ascii')

    # 同名检测
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as check_db:
        from sqlalchemy import select as _sel
        result = await check_db.execute(
            _sel(Persona).where(
                Persona.user_id == current_user.id,
                Persona.name == preview["name"],
            )
        )
        same_names = list(result.scalars().all())
    dup = {"is_duplicate": False, "similar_persona": None}
    if same_names:
        dup["similar_persona"] = {"id": str(same_names[0].id), "name": same_names[0].name}
        dup["is_duplicate"] = True

    # MVU 卡 / 大卡的 card_data 可达 MB 级，前端 form 来回送会击穿连接体积限制。
    # 把完整 raw_card 缓存到 Redis（10 min TTL），返回 cache_key，前端 confirm 时凭 key
    # 取回完整数据落库 —— card_data 始终是完整的，但前端 form body 降到 KB 级。
    import uuid as _uuid_mod
    from app.services.redis_client import cache_set_json
    cache_key = f"import:raw_card:{_uuid_mod.uuid4()}"
    cached = await cache_set_json(cache_key, raw_card, ttl_seconds=600)
    # preview 里把 card_data 缩成 placeholder 减小 parse 响应体积；
    # 真正的 card_data 落库时从 Redis 取（cache_key 即标识）
    if cached:
        preview = dict(preview)
        preview["card_data"] = {"_cached": True, "_cache_key": cache_key}

    return {
        "source_format": f"chara_card_v{version}",
        "source_filename": source_filename,
        "preview": preview,
        "missing_fields": [],
        "duplicate_check": dup,
        "avatar_preview": avatar_preview,
        "cache_key": cache_key if cached else None,
        "mvu_compatibility": analyze_card_compatibility(raw_card),
    }


@router.post("/import/confirm")
async def import_confirm(
    parse_result: str = Form(...),
    overrides: str = Form("{}"),
    source_url: str | None = Form(None),
    avatar_file: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """确认导入，写入数据库。"""
    from app.services.persona_import_service import CardParser

    try:
        preview = json.loads(parse_result)
        overrides_dict = json.loads(overrides)
    except json.JSONDecodeError:
        raise AppException("无效的 JSON 数据", status_code=400)

    # 合并 overrides
    preview.update(overrides_dict)
    if source_url:
        preview["source_url"] = source_url

    # 如果 parse 时把完整 raw_card 缓存到 Redis（避开 form 体积限制），
    # 这里凭 cache_key 取回，用真实 raw_card 派生 card_data + 内嵌 worldbook。
    # 详见 import_parse 注释。失败仅 warning，回退用 preview 里残留的 card_data。
    card_data_placeholder = preview.get("card_data") or {}
    cache_key = (
        card_data_placeholder.get("_cache_key")
        if isinstance(card_data_placeholder, dict)
        else None
    )
    if cache_key:
        from app.services.redis_client import cache_get_json, cache_delete
        raw_card = await cache_get_json(cache_key)
        if raw_card is not None:
            try:
                version = CardParser.detect_version(raw_card)
                data = CardParser.extract_data(raw_card, version)
                # 用 raw_card 派生最完整的 card_data + character_book + regex_scripts
                preview["card_data"] = raw_card
                if data.get("character_book") and "_character_book" not in preview:
                    preview["_character_book"] = data["character_book"]
                if data.get("regex_scripts") and "_regex_scripts" not in preview:
                    preview["_regex_scripts"] = data["regex_scripts"]
            except Exception:
                logger.exception("从 cache_key 恢复 raw_card 失败，回退到 preview 残留数据")
                preview["card_data"] = {}
            # 确保不在 DB 里留下 placeholder 痕迹
            if isinstance(preview.get("card_data"), dict) and preview["card_data"].get("_cached"):
                preview["card_data"] = {}
            # 用完即删
            await cache_delete(cache_key)
        else:
            # Redis 过期 / 异常 → 用空 card_data 兜底，让落库不挂
            logger.warning(f"raw_card 缓存命中失败 cache_key={cache_key}，card_data 置空")
            preview["card_data"] = {}

    # 保存头像
    if avatar_file:
        os.makedirs(os.path.join(AVATAR_DIR, str(current_user.id)), exist_ok=True)
        avatar_filename = f"{_uuid.uuid4()}.png"
        avatar_path = os.path.join(AVATAR_DIR, str(current_user.id), avatar_filename)
        content = await avatar_file.read()
        with open(avatar_path, 'wb') as f:
            f.write(content)
        preview["avatar_url"] = f"/static/avatars/{current_user.id}/{avatar_filename}"

    preview.pop("avatar_preview", None)
    # 抽出内嵌 character_book（v2/v3）— 单独建 Worldbook，不进 Persona 字段
    character_book = preview.pop("_character_book", None)
    # 抽出内嵌 regex_scripts（v2/v3 extensions）— 单独建 RegexPreset 并挂到 persona
    regex_scripts = preview.pop("_regex_scripts", None)
    # 强制覆盖：JSON 往返会把 datetime 变成字符串，这里确保类型正确
    preview["source"] = "imported"
    preview["imported_at"] = datetime.utcnow()

    try:
        persona = await persona_service.create_persona(db, current_user.id, preview)
    except ValueError as e:
        raise AppException(str(e), status_code=400)

    # 处理内嵌世界书：自动建 Worldbook + 挂到 persona.default_worldbook_ids
    # 同名 upsert：如果该用户已有同名世界书（说明此前导入过同一张卡），覆盖其条目，
    # 而不是再建一本。这样反复导入同名角色卡不会留下一堆重复世界书。
    worldbook_attached: str | None = None
    if character_book and isinstance(character_book, dict):
        try:
            from app.services.worldbook import service as wb_service
            from app.services.worldbook.import_export import from_character_book
            from app.models.worldbook import Worldbook

            wb_fields = from_character_book(character_book, persona_name=persona.name)

            existing_q = await db.execute(
                select(Worldbook).where(
                    Worldbook.user_id == current_user.id,
                    Worldbook.name == wb_fields["name"],
                )
            )
            existing_wb = existing_q.scalar_one_or_none()
            if existing_wb is not None:
                wb = await wb_service.update_worldbook(
                    db,
                    worldbook_id=existing_wb.id,
                    user_id=current_user.id,
                    data={
                        **wb_fields,
                        "_llm_detection_enabled": current_user.output_contract_llm_detection_enabled,
                        "_llm_detection_limit": current_user.output_contract_llm_detection_limit,
                    },
                )
            else:
                wb = await wb_service.create_worldbook(
                    db,
                    user_id=current_user.id,
                    llm_detection_enabled=current_user.output_contract_llm_detection_enabled,
                    llm_detection_limit=current_user.output_contract_llm_detection_limit,
                    **wb_fields,
                )
            persona.default_worldbook_ids = [str(wb.id)]
            db.add(persona)
            await db.commit()
            await db.refresh(persona)
            worldbook_attached = str(wb.id)
        except Exception:
            logger.exception("内嵌 character_book 抽取失败，persona 已建但 worldbook 未挂载")

    # 处理内嵌正则脚本：自动建 RegexPreset + 挂到 persona.default_regex_preset_id
    # 同名 upsert（同 worldbook 行为）：反复导入同名卡不会留垃圾。
    # 不做正则合法性校验——ST 自己导入卡时也不校验，无效脚本运行时会被 parse_js_regex 跳过。
    regex_preset_attached: str | None = None
    if regex_scripts and isinstance(regex_scripts, list) and len(regex_scripts) > 0:
        try:
            from app.models.regex_preset import RegexPreset

            preset_name = f"{persona.name} - 内嵌正则"
            existing_q = await db.execute(
                select(RegexPreset).where(
                    RegexPreset.user_id == current_user.id,
                    RegexPreset.name == preset_name,
                )
            )
            existing_rp = existing_q.scalar_one_or_none()
            if existing_rp is not None:
                existing_rp.scripts = regex_scripts
                db.add(existing_rp)
                await db.commit()
                await db.refresh(existing_rp)
                rp = existing_rp
            else:
                rp = RegexPreset(
                    user_id=current_user.id,
                    name=preset_name,
                    description=f"角色卡「{persona.name}」内嵌的正则脚本",
                    scripts=regex_scripts,
                )
                db.add(rp)
                await db.commit()
                await db.refresh(rp)

            persona.default_regex_preset_id = rp.id
            db.add(persona)
            await db.commit()
            await db.refresh(persona)
            regex_preset_attached = str(rp.id)
        except Exception:
            logger.exception("内嵌 regex_scripts 抽取失败，persona 已建但正则预设未挂载")

    return {
        "persona": await _persona_response_with_mvu(db, persona),
        "avatar_saved": bool(preview.get("avatar_url")),
        "worldbook_attached": worldbook_attached,
        "regex_preset_attached": regex_preset_attached,
    }


@router.get("/{persona_id}/export")
async def export_persona(
    persona_id: str,
    format: str = "png",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出角色卡为 PNG 或 JSON。仅自己拥有的或系统模板可导出。"""
    from uuid import UUID
    from app.services.persona_import_service import prepare_export_data, build_export_png
    import httpx

    persona = await persona_service.get_persona_by_id(db, UUID(persona_id))
    if persona is None:
        raise NotFoundException("角色卡不存在")
    if persona.user_id is not None and persona.user_id != current_user.id:
        raise NotFoundException("角色卡不存在")

    export_json = prepare_export_data(persona)

    if format == "json":
        return JSONResponse(content=export_json)

    # PNG 导出
    avatar_bytes: bytes
    if persona.avatar_url:
        avatar_path = os.path.join(
            os.path.dirname(__file__), "..", "..",
            persona.avatar_url.lstrip('/'),
        )
        if os.path.exists(avatar_path):
            with open(avatar_path, 'rb') as f:
                avatar_bytes = f.read()
        else:
            avatar_bytes = _generate_placeholder_png()
    else:
        avatar_bytes = _generate_placeholder_png()

    png_bytes = build_export_png(persona, avatar_bytes)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={persona.name}.png"},
    )


def _generate_placeholder_png() -> bytes:
    """生成 256×384 纯色占位 PNG。"""
    import struct as _st
    import zlib

    width, height = 256, 384
    raw = b''
    for y in range(height):
        raw += b'\x00'  # filter byte
        raw += b'\x7c\x5c\xfc' * width  # purple-ish

    def _chunk(ctype, data):
        c = _st.pack('>I', len(data)) + ctype + data
        crc = sum(ord(chr(b)) if isinstance(b, int) else b for b in c) & 0xFFFFFFFF  # simplified
        return c

    # Use proper CRC
    from app.services.persona_import_service import _png_crc32

    def _c(ctype, data):
        c = _st.pack('>I', len(data)) + ctype + data
        crc = _png_crc32(ctype + data)
        return c + _st.pack('>I', crc)

    ihdr = _st.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n'
            + _c(b'IHDR', ihdr)
            + _c(b'IDAT', zlib.compress(raw))
            + _c(b'IEND', b''))
