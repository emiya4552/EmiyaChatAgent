# -*- coding: utf-8 -*-
"""世界书 CRUD 业务。"""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.worldbook import Worldbook
from app.services.output_contracts import (
    annotate_entries,
    build_manual_contract,
    detect_single_entry,
)
from app.services.output_contracts.attachment import (
    accept_latest_auto_definition,
    apply_manual_definition,
    canonicalize_attachment,
    mark_attachment_reviewed,
    set_attachment_enabled,
)
from app.utils.exceptions import ForbiddenException, NotFoundException

logger = logging.getLogger(__name__)


# ─── 查询 ──────────────────────────────────────────────────


async def list_worldbooks(db: AsyncSession, user_id: UUID) -> list[Worldbook]:
    """列出用户可见的所有世界书（自己的 + 系统模板）。按更新时间倒序。"""
    result = await db.execute(
        select(Worldbook)
        .where((Worldbook.user_id == user_id) | (Worldbook.user_id.is_(None)))
        .order_by(Worldbook.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_worldbook(
    db: AsyncSession, worldbook_id: UUID, user_id: UUID | None = None
) -> Worldbook | None:
    """获取单本世界书。user_id 给定时校验所有权（None 即系统模板也可访问）。"""
    result = await db.execute(
        select(Worldbook).where(Worldbook.id == worldbook_id)
    )
    wb = result.scalar_one_or_none()
    if wb is None:
        return None
    if user_id is not None and wb.user_id is not None and wb.user_id != user_id:
        raise ForbiddenException("无权访问该世界书")
    return wb


async def get_worldbooks_by_ids(
    db: AsyncSession, worldbook_ids: list[UUID]
) -> list[Worldbook]:
    """按 id 列表批量取，保持入参顺序。"""
    if not worldbook_ids:
        return []
    result = await db.execute(
        select(Worldbook).where(Worldbook.id.in_(worldbook_ids))
    )
    by_id = {wb.id: wb for wb in result.scalars().all()}
    return [by_id[wid] for wid in worldbook_ids if wid in by_id]


# ─── 写入 ──────────────────────────────────────────────────


async def create_worldbook(
    db: AsyncSession,
    user_id: UUID,
    name: str,
    description: str | None = None,
    entries: list[dict] | None = None,
    scan_depth: int = 2,
    case_sensitive: bool = False,
    match_whole_words: bool = False,
    extensions: dict | None = None,
    llm_detection_enabled: bool = False,
    llm_detection_limit: int = 30,
) -> Worldbook:
    annotated_entries = await annotate_entries(
        entries or [],
        llm_enabled=llm_detection_enabled,
        llm_limit=max(0, int(llm_detection_limit or 0)),
    )
    wb = Worldbook(
        user_id=user_id,
        name=name,
        description=description,
        entries=annotated_entries,
        scan_depth=scan_depth,
        case_sensitive=case_sensitive,
        match_whole_words=match_whole_words,
        extensions=extensions or {},
    )
    db.add(wb)
    await db.commit()
    await db.refresh(wb)
    return wb


async def update_worldbook(
    db: AsyncSession,
    worldbook_id: UUID,
    user_id: UUID,
    data: dict,
) -> Worldbook | None:
    """更新世界书。`data` 可含任意 ORM 字段子集（name/description/entries/...）。"""
    wb = await get_worldbook(db, worldbook_id, user_id)
    if wb is None:
        return None
    if wb.user_id is None:
        # 系统模板不可改
        raise ForbiddenException("系统模板世界书不可编辑")
    if "entries" in data and data["entries"] is not None:
        data["entries"] = await annotate_entries(
            data["entries"],
            llm_enabled=bool(data.pop("_llm_detection_enabled", False)),
            llm_limit=max(0, int(data.pop("_llm_detection_limit", 30) or 0)),
        )
    else:
        data.pop("_llm_detection_enabled", None)
        data.pop("_llm_detection_limit", None)
    for k, v in data.items():
        if hasattr(wb, k) and k != "id" and k != "user_id":
            setattr(wb, k, v)
    db.add(wb)
    await db.commit()
    await db.refresh(wb)
    return wb


async def detect_worldbook_entry_output_contract(
    db: AsyncSession,
    worldbook_id: UUID,
    user_id: UUID,
    entry_uid: int,
) -> Worldbook:
    """对单条世界书 entry 主动执行 AI 输出契约识别，并保存结果。"""
    wb = await get_worldbook(db, worldbook_id, user_id)
    if wb is None:
        raise NotFoundException("世界书不存在")
    if wb.user_id is None:
        raise ForbiddenException("系统模板世界书不可编辑")

    entries = [dict(e or {}) for e in (wb.entries or [])]
    for idx, entry in enumerate(entries):
        if int(entry.get("uid", -1)) == int(entry_uid):
            entries[idx] = await detect_single_entry(entry)
            wb.entries = entries
            db.add(wb)
            await db.commit()
            await db.refresh(wb)
            return wb

    raise NotFoundException("世界书条目不存在")


async def declare_entry_output_contract(
    db: AsyncSession,
    worldbook_id: UUID,
    user_id: UUID,
    entry_uid: int,
    *,
    mode: str,
    section_names: list[str],
) -> Worldbook:
    """用户显式声明单条 entry 的输出模板（source=manual、reviewed=true），保存并返回。

    声明是最高权威的输入（ADR-2b），运行时优先于任何启发式 / LLM 识别结果。
    """
    wb = await get_worldbook(db, worldbook_id, user_id)
    if wb is None:
        raise NotFoundException("世界书不存在")
    if wb.user_id is None:
        raise ForbiddenException("系统模板世界书不可编辑")

    entries = [dict(e or {}) for e in (wb.entries or [])]
    for idx, entry in enumerate(entries):
        if int(entry.get("uid", -1)) == int(entry_uid):
            entry["output_contract"] = build_manual_contract(
                entry, mode=mode, section_names=section_names
            )
            entries[idx] = entry
            wb.entries = entries
            db.add(wb)
            await db.commit()
            await db.refresh(wb)
            return wb

    raise NotFoundException("世界书条目不存在")


async def update_entry_output_contract(
    db: AsyncSession,
    worldbook_id: UUID,
    user_id: UUID,
    entry_uid: int,
    *,
    definition: dict | None = None,
    enabled: bool | None = None,
) -> Worldbook:
    """保存人工 definition 或仅切换 Attachment 的启用状态。"""
    wb = await get_worldbook(db, worldbook_id, user_id)
    if wb is None:
        raise NotFoundException("世界书不存在")
    if wb.user_id is None:
        raise ForbiddenException("系统模板世界书不可编辑")

    entries = [dict(item or {}) for item in (wb.entries or [])]
    for index, entry in enumerate(entries):
        if int(entry.get("uid", -1)) != int(entry_uid):
            continue
        current = canonicalize_attachment(entry.get("output_contract"), entry)
        if definition is not None:
            current = apply_manual_definition(entry, definition, existing=current)
        if enabled is not None:
            current = set_attachment_enabled(entry, current, enabled)
        entry["output_contract"] = current
        entries[index] = entry
        wb.entries = entries
        db.add(wb)
        await db.commit()
        await db.refresh(wb)
        return wb
    raise NotFoundException("世界书条目不存在")


async def confirm_entry_output_contract(
    db: AsyncSession,
    worldbook_id: UUID,
    user_id: UUID,
    entry_uid: int,
) -> Worldbook:
    """把单条 entry 现有的识别结果标记为“用户已确认”（reviewed=true），提升其权威性。

    只改 reviewed 标记，不改契约内容——区别于 declare（用户重新声明模板）。
    """
    wb = await get_worldbook(db, worldbook_id, user_id)
    if wb is None:
        raise NotFoundException("世界书不存在")
    if wb.user_id is None:
        raise ForbiddenException("系统模板世界书不可编辑")

    entries = [dict(e or {}) for e in (wb.entries or [])]
    for idx, entry in enumerate(entries):
        if int(entry.get("uid", -1)) == int(entry_uid):
            raw_attachment = entry.get("output_contract")
            if not isinstance(raw_attachment, dict):
                raise NotFoundException("该条目尚无输出契约可确认")
            entry["output_contract"] = mark_attachment_reviewed(entry, raw_attachment)
            entries[idx] = entry
            wb.entries = entries
            db.add(wb)
            await db.commit()
            await db.refresh(wb)
            return wb

    raise NotFoundException("世界书条目不存在")


async def restore_entry_output_contract_auto_definition(
    db: AsyncSession,
    worldbook_id: UUID,
    user_id: UUID,
    entry_uid: int,
) -> Worldbook:
    """放弃人工定义，恢复最近一次自动识别候选。"""
    wb = await get_worldbook(db, worldbook_id, user_id)
    if wb is None:
        raise NotFoundException("世界书不存在")
    if wb.user_id is None:
        raise ForbiddenException("系统模板世界书不可编辑")

    entries = [dict(item or {}) for item in (wb.entries or [])]
    for index, entry in enumerate(entries):
        if int(entry.get("uid", -1)) != int(entry_uid):
            continue
        raw_attachment = entry.get("output_contract")
        if not isinstance(raw_attachment, dict):
            raise NotFoundException("该条目尚无自动识别候选")
        try:
            entry["output_contract"] = accept_latest_auto_definition(
                entry, raw_attachment, reviewed=False
            )
        except ValueError as exc:
            raise NotFoundException(str(exc)) from exc
        entries[index] = entry
        wb.entries = entries
        db.add(wb)
        await db.commit()
        await db.refresh(wb)
        return wb
    raise NotFoundException("世界书条目不存在")


async def delete_worldbook(
    db: AsyncSession, worldbook_id: UUID, user_id: UUID
) -> bool:
    """删除世界书。同时清掉所有引用它的 persona.default_worldbook_ids /
    conversation.worldbook_ids（不留悬空 ID）。"""
    wb = await get_worldbook(db, worldbook_id, user_id)
    if wb is None:
        raise NotFoundException("世界书不存在")
    if wb.user_id is None:
        raise ForbiddenException("系统模板世界书不可删除")

    # 清理引用（小用户量场景下全表 SCAN 可接受；后续若引用计数高再加 GIN）
    from app.models.conversation import Conversation
    from app.models.persona import Persona

    wid_str = str(worldbook_id)

    # personas
    persona_rows = await db.execute(
        select(Persona).where(Persona.user_id == user_id)
    )
    for p in persona_rows.scalars().all():
        ids = list(p.default_worldbook_ids or [])
        if wid_str in [str(x) for x in ids]:
            p.default_worldbook_ids = [x for x in ids if str(x) != wid_str]
            db.add(p)

    # conversations
    conv_rows = await db.execute(
        select(Conversation).where(Conversation.user_id == user_id)
    )
    for c in conv_rows.scalars().all():
        ids = list(c.worldbook_ids or [])
        if wid_str in [str(x) for x in ids]:
            c.worldbook_ids = [x for x in ids if str(x) != wid_str]
            db.add(c)

    await db.delete(wb)
    await db.commit()
    return True
