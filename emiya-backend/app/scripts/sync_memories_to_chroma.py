# -*- coding: utf-8 -*-
"""将 PostgreSQL 中所有有效记忆同步到 ChromaDB。

使用场景：
- ChromaDB 数据丢失或从未成功写入
- 初次部署后需要批量导入
- 定期巡检发现 PG 与 ChromaDB 数据量不一致

运行方式：
    cd G:\charAgent\emiya-backend
    python -m app.scripts.sync_memories_to_chroma
"""
import asyncio
import logging
import sys
from uuid import UUID

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.memory import Memory
from app.services.memory.chroma_client import add_memory, get_or_create_collection

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


async def sync_all_memories(user_id: str | None = None) -> dict:
    """将 PostgreSQL memories 表中有数据的用户全部同步到 ChromaDB。

    Args:
        user_id: 指定用户 ID（None = 全部用户）

    Returns:
        dict: {"total": 总处理数, "success": 成功数, "failed": 失败数, "users": 用户数}
    """
    stats = {"total": 0, "success": 0, "failed": 0, "users": 0}

    async with AsyncSessionLocal() as db:
        # 查询所有有效记忆
        query = select(Memory).where(Memory.is_deleted == False)
        if user_id:
            query = query.where(Memory.user_id == UUID(user_id))

        result = await db.execute(query.order_by(Memory.extracted_at.asc()))
        memories = list(result.scalars().all())

        if not memories:
            logger.info("没有需要同步的记忆")
            return stats

        # 按用户分组
        by_user: dict[str, list[Memory]] = {}
        for m in memories:
            uid = str(m.user_id)
            by_user.setdefault(uid, []).append(m)

        stats["users"] = len(by_user)
        logger.info(f"开始同步 {len(memories)} 条记忆（{len(by_user)} 个用户）...")

        for uid, mems in by_user.items():
            # 确保用户的 collection 存在
            try:
                get_or_create_collection(uid)
            except Exception as e:
                logger.error(f"用户 {uid} 创建 collection 失败: {e}")
                stats["failed"] += len(mems)
                continue

            for m in mems:
                stats["total"] += 1
                ok = await add_memory(
                    memory_id=str(m.id),
                    user_id=uid,
                    content=m.content,
                    metadata={
                        "category": m.category,
                        "importance": m.importance,
                        "conversation_id": str(m.source_conversation_id) if m.source_conversation_id else "",
                        "extracted_at": m.extracted_at.isoformat() if m.extracted_at else "",
                    },
                )
                if ok:
                    stats["success"] += 1
                else:
                    stats["failed"] += 1

                if stats["total"] % 20 == 0:
                    logger.info(f"  进度: {stats['total']}/{len(memories)} (成功 {stats['success']}, 失败 {stats['failed']})")

    logger.info(
        f"同步完成: 共 {stats['total']} 条, 成功 {stats['success']}, 失败 {stats['failed']}, "
        f"涉及 {stats['users']} 个用户"
    )
    return stats


if __name__ == "__main__":
    target_user = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(sync_all_memories(target_user))
