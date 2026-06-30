# -*- coding: utf-8 -*-
"""上下文管理服务：滑动窗口和摘要压缩。"""
import logging

from app.config import settings
from app.models.message import Message
from app.services.llm_service import call_deepseek_non_stream

logger = logging.getLogger(__name__)


def _format_history(messages: list[Message]) -> list[dict]:
    """将消息列表格式化为 API 格式。"""
    return [
        {"role": msg.role, "content": msg.content}
        for msg in messages
        if msg.role in ("user", "assistant")
    ]


async def compress_history(messages: list[Message]) -> str:
    """对消息列表生成摘要（全新压缩，不考虑已有摘要）。

    Args:
        messages: 需要压缩的消息列表。

    Returns:
        摘要文本。
    """
    if not messages:
        return ""

    formatted = _format_history(messages)
    compress_prompt = [
        {
            "role": "system",
            "content": "请用一大段中文对以下对话历史进行摘要。包含：主要话题、关键信息、用户情绪走向。严格不超过300字，如果信息过多请只保留最重要的内容。",
        },
        {
            "role": "user",
            "content": "\n".join(
                f"{m['role']}: {m['content'][:200]}" for m in formatted
            ),
        },
    ]

    try:
        summary = await call_deepseek_non_stream(
            compress_prompt,
            temperature=settings.SUMMARY_TEMPERATURE,
            max_tokens=settings.SUMMARY_MAX_TOKENS,
        )
        logger.info(f"摘要生成成功，原 {len(messages)} 条消息 → 摘要 {len(summary)} 字")
        summary_text = summary.strip()[:500]
        return f"[对话摘要] {summary_text}"
    except Exception as e:
        logger.error(f"摘要生成失败: {e}")
        return f"[对话摘要] 之前进行了 {len(messages) // 2} 轮对话"


async def merge_summary(
    existing_summary: str, new_messages: list[Message]
) -> str:
    """将新增溢出消息合并到已有摘要中，生成一份更新后的摘要。

    不简单拼接——而是把已有摘要 + 新增消息一起交给 LLM，
    让它产出合并后的新版摘要，保持长度有界（~300 字）。

    Args:
        existing_summary: 已有的摘要文本（含 "[对话摘要] " 前缀）。
        new_messages: 新增的溢出消息（尚未被摘要覆盖的）。

    Returns:
        合并后的摘要文本。
    """
    if not new_messages:
        return existing_summary

    # 去输入前缀，防止 LLM 在输出中复刻
    clean_existing = existing_summary.removeprefix("[对话摘要] ").strip()

    formatted = _format_history(new_messages)
    merge_prompt = [
        {
            "role": "system",
            "content": (
                "你是一个对话摘要维护助手。请将新增对话内容合并到已有摘要中，"
                "生成一份更新后的完整摘要。包含：主要话题、关键信息、用户情绪走向。"
                "严格不超过300字。如果信息过多，保留最近和最重要的内容，精简甚至省略较早且不重要的信息。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"已有摘要：\n{clean_existing}\n\n"
                f"新增对话：\n"
                + "\n".join(
                    f"{m['role']}: {m['content'][:200]}" for m in formatted
                )
            ),
        },
    ]

    try:
        summary = await call_deepseek_non_stream(
            merge_prompt,
            temperature=settings.SUMMARY_TEMPERATURE,
            max_tokens=settings.SUMMARY_MAX_TOKENS,
        )
        logger.info(
            f"摘要合并成功，+{len(new_messages)} 条消息 → 摘要 {len(summary)} 字"
        )
        # 去输出前缀（防 LLM 复刻）+ 硬截断兜底
        summary_text = summary.strip().removeprefix("[对话摘要] ").strip()[:500]
        return f"[对话摘要] {summary_text}"
    except Exception as e:
        logger.error(f"摘要合并失败: {e}")
        return existing_summary


async def update_summary(
    messages: list[Message],
    existing_summary: str | None = None,
) -> str:
    """统一的摘要更新入口：无已有摘要则全新压缩，有则增量合并。

    Args:
        messages: 需要处理的消息（全新压缩时为全部溢出，增量时为新增溢出）。
        existing_summary: 已有的持久化摘要。

    Returns:
        更新后的摘要文本。
    """
    if not messages:
        return existing_summary or ""

    if existing_summary:
        return await merge_summary(existing_summary, messages)
    else:
        return await compress_history(messages)
