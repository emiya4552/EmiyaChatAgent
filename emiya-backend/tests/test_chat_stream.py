# -*- coding: utf-8 -*-
"""聊天 SSE 流式端点的协议测试。

覆盖：
- message_done 事件携带真 Message.id（而非空字符串或假 UUID）
- 流式中断时 error 事件携带 partial_message_id
- 不再 emit 重复的 message_done
"""
import json
import re
import uuid

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.message import Message


def _parse_sse(text: str) -> list[dict]:
    """从 SSE 文本解析事件列表 [{event, data}]."""
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = None
        data_str = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_name = line[7:].strip()
            elif line.startswith("data: "):
                data_str = line[6:].strip()
        if event_name and data_str:
            try:
                events.append({"event": event_name, "data": json.loads(data_str)})
            except json.JSONDecodeError:
                events.append({"event": event_name, "data": data_str})
    return events


# ─── B4: 正常路径 message_done 带真 message_id ─────────────────────


async def test_message_done_carries_real_assistant_message_id(
    client, auth_headers, test_conversation, mock_deepseek_normal,
):
    """正常完成时，message_done 的 data.message_id 等于 DB 里 assistant Message 的 id。"""
    response = await client.post(
        f"/api/v1/conversations/{test_conversation.id}/chat",
        json={"content": "你好", "reply_length": "short"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text

    events = _parse_sse(response.text)

    # 收到至少一个 message_done
    done_events = [e for e in events if e["event"] == "message_done"]
    assert len(done_events) >= 1, f"应收到 message_done 事件，实际事件: {[e['event'] for e in events]}"

    # message_id 是有效 UUID（非空字符串、非凭空生成）
    message_id = done_events[-1]["data"].get("message_id")
    assert message_id, f"message_done.data.message_id 不能为空，实际: {done_events[-1]['data']!r}"

    # message_id 在 DB 里能找到对应的 assistant Message
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Message).where(
                Message.conversation_id == test_conversation.id,
                Message.role == "assistant",
            )
        )
        assistant_msgs = list(result.scalars().all())

    assert len(assistant_msgs) == 1, f"DB 里应有 1 条 assistant 消息，实际 {len(assistant_msgs)}"
    real_id = str(assistant_msgs[0].id)
    assert message_id == real_id, f"SSE 的 message_id={message_id} ≠ DB 的 {real_id}"


async def test_no_duplicate_message_done(
    client, auth_headers, test_conversation, mock_deepseek_normal,
):
    """正常完成时，message_done 事件只应 emit 一次（不再有 api/chat.py 重复 emit）。"""
    response = await client.post(
        f"/api/v1/conversations/{test_conversation.id}/chat",
        json={"content": "你好", "reply_length": "short"},
        headers=auth_headers,
    )
    events = _parse_sse(response.text)
    done_events = [e for e in events if e["event"] == "message_done"]
    assert len(done_events) == 1, f"message_done 应只 emit 一次，实际 {len(done_events)} 次"


# ─── B5: 中断路径 error 带 partial_message_id ─────────────────────


async def test_tool_only_mvu_update_is_applied_without_content(
    client, auth_headers, test_conversation, mock_deepseek_normal, monkeypatch,
):
    from app.config import settings
    from app.models.conversation import Conversation
    from app.models.persona import Persona
    from app.models.worldbook import Worldbook

    monkeypatch.setattr(settings, "MVU_TOOL_UPDATE_ENABLED", True)

    async def _emit_tool_only(*args, **kwargs):
        assert kwargs.get("tools")
        tool_calls_out = kwargs.get("tool_calls_out")
        if tool_calls_out is not None:
            tool_calls_out.append({
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "update_variables",
                    "arguments": json.dumps({
                        "patch": [
                            {"op": "replace", "path": "/score", "value": "150"}
                        ]
                    }),
                },
            })
        if False:
            yield ""

    monkeypatch.setattr(
        "app.services.chat_service.call_deepseek_stream",
        _emit_tool_only,
    )

    async with AsyncSessionLocal() as session:
        persona = await session.get(Persona, test_conversation.persona_id)
        persona.uses_mvu = True

        worldbook = Worldbook(
            id=uuid.uuid4(),
            user_id=test_conversation.user_id,
            name="mvu rules",
            entries=[
                {
                    "uid": 1,
                    "comment": "[mvu_update] rules",
                    "content": (
                        "rules:\n"
                        "  score:\n"
                        "    type: number\n"
                        "    range: 0~100\n"
                    ),
                    "enabled": True,
                    "constant": True,
                    "selective": False,
                    "position": 0,
                    "order": 0,
                    "role": "system",
                }
            ],
        )
        conv = await session.get(Conversation, test_conversation.id)
        conv.worldbook_ids = [str(worldbook.id)]
        conv.variables = {"stat_data": {"score": 40}}
        session.add(worldbook)
        await session.commit()

    response = await client.post(
        f"/api/v1/conversations/{test_conversation.id}/chat",
        json={"content": "update score", "reply_length": "short"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text

    events = _parse_sse(response.text)
    done_events = [e for e in events if e["event"] == "message_done"]
    assert len(done_events) == 1

    done = done_events[0]["data"]
    assert done["variables"]["stat_data"]["score"] == 100
    assert done["mvu_runtime_view"]["update"]["channel"] == "tool"
    assert done["mvu_runtime_view"]["update"]["applied"] == 1
    assert done["mvu_runtime_view"]["update"]["clamped"][0]["path"] == "/score"

    async with AsyncSessionLocal() as session:
        conv = await session.get(Conversation, test_conversation.id)
        assert conv.variables["stat_data"]["score"] == 100


async def test_error_carries_partial_message_id_on_interrupt(
    client, auth_headers, test_conversation, mock_deepseek_interrupt_after_2,
):
    """流式生成中断时，error event 应携带 partial_message_id 指向 DB 里已写入的部分消息。"""
    response = await client.post(
        f"/api/v1/conversations/{test_conversation.id}/chat",
        json={"content": "你好", "reply_length": "short"},
        headers=auth_headers,
    )
    assert response.status_code == 200

    events = _parse_sse(response.text)
    error_events = [e for e in events if e["event"] == "error"]
    assert len(error_events) >= 1, f"应收到 error 事件，实际事件: {[e['event'] for e in events]}"

    partial_id = error_events[-1]["data"].get("partial_message_id")
    assert partial_id, f"error.data.partial_message_id 不能为空（中断时有部分内容）：{error_events[-1]['data']!r}"

    # 该 id 在 DB 里能找到 assistant Message，且 content 以 [流式中断] 结尾
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Message).where(
                Message.conversation_id == test_conversation.id,
                Message.role == "assistant",
            )
        )
        assistant_msgs = list(result.scalars().all())

    assert len(assistant_msgs) == 1
    assert str(assistant_msgs[0].id) == partial_id
    assert assistant_msgs[0].content.endswith("[流式中断]"), \
        f"中断消息 content 应以 [流式中断] 结尾，实际: {assistant_msgs[0].content!r}"
