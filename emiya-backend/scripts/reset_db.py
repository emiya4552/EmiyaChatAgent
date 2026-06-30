"""清空数据库，仅保留 users、personas 和 alembic_version 表。

同时清理 ChromaDB 中的记忆向量数据。

运行方式：python -m scripts.reset_db
"""
import asyncio
import logging

from app.database import AsyncSessionLocal
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 需要清空的表（按外键依赖顺序）
TABLES_TO_CLEAR = [
    "emotion_records",
    "memories",
    "messages",
    "relationships",
    "conversations",
]


async def clear_postgres() -> None:
    """清空 PostgreSQL 中的业务数据表。"""
    async with AsyncSessionLocal() as db:
        for table in TABLES_TO_CLEAR:
            await db.execute(text(f"DELETE FROM {table}"))
            logger.info(f"已清空: {table}")
        await db.commit()
    logger.info("PostgreSQL 清空完成")


async def clear_chromadb() -> None:
    """清空 ChromaDB 中的所有记忆向量集合。"""
    try:
        from app.services.memory.chroma_client import _get_chroma_client

        client = _get_chroma_client()
        collections = client.list_collections()
        for col in collections:
            client.delete_collection(col.name)
            logger.info(f"已删除 ChromaDB 集合: {col.name}")
        logger.info(f"ChromaDB 清空完成（{len(collections)} 个集合）")
    except Exception as e:
        logger.warning(f"ChromaDB 清空失败（可能未运行）: {e}")


async def main() -> None:
    logger.info("开始清空数据库...")
    await clear_postgres()
    await clear_chromadb()
    logger.info("数据库重置完成。保留: users, personas, alembic_version")


if __name__ == "__main__":
    asyncio.run(main())
