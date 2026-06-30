# -*- coding: utf-8 -*-
"""聊天 SSE 流式端点，集成情绪分析和 DB 持久化。"""
import json
import logging
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.chat import ChatMessageRequest
from app.services.chat_service import process_chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["聊天"])


@router.get("/conversations/{conversation_id}/live")
async def live_stream(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """实时旁观 SSE 端点 — 订阅对话的 Redis PubSub 流。

    任何人（有 token）都可以围观任意对话的实时生成过程。
    脚本驱动对话时，前端打开此对话即可看到逐字打出的动画。
    """
    from app.services.redis_client import subscribe_conversation

    return StreamingResponse(
        subscribe_conversation(str(conversation_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/conversations/{conversation_id}/chat")
async def chat_stream(
    conversation_id: uuid.UUID,
    request: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE 流式聊天端点。

    process_chat 自己 yield 所有 SSE 事件（含 emotion / message_delta /
    message_done / affinity_update / error 等），本端点只做透传 + 异常包装。
    """
    async def generate():
        try:
            async for sse_event in process_chat(
                db, conversation_id, current_user.id, request.content,
                reply_length=request.reply_length or "medium",
            ):
                yield sse_event
        except Exception as e:
            logger.error(f"流式对话异常: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': '回复生成失败，请稍后重试'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
