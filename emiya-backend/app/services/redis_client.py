# -*- coding: utf-8 -*-
"""Redis 客户端 — 单例连接 + PubSub 封装。"""
import json
import logging
from typing import AsyncGenerator

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    """获取 Redis 连接（懒初始化单例）。"""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def close_redis() -> None:
    """关闭 Redis 连接。"""
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


async def publish_token(conversation_id: str, event_type: str, data: dict) -> None:
    """向 Redis PubSub 频道发布聊天事件。"""
    try:
        r = _get_redis()
        payload = json.dumps({"event": event_type, "data": data}, ensure_ascii=False)
        await r.publish(f"conv:{conversation_id}:live", payload)
    except Exception:
        logger.exception("Redis publish 失败（降级忽略）")


# ─── 通用 KV 缓存（用于 import_parse → import_confirm 的 raw_card 暂存） ─

async def cache_set_json(key: str, value: dict, ttl_seconds: int = 600) -> bool:
    """把 dict 序列化为 JSON 存 Redis，返回是否成功。失败仅 warning。"""
    try:
        r = _get_redis()
        await r.set(key, json.dumps(value, ensure_ascii=False), ex=ttl_seconds)
        return True
    except Exception:
        logger.warning(f"Redis cache_set_json 失败 key={key}")
        return False


async def cache_get_json(key: str) -> dict | None:
    """从 Redis 拿回并反序列化，缺失或失败返回 None。"""
    try:
        r = _get_redis()
        raw = await r.get(key)
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        logger.warning(f"Redis cache_get_json 失败 key={key}")
        return None


async def cache_delete(key: str) -> None:
    """删除一个键。失败仅 warning。"""
    try:
        r = _get_redis()
        await r.delete(key)
    except Exception:
        logger.warning(f"Redis cache_delete 失败 key={key}")


async def subscribe_conversation(conversation_id: str) -> AsyncGenerator[str, None]:
    """订阅指定对话的实时流，yield SSE 格式字符串。"""
    try:
        r = _get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(f"conv:{conversation_id}:live")

        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                yield f"data: {data}\n\n"
    except Exception as e:
        logger.warning(f"Redis subscribe 异常: {e}")
        yield f"event: error\ndata: {json.dumps({'error': 'live connection lost'}, ensure_ascii=False)}\n\n"
    finally:
        try:
            await pubsub.unsubscribe(f"conv:{conversation_id}:live")
        except Exception:
            pass
