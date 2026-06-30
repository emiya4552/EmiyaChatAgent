# -*- coding: utf-8 -*-
"""Token 计数工具，使用 tiktoken 库。"""
import tiktoken

# cl100k_base 编码器
_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """计算文本的 token 数量。"""
    return len(_ENCODING.encode(text))
