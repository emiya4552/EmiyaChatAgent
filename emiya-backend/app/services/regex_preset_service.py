# -*- coding: utf-8 -*-
"""正则预设服务：CRUD + 导入 + 对话中生效脚本查询。

所有 CRUD 都按 user_id 过滤；RegexPreset 是用户私有资源（详见 ADR-0013）。
"""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.regex_preset import RegexPreset
from app.schemas.regex_preset import RegexPresetCreate, RegexPresetUpdate
from app.services.regex_processor import parse_js_regex

logger = logging.getLogger(__name__)


def validate_scripts(scripts: list[dict]) -> list[str]:
    """验证所有脚本的正则合法性，返回错误信息列表（空列表=全部合法）。"""
    errors = []
    for i, s in enumerate(scripts):
        if s.get("disabled", False):
            continue
        find_regex = s.get("findRegex", "")
        if not find_regex:
            continue
        pattern = parse_js_regex(find_regex)
        if pattern is None:
            name = s.get("scriptName", f"脚本 #{i + 1}")
            errors.append(f"「{name}」的正则表达式不合法: {find_regex}")
    return errors


async def list_regex_presets(db: AsyncSession, user_id: UUID) -> list[dict]:
    result = await db.execute(
        select(RegexPreset)
        .where(RegexPreset.user_id == user_id)
        .order_by(RegexPreset.updated_at.desc())
    )
    presets = result.scalars().all()
    return [
        {
            "id": rp.id,
            "name": rp.name,
            "description": rp.description,
            "script_count": len(rp.scripts) if rp.scripts else 0,
            "created_at": rp.created_at,
            "updated_at": rp.updated_at,
        }
        for rp in presets
    ]


async def create_regex_preset(
    db: AsyncSession, user_id: UUID, data: RegexPresetCreate
) -> RegexPreset:
    if data.scripts:
        errors = validate_scripts(data.scripts)
        if errors:
            raise ValueError("正则验证失败:\n" + "\n".join(errors))
    rp = RegexPreset(
        user_id=user_id,
        name=data.name,
        description=data.description,
        scripts=data.scripts,
    )
    db.add(rp)
    await db.commit()
    await db.refresh(rp)
    return rp


async def get_regex_preset(
    db: AsyncSession, rp_id: UUID, user_id: UUID | None = None
) -> RegexPreset | None:
    """user_id 给定则校验所有权（不属于该用户返回 None）；未给则不校验（运行时复用）。"""
    result = await db.execute(select(RegexPreset).where(RegexPreset.id == rp_id))
    rp = result.scalar_one_or_none()
    if rp is None:
        return None
    if user_id is not None and rp.user_id != user_id:
        return None
    return rp


async def get_regex_preset_by_name(
    db: AsyncSession, name: str, user_id: UUID
) -> RegexPreset | None:
    """按 (user_id, name) 查找该用户的正则预设。"""
    result = await db.execute(
        select(RegexPreset).where(
            RegexPreset.user_id == user_id,
            RegexPreset.name == name,
        )
    )
    return result.scalar_one_or_none()


async def update_regex_preset(
    db: AsyncSession, rp_id: UUID, user_id: UUID, data: RegexPresetUpdate
) -> RegexPreset | None:
    rp = await get_regex_preset(db, rp_id, user_id)
    if rp is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    if "scripts" in update_data and update_data["scripts"]:
        errors = validate_scripts(update_data["scripts"])
        if errors:
            raise ValueError("正则验证失败:\n" + "\n".join(errors))
    for field, value in update_data.items():
        setattr(rp, field, value)
    db.add(rp)
    await db.commit()
    await db.refresh(rp)
    return rp


async def delete_regex_preset(
    db: AsyncSession, rp_id: UUID, user_id: UUID
) -> bool:
    rp = await get_regex_preset(db, rp_id, user_id)
    if rp is None:
        return False
    await db.delete(rp)
    await db.commit()
    return True


async def import_regex_preset_json(
    db: AsyncSession, user_id: UUID, data: dict, source_name: str = "unnamed"
) -> RegexPreset:
    """从 JSON 导入正则预设。支持两种格式：
    - 含 name 字段的完整导出格式
    - 纯 scripts 数组格式
    """
    if isinstance(data, list):
        scripts = data
        name = source_name.rsplit(".", 1)[0] if "." in source_name else source_name
    else:
        scripts = data.get("scripts", [])
        name = data.get("name", source_name.rsplit(".", 1)[0] if "." in source_name else source_name)

    if scripts:
        errors = validate_scripts(scripts)
        if errors:
            raise ValueError("导入的正则表达式不合法:\n" + "\n".join(errors))

    rp = RegexPreset(
        user_id=user_id,
        name=name,
        description=data.get("description") if isinstance(data, dict) else None,
        scripts=scripts,
    )
    db.add(rp)
    await db.commit()
    await db.refresh(rp)
    return rp


async def get_active_scripts(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> list[dict]:
    """获取对话当前生效的正则脚本（promptOnly=false 部分，前端用）。

    查询路径：conversation.regex_preset_id → RegexPreset.scripts
    fallback：conversation.preset_id → Preset.regex_preset_id → RegexPreset.scripts
    """
    from app.models.conversation import Conversation

    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        return []

    regex_preset_id = conv.regex_preset_id
    if regex_preset_id is None and conv.preset_id:
        from app.models.preset import Preset
        p_result = await db.execute(
            select(Preset).where(Preset.id == conv.preset_id)
        )
        preset = p_result.scalar_one_or_none()
        if preset:
            regex_preset_id = preset.regex_preset_id

    if regex_preset_id is None:
        return []

    rp = await get_regex_preset(db, regex_preset_id)
    if rp is None:
        return []

    return [
        s for s in rp.scripts
        if not s.get("disabled", False) and not s.get("promptOnly", False)
    ]


async def get_prompt_only_scripts(
    db: AsyncSession, conv_regex_preset_id: UUID | None,
    preset_id: UUID | None,
) -> list[dict]:
    """获取 promptOnly=true 的脚本（后端生成时使用）。"""
    regex_preset_id = conv_regex_preset_id
    if regex_preset_id is None and preset_id:
        from app.models.preset import Preset
        result = await db.execute(
            select(Preset).where(Preset.id == preset_id)
        )
        preset = result.scalar_one_or_none()
        if preset:
            regex_preset_id = preset.regex_preset_id

    if regex_preset_id is None:
        return []

    rp = await get_regex_preset(db, regex_preset_id)
    if rp is None:
        return []

    return [
        s for s in rp.scripts
        if not s.get("disabled", False) and s.get("promptOnly", False)
    ]
