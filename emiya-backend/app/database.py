# -*- coding: utf-8 -*-
"""数据库连接模块，提供 SQLAlchemy 异步引擎和会话管理。"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# 创建异步引擎，连接池大小 10，最大溢出 20
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

# 异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库会话。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
