# -*- coding: utf-8 -*-
"""输出契约持久化数据使用的稳定哈希。"""
from __future__ import annotations

import hashlib


def content_hash(content: str) -> str:
    """计算世界书 entry 内容的 SHA-256 标识。"""
    digest = hashlib.sha256((content or "").encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
