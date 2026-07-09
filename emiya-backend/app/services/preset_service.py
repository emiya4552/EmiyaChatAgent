# -*- coding: utf-8 -*-
"""预设服务：数据库 CRUD + ST 格式导入。

所有 CRUD 都按 user_id 过滤；Preset 是用户私有资源（详见 ADR-0013）。
"""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preset import Preset
from app.models.regex_preset import RegexPreset
from app.schemas.preset import PresetCreate, PresetUpdate

logger = logging.getLogger(__name__)


def _is_st_format(data: dict) -> bool:
    return "prompts" in data and isinstance(data.get("prompts"), list)


def _convert_st_preset(data: dict, source_name: str) -> dict:
    """将 ST 格式预设转换为内部四部分结构。"""
    prompts = data.get("prompts", [])
    out_prompts = []

    for p in prompts:
        content = p.get("content", "")
        if not content:
            continue
        out_prompts.append({
            "identifier": p.get("identifier", ""),
            "name": p.get("name", p.get("identifier", "")),
            "role": p.get("role", "system"),
            "content": content,
            "enabled": p.get("enabled", True),
            "injection_position": p.get("injection_position", 0),
            "injection_depth": p.get("injection_depth", 4),
            "injection_order": p.get("injection_order", 100),
            "system_prompt": p.get("system_prompt", False),
            "marker": p.get("marker", False),
            "forbid_overrides": p.get("forbid_overrides", False),
        })

    sampling_params = {}
    for key in ("temperature", "frequency_penalty", "presence_penalty",
                "top_p", "top_k", "top_a", "min_p", "repetition_penalty"):
        if key in data:
            sampling_params[key] = data[key]

    context_settings = {}
    for key in ("openai_max_context", "openai_max_tokens",
                "token_budget_safety_margin", "history_budget_cap",
                "worldbook_budget_pct", "worldbook_budget_cap",
                "names_behavior", "stream_openai"):
        if key in data:
            context_settings[key] = data[key]

    return {
        "name": source_name.rsplit(".", 1)[0] if "." in source_name else source_name,
        "description": f"从 ST 预设导入（{len(out_prompts)} 个 prompt）",
        "sampling_params": sampling_params,
        "context_settings": context_settings,
        "prompts": out_prompts,
        "extensions": data.get("extensions", {}),
    }


async def _validate_regex_preset_owner(
    db: AsyncSession, regex_preset_id: UUID | None, user_id: UUID
) -> None:
    """校验给定 regex_preset_id 属于该用户；不属于则抛 ValueError。

    Preset 不能引用别人的 RegexPreset（详见 ADR-0013 决定 4）。
    """
    if regex_preset_id is None:
        return
    result = await db.execute(
        select(RegexPreset.user_id).where(RegexPreset.id == regex_preset_id)
    )
    owner = result.scalar_one_or_none()
    if owner is None:
        raise ValueError("正则预设不存在")
    if owner != user_id:
        raise ValueError("正则预设不存在或无权访问")


# ─── CRUD ───


async def list_presets(db: AsyncSession, user_id: UUID) -> list[dict]:
    result = await db.execute(
        select(Preset)
        .where(Preset.user_id == user_id)
        .order_by(Preset.updated_at.desc())
    )
    presets = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "prompt_count": len(p.prompts) if p.prompts else 0,
            # 暴露关联的正则预设 ID，供前端创建对话弹窗的"关联预导入"使用（详见 ADR-0014）
            "regex_preset_id": p.regex_preset_id,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
        for p in presets
    ]


async def create_preset(
    db: AsyncSession, user_id: UUID, data: PresetCreate
) -> Preset:
    # 校验跨用户引用
    rp_id = getattr(data, "regex_preset_id", None)
    await _validate_regex_preset_owner(db, rp_id, user_id)
    preset = Preset(
        user_id=user_id,
        name=data.name,
        description=data.description,
        sampling_params=data.sampling_params,
        context_settings=data.context_settings,
        prompts=data.prompts,
        extensions=data.extensions,
        regex_preset_id=rp_id,
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset


async def get_preset(
    db: AsyncSession, preset_id: UUID, user_id: UUID | None = None
) -> Preset | None:
    """user_id 给定则校验所有权（不属于该用户返回 None）；未给则不校验（仅运行时复用）。"""
    result = await db.execute(select(Preset).where(Preset.id == preset_id))
    preset = result.scalar_one_or_none()
    if preset is None:
        return None
    if user_id is not None and preset.user_id != user_id:
        return None
    return preset


async def update_preset(
    db: AsyncSession, preset_id: UUID, user_id: UUID, data: PresetUpdate
) -> Preset | None:
    preset = await get_preset(db, preset_id, user_id)
    if preset is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    if "regex_preset_id" in update_data:
        await _validate_regex_preset_owner(db, update_data["regex_preset_id"], user_id)
    for field, value in update_data.items():
        setattr(preset, field, value)
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset


async def delete_preset(
    db: AsyncSession, preset_id: UUID, user_id: UUID
) -> bool:
    preset = await get_preset(db, preset_id, user_id)
    if preset is None:
        return False
    await db.delete(preset)
    await db.commit()
    return True


# ─── 导入/导出 ───


async def import_preset_json(
    db: AsyncSession, user_id: UUID, data: dict, source_filename: str = "unnamed"
) -> Preset:
    if _is_st_format(data):
        data = _convert_st_preset(data, source_filename)

    preset_name = data.get("name", source_filename.rsplit(".", 1)[0])

    preset = Preset(
        user_id=user_id,
        name=preset_name,
        description=data.get("description"),
        sampling_params=data.get("sampling_params", {}),
        context_settings=data.get("context_settings", {}),
        prompts=data.get("prompts", []),
        extensions=data.get("extensions", {}),
    )

    # 如果 extensions 中包含 regex_scripts，自动创建/更新该用户私有的 RegexPreset
    regex_scripts = data.get("extensions", {}).get("regex_scripts", [])
    if regex_scripts:
        from app.services.regex_preset_service import (
            get_regex_preset_by_name,
            update_regex_preset,
        )
        from app.schemas.regex_preset import RegexPresetUpdate

        regex_name = f"{preset_name}_regex"
        existing_rp = await get_regex_preset_by_name(db, regex_name, user_id)
        if existing_rp:
            await update_regex_preset(
                db, existing_rp.id, user_id,
                RegexPresetUpdate(scripts=regex_scripts),
            )
            preset.regex_preset_id = existing_rp.id
        else:
            rp = RegexPreset(user_id=user_id, name=regex_name, scripts=regex_scripts)
            db.add(rp)
            await db.flush()
            preset.regex_preset_id = rp.id

    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset


async def export_preset(
    db: AsyncSession, preset_id: UUID, user_id: UUID
) -> dict | None:
    preset = await get_preset(db, preset_id, user_id)
    if preset is None:
        return None
    return {
        "name": preset.name,
        "description": preset.description,
        "sampling_params": preset.sampling_params,
        "context_settings": preset.context_settings,
        "prompts": preset.prompts,
        "extensions": preset.extensions,
    }


# ─── 运行时读取（用于 prompt 注入） ───


async def get_preset_for_injection(
    db: AsyncSession, preset_id: UUID
) -> dict | None:
    """返回 PresetInjector 所需的 dict 格式: {prompts, extensions}。

    运行时调用，所有权校验由调用方（conversation 已经按 user_id 过滤过）保证。
    """
    preset = await get_preset(db, preset_id)
    if preset is None:
        return None
    return {
        "prompts": preset.prompts,
        "extensions": preset.extensions,
    }
