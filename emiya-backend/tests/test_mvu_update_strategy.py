# -*- coding: utf-8 -*-
"""ADR-0022：MVU 更新策略（inline 默认 / double_ai 可选 / tool 已移除）单元测试。

验证 `divert_update_entries` 这个 knob 随策略切换——inline→False（更新走正文内联
<UpdateVariable>，不跑 run_update_pass）；double_ai→True（回复后独立 pass）。
"""
from app.config import settings
from app.services.mvu_runtime.policy import (
    MvuRuntimePolicy,
    build_mvu_policy,
    build_mvu_policy_for_user_persona,
)


def test_inline_default_divert_false():
    p = build_mvu_policy(persona_uses_mvu=True, compat_enabled=True, update_strategy="inline")
    assert p.active is True
    assert p.update_strategy == "inline"
    assert p.divert_update_entries is False  # inline 不分流：更新留在正文


def test_double_ai_divert_true():
    p = build_mvu_policy(persona_uses_mvu=True, compat_enabled=True, update_strategy="double_ai")
    assert p.divert_update_entries is True


def test_unknown_strategy_normalizes_to_inline():
    p = build_mvu_policy(persona_uses_mvu=True, compat_enabled=True, update_strategy="weird")
    assert p.update_strategy == "inline"
    assert p.divert_update_entries is False


def test_non_mvu_never_diverts_even_double_ai():
    # 非 MVU 卡（active=False）：无论策略，divert 恒 False（不注入任何 MVU 更新指令）。
    p = build_mvu_policy(persona_uses_mvu=False, compat_enabled=True, update_strategy="double_ai")
    assert p.active is False
    assert p.divert_update_entries is False


def test_compat_disabled_never_diverts():
    p = build_mvu_policy(persona_uses_mvu=True, compat_enabled=False, update_strategy="double_ai")
    assert p.active is False
    assert p.divert_update_entries is False


def test_default_field_is_inline():
    # 直接构造不传策略 → 默认 inline。
    p = MvuRuntimePolicy(raw_uses_mvu=True, compat_enabled=True)
    assert p.update_strategy == "inline"
    assert p.divert_update_entries is False


def test_for_user_persona_reads_settings_default(monkeypatch):
    monkeypatch.setattr(settings, "MVU_UPDATE_STRATEGY", "double_ai")
    user = type("U", (), {"mvu_compat_enabled": True})()
    persona = type("P", (), {"uses_mvu": True})()
    p = build_mvu_policy_for_user_persona(user=user, persona=persona)
    assert p.update_strategy == "double_ai"
    assert p.divert_update_entries is True


def test_for_user_persona_explicit_override_wins(monkeypatch):
    monkeypatch.setattr(settings, "MVU_UPDATE_STRATEGY", "double_ai")
    user = type("U", (), {"mvu_compat_enabled": True})()
    persona = type("P", (), {"uses_mvu": True})()
    # 显式传 inline 覆盖全局 double_ai
    p = build_mvu_policy_for_user_persona(user=user, persona=persona, update_strategy="inline")
    assert p.update_strategy == "inline"
    assert p.divert_update_entries is False
