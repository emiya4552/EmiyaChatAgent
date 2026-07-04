# -*- coding: utf-8 -*-
"""DeepSeek API 调用封装，支持非流式和流式两种模式。"""
import json
import logging
from typing import AsyncGenerator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_llm_client: httpx.AsyncClient | None = None


def _get_llm_client() -> httpx.AsyncClient:
    """获取共享的 httpx AsyncClient（懒初始化 + 连接池复用）。"""
    global _llm_client
    if _llm_client is None:
        _llm_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.DEEPSEEK_TIMEOUT),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=20),
        )
    return _llm_client


async def close_llm_client() -> None:
    """关闭共享的 httpx AsyncClient。"""
    global _llm_client
    if _llm_client is not None:
        await _llm_client.aclose()
        _llm_client = None


async def call_deepseek_non_stream(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 2000,
    top_p: float | None = None,
    frequency_penalty: float | None = None,
    presence_penalty: float | None = None,
) -> str:
    """调用 DeepSeek API（非流式），返回完整回复文本。"""
    url = f"{settings.DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if top_p is not None:
        payload["top_p"] = top_p
    if frequency_penalty is not None:
        payload["frequency_penalty"] = frequency_penalty
    if presence_penalty is not None:
        payload["presence_penalty"] = presence_penalty

    client = _get_llm_client()
    try:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        logger.error(f"DeepSeek API 返回错误: {e.response.status_code}, {e.response.text}")
        raise
    except httpx.RequestError as e:
        logger.error(f"DeepSeek API 请求失败: {e}")
        raise

async def call_deepseek_tools_non_stream(
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: str | dict = "auto",
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1000,
) -> tuple[str, list[dict]]:
    """Call DeepSeek once and return both content and tool calls."""
    url = f"{settings.DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": model or settings.DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice

    client = _get_llm_client()
    try:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        message = data["choices"][0].get("message") or {}
        return message.get("content") or "", list(message.get("tool_calls") or [])
    except httpx.HTTPStatusError as e:
        logger.error(
            f"DeepSeek API tool call returned error: {e.response.status_code}, {e.response.text}"
        )
        raise
    except httpx.RequestError as e:
        logger.error(f"DeepSeek API tool call request failed: {e}")
        raise


def _accumulate_tool_call_deltas(acc: dict, deltas: list) -> None:
    """把流式 delta.tool_calls 片段按 index 累积（OpenAI/DeepSeek 约定）。

    acc: {index: {"id","type","function":{"name","arguments"}}}；arguments 分片拼接。
    """
    for d in deltas or []:
        if not isinstance(d, dict):
            continue
        idx = d.get("index", 0)
        slot = acc.setdefault(
            idx, {"id": None, "type": "function", "function": {"name": "", "arguments": ""}}
        )
        if d.get("id"):
            slot["id"] = d["id"]
        if d.get("type"):
            slot["type"] = d["type"]
        fn = d.get("function") or {}
        if fn.get("name"):
            slot["function"]["name"] = fn["name"]
        if fn.get("arguments"):
            slot["function"]["arguments"] += fn["arguments"]


async def call_deepseek_stream(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 2000,
    top_p: float | None = None,
    frequency_penalty: float | None = None,
    presence_penalty: float | None = None,
    tools: list[dict] | None = None,
    tool_calls_out: list | None = None,
) -> AsyncGenerator[str, None]:
    """调用 DeepSeek API（流式），逐 token 返回回复内容。

    ADR-0005：传入 `tools` 时启用 function calling；`tool_calls_out` 若给了一个 list，
    流结束后会被填入本次累积好的 tool_calls（单次调用同时拿 content + tool_call）。
    """
    url = f"{settings.DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if top_p is not None:
        payload["top_p"] = top_p
    if frequency_penalty is not None:
        payload["frequency_penalty"] = frequency_penalty
    if presence_penalty is not None:
        payload["presence_penalty"] = presence_penalty
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    tc_acc: dict = {}
    client = _get_llm_client()
    try:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                        if tools and delta.get("tool_calls"):
                            _accumulate_tool_call_deltas(tc_acc, delta["tool_calls"])
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
    except httpx.HTTPStatusError as e:
        logger.error(f"DeepSeek API 流式调用返回错误: {e.response.status_code}")
        raise
    except httpx.RequestError as e:
        logger.error(f"DeepSeek API 流式调用请求失败: {e}")
        raise
    finally:
        if tool_calls_out is not None and tc_acc:
            tool_calls_out.extend(tc_acc[k] for k in sorted(tc_acc))


async def call_deepseek_stream_prefix(
    messages: list[dict],
    prefix_text: str,
    temperature: float = 0.7,
    max_tokens: int = 800,
    stop: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """DeepSeek Chat Prefix Completion（Beta 端点）。

    用法：在 messages 末尾追加 assistant role + prefix=true 消息；DeepSeek 会从
    该 prefix 续写。用于"模型主回复缺世界书要求的尾部模板时，强制补"的场景。

    Beta 端点：将 DEEPSEEK_BASE_URL 的 /v1 替换为 /beta；模型仍是 deepseek-chat。

    Args:
        messages: 主回复用的完整 messages（含 system + history + user）
        prefix_text: 作为 assistant 消息的 prefix 文本；模型从其末尾续写
        stop: 停止序列列表（如 ["</details>"] 让模型填完模板就停）
    """
    # 把 v1 端点换成 beta（prefix completion 仅 beta 支持）
    base = settings.DEEPSEEK_BASE_URL.rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")] + "/beta"
    elif not base.endswith("/beta"):
        base = base + "/beta"
    url = f"{base}/chat/completions"

    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    # 末位追加 assistant prefix 消息
    augmented = list(messages) + [
        {"role": "assistant", "content": prefix_text, "prefix": True}
    ]
    payload: dict = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": augmented,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if stop:
        payload["stop"] = stop

    client = _get_llm_client()
    try:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
    except httpx.HTTPStatusError as e:
        logger.warning(
            f"DeepSeek prefix completion 失败 {e.response.status_code}: "
            f"{e.response.text[:200]}"
        )
        raise
    except httpx.RequestError as e:
        logger.warning(f"DeepSeek prefix completion 请求失败: {e}")
        raise
