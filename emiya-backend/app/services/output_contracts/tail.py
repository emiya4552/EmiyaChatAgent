# -*- coding: utf-8 -*-
"""尾部模板契约支持。

本模块集中承接历史的世界书尾部模板启发式识别和 prefix continuation 续写。
调用方只关心“缺了哪些尾部块、能否补写”，不需要知道 `<details>`、
`<summary>`、自定义标签和 scaffold 的具体拼法。
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import AsyncGenerator
from uuid import UUID

from app.config import settings
from app.services.llm_service import call_deepseek_stream_prefix
from app.services.output_contracts.types import (
    TailBlockContract,
    VisibleOutputContract,
)

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[UUID, str, dict], Awaitable[None]]
UpdateReplyFn = Callable[[str], None]


def find_missing_tail_blocks(
    reply: str,
    blocks: list[TailBlockContract],
) -> list[TailBlockContract]:
    """返回缺失的尾部模板块，并按世界书 order 排序。"""
    missing = [block for block in blocks if block.marker and block.marker not in reply]
    missing.sort(key=lambda block: block.order)
    return missing


def build_template_scaffold(
    content: str,
    abstract: dict | None = None,
) -> str:
    """从模板原文确定性提取 prefix continuation 使用的最小前缀。"""
    hint = (abstract or {}).get("template_span_hint") or {}
    summary_text = str(hint.get("summary_text") or "").strip()

    details_match = re.search(r"<details[^>]*>", content, re.IGNORECASE)
    if not details_match:
        return ""

    search_start = details_match.end()
    if summary_text:
        summary_idx = content.find(summary_text, search_start)
        if summary_idx != -1:
            search_start = summary_idx

    summary_end_idx = content.find("</summary>", search_start)
    if summary_end_idx == -1:
        return content[details_match.start():details_match.end()]

    end = summary_end_idx + len("</summary>")
    rest = content[end:]
    inner_match = re.match(r"\s*<[A-Za-z][^/>]*>", rest)
    if inner_match:
        end = end + inner_match.end()

    return content[details_match.start():end]


def build_tail_block_scaffold(block: TailBlockContract) -> str:
    """按契约块的原文和抽象 hint 提取可续写前缀。"""
    return build_template_scaffold(block.content, block.abstract)


def build_tail_template_directive(blocks: list[TailBlockContract] | list[str]) -> str:
    """构造要求模型追加尾部模板的系统提醒。"""
    markers = [block.marker if isinstance(block, TailBlockContract) else str(block) for block in blocks]
    bullets = "\n".join(f"- {marker}" for marker in markers if marker)
    return (
        "[输出尾部模板强制约束]\n"
        "本轮回复必须在正文之后追加以下世界书要求的 HTML 模板"
        "（按各模板内字段定义填空，模板原文见上文世界书条目）：\n"
        f"{bullets}\n"
        "即便上文 / 预设要求严格的输出格式（如 <content></content> 包裹、"
        "单一标签结构、思维链分段等），HTML 模板块**必须**追加输出，不得省略。"
        "如有 <content> 闭合标签，模板追加在标签之后。"
    )


async def continue_missing_tail_blocks(
    *,
    reply: str,
    contract: VisibleOutputContract,
    messages: list[dict],
    conversation_id: UUID,
    chat_config: dict,
    broadcast: BroadcastFn | None = None,
    update_reply: UpdateReplyFn | None = None,
) -> AsyncGenerator[str, None]:
    """用 prefix continuation 补写缺失尾部块，并逐段产出 SSE delta。"""
    blocks = contract.required_tail_blocks
    if not blocks:
        return

    current_reply = reply or ""
    missing = find_missing_tail_blocks(current_reply, blocks)
    if not missing:
        return

    missing = missing[: settings.WORLDBOOK_TAIL_CONTINUATION_MAX]
    logger.info(
        "[尾部模板续写] 主回复缺 %s 个模板，开始 prefix continuation: %s",
        len(missing),
        [block.marker for block in missing],
    )

    cont_temperature = chat_config.get("temperature", settings.CHAT_TEMPERATURE)
    cont_max_tokens = settings.WORLDBOOK_TAIL_CONTINUATION_MAX_TOKENS

    for block in missing:
        try:
            scaffold = build_tail_block_scaffold(block)
            if not scaffold.strip():
                continue

            scaffold_payload = "\n\n" + scaffold
            yield f"event: message_delta\ndata: {json.dumps({'content': scaffold_payload}, ensure_ascii=False)}\n\n"
            if broadcast is not None:
                await broadcast(conversation_id, "message_delta", {"content": scaffold_payload})
            current_reply += scaffold_payload

            try:
                async for token in call_deepseek_stream_prefix(
                    messages=messages,
                    prefix_text=current_reply,
                    temperature=cont_temperature,
                    max_tokens=cont_max_tokens,
                    stop=["</details>"],
                ):
                    yield f"event: message_delta\ndata: {json.dumps({'content': token}, ensure_ascii=False)}\n\n"
                    if broadcast is not None:
                        await broadcast(conversation_id, "message_delta", {"content": token})
                    current_reply += token
            except Exception as exc:
                logger.warning(
                    "[尾部模板续写] marker=%s stream 失败，主回复保留 scaffold 但不闭合: %s",
                    block.marker,
                    exc,
                )
                continue

            closing = "\n</details>"
            yield f"event: message_delta\ndata: {json.dumps({'content': closing}, ensure_ascii=False)}\n\n"
            if broadcast is not None:
                await broadcast(conversation_id, "message_delta", {"content": closing})
            current_reply += closing
        except Exception as exc:
            logger.warning("[尾部模板续写] marker=%s 失败，静默跳过: %s", block.marker, exc)
            continue

    if update_reply is not None:
        update_reply(current_reply)
