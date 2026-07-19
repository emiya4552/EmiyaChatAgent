# -*- coding: utf-8 -*-
"""ADR-0021：世界书 EJS 真 JS 沙箱（V8 / mini-racer）单元测试。

重点验证 v0 `ejs_engine` 会**静默出错**的地方在 V8 下被正确求值：
  - 状态门（`if (_.get(...) === 'x')`）真正生效（堕落态不再泄漏善良人格）；
  - lodash `_.get` / 箭头函数 / `.includes` / `Object.keys` / `Math.*` 可用；
  - 死循环被 timeout 拦下 → 回退 v0；无 `<%` 透传；开关关时走 v0。
mini-racer 未装时整组 skip（V8 是可选原生依赖，缺失走 v0 回退）。
"""
import pytest

from app.services import js_ejs_engine as je

pytestmark = pytest.mark.skipif(
    not je.is_available(), reason="mini-racer 未装 / V8 不可用（生产回退 v0）"
)

# 这张「魔法少女」卡的典型写法：if 条件 + const + 数组 .includes 分支，全在真 JS 里。
# v0 引擎会把 `if(){ const… }` 当普通 EXEC 丢弃 → 外层门失效 → 善良人格无条件泄漏。
GATE = (
    "<%\n"
    "if (_.get(getvar('stat_data'), '主角.核心状态.人格状态') === '善良') {\n"
    "    const phase = _.get(getvar('stat_data'), '进程.阶段');\n"
    "%>"
    "persona: 善良作家\n"
    "<%_ if (['战斗回合','战斗准备'].includes(phase)) { _%>"
    "focus: 战斗"
    "<%_ } else { _%>"
    "focus: 幕间"
    "<%_ } _%>"
    "<%\n}\n%>"
)


def _scope(state: str, phase: str = "战斗回合") -> dict:
    return {"stat_data": {"主角": {"核心状态": {"人格状态": state}}, "进程": {"阶段": phase}}}


def test_state_gate_善良_renders_with_branch():
    out = je.render(GATE, _scope("善良", "战斗回合"))
    assert "persona: 善良作家" in out
    assert "focus: 战斗" in out  # .includes 分支命中
    assert "幕间" not in out


def test_state_gate_善良_else_branch():
    out = je.render(GATE, _scope("善良", "日常"))
    assert "persona: 善良作家" in out
    assert "focus: 幕间" in out  # else 分支


def test_state_gate_堕落_is_empty():
    # 关键回归：v0 会在堕落态仍泄漏善良人格；V8 下门生效 → 空。
    out = je.render(GATE, _scope("堕落", "战斗回合")).strip()
    assert out == "", f"堕落态不应渲染善良人格，实得: {out!r}"


def test_lodash_arrow_array_object_math():
    tpl = (
        "<% const items = _.get(getvar('stat_data'), '列表', []); %>"
        "<%= items.filter(x => x > 2).map(x => x * 10).join(',') %>|"
        "<%= Object.keys(_.get(getvar('stat_data'), 'm', {})).length %>|"
        "<%= Math.max.apply(null, items) %>|"
        "<%= _.sum(items) %>"
    )
    out = je.render(tpl, {"stat_data": {"列表": [1, 2, 3, 4], "m": {"a": 1, "b": 2}}})
    assert out == "30,40|2|4|10"


def test_no_ejs_passthrough():
    assert je.render("纯文本无模板", {"stat_data": {}}) == "纯文本无模板"
    assert je.render("", {}) == ""


def test_getwi_lookup():
    tpl = "<%= getwi('book', 'k') %>"
    out = je.render(tpl, {"stat_data": {}, "__wi_entries": {"k": "命中WI"}})
    assert out == "命中WI"


def test_timeout_raises_render_error():
    # 死循环必须被 timeout 拦下（防恶意/写坏卡卡死 prompt 构建）。
    with pytest.raises(je.JsEjsRenderError):
        je.render("<% while(true){} %>", {"stat_data": {}}, timeout_ms=120)


def test_render_error_on_bad_js():
    # 卡内 JS 抛错（引用未定义）→ JsEjsRenderError（调用方回退 v0）。
    with pytest.raises(je.JsEjsRenderError):
        je.render("<%= 不存在的函数() %>", {"stat_data": {}})


def test_fallback_enabled_uses_v8():
    # 开关开 + V8 可用：堕落态门生效 → 空。
    out = je.render_with_fallback(GATE, _scope("堕落"), enabled=True).strip()
    assert out == ""


def test_fallback_disabled_uses_v0_and_leaks():
    # 开关关：走 v0，堕落态仍泄漏善良人格（证明确实回退到 v0，并锚定 ADR-0021 描述的 v0 缺陷）。
    out = je.render_with_fallback(GATE, _scope("堕落"), enabled=False)
    assert "善良作家" in out


def test_fallback_on_render_error_degrades_to_v0():
    # V8 渲染抛错（死循环超时）时 render_with_fallback 不抛、回退 v0 出一个字符串。
    out = je.render_with_fallback("<% while(true){} %>后缀", _scope("善良"), enabled=True)
    assert isinstance(out, str)  # v0 对该块静默丢弃，至少不炸
