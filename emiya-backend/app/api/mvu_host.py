# -*- coding: utf-8 -*-
"""MVU 卡 UI 宿主能力端点（ADR-0008d D2）。

卡 UI（如 WuWa 飞讯手机终端）经浏览器 Host 的 Bridge 请求这些宿主能力；前端能力处理器
（`makeCapabilityHandler` 的 providers）把 read/dangerous 层请求转成对这些端点的调用。
全部校验会话所有权；**dangerous 层**（`generateRaw` 卡调 LLM、`set/create/deleteChatMessages`
卡改会话楼层）额外要求 `conv.mvu_capabilities.dangerous is True`（per-conversation opt-in）。

message_id 采用 TavernHelper 语义：会话内按 `created_at` 升序的 **0-based 序号**（`-1`=最后一条）；
`{{lastMessageId}}` 宏在此按 n-1 兜底替换。
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.message import Message
from app.models.user import User
from app.services.conversation_service import get_conversation_by_id
from app.services.llm_service import call_deepseek_non_stream
from app.utils.exceptions import AppException, NotFoundException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/conversations", tags=["MVU Host 能力"])

# 卡触发生成的安全上限：卡自带 custom_api/花费不可控，这里一律走 EMIYA 自己的 LLM + 封顶 token。
_GENERATE_MAX_TOKENS_CAP = 2000


# ── 请求/响应模型 ──────────────────────────────────────────────
class GenerateRawRequest(BaseModel):
    """generateRaw 的裁剪配置（TavernHelper generateConfig 的安全子集）。

    **安全**：忽略卡传的 `custom_api`（卡自带 apiurl/key → SSRF/滥用风险），只用 EMIYA 的 LLM。
    """
    user_input: str | None = None
    prompt: str | None = None
    ordered_prompts: list[dict] | None = None
    temperature: float = 1.0
    max_tokens: int = 1200


class ChatMessageItem(BaseModel):
    message_id: int | None = None  # set/delete 用；create 忽略
    role: str | None = None        # create 用：user/assistant/system
    message: str | None = None     # 文本；set 时 None=不改
    data: dict | None = None       # per-message 变量袋；set 时 None=不改


class CreateChatMessagesRequest(BaseModel):
    messages: list[ChatMessageItem] = Field(default_factory=list)
    insert_before: int | None = None  # None=追加到末尾


class SetChatMessagesRequest(BaseModel):
    messages: list[ChatMessageItem] = Field(default_factory=list)


class DeleteChatMessagesRequest(BaseModel):
    message_ids: list[int] = Field(default_factory=list)


# ── helpers ────────────────────────────────────────────────────
async def _load_conv_or_404(db: AsyncSession, conversation_id: UUID, user_id: UUID):
    conv = await get_conversation_by_id(db, conversation_id, user_id)
    if conv is None:
        raise NotFoundException("对话不存在")
    return conv


def _require_dangerous(conv) -> None:
    """dangerous 能力门控：per-conversation 未显式开启则 403。"""
    if not (conv.mvu_capabilities or {}).get("dangerous"):
        raise AppException(
            "该会话未开启 MVU 危险能力（卡调 LLM / 改会话楼层）；请在对话设置里开启后重试。",
            status_code=403,
        )


async def _ordered_messages(db: AsyncSession, conversation_id: UUID) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    return list(result.scalars().all())


def _msg_view(idx: int, m: Message) -> dict:
    return {"message_id": idx, "role": m.role, "message": m.content, "data": m.data or {}}


def _resolve_range(spec: str, n: int) -> list[int]:
    """把 TavernHelper 的 id/range 规格解析成 0-based 序号列表。
    支持：`-1`（最后一条）、`3`（单条）、`0-5`（闭区间）、`{{lastMessageId}}` 宏（→ n-1）。"""
    if n <= 0:
        return []
    s = str(spec or "-1").replace("{{lastMessageId}}", str(n - 1)).strip()

    def norm(i: int) -> int:
        return i + n if i < 0 else i

    if "-" in s and not s.startswith("-"):
        a, _, b = s.partition("-")
        try:
            lo, hi = norm(int(a)), norm(int(b))
        except ValueError:
            return []
        lo, hi = max(0, min(lo, hi)), min(n - 1, max(lo, hi))
        return list(range(lo, hi + 1))
    try:
        i = norm(int(s))
    except ValueError:
        return []
    return [i] if 0 <= i < n else []


# ── read 层：读会话楼层 / 世界书 ────────────────────────────────
@router.get("/{conversation_id}/mvu/chat-messages")
async def mvu_get_chat_messages(
    conversation_id: UUID,
    range: str = Query("-1", description="TavernHelper id/range：-1 / 3 / 0-5 / {{lastMessageId}}"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """getChatMessages（read）：返回指定楼层的 {message_id, role, message, data}。"""
    conv = await _load_conv_or_404(db, conversation_id, current_user.id)
    msgs = await _ordered_messages(db, conv.id)
    idxs = _resolve_range(range, len(msgs))
    return [_msg_view(i, msgs[i]) for i in idxs]


@router.get("/{conversation_id}/mvu/worldbook")
async def mvu_get_worldbook(
    conversation_id: UUID,
    name: str | None = Query(None, description="世界书名（缺省=会话绑定的全部）"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """getWorldbook（read）：返回会话绑定世界书的条目（只读）。"""
    from app.services.worldbook.service import get_worldbooks_by_ids

    conv = await _load_conv_or_404(db, conversation_id, current_user.id)
    ids = [UUID(str(x)) for x in (conv.worldbook_ids or [])]
    books = await get_worldbooks_by_ids(db, ids)
    entries: list[dict] = []
    for b in books:
        if name and b.name != name:
            continue
        for e in (b.entries or []):
            entries.append(e)
    return entries


# ── dangerous 层：卡调 LLM / 卡改会话楼层（per-conversation opt-in）──
@router.post("/{conversation_id}/mvu/generate")
async def mvu_generate_raw(
    conversation_id: UUID,
    request: GenerateRawRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """generateRaw（dangerous）：卡触发 LLM 生成。忽略卡自带 custom_api，走 EMIYA LLM + 封顶 token。"""
    conv = await _load_conv_or_404(db, conversation_id, current_user.id)
    _require_dangerous(conv)

    messages: list[dict] = []
    for p in (request.ordered_prompts or []):
        if not isinstance(p, dict):
            continue  # 跳过 'chat_history'/'user_input' 这类字符串标记（本端点不展开）
        role = (p.get("role") or "system").lower()
        content = p.get("content") or p.get("message") or ""
        if role in ("user", "assistant", "system") and content:
            messages.append({"role": role, "content": content})
    if request.user_input:
        messages.append({"role": "user", "content": request.user_input})
    if not messages and request.prompt:
        messages.append({"role": "user", "content": request.prompt})
    if not messages:
        raise AppException("generateRaw：空 prompt", status_code=400)

    text = await call_deepseek_non_stream(
        messages,
        temperature=max(0.0, min(request.temperature, 2.0)),
        max_tokens=max(1, min(request.max_tokens, _GENERATE_MAX_TOKENS_CAP)),
    )
    logger.info("[MVU-CAP] generateRaw conv=%s prompts=%s out_chars=%s", conv.id, len(messages), len(text or ""))
    return {"text": text}


@router.post("/{conversation_id}/mvu/chat-messages")
async def mvu_create_chat_messages(
    conversation_id: UUID,
    request: CreateChatMessagesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """createChatMessages（dangerous）：卡往会话追加楼层（带 per-message data）。只能改自己会话。"""
    conv = await _load_conv_or_404(db, conversation_id, current_user.id)
    _require_dangerous(conv)
    created: list[Message] = []
    for it in request.messages:
        role = (it.role or "system").lower()
        if role not in ("user", "assistant", "system"):
            role = "system"
        m = Message(
            conversation_id=conv.id,
            role=role,
            content=it.message or "",
            data=it.data,
        )
        db.add(m)
        created.append(m)
    await db.commit()
    msgs = await _ordered_messages(db, conv.id)
    id_by_pk = {str(m.id): i for i, m in enumerate(msgs)}
    return [
        {"message_id": id_by_pk.get(str(m.id)), "role": m.role, "message": m.content, "data": m.data or {}}
        for m in created
    ]


@router.patch("/{conversation_id}/mvu/chat-messages")
async def mvu_set_chat_messages(
    conversation_id: UUID,
    request: SetChatMessagesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """setChatMessages（dangerous）：按 message_id 改楼层文本/data（None=不改该字段）。"""
    conv = await _load_conv_or_404(db, conversation_id, current_user.id)
    _require_dangerous(conv)
    msgs = await _ordered_messages(db, conv.id)
    n = len(msgs)
    updated: list[dict] = []
    for it in request.messages:
        if it.message_id is None:
            continue
        idx = it.message_id + n if it.message_id < 0 else it.message_id
        if not (0 <= idx < n):
            continue
        m = msgs[idx]
        if it.message is not None:
            m.content = it.message
        if it.data is not None:
            m.data = it.data
        db.add(m)
        updated.append(_msg_view(idx, m))
    await db.commit()
    return updated


@router.delete("/{conversation_id}/mvu/chat-messages")
async def mvu_delete_chat_messages(
    conversation_id: UUID,
    request: DeleteChatMessagesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """deleteChatMessages（dangerous）：按 message_id（0-based 序号）删楼层。"""
    conv = await _load_conv_or_404(db, conversation_id, current_user.id)
    _require_dangerous(conv)
    msgs = await _ordered_messages(db, conv.id)
    n = len(msgs)
    deleted = 0
    for mid in request.message_ids:
        idx = mid + n if mid < 0 else mid
        if 0 <= idx < n:
            await db.delete(msgs[idx])
            deleted += 1
    await db.commit()
    return {"deleted": deleted}
