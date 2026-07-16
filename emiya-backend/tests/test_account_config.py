# -*- coding: utf-8 -*-
"""账户级配置（ADR-4）：解析器/钳制 + API 增量合并回归。

覆盖：
- 空 account_config = 全局 settings（放开后行为不变，回归锁）。
- clamp 钳制越界值（footgun 防护）。
- 提取频率倍率、记忆总开关、预算子集。
- filter_account_config 白名单 + 钳制 + null 清空。
- PATCH /users/me 的 account_config 增量合并（不丢旧键、未知键丢弃、越界钳制、null 清空）。
"""
import pytest

from app.config import settings
from app.services import config_registry as reg


# ── 纯解析器（无 DB）──

def test_empty_account_config_equals_global_defaults():
    """放开前后行为一致：空配置 → 全部 settings 默认。"""
    t = reg.resolve_memory_tuning({})
    assert t.top_k == settings.MEMORY_TOP_K
    assert t.threshold == settings.MEMORY_SIMILARITY_THRESHOLD
    assert t.recency_weight == settings.RECENCY_WEIGHT
    assert t.recency_half_life_days == settings.RECENCY_HALF_LIFE_DAYS
    assert t.mmr_lambda == settings.MMR_LAMBDA
    assert t.dedup_threshold == settings.MEMORY_DEDUP_THRESHOLD
    assert reg.memory_enabled({}) is True
    assert reg.query_rewriting_enabled({}) == settings.ENABLE_QUERY_REWRITING
    assert reg.contradiction_detection_enabled({}) == settings.ENABLE_CONTRADICTION_DETECTION
    assert reg.resolve_window_size({}) == settings.WINDOW_SIZE
    assert reg.resolve_extraction_multiplier({}) == 1.0
    assert reg.account_budget_defaults({}) == {}


def test_clamp_out_of_range():
    assert reg.account_value({"memory_top_k": 999}, "memory_top_k") == 20
    assert reg.account_value({"memory_top_k": 0}, "memory_top_k") == 1
    assert reg.account_value({"memory_similarity_threshold": 2.0}, "memory_similarity_threshold") == 1.0
    assert reg.account_value({"memory_similarity_threshold": -1}, "memory_similarity_threshold") == 0.0
    assert reg.account_value({"window_size": 5000}, "window_size") == 200


def test_bad_value_falls_to_default():
    assert reg.account_value({"memory_top_k": "garbage"}, "memory_top_k") == settings.MEMORY_TOP_K
    assert reg.account_value({"memory_extraction_cadence": "bogus"}, "memory_extraction_cadence") == "standard"


def test_extraction_multiplier_presets():
    assert reg.resolve_extraction_multiplier({"memory_extraction_cadence": "frequent"}) == 0.5
    assert reg.resolve_extraction_multiplier({"memory_extraction_cadence": "sparse"}) == 2.0
    assert reg.resolve_extraction_multiplier({"memory_extraction_cadence": "standard"}) == 1.0


def test_memory_master_switch():
    assert reg.memory_enabled({"memory_enabled": False}) is False
    assert reg.memory_enabled({"memory_enabled": True}) is True


def test_account_budget_defaults_subset_only_set_keys():
    ac = {"openai_max_context": 50000, "worldbook_budget_pct": 30, "memory_top_k": 5}
    assert reg.account_budget_defaults(ac) == {
        "openai_max_context": 50000, "worldbook_budget_pct": 30,
    }


def test_filter_account_config_whitelist_clamp_null():
    clean, dropped = reg.filter_account_config({
        "memory_top_k": 999,      # 钳到 20
        "bogus": 1,                # 未知键丢弃
        "memory_enabled": False,
        "memory_mmr_lambda": None,  # null=未设，不入库
    })
    assert clean == {"memory_top_k": 20, "memory_enabled": False}
    assert dropped == ["bogus"]


def test_memory_tuning_reads_account_overrides():
    ac = {"memory_top_k": 7, "memory_mmr_lambda": 0.9, "memory_recency_weight": 0.1}
    t = reg.resolve_memory_tuning(ac)
    assert t.top_k == 7 and t.mmr_lambda == 0.9 and t.recency_weight == 0.1
    # 未设的项仍回退全局
    assert t.threshold == settings.MEMORY_SIMILARITY_THRESHOLD


# ── API 增量合并（DB）──

@pytest.mark.asyncio
async def test_patch_account_config_merge_clamp_and_clear(client, auth_headers):
    # 1) 存单键
    r1 = await client.patch(
        "/api/v1/users/me", json={"account_config": {"memory_top_k": 7}}, headers=auth_headers,
    )
    assert r1.status_code == 200
    assert r1.json()["account_config"] == {"memory_top_k": 7}

    # 2) 合并：加新键不丢旧键
    r2 = await client.patch(
        "/api/v1/users/me", json={"account_config": {"memory_enabled": False}}, headers=auth_headers,
    )
    assert r2.json()["account_config"] == {"memory_top_k": 7, "memory_enabled": False}

    # 3) 钳制越界 + 未知键丢弃
    r3 = await client.patch(
        "/api/v1/users/me",
        json={"account_config": {"memory_top_k": 999, "bogus": 1}},
        headers=auth_headers,
    )
    ac3 = r3.json()["account_config"]
    assert ac3["memory_top_k"] == 20 and "bogus" not in ac3

    # 4) null 清空该键（回退全局），其它键保留
    r4 = await client.patch(
        "/api/v1/users/me", json={"account_config": {"memory_enabled": None}}, headers=auth_headers,
    )
    ac4 = r4.json()["account_config"]
    assert "memory_enabled" not in ac4 and ac4["memory_top_k"] == 20


@pytest.mark.asyncio
async def test_patch_account_config_untouched_when_absent(client, auth_headers):
    # 先设一个值
    await client.patch(
        "/api/v1/users/me", json={"account_config": {"memory_top_k": 8}}, headers=auth_headers,
    )
    # 只改昵称、不带 account_config → account_config 不受影响
    r = await client.patch(
        "/api/v1/users/me", json={"nickname": "新昵称"}, headers=auth_headers,
    )
    assert r.json()["account_config"] == {"memory_top_k": 8}
    assert r.json()["nickname"] == "新昵称"
