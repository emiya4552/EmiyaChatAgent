# -*- coding: utf-8 -*-
"""ADR-0008d MVU 卡 UI 能力端点纯逻辑单测（range 解析 + dangerous 门控）。"""
import pytest

from app.api.mvu_host import _require_dangerous, _resolve_range
from app.utils.exceptions import AppException


class _Conv:
    def __init__(self, caps):
        self.mvu_capabilities = caps


def test_resolve_range_forms():
    n = 5
    assert _resolve_range("-1", n) == [4]        # 最后一条
    assert _resolve_range("0", n) == [0]
    assert _resolve_range("3", n) == [3]
    assert _resolve_range("0-4", n) == [0, 1, 2, 3, 4]
    assert _resolve_range("1-3", n) == [1, 2, 3]
    assert _resolve_range("-2", n) == [3]         # 负索引
    assert _resolve_range("0-{{lastMessageId}}", n) == [0, 1, 2, 3, 4]  # 宏兜底
    assert _resolve_range("99", n) == []          # 越界
    assert _resolve_range("-1", 0) == []          # 空会话
    assert _resolve_range("3-1", n) == [1, 2, 3]  # 逆序区间归一


def test_require_dangerous_gate():
    # 未开启 → 403
    with pytest.raises(AppException) as ei:
        _require_dangerous(_Conv({}))
    assert ei.value.status_code == 403
    with pytest.raises(AppException):
        _require_dangerous(_Conv({"dangerous": False}))
    with pytest.raises(AppException):
        _require_dangerous(_Conv(None))
    # 开启 → 放行（不抛）
    _require_dangerous(_Conv({"dangerous": True}))
