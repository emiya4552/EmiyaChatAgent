# -*- coding: utf-8 -*-
"""config_registry 单一事实源 + 三层继承回归测试。

覆盖：
- 系统默认与旧硬编码逐值一致（回归锁，防 registry 改动误伤 effective 回显）。
- chat_config 白名单键集 / 过滤未知键。
- 可继承项不伪造系统默认。
- resolve_require_confirmed 三层继承（含此前缺账户层的 bug 回归）。
- 前后端契约快照：EXPECTED_SCHEMA 同时是 emiya-frontend/src/config/configSchema.ts
  必须镜像的重叠元数据；改这里务必同步改那里。
"""
from app.config import settings
from app.services import config_registry as reg
from app.services.output_contracts import policy
from app.services.output_contracts.types import VisibleOutputContract, SectionContract


# ── 前后端对照快照：{key: (group, advanced, inheritable, has_system_default)} ──
# 这是 chat_config 对话覆盖层的重叠契约，前端 configSchema.ts 必须逐项镜像。
EXPECTED_SCHEMA = {
    "temperature": ("sampling", False, False, True),
    "top_p": ("sampling", True, False, False),
    "top_k": ("sampling", True, False, False),
    "top_a": ("sampling", True, False, False),
    "min_p": ("sampling", True, False, False),
    "frequency_penalty": ("sampling", True, False, False),
    "presence_penalty": ("sampling", True, False, False),
    "repetition_penalty": ("sampling", True, False, False),
    "openai_max_context": ("token_budget", False, False, True),
    "openai_max_tokens": ("token_budget", True, False, False),
    "token_budget_safety_margin": ("token_budget", True, False, True),
    "history_budget_cap": ("token_budget", True, False, True),
    "worldbook_budget_pct": ("worldbook", True, False, True),
    "worldbook_budget_cap": ("worldbook", True, False, True),
    "worldbook_overflow_alert": ("worldbook", True, False, False),
    "output_contract_mode": ("output_contract_exec", False, True, False),
    "output_contract_allow_full_rewrite": ("output_contract_exec", True, True, False),
    "output_contract_strict_fallback": ("output_contract_exec", True, True, False),
    "output_contract_require_confirmed": ("output_contract_exec", True, True, False),
}


def test_schema_snapshot_matches_registry():
    """registry 结构与 EXPECTED_SCHEMA 逐项一致（前端 configSchema.ts 同源）。"""
    live = {
        it.key: (it.group, it.advanced, it.inheritable, it.has_system_default)
        for it in reg.CHAT_CONFIG_ITEMS
    }
    assert live == EXPECTED_SCHEMA, (
        "config_registry 与 EXPECTED_SCHEMA 不一致——"
        "同步更新 emiya-frontend/src/config/configSchema.ts 与本快照"
    )


def test_allowed_keys_is_nineteen():
    keys = reg.chat_config_allowed_keys()
    assert len(keys) == 19
    assert keys == frozenset(EXPECTED_SCHEMA)


def test_no_duplicate_keys():
    seen = [it.key for it in reg.CHAT_CONFIG_ITEMS]
    assert len(seen) == len(set(seen))


def test_system_default_matches_legacy_hardcoded():
    """回归锁：system_default 与重构前 _system_default_chat_config 逐值相等。"""
    assert reg.system_default_chat_config() == {
        "temperature": settings.CHAT_TEMPERATURE,
        "openai_max_context": settings.MAX_CONTEXT_TOKENS,
        "token_budget_safety_margin": settings.TOKEN_BUDGET_SAFETY_MARGIN,
        "history_budget_cap": 0,
        "worldbook_budget_pct": settings.WORLDBOOK_BUDGET_PCT,
        "worldbook_budget_cap": settings.WORLDBOOK_BUDGET_CAP,
    }


def test_inheritable_items_have_no_system_default():
    """可继承项（null=继承）不进 system_default，避免伪造默认遮蔽继承。"""
    for it in reg.CHAT_CONFIG_ITEMS:
        if it.inheritable:
            assert not it.has_system_default
            assert it.key not in reg.system_default_chat_config()


def test_filter_chat_config_drops_unknown():
    clean, dropped = reg.filter_chat_config(
        {"temperature": 0.8, "bogus": 1, "output_contract_mode": "strict"}
    )
    assert clean == {"temperature": 0.8, "output_contract_mode": "strict"}
    assert dropped == ["bogus"]


def test_filter_chat_config_empty():
    assert reg.filter_chat_config(None) == ({}, [])
    assert reg.filter_chat_config({}) == ({}, [])


# ── resolve_require_confirmed 三层继承（对话 > 账户 > 全局）──


def test_require_confirmed_account_overrides_global(monkeypatch):
    """回归：账户 True + 对话 null → True（修复前账户层拿不到值，恒退全局）。"""
    monkeypatch.setattr(settings, "OUTPUT_CONTRACT_REQUIRE_CONFIRMED", False)
    assert policy.resolve_require_confirmed(
        account_defaults={"output_contract_require_confirmed": True},
        conversation_overrides={"output_contract_require_confirmed": None},
    ) is True


def test_require_confirmed_account_none_falls_to_global(monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_CONTRACT_REQUIRE_CONFIRMED", True)
    assert policy.resolve_require_confirmed(
        account_defaults={"output_contract_require_confirmed": None},
        conversation_overrides={"output_contract_require_confirmed": None},
    ) is True
    monkeypatch.setattr(settings, "OUTPUT_CONTRACT_REQUIRE_CONFIRMED", False)
    assert policy.resolve_require_confirmed(
        account_defaults={"output_contract_require_confirmed": None},
        conversation_overrides=None,
    ) is False


def test_require_confirmed_conversation_wins(monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_CONTRACT_REQUIRE_CONFIRMED", True)
    # 对话 False 覆盖账户 True。
    assert policy.resolve_require_confirmed(
        account_defaults={"output_contract_require_confirmed": True},
        conversation_overrides={"output_contract_require_confirmed": False},
    ) is False


# ── resolve_policy 默认取自 registry ──


def test_resolve_policy_defaults_from_registry():
    """无账户/对话覆盖时 requested 落 DEFAULT_MODE=auto；空契约 auto→repair。"""
    empty = VisibleOutputContract()  # 无 required_sections
    p = policy.resolve_policy(empty)
    assert p["requested_mode"] == reg.DEFAULT_MODE == "auto"
    assert p["mode"] == "repair"  # _dispatch_auto: 无 full_document → repair
    assert p["strict_fallback"] == reg.DEFAULT_STRICT_FALLBACK == "repair"


def test_resolve_policy_auto_full_document_dispatches_guide():
    fd = VisibleOutputContract(
        mode="full_document",
        required_sections=[SectionContract(name="chapter")],
    )
    p = policy.resolve_policy(fd)
    assert p["mode"] == "guide"  # 有 full_document → guide
