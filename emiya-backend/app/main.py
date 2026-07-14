# -*- coding: utf-8 -*-
"""FastAPI 应用入口，配置 CORS、日志、路由注册。"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.utils.exceptions import add_exception_handlers
from app.utils.limiter import limiter

# 日志配置
# root → WARNING：挡住所有第三方库的 INFO/DEBUG 噪音（httpx, urllib3, chromadb 等）
# app  → INFO：项目业务日志可见
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# 项目 logger：所有 app.* 模块设 INFO，业务流可见
logging.getLogger("app").setLevel(logging.INFO)
logging.getLogger("scripts").setLevel(logging.INFO)

# 压制已知的第三方噪音源
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# 业务日志按类别分流到 LOG_DIR 下不同文件（prompt.log / output_contract.log /
# app.log 兜底）；只读现有 logger 名 + 消息前缀，不改业务代码，控制台仍全量。
# 分类标准与前缀表见 app/logging_setup.py。
if settings.LOG_SPLIT_ENABLED:
    from app.logging_setup import setup_split_logging

    setup_split_logging(
        log_dir=settings.LOG_DIR,
        focus=settings.LOG_FOCUS,
        reset=settings.LOG_RESET_ON_START,
    )

logger = logging.getLogger(__name__)

app = FastAPI(
    title="EMIYA",
    version="1.0.0",
    description="AI Chat",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS 中间件配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册全局异常处理器
add_exception_handlers(app)

# 静态文件：头像
import os
from fastapi.staticfiles import StaticFiles
_avatar_dir = os.path.join(os.path.dirname(__file__), "..", "uploads", "avatars")
os.makedirs(_avatar_dir, exist_ok=True)
app.mount("/static/avatars", StaticFiles(directory=_avatar_dir), name="avatars")

# 注册路由
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.emotions import router as emotions_router
from app.api.personas import router as personas_router
from app.api.presets import router as presets_router
from app.api.regex_presets import router as regex_presets_router
from app.api.templates import router as templates_router
from app.api.memories import router as memories_router
from app.api.mvu_host import router as mvu_host_router
from app.api.relationships import router as relationships_router
from app.api.users import router as users_router
from app.api.worldbooks import router as worldbooks_router

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(emotions_router)
app.include_router(personas_router)
app.include_router(presets_router)
app.include_router(regex_presets_router)
app.include_router(templates_router)
app.include_router(memories_router)
app.include_router(mvu_host_router)
app.include_router(relationships_router)
app.include_router(users_router)
app.include_router(worldbooks_router)

@app.on_event("startup")
async def startup_cleanup():
    """预热 BGE 模型。"""
    # 预热 BGE Embedding 模型（避免首条消息冷启动 3~15 秒延迟）
    try:
        import asyncio as _asyncio
        from app.services.memory.chroma_client import _get_embedding_function
        await _asyncio.to_thread(_get_embedding_function)
    except Exception as e:
        logger.warning(f"BGE 模型预热失败（将使用 ChromaDB 内置 ONNX 兜底）: {e}")


@app.on_event("shutdown")
async def shutdown_cleanup():
    """关闭时释放 httpx 连接池。"""
    try:
        from app.services.llm_service import close_llm_client
        await close_llm_client()
    except Exception as e:
        logger.warning(f"httpx 客户端关闭失败: {e}")

    try:
        from app.services.redis_client import close_redis
        await close_redis()
    except Exception as e:
        logger.warning(f"Redis 客户端关闭失败: {e}")


@app.get("/health")
async def health_check():
    """健康检查端点。"""
    return {"status": "ok"}
