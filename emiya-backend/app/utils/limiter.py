# -*- coding: utf-8 -*-
"""共享的 IP 限流器（slowapi）。

在独立模块以避免 main.py / api/auth.py 循环 import。
main.py 在创建 FastAPI 实例时把 limiter 挂到 app.state，并注册异常处理器。
"""
from slowapi import Limiter
from slowapi.util import get_remote_address


limiter = Limiter(key_func=get_remote_address)
