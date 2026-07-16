# -*- coding: utf-8 -*-
"""ChromaDB 操作封装 — 中文向量存储与语义检索。"""
import logging
import math
import os
import threading
from datetime import datetime, timezone
from typing import Optional

# 跳过 HuggingFace 联网验证，直接使用本地缓存模型
# （国内网络环境下 huggingface.co 不可达，模型已通过镜像预先缓存）
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.services.config_registry import MemoryTuning

logger = logging.getLogger(__name__)

_client: Optional[chromadb.HttpClient] = None
_lock = threading.Lock()
_embedding_fn = None


def _get_embedding_function():
    """获取中文 Embedding 函数。

    优先使用 BGE 本地模型（需 sentence-transformers + tokenizers >= 0.22），
    加载失败时返回 None，由 ChromaDB 服务端内置 ONNX embedding 兜底。
    服务端默认模型为 all-MiniLM-L6-v2（英文优化，中文语义检索有损但功能可用）。
    """
    global _embedding_fn
    if _embedding_fn is not None:
        return _embedding_fn

    try:
        from chromadb.utils import embedding_functions
        _embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.EMBEDDING_MODEL_NAME,
            device="cpu",
        )
        logger.info(f"中文 Embedding 模型已加载: {settings.EMBEDDING_MODEL_NAME}")
        return _embedding_fn
    except Exception as e:
        logger.info(
            f"本地 BGE 模型不可用（{e}），使用 ChromaDB 服务端默认 embedding。"
            f"如需更好的中文检索效果，请确保 sentence-transformers 及其依赖版本兼容。"
        )
        _embedding_fn = None
        return None


def _get_chroma_client() -> chromadb.HttpClient:
    """获取 ChromaDB HTTP 客户端（线程安全单例）。"""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = chromadb.HttpClient(
                    host=settings.CHROMA_HOST,
                    port=settings.CHROMA_PORT,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                logger.info(f"ChromaDB 客户端已连接: {settings.CHROMA_HOST}:{settings.CHROMA_PORT}")
    return _client


def get_or_create_collection(user_id: str):
    """获取或创建用户的记忆集合。"""
    client = _get_chroma_client()
    collection_name = f"user_{user_id}_memories"
    ef = _get_embedding_function()

    try:
        if ef is not None:
            return client.get_or_create_collection(
                name=collection_name,
                embedding_function=ef,
                metadata={"user_id": user_id},
            )
        else:
            return client.get_or_create_collection(
                name=collection_name,
                metadata={"user_id": user_id},
            )
    except Exception as e:
        logger.error(f"创建/获取 ChromaDB Collection 失败: {e}")
        raise


def _l2_to_similarity(distance: float) -> float:
    """将 L2 距离转换为 0-1 相似度。

    BGE 模型输出归一化向量，L2 ∈ [0, 2] → similarity = 1 - distance/2。
    未归一化场景下 L2 可能超过 2，使用 exp(-distance/k) 做平滑衰减，k=1.5。
    """
    if distance <= 2.0:
        return max(0.0, 1.0 - distance / 2.0)
    else:
        return max(0.0, math.exp(-distance / 1.5))


def _get_recency_weight(extracted_at: str | None, half_life_days: float | None = None) -> float:
    """计算记忆的时新权重。

    使用指数衰减: recency = 2^(-days_since / half_life_days)
    half_life_days: 账户级覆盖（ADR-4）；None 时回退全局 settings.RECENCY_HALF_LIFE_DAYS。
    """
    if not extracted_at:
        return 0.5
    if half_life_days is None:
        half_life_days = settings.RECENCY_HALF_LIFE_DAYS
    try:
        extracted_dt = datetime.fromisoformat(extracted_at)
        now = datetime.now(timezone.utc)
        if extracted_dt.tzinfo is None:
            from datetime import timezone as tz
            extracted_dt = extracted_dt.replace(tzinfo=tz.utc)
        days = (now - extracted_dt).total_seconds() / 86400.0
        return math.pow(2, -days / half_life_days)
    except Exception:
        return 0.5


def _char_bigrams(text: str) -> set[str]:
    """提取文本的字符 bigram 集合，用于中文文本相似度计算。

    单字集合对中文区分度不足（"我很生气" 与 "我非常愤怒" 仅共享 "我"），
    bigram 能捕捉短语级重叠（"喜欢编程" vs "喜欢编程特别是" → 共享 "喜欢"+"欢编"+"编程"）。
    """
    return {text[i:i+2] for i in range(len(text) - 1)} if len(text) >= 2 else set(text)


def _jaccard_similarity(a: str, b: str) -> float:
    """计算两段文本的 bigram Jaccard 相似度，范围 [0, 1]。

    Jaccard = |bigrams(a) ∩ bigrams(b)| / |bigrams(a) ∪ bigrams(b)|
    分母用并集而非单侧最大值，确保对称性且不会超过 1.0。
    """
    bg_a = _char_bigrams(a)
    bg_b = _char_bigrams(b)
    if not bg_a or not bg_b:
        return 0.0
    intersection = len(bg_a & bg_b)
    union = len(bg_a | bg_b)
    return intersection / union


def _mmr_rerank(
    results: list[dict],
    query: str,
    lambda_param: float | None = None,
) -> list[dict]:
    """MMR (Maximal Marginal Relevance) 重排序。

    平衡相关性和多样性，避免 Top-K 中出现高度重复的记忆。
    lambda=1 纯相似度排序，lambda=0 纯多样性。

    相似度用 bigram Jaccard 而非 embedding，原因：
    - MMR 的目标是去冗余（"我喜欢猫" vs "我喜欢猫咪"），不是语义判同
    - 语义不同的同义表达（"我很生气" vs "我非常愤怒"）不应被惩罚
    - 单字 Jaccard 对中文区分度太低，bigram 是工程上轻量且有效的折中
    """
    if lambda_param is None:
        lambda_param = settings.MMR_LAMBDA
    if len(results) <= 1 or lambda_param >= 1.0:
        return results

    selected = [results[0]]
    remaining = results[1:]

    while remaining:
        best_score = -float("inf")
        best_idx = 0
        for i, item in enumerate(remaining):
            max_sim_to_selected = 0.0
            for s in selected:
                sim = _jaccard_similarity(item["content"], s["content"])
                if sim > max_sim_to_selected:
                    max_sim_to_selected = sim
            mmr = lambda_param * item["relevance"] - (1 - lambda_param) * max_sim_to_selected
            if mmr > best_score:
                best_score = mmr
                best_idx = i
        selected.append(remaining.pop(best_idx))

    return selected


async def add_memory(memory_id: str, user_id: str, content: str, metadata: dict) -> bool:
    """将记忆向量化并存入 ChromaDB。

    Returns:
        bool: 写入成功返回 True，失败返回 False（调用方据此决定是否重试或降级）。
    """
    try:
        collection = get_or_create_collection(user_id)
        metadata.setdefault("extracted_at", datetime.now(timezone.utc).isoformat())
        collection.add(ids=[memory_id], documents=[content], metadatas=[metadata])
        logger.debug(f"ChromaDB 写入记忆: {memory_id}")
        return True
    except Exception as e:
        logger.error(f"ChromaDB 写入失败 (memory_id={memory_id}): {e}")
        return False


async def search_memories(
    user_id: str,
    query: str,
    top_k: int | None = None,
    threshold: float | None = None,
    scope_filter: str | None = None,
    tuning: MemoryTuning | None = None,
) -> list[dict]:
    """语义搜索用户记忆，融合相似度 + 时新权重 + MMR 重排序。

    Args:
        scope_filter: 按 scope 过滤 ('conversation:{id}' / None=不筛选)
        tuning: 账户级检索调参（ADR-4）；None 时全部回退全局 settings。

    Returns:
        [{"memory_id", "content", "category", "relevance", "recency_weight", "combined_score"}, ...]
    """
    # 账户级调参（ADR-4）：显式 top_k/threshold 优先 > tuning > 全局默认。
    if top_k is None:
        top_k = tuning.top_k if tuning else settings.MEMORY_TOP_K
    if threshold is None:
        threshold = tuning.threshold if tuning else settings.MEMORY_SIMILARITY_THRESHOLD
    recency_weight = tuning.recency_weight if tuning else settings.RECENCY_WEIGHT
    recency_half_life = tuning.recency_half_life_days if tuning else settings.RECENCY_HALF_LIFE_DAYS
    mmr_lambda = tuning.mmr_lambda if tuning else settings.MMR_LAMBDA

    try:
        collection = get_or_create_collection(user_id)
        # 检索 3×top_k 做重排序缓冲
        query_kwargs: dict = {
            "query_texts": [query],
            "n_results": min(top_k * 3, 30),
        }
        if scope_filter:
            query_kwargs["where"] = {"scope": scope_filter}
        results = collection.query(**query_kwargs)

        memories = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                distance = results.get("distances", [[]])[0][i] if results.get("distances") else 1.0
                similarity = _l2_to_similarity(distance)
                metadata = results.get("metadatas", [[]])[0][i] or {}

                recency = _get_recency_weight(
                    metadata.get("extracted_at"), half_life_days=recency_half_life
                )
                combined = (1 - recency_weight) * similarity + recency_weight * recency

                if combined >= threshold:
                    memories.append({
                        "memory_id": doc_id,
                        "content": results["documents"][0][i],
                        "category": metadata.get("category", ""),
                        "scope": metadata.get("scope", "global"),
                        "memory_type": metadata.get("memory_type", "fact"),
                        "relevance": round(similarity, 4),
                        "recency_weight": round(recency, 4),
                        "combined_score": round(combined, 4),
                        "extracted_at": metadata.get("extracted_at", ""),
                        "conversation_id": metadata.get("conversation_id", ""),
                    })

        # MMR 重排序去重（lambda 账户可覆盖，ADR-4）
        memories = _mmr_rerank(memories, query, lambda_param=mmr_lambda)
        memories = memories[:top_k]

        logger.debug(f"ChromaDB 检索: '{query[:40]}...' → {len(memories)} 条 (MMR reranked)")
        return memories
    except Exception as e:
        logger.error(f"ChromaDB 检索失败: {e}")
        return []


async def delete_memory_vector(memory_id: str, user_id: str) -> None:
    """从 ChromaDB 中删除一条记忆的向量。"""
    try:
        collection = get_or_create_collection(user_id)
        collection.delete(ids=[memory_id])
        logger.debug(f"ChromaDB 删除记忆向量: {memory_id}")
    except Exception as e:
        logger.error(f"ChromaDB 删除失败: {e}")


async def update_memory_vector(
    memory_id: str, user_id: str, content: str, metadata: dict
) -> None:
    """更新记忆向量（delete + add）。"""
    await delete_memory_vector(memory_id, user_id)
    await add_memory(memory_id, user_id, content, metadata)
