# -*- coding: utf-8 -*-
"""测试基建：测试数据库 + 外部依赖 mock + 工厂 fixtures。

约束：本文件的第一行必须 set DATABASE_URL 环境变量，确保 app.config.Settings
在第一次 import 时读到测试数据库 URL。

测试数据库 `emiya_test` 需要预先在 PG 里创建：
    docker exec emiya-pg psql -U emiya -d emiya -c "CREATE DATABASE emiya_test;"
"""
import os

# === 必须在任何 `from app.x` import 之前 set ===
os.environ["DATABASE_URL"] = "postgresql+asyncpg://emiya:emiya_dev_2026@localhost:5432/emiya_test"

import uuid
from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

from app.database import AsyncSessionLocal, engine
from app.models import Base


# ─── Schema 准备（session scope，只跑一次） ─────────────────────────


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_schema():
    """启动时重建测试库 schema（不依赖 alembic）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


# ─── 每个测试前 TRUNCATE ─────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def clean_db(setup_schema):
    """每个测试前清空所有业务表，RESTART IDENTITY + CASCADE。"""
    from app.utils.limiter import limiter
    limiter.reset()
    async with AsyncSessionLocal() as session:
        await session.execute(text("""
            TRUNCATE TABLE
                emotion_records, memories, relationships, messages,
                password_reset_tokens, user_sessions,
                conversations, presets, prompt_templates, regex_presets,
                personas, users
            RESTART IDENTITY CASCADE
        """))
        await session.commit()
    yield


# ─── 外部依赖 mock（每个测试都生效） ───────────────────────────


@pytest.fixture(autouse=True)
def mock_external(monkeypatch):
    """Mock Redis PubSub 和 ChromaDB，避免测试连真实外部服务。"""
    async def _noop_publish(*args, **kwargs):
        return None

    async def _empty_search(*args, **kwargs):
        return []

    async def _ok_add(*args, **kwargs):
        return True

    async def _noop_delete(*args, **kwargs):
        return None

    # Redis
    monkeypatch.setattr("app.services.redis_client.publish_token", _noop_publish)
    monkeypatch.setattr("app.services.chat_service.publish_token", _noop_publish, raising=False)

    # ChromaDB — 各模块都有本地绑定
    monkeypatch.setattr("app.services.memory.chroma_client.search_memories", _empty_search)
    monkeypatch.setattr("app.services.memory.chroma_client.add_memory", _ok_add)
    monkeypatch.setattr("app.services.memory.chroma_client.delete_memory_vector", _noop_delete)
    monkeypatch.setattr("app.services.langgraph.nodes.search_memories", _empty_search)
    monkeypatch.setattr("app.services.memory.extraction.search_memories", _empty_search)
    monkeypatch.setattr("app.services.memory.extraction.add_memory", _ok_add)
    monkeypatch.setattr("app.services.memory.extraction.delete_memory_vector", _noop_delete)


# ─── DeepSeek 默认 mock（返回简单 token / JSON） ───────────────────


def _default_json_response(messages):
    """根据 prompt 内容猜测应该返回什么 JSON。"""
    last = messages[-1].get("content", "") if messages else ""
    if "情绪" in last and "JSON" in last:
        return '{"emotion": "平静", "intensity": 5, "confidence": 0.5, "triggers": []}'
    if "提取" in last and "记忆" in last:
        return "[]"
    if "好感" in last and "affinity" in last.lower():
        return '{"affinity_delta": 0, "affinity_reason": ""}'
    if "矛盾" in last:
        return '{"contradiction": false, "reason": ""}'
    if "改写" in last or "结构化短查询" in last:
        return last[:30]  # 改写就回声前 30 字
    return ""


@pytest.fixture
def mock_deepseek_normal(monkeypatch):
    """配置 DeepSeek 正常返回 3 个 token + 默认 JSON。"""
    async def _emit_tokens(*args, **kwargs):
        for t in ["你", "好", "！"]:
            yield t

    async def _emit_json(*args, **kwargs):
        messages = kwargs.get("messages") or (args[0] if args else [])
        return _default_json_response(messages)

    # call_deepseek_stream 各 use site
    monkeypatch.setattr("app.services.llm_service.call_deepseek_stream", _emit_tokens)
    monkeypatch.setattr("app.services.chat_service.call_deepseek_stream", _emit_tokens)

    # call_deepseek_non_stream 各 use site
    monkeypatch.setattr("app.services.llm_service.call_deepseek_non_stream", _emit_json)
    monkeypatch.setattr("app.services.langgraph.nodes.call_deepseek_non_stream", _emit_json, raising=False)
    monkeypatch.setattr("app.services.emotion_service.call_deepseek_non_stream", _emit_json)
    monkeypatch.setattr("app.services.memory.extraction.call_deepseek_non_stream", _emit_json)
    monkeypatch.setattr("app.services.context_service.call_deepseek_non_stream", _emit_json)


@pytest.fixture
def mock_deepseek_interrupt_after_2(monkeypatch):
    """流式返回 2 个 token 后抛 RuntimeError（模拟连接中断）。"""
    async def _emit_then_raise(*args, **kwargs):
        yield "你"
        yield "好"
        raise RuntimeError("simulated stream interrupt")

    async def _emit_json(*args, **kwargs):
        messages = kwargs.get("messages") or (args[0] if args else [])
        return _default_json_response(messages)

    monkeypatch.setattr("app.services.llm_service.call_deepseek_stream", _emit_then_raise)
    monkeypatch.setattr("app.services.chat_service.call_deepseek_stream", _emit_then_raise)
    monkeypatch.setattr("app.services.llm_service.call_deepseek_non_stream", _emit_json)
    monkeypatch.setattr("app.services.langgraph.nodes.call_deepseek_non_stream", _emit_json, raising=False)
    monkeypatch.setattr("app.services.emotion_service.call_deepseek_non_stream", _emit_json)
    monkeypatch.setattr("app.services.memory.extraction.call_deepseek_non_stream", _emit_json)
    monkeypatch.setattr("app.services.context_service.call_deepseek_non_stream", _emit_json)


# ─── 工厂 fixtures ─────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_user():
    from app.models.user import User
    from app.utils.security import hash_password
    async with AsyncSessionLocal() as session:
        user = User(
            id=uuid.uuid4(),
            email=f"test-{uuid.uuid4().hex[:8]}@test.com",
            nickname="测试用户",
            password_hash=hash_password("old-password"),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def test_persona():
    from app.models.persona import Persona
    async with AsyncSessionLocal() as session:
        persona = Persona(
            id=uuid.uuid4(),
            name="测试角色",
            personality="温柔，善解人意",
            first_message=None,  # 不要 first_message 避免污染 messages 表
            is_template=False,
        )
        session.add(persona)
        await session.commit()
        await session.refresh(persona)
        return persona


@pytest_asyncio.fixture
async def test_conversation(test_user, test_persona):
    from app.models.conversation import Conversation
    async with AsyncSessionLocal() as session:
        conv = Conversation(
            id=uuid.uuid4(),
            user_id=test_user.id,
            persona_id=test_persona.id,
            chat_config={},
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        return conv


# ─── HTTP client fixtures ─────────────────────────────────────


@pytest_asyncio.fixture
async def auth_headers(test_user):
    from app.utils.security import create_access_token
    from app.models.user_session import UserSession

    async with AsyncSessionLocal() as session:
        user_session = UserSession(
            id=uuid.uuid4(),
            user_id=test_user.id,
            user_agent="pytest",
            device_label="pytest",
            ip_address="127.0.0.1",
            last_seen_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        session.add(user_session)
        await session.commit()
    token = create_access_token(str(test_user.id), str(user_session.id), expires_delta=timedelta(days=1))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client():
    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
