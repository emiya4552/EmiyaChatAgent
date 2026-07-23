# -*- coding: utf-8 -*-
"""Token 预算：预设 overhead 前置称重 + 越界告警兜底。

回归背景：预设注入是 system 前缀的大头，却在历史裁剪「之后」才注入，
若不前置称重，history_available 系统性高估、最终 prompt 超 max_context。
见 nodes.node_build_prompt、preset_injector.estimate_injection_tokens。
"""
from app.services.token_budget import (
    build_prompt_budget_plan,
    build_token_budget_report,
    count_message_tokens,
)
from app.services.preset_injector import PresetInjector


# 显式 chat_config → 预算完全确定，不依赖 settings 默认。
# history_available = 10000 - 1000(reserved) - 200(safety) - prefix = 8800 - overhead
_CC = {
    "openai_max_context": 10000,
    "openai_max_tokens": 1000,
    "token_budget_safety_margin": 200,
}


def _make_prompt(name, content, enabled=True, position=0, order=100, role="system"):
    return {
        "identifier": name,
        "name": name,
        "enabled": enabled,
        "injection_position": position,
        "injection_depth": 4,
        "injection_order": order,
        "role": role,
        "content": content,
        "marker": False,
    }


class TestPromptBudgetPlanOverhead:
    def test_overhead_shrinks_history_budget_one_for_one(self):
        base = build_prompt_budget_plan(
            prefix_messages=[], chat_config=_CC, reply_length="medium",
        )
        withoh = build_prompt_budget_plan(
            prefix_messages=[], chat_config=_CC, reply_length="medium",
            overhead_tokens=800,
        )
        assert base.history_budget == 8800
        assert withoh.history_budget == 8000
        assert base.prompt_prefix_tokens == 0
        assert withoh.prompt_prefix_tokens == 800

    def test_default_overhead_zero_preserves_old_behavior(self):
        """不传 overhead_tokens 时与改动前完全一致。"""
        plan = build_prompt_budget_plan(
            prefix_messages=[{"role": "system", "content": "hi"}],
            chat_config=_CC, reply_length="medium",
        )
        prefix = count_message_tokens([{"role": "system", "content": "hi"}])
        assert plan.prompt_prefix_tokens == prefix
        assert plan.history_available == max(0, 8800 - prefix)

    def test_overhead_cannot_push_history_negative(self):
        plan = build_prompt_budget_plan(
            prefix_messages=[], chat_config=_CC, reply_length="medium",
            overhead_tokens=999999,
        )
        assert plan.history_available == 0
        assert plan.history_budget == 0


class TestBudgetReportOverflow:
    def _report(self, final_prompt_tokens):
        plan = build_prompt_budget_plan(
            prefix_messages=[], chat_config=_CC, reply_length="medium",
        )
        return build_token_budget_report(
            plan=plan,
            final_prompt_tokens=final_prompt_tokens,
            history_tokens=0,
            history_candidate_tokens=0,
            history_kept_messages=0,
            history_candidate_messages=0,
            worldbook_used_tokens=0,
            worldbook_budget={"budget": 0, "pct": 0, "cap": 0},
        )

    def test_flags_over_budget(self):
        # 9500 + 1000(reserved) = 10500 > 10000
        r = self._report(9500)
        assert r["over_budget"] is True
        assert r["budget_overflow_tokens"] == 500
        assert r["remaining_context"] == 0

    def test_within_budget(self):
        # 8000 + 1000 = 9000 < 10000
        r = self._report(8000)
        assert r["over_budget"] is False
        assert r["budget_overflow_tokens"] == 0
        assert r["remaining_context"] == 1000

    def test_exact_boundary_not_over(self):
        # 9000 + 1000 = 10000 == max_context，不算越界
        r = self._report(9000)
        assert r["over_budget"] is False
        assert r["budget_overflow_tokens"] == 0


class TestPresetOverheadEstimate:
    def test_empty_preset_zero(self):
        assert PresetInjector.estimate_injection_tokens({"prompts": []}) == 0

    def test_skips_disabled_marker_and_empty(self):
        preset = {"prompts": [
            _make_prompt("keep", "hello world"),
            _make_prompt("off", "disabled body", enabled=False),
            _make_prompt("empty", ""),
        ]}
        preset["prompts"].append(
            {**_make_prompt("m", "marker body"), "marker": True},
        )
        expect = count_message_tokens([{"role": "system", "content": "hello world"}])
        assert PresetInjector.estimate_injection_tokens(preset) == expect

    def test_matches_injected_tokens(self):
        """称重与真正 inject 出来的注入项 token 同源一致（防两处渲染漂移）。"""
        preset = {"prompts": [
            _make_prompt("p1", "aaa bbb ccc", position=0),
            _make_prompt("p2", "ddd eee", position=1),
        ]}
        injected = PresetInjector.inject([], preset)
        assert PresetInjector.estimate_injection_tokens(preset) == count_message_tokens(injected)
