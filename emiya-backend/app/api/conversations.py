# -*- coding: utf-8 -*-
"""对话管理 API 路由。"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationResponse,
    PresetApplyRequest,
    ConversationConfigUpdate,
    RegexPresetSwitchRequest,
    GreetingSwitchRequest,
)
from app.schemas.message import MessageResponse
from app.schemas.worldbook import AuthorNoteUpdate, WorldbookBindingUpdate
from app.services.conversation_service import (
    apply_preset_to_conversation,
    create_conversation,
    delete_conversation,
    get_conversation_by_id,
    get_conversation_messages,
    get_user_conversations,
    reload_conversation_mvu_initial_state,
    update_conversation_config,
)
from app.config import settings
from app.services.mvu_runtime import describe_conversation_mvu_state
from app.services.regex_preset_service import get_active_scripts
from app.utils.exceptions import NotFoundException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/conversations", tags=["对话"])


def _system_default_chat_config() -> dict:
    """系统层面真正会下发到 LLM / token budget 的默认值。
    只列出我们有稳定单值默认的字段；像 top_p / top_k / repetition_penalty
    我们不主动下发（由 LLM 端兜底），不在这里伪造默认值。
    """
    return {
        "temperature": settings.CHAT_TEMPERATURE,
        # 与 nodes._calc_history_budget 的口径一致；chat_service 还会按 reply_length 再做下调
        "openai_max_tokens": settings.CHAT_MAX_TOKENS,
        "openai_max_context": settings.MAX_CONTEXT_TOKENS,
    }


def _compute_effective_chat_config(chat_config: dict | None) -> dict:
    """系统默认 ∪ chat_config（后者优先）。用于前端配置面板回显当前生效值。"""
    merged = _system_default_chat_config()
    if chat_config:
        for k, v in chat_config.items():
            if v is not None:
                merged[k] = v
    return merged


def _conv_to_response(c, reply_length_enabled: bool = True):
    """同步版（用于无 DB 上下文的快路径）。reply_length_enabled 由调用方计算后传入；
    默认 True 兼容旧调用方——但所有 API 路由都应改用 _conv_to_response_with_derived。"""
    chat_config = c.chat_config or {}
    return ConversationResponse(
        id=c.id,
        persona_id=c.persona_id,
        persona_name=c.persona.name if c.persona else None,
        title=c.title,
        user_persona_id=c.user_persona_id,
        user_persona_name=c.user_persona.name if c.user_persona else None,
        preset_id=c.preset_id,
        preset_name=c.preset.name if c.preset else None,
        chat_config=chat_config,
        effective_chat_config=_compute_effective_chat_config(chat_config),
        template_id=c.template_id,
        regex_preset_id=c.regex_preset_id,
        worldbook_ids=[str(x) for x in (c.worldbook_ids or [])],
        author_note=c.author_note,
        an_depth=c.an_depth,
        an_role=c.an_role,
        an_interval=c.an_interval,
        analyze_emotion=c.analyze_emotion,
        reply_length_enabled=reply_length_enabled,
        variables=c.variables or {},
        mvu_state=describe_conversation_mvu_state(c.variables or {}),
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


async def _compute_reply_length_enabled(
    db: AsyncSession, template_id: UUID | None,
    *,
    cache: dict[UUID | None, bool] | None = None,
) -> bool:
    """该 template_id 对应模板的 reply_length block 是否启用。

    template_id=None → 用 prompt_renderer.DEFAULT_TEMPLATE_BLOCKS。
    模板已被删（外键已 SET NULL 但前端还没刷新）→ 兜底用默认模板。

    可选 cache 避免 list 接口 N+1。
    """
    if cache is not None and template_id in cache:
        return cache[template_id]

    def _check_default() -> bool:
        from app.services.prompt_renderer import DEFAULT_TEMPLATE_BLOCKS
        for b in DEFAULT_TEMPLATE_BLOCKS:
            if b.type == "reply_length":
                return b.enabled
        return False

    if template_id is None:
        result = _check_default()
    else:
        from app.models.prompt_template import PromptTemplate
        tpl = await db.get(PromptTemplate, template_id)
        if tpl is None:
            result = _check_default()
        else:
            result = False
            for b in (tpl.blocks or []):
                if b.get("type") == "reply_length":
                    result = bool(b.get("enabled", True))
                    break

    if cache is not None:
        cache[template_id] = result
    return result


async def _conv_to_response_with_derived(c, db: AsyncSession):
    """带 derived 字段的异步版（reply_length_enabled 等需要查 DB 的字段）。"""
    rle = await _compute_reply_length_enabled(db, c.template_id)
    return _conv_to_response(c, reply_length_enabled=rle)


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的对话列表。"""
    conversations = await get_user_conversations(db, current_user.id)
    # cache 复用同一模板的 reply_length 查询，避免 N+1
    cache: dict[UUID | None, bool] = {}
    out: list[ConversationResponse] = []
    for c in conversations:
        rle = await _compute_reply_length_enabled(db, c.template_id, cache=cache)
        out.append(_conv_to_response(c, reply_length_enabled=rle))
    return out


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_new_conversation(
    request: ConversationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """新建对话。"""
    conversation = await create_conversation(
        db, current_user.id, request.persona_id, request.user_persona_id,
        title=request.title, preset_id=request.preset_id,
        template_id=request.template_id,
        regex_preset_id=request.regex_preset_id,
        worldbook_ids=request.worldbook_ids,
        greeting_index=request.greeting_index,
    )
    return await _conv_to_response_with_derived(conversation, db)


@router.put("/{conversation_id}/apply-preset", response_model=ConversationResponse)
async def apply_preset(
    conversation_id: UUID,
    request: PresetApplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """将预设应用到对话（合并采样参数和上下文设置到 chat_config）。"""
    conv = await apply_preset_to_conversation(
        db, conversation_id, request.preset_id, current_user.id,
    )
    if conv is None:
        raise NotFoundException("对话或预设不存在")
    return await _conv_to_response_with_derived(conv, db)


@router.put("/{conversation_id}/config", response_model=ConversationResponse)
async def update_config(
    conversation_id: UUID,
    request: ConversationConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新对话配置。"""
    conv = await update_conversation_config(
        db, conversation_id, request.chat_config, current_user.id,
    )
    if conv is None:
        raise NotFoundException("对话不存在")
    return await _conv_to_response_with_derived(conv, db)


class ConversationToggleRequest(BaseModel):
    """对话级开关 PATCH（如 analyze_emotion 等独立开关）。"""
    analyze_emotion: bool | None = Field(None, description="情绪分析功能开关")


@router.patch("/{conversation_id}/toggles", response_model=ConversationResponse)
async def update_conversation_toggles(
    conversation_id: UUID,
    request: ConversationToggleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新对话级独立开关。"""
    conv = await get_conversation_by_id(db, conversation_id, current_user.id)
    if conv is None:
        raise NotFoundException("对话不存在")
    if request.analyze_emotion is not None:
        conv.analyze_emotion = request.analyze_emotion
    db.add(conv)
    await db.commit()
    # get_conversation_by_id 已带 joinedload，再调一次拿一致的关联对象
    fresh = await get_conversation_by_id(db, conversation_id, current_user.id)
    return await _conv_to_response_with_derived(fresh, db)


class TemplateSwitchRequest(BaseModel):
    template_id: UUID | None = Field(None, description="模板 ID（None=使用默认）")


@router.put("/{conversation_id}/template", response_model=ConversationResponse)
async def update_conversation_template(
    conversation_id: UUID,
    request: TemplateSwitchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """切换对话的 Prompt 模板。template_id=None 表示使用默认。"""
    conv = await get_conversation_by_id(db, conversation_id, current_user.id)
    if conv is None:
        raise NotFoundException("对话不存在")
    conv.template_id = request.template_id
    db.add(conv)
    await db.commit()
    conv = await get_conversation_by_id(db, conversation_id, current_user.id)
    return await _conv_to_response_with_derived(conv, db)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除对话。"""
    await delete_conversation(db, conversation_id, current_user.id)


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: UUID,
    limit: int = Query(200, ge=1, le=500, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取对话的消息列表（分页，按时间倒序）。"""
    conv = await get_conversation_by_id(db, conversation_id, current_user.id)
    if conv is None:
        raise NotFoundException("对话不存在")

    messages = await get_conversation_messages(db, conversation_id, limit=limit, offset=offset)
    return [MessageResponse.model_validate(m) for m in messages]


@router.put("/{conversation_id}/regex-preset", response_model=ConversationResponse)
async def switch_regex_preset(
    conversation_id: UUID,
    request: RegexPresetSwitchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """切换对话的正则预设。regex_preset_id=None 表示取消正则绑定。"""
    conv = await get_conversation_by_id(db, conversation_id, current_user.id)
    if conv is None:
        raise NotFoundException("对话不存在")

    if request.regex_preset_id is not None:
        from app.services.regex_preset_service import get_regex_preset
        rp = await get_regex_preset(db, request.regex_preset_id, current_user.id)
        if rp is None:
            raise NotFoundException("正则预设不存在")

    conv.regex_preset_id = request.regex_preset_id
    db.add(conv)
    await db.commit()

    conv = await get_conversation_by_id(db, conversation_id, current_user.id)
    return await _conv_to_response_with_derived(conv, db)


class GreetingSwitchResponse(BaseModel):
    """切换开场白的轻量响应：只回新 Message 的 id + content。"""
    message_id: UUID
    content: str


@router.put("/{conversation_id}/greeting", response_model=GreetingSwitchResponse)
async def switch_greeting(
    conversation_id: UUID,
    request: GreetingSwitchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """切换对话的开场白（仅在用户尚未回复时可用）。

    详见 ADR-0017：开场白切换从"创建前选"搬到"创建后在 UI 里左右切"。
    校验条件：该对话只有 1 条消息且 role==assistant（即用户没回复过）。
    """
    from app.models.message import Message
    from app.models.persona import Persona

    conv = await get_conversation_by_id(db, conversation_id, current_user.id)
    if conv is None:
        raise NotFoundException("对话不存在")

    # 拉所有消息，校验"刚创建未开始"的状态
    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at)
    )
    msgs = list(msg_result.scalars().all())
    if len(msgs) != 1 or msgs[0].role != "assistant":
        from app.utils.exceptions import AppException
        raise AppException(
            "开场白切换仅在对话尚未开始时可用", status_code=400,
        )

    # 拉 persona 算新开场白
    if conv.persona_id is None:
        raise NotFoundException("对话未绑定角色卡")
    persona = await db.get(Persona, conv.persona_id)
    if persona is None:
        raise NotFoundException("角色卡不存在")

    idx = request.greeting_index
    alts = list(persona.alternate_greetings or [])
    if idx == 0:
        new_text = persona.first_message
    elif 1 <= idx <= len(alts):
        new_text = alts[idx - 1]
    else:
        from app.utils.exceptions import AppException
        raise AppException("开场白索引越界", status_code=400)

    if not new_text:
        from app.utils.exceptions import AppException
        raise AppException("该位置的开场白为空", status_code=400)

    # 用 message_pipeline 走完整流程（MacroEngine → reply 正则 → MVU 解析）
    # 与 create_conversation 完全一致，详见 ADR-0015。
    from app.services.message_pipeline import process_assistant_message_text
    from app.models.user import User as UserModel
    user_row = await db.get(UserModel, current_user.id)
    user_persona = None
    if conv.user_persona_id:
        user_persona = await db.get(Persona, conv.user_persona_id)
    macro_scope = {
        "local": dict(conv.variables or {}),
        "global": dict((user_row.global_variables if user_row else None) or {}),
        "names": {
            "user": (user_persona.name if user_persona else None)
                    or (user_row.nickname if user_row else "")
                    or "",
            "char": persona.name,
        },
    }
    processed_text, updated_scope = await process_assistant_message_text(
        new_text,
        db=db,
        conv=conv,
        mvu_scope=macro_scope,
        macro_scope=macro_scope,
        run_macro=True,
    )

    # 写回 Message + conv.variables（如果 UpdateVariable 解析出新 stat_data）
    msgs[0].content = processed_text
    db.add(msgs[0])
    if updated_scope is not None:
        local_after = updated_scope.get("local") or {}
        if local_after:
            conv.variables = local_after
            db.add(conv)
    await db.commit()
    await db.refresh(msgs[0])

    return GreetingSwitchResponse(
        message_id=msgs[0].id,
        content=msgs[0].content,
    )


@router.get("/{conversation_id}/regex-scripts")
async def get_conversation_regex_scripts(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取对话当前生效的正则脚本（promptOnly=false，前端显示用）。"""
    scripts = await get_active_scripts(db, conversation_id, current_user.id)
    return {"scripts": scripts}


@router.put("/{conversation_id}/worldbooks", response_model=ConversationResponse)
async def update_conversation_worldbooks(
    conversation_id: UUID,
    request: WorldbookBindingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新对话绑定的世界书列表（覆盖式；顺序敏感）。"""
    conv = await get_conversation_by_id(db, conversation_id, current_user.id)
    if conv is None:
        raise NotFoundException("对话不存在")

    # 校验所有 worldbook_id 都属于当前用户或系统模板
    from app.services.worldbook.service import get_worldbooks_by_ids

    found = await get_worldbooks_by_ids(db, request.worldbook_ids)
    for wb in found:
        if wb.user_id is not None and wb.user_id != current_user.id:
            raise NotFoundException(f"世界书 {wb.id} 不存在或无权访问")
    if len(found) != len(request.worldbook_ids):
        raise NotFoundException("部分世界书不存在")

    conv.worldbook_ids = [str(x) for x in request.worldbook_ids]
    db.add(conv)
    await db.commit()
    conv = await get_conversation_by_id(db, conversation_id, current_user.id)
    return await _conv_to_response_with_derived(conv, db)


@router.delete("/{conversation_id}/variables", response_model=ConversationResponse)
async def clear_conversation_variables(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """清空对话级 MVU 变量桶（Conversation.variables）。

    用于变量被脚本写坏时的兜底重置；不影响全局变量。详见 ADR-0009。
    """
    conv = await get_conversation_by_id(db, conversation_id, current_user.id)
    if conv is None:
        raise NotFoundException("对话不存在")
    conv.variables = {}
    db.add(conv)
    await db.commit()
    conv = await get_conversation_by_id(db, conversation_id, current_user.id)
    return await _conv_to_response_with_derived(conv, db)


@router.post("/{conversation_id}/variables/reload-mvu-initial-state", response_model=ConversationResponse)
async def reload_mvu_initial_state(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """缺失合并式重载 MVU 初始状态。

    从当前角色卡和绑定世界书的 [opening]/[initvar] 条目重新读取初始值，
    只填补缺失字段，不覆盖用户/LLM 已写过的字段。
    """
    conv = await reload_conversation_mvu_initial_state(
        db, conversation_id, current_user.id,
    )
    if conv is None:
        raise NotFoundException("对话不存在")
    return await _conv_to_response_with_derived(conv, db)


@router.put("/{conversation_id}/author-note", response_model=ConversationResponse)
async def update_conversation_author_note(
    conversation_id: UUID,
    request: AuthorNoteUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新对话的 Author's Note（任一字段缺省则不变）。"""
    conv = await get_conversation_by_id(db, conversation_id, current_user.id)
    if conv is None:
        raise NotFoundException("对话不存在")

    payload = request.model_dump(exclude_none=True)
    # 显式允许把 author_note 置空字符串
    if "author_note" in request.model_dump():
        # exclude_none 会过滤掉显式 null，但这里希望保留 "" 或 None 都生效
        payload["author_note"] = request.author_note

    for k, v in payload.items():
        setattr(conv, k, v)
    db.add(conv)
    await db.commit()
    conv = await get_conversation_by_id(db, conversation_id, current_user.id)
    return await _conv_to_response_with_derived(conv, db)
