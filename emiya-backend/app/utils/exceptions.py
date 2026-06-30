# -*- coding: utf-8 -*-
"""全局异常处理。"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    """应用自定义异常基类。"""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


class AuthException(AppException):
    """认证异常。"""

    def __init__(self, message: str = "认证失败"):
        super().__init__(message, status_code=401)


class NotFoundException(AppException):
    """资源不存在异常。"""

    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, status_code=404)


class ForbiddenException(AppException):
    """权限不足异常。"""

    def __init__(self, message: str = "无权限访问"):
        super().__init__(message, status_code=403)


def add_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器到 FastAPI 应用。

    Args:
        app: FastAPI 应用实例。
    """

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"未处理的异常: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "服务器内部错误"},
        )
