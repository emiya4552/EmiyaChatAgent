# -*- coding: utf-8 -*-
"""ADR-0008c 阶段1：MVU 浏览器运行时 down-channel 的单元测试。

覆盖 `_build_mvu_browser_sync`：开关/uses_mvu 门控、载荷结构、base_stat 深拷贝隔离。
"""
from app.config import settings
from app.services.chat_service import _build_mvu_browser_sync
from app.services.langgraph.nodes import _should_retire_backend_apply


def _state(**over):
    st = {
        "persona_uses_mvu": True,
        "mvu_scope": {"local": {"stat_data": {"伶伶": {"当前好感度": 15}}}},
        "assistant_reply": "旁白……<UpdateVariable>[{\"op\":\"delta\",\"path\":\"/伶伶/当前好感度\",\"value\":2}]</UpdateVariable>",
        "mvu_tool_calls": [],
    }
    st.update(over)
    return st


def test_off_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "MVU_BROWSER_RUNTIME", False)
    assert _build_mvu_browser_sync(_state()) is None


def test_on_but_not_uses_mvu_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "MVU_BROWSER_RUNTIME", True)
    assert _build_mvu_browser_sync(_state(persona_uses_mvu=False)) is None


def test_on_and_uses_mvu_carries_layer1_material(monkeypatch):
    monkeypatch.setattr(settings, "MVU_BROWSER_RUNTIME", True)
    sync = _build_mvu_browser_sync(_state())
    assert sync is not None
    assert sync["base_stat"] == {"伶伶": {"当前好感度": 15}}
    assert "<UpdateVariable>" in sync["raw_reply"]
    assert sync["tool_calls"] == []


def test_base_stat_is_deep_copied(monkeypatch):
    """apply 会原地改 stat_data；base_stat 必须是快照，不能被后续改动污染。"""
    monkeypatch.setattr(settings, "MVU_BROWSER_RUNTIME", True)
    state = _state()
    sync = _build_mvu_browser_sync(state)
    # 模拟 node_post_process 原地应用后把好感度改到 17
    state["mvu_scope"]["local"]["stat_data"]["伶伶"]["当前好感度"] = 17
    assert sync["base_stat"]["伶伶"]["当前好感度"] == 15  # 快照仍是 S(N-1)


def test_missing_mvu_scope_is_safe(monkeypatch):
    monkeypatch.setattr(settings, "MVU_BROWSER_RUNTIME", True)
    sync = _build_mvu_browser_sync(_state(mvu_scope=None, mvu_tool_calls=None))
    assert sync["base_stat"] == {}
    assert sync["tool_calls"] == []


# ── ADR-0008c 阶段3：退役后端 apply 门控 ──

def test_retire_gate_off_by_default(monkeypatch):
    monkeypatch.setattr(settings, "MVU_BROWSER_RUNTIME", True)
    monkeypatch.setattr(settings, "MVU_RETIRE_BACKEND_APPLY", False)
    assert _should_retire_backend_apply(_state()) is False


def test_retire_gate_needs_all_three(monkeypatch):
    monkeypatch.setattr(settings, "MVU_RETIRE_BACKEND_APPLY", True)
    monkeypatch.setattr(settings, "MVU_BROWSER_RUNTIME", True)
    assert _should_retire_backend_apply(_state(persona_uses_mvu=True)) is True
    # 缺任一 → 不退役
    assert _should_retire_backend_apply(_state(persona_uses_mvu=False)) is False
    monkeypatch.setattr(settings, "MVU_BROWSER_RUNTIME", False)
    assert _should_retire_backend_apply(_state(persona_uses_mvu=True)) is False
