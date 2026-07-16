# -*- coding: utf-8 -*-
"""长期记忆提取 — LLM 事实提取 + 去重 + 矛盾检测 + Query 改写。"""
import json
import logging
import re
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.memory import Memory
from app.schemas.memory import MemoryExtractionResult
from app.services.config_registry import (
    contradiction_detection_enabled,
    resolve_memory_tuning,
)
from app.services.llm_service import call_deepseek_non_stream
from app.services.memory.chroma_client import add_memory, search_memories, delete_memory_vector

logger = logging.getLogger(__name__)

# ===== Query 改写 =====

QUERY_REWRITE_PROMPT = """将以下口语化的对话消息改写为用于记忆检索的结构化短查询。
提取关键实体、话题和意图，用中文关键词表达。

用户消息：{user_message}

仅返回改写后的查询文本，不要有其他内容。"""


async def rewrite_query_for_retrieval(
    user_message: str, *, enabled: bool | None = None
) -> str:
    """将口语化用户消息改写为更适合向量检索的结构化查询。

    "嗯" → "日常闲聊 情绪表达"
    "我想喝奶茶" → "奶茶 饮品偏好"
    "今天不开心" → "负面情绪 今日经历"

    enabled: 账户级覆盖（ADR-4）；None 时回退全局 settings.ENABLE_QUERY_REWRITING。
    """
    if enabled is None:
        enabled = settings.ENABLE_QUERY_REWRITING
    if not enabled:
        return user_message

    try:
        response = await call_deepseek_non_stream(
            messages=[{"role": "user", "content": QUERY_REWRITE_PROMPT.format(user_message=user_message)}],
            temperature=0.0,
            max_tokens=50,
        )
        rewritten = response.strip()
        if rewritten and len(rewritten) > 1:
            logger.debug(f"Query 改写: '{user_message[:30]}' → '{rewritten[:50]}'")
            return rewritten
    except Exception as e:
        logger.warning(f"Query 改写失败，使用原始消息: {e}")
    return user_message


# ===== 记忆提取 =====

MEMORY_EXTRACTION_PROMPT = """你是一个信息提取助手。请仔细阅读以下对话，提取用户透露的所有个人相关信息。

{existing_memories}

对话内容：
{recent_dialogues}

提取规则：
- 提取每一条可能对理解用户有帮助的信息
- 包括但不限于：用户的身份背景、喜好厌恶、重要经历、生活习惯、情绪模式、人际关系、目标愿望
- 可以适当推断（如用户说"加班到凌晨"→ 可以推断"用户工作压力大"）

不要提取：
- 用户仅仅没有拒绝助理的某个建议（除非用户明确表达了兴趣）
- 助理的比喻或观点，不要当做用户自身的态度
- 朋友对用户的评价，除非用户明确表示认同

类别：basic_info（基本信息）、preference（喜好偏好）、experience（经历事件）、habit（生活习惯）、emotion_pattern（情绪模式）、relationship（人际关系）、goal（目标愿望）

返回格式（仅 JSON）：
[
  {{
    "content": "用户25岁，在北京做程序员",
    "category": "basic_info",
    "importance": 0.8,
    "is_temporal": false,
    "memory_type": "fact",
    "extends_memory": null
  }},
  {{
    "content": "用户喜欢喝芋泥波波奶茶",
    "category": "preference",
    "importance": 0.7,
    "is_temporal": false,
    "memory_type": "fact",
    "extends_memory": null
  }},
  {{
    "content": "用户今天加班到很晚",
    "category": "experience",
    "importance": 0.4,
    "is_temporal": true,
    "memory_type": "event",
    "extends_memory": null
  }}
]

字段说明：
- content: 一句话描述（包含具体细节，不要笼统）
- category: 类别标签
- importance: 0-1。持久信息 0.6-0.9，临时事件 0.4-0.6
- is_temporal: true=会很快过时的事件（"今天加班"、"下周出差"），false=持久信息
- memory_type: fact=持久事实（可长期引用）、event=一次性事件（已过去的时间点）、state=用户的状态或情绪模式（可能随时间改变）。is_temporal=true 时通常应为 event
- extends_memory: 补充已有记忆时写关键词，否则 null

只返回 JSON，不要其他任何文字。"""


def _safe_parse_memory_json(text: str) -> list[dict]:
    """容错解析记忆提取的 JSON 返回。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return []


async def extract_memories_from_dialogues(
    dialogues: list[dict],
    existing_memories: list[str] | None = None,
) -> list[MemoryExtractionResult]:
    """调用 LLM 从对话中提取长期记忆事实。

    Args:
        dialogues: [{"role": "user", "content": "..."}, ...] 格式的对话列表。
        existing_memories: 当前对话已有的记忆内容列表，注入 prompt 引导 LLM 避免重复。

    Returns:
        提取到的记忆列表（已过滤 importance < 0.3 的结果）。
    """
    if existing_memories:
        mem_list = "\n".join(f"- {m}" for m in existing_memories[:10])
        existing_section = f"你现在已经知道关于用户的信息：\n{mem_list}\n\n请从以下新对话中提取你之前不知道的信息。包括对已有记忆的补充细节和全新事实。"
    else:
        existing_section = ""

    prompt = MEMORY_EXTRACTION_PROMPT.format(
        existing_memories=existing_section,
        recent_dialogues="\n".join(
            f"{d['role']}: {d['content']}" for d in dialogues
        ),
    )

    try:
        response = await call_deepseek_non_stream(
            messages=[{"role": "user", "content": prompt}],
            temperature=settings.MEMORY_EXTRACTION_TEMPERATURE,
            max_tokens=settings.MEMORY_EXTRACTION_MAX_TOKENS,
        )
        logger.debug(f"记忆提取原始响应: {response[:300]}")

        data = _safe_parse_memory_json(response)
        results = []
        for item in data:
            if not isinstance(item, dict):
                continue
            importance = item.get("importance", 0)
            if not isinstance(importance, (int, float)) or importance < 0.4:
                continue
            content = item.get("content", "")
            category = item.get("category", "basic_info")
            if not content:
                continue

            # is_temporal 标记为 True 时自动降低 importance（最多 0.5）
            if item.get("is_temporal", False):
                importance = min(float(importance), 0.5)

            memory_type = item.get("memory_type", "")
            if not memory_type:
                if item.get("is_temporal"):
                    memory_type = "event"
                elif category in ("emotion_pattern",):
                    memory_type = "state"
                else:
                    memory_type = "fact"

            results.append(MemoryExtractionResult(
                content=content,
                category=category,
                importance=min(float(importance), 1.0),
                memory_type=memory_type,
            ))
        return results
    except Exception as e:
        logger.error(f"记忆提取失败: {e}")
        return []


# ===== 矛盾检测 =====

CONTRADICTION_CHECK_PROMPT = """判断以下两条陈述是否存在逻辑矛盾。

陈述 A：{existing}
陈述 B：{new}

返回格式（仅 JSON）：
{{"contradiction": true, "reason": "A说养猫，B说养狗，互为矛盾"}}
或
{{"contradiction": false, "reason": ""}}

注意：
- 只有明确的逻辑矛盾（互斥事实）才算 contradiction
- 时间变化（"以前不喜欢，现在喜欢"）不算矛盾
- 程度变化（"以前喜欢，现在超爱"）不算矛盾
- 只返回 JSON"""


async def _detect_contradiction(
    existing_content: str, new_content: str, *, enabled: bool | None = None
) -> tuple[bool, str]:
    """检测两条记忆是否存在逻辑矛盾。

    enabled: 账户级覆盖（ADR-4）；None 时回退全局 settings.ENABLE_CONTRADICTION_DETECTION。

    Returns:
        (is_contradiction, reason)
    """
    if enabled is None:
        enabled = settings.ENABLE_CONTRADICTION_DETECTION
    if not enabled:
        return False, ""

    try:
        prompt = CONTRADICTION_CHECK_PROMPT.format(
            existing=existing_content, new=new_content
        )
        response = await call_deepseek_non_stream(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=100,
        )
        data = json.loads(response)
        return data.get("contradiction", False), data.get("reason", "")
    except Exception as e:
        logger.warning(f"矛盾检测失败: {e}")
        return False, ""


# ===== 去重 + 矛盾检测 + 保存 =====

async def deduplicate_and_save(
    user_id: str,
    extracted_memories: list[MemoryExtractionResult],
    db: AsyncSession,
    conversation_id: UUID | None = None,
    account_config: dict | None = None,
) -> int:
    """去重、矛盾检测后保存新记忆到 PostgreSQL + ChromaDB。

    scope 固定为 conversation:{conversation_id}。
    account_config: 账户级覆盖（ADR-4）——去重阈值与矛盾检测开关；None 时回退全局。

    Returns:
        实际新增的记忆数量。
    """
    if not extracted_memories:
        return 0

    # 账户级记忆调参（ADR-4）：dedup 阈值 + 矛盾检测开关（缺省回退全局）。
    tuning = resolve_memory_tuning(account_config)
    contradiction_enabled = contradiction_detection_enabled(account_config)
    dedup_threshold = tuning.dedup_threshold

    count_result = await db.execute(
        select(func.count()).where(
            Memory.user_id == UUID(user_id),
            Memory.is_deleted == False,
        )
    )
    current_count = count_result.scalar()
    max_allowed = settings.MEMORY_MAX_PER_USER

    saved_count = 0
    for mem in extracted_memories:
        if current_count + saved_count >= max_allowed:
            logger.info(f"用户 {user_id} 记忆数已达上限 {max_allowed}")
            break

        # 1. 相似度去重（收窄到当前对话）；dedup_threshold 已按账户 tuning 解析（见上）。
        dedup_scope = f"conversation:{conversation_id}" if conversation_id else None
        existing = await search_memories(
            user_id=user_id, query=mem.content, top_k=1,
            threshold=dedup_threshold, scope_filter=dedup_scope,
        )
        if existing:
            top = existing[0]
            if top["combined_score"] >= dedup_threshold:
                # 2. 检查是否矛盾
                has_contradiction, reason = await _detect_contradiction(
                    top["content"], mem.content, enabled=contradiction_enabled
                )
                if has_contradiction:
                    # 矛盾：标记旧记忆为已删除，继续保存新记忆
                    memory_id = UUID(top["memory_id"])
                    old_result = await db.execute(
                        select(Memory).where(Memory.id == memory_id)
                    )
                    old_mem = old_result.scalar_one_or_none()
                    if old_mem:
                        old_mem.is_deleted = True
                        db.add(old_mem)
                    await delete_memory_vector(top["memory_id"], user_id)
                    logger.info(f"矛盾检测: 旧记忆已标记删除 ({reason})")
                    # 继续保存新记忆
                elif top["combined_score"] >= 0.95:
                    # 高度相似且不矛盾 → 几乎相同的记忆，跳过
                    logger.debug(f"跳过近乎重复的记忆: {mem.content[:40]}...")
                    continue
                # else: 相似但不矛盾（0.75~0.95）→ 互补信息，不跳过，正常保存

        # 3. scope 固定为 conversation:{id}
        scope_value = f"conversation:{conversation_id}" if conversation_id else "conversation:unknown"

        # 4. 写入 PostgreSQL
        memory_record = Memory(
            user_id=UUID(user_id),
            content=mem.content,
            category=mem.category,
            importance=mem.importance,
            scope=scope_value,
            memory_type=mem.memory_type,
            source_conversation_id=conversation_id,
        )
        db.add(memory_record)
        await db.flush()

        # 5. 写入 ChromaDB（含完整 metadata）
        chroma_ok = await add_memory(
            memory_id=str(memory_record.id),
            user_id=user_id,
            content=mem.content,
            metadata={
                "category": mem.category,
                "importance": mem.importance,
                "scope": scope_value,
                "memory_type": mem.memory_type,
                "conversation_id": str(conversation_id) if conversation_id else "",
                "extracted_at": memory_record.extracted_at.isoformat(),
            },
        )
        if not chroma_ok:
            logger.warning(
                f"ChromaDB 写入失败但 PostgreSQL 已保存 (memory_id={memory_record.id})，"
                f"记忆将在下次同步时修复"
            )
        saved_count += 1

    if saved_count > 0:
        await db.commit()
        logger.info(f"记忆提取完成: 新增 {saved_count} 条记忆（用户 {user_id}）")

    return saved_count
