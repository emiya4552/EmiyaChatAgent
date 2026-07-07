import json

from app.services.ejs_engine import EJSEngine
from app.services.message_pipeline import (
    _apply_json_patch_ops,
    _apply_update_variable_to_scope,
    _parse_update_variable,
)
from app.services.mvu_runtime import (
    analyze_card_compatibility,
    build_initial_state,
    merge_initial_state_missing_only,
)
from app.services.worldbook.injector import WorldbookInjector
from app.services.worldbook.scanner import ActiveEntry


def test_update_variable_initvar_still_replaces_stat_data():
    text = """
<UpdateVariable>
<initvar>
伶伶:
  当前好感度: 12
</initvar>
</UpdateVariable>
"""

    assert _parse_update_variable(text) == {"伶伶": {"当前好感度": 12}}


def test_update_variable_yaml_dates_are_json_safe_strings():
    text = """
<UpdateVariable>
<initvar>
伶伶:
  初遇日期: 2026-07-02
</initvar>
</UpdateVariable>
"""

    parsed = _parse_update_variable(text)

    assert parsed == {"伶伶": {"初遇日期": "2026-07-02"}}
    json.dumps(parsed)


def test_update_variable_json_patch_mutates_stat_data_before_display_regex():
    text = """
<UpdateVariable>
<Analysis>debug text remains display-only</Analysis>
<JSONPatch>[
  {"op":"replace","path":"/伶伶/当前好感度","value":15},
  {"op":"replace","path":"/user/存在创口","value":true},
  {"op":"delta","path":"/伶伶/阶段","value":1},
  {"op":"insert","path":"/伶伶/事件/-","value":"开场"}
]</JSONPatch>
</UpdateVariable>
"""
    scope = {"local": {"stat_data": {"伶伶": {"阶段": 2}}}, "global": {}, "names": {}}

    updated = _apply_update_variable_to_scope(text, scope)

    assert updated is scope
    stat_data = updated["local"]["stat_data"]
    assert stat_data["伶伶"]["当前好感度"] == 15
    assert stat_data["伶伶"]["阶段"] == 3
    assert stat_data["伶伶"]["事件"] == ["开场"]
    assert stat_data["user"]["存在创口"] is True


def test_ejs_supports_local_var_default_typeof_and_else_if():
    template = """
<%_
if (typeof affectionVal === 'undefined') var affectionVal = getvar('stat_data.伶伶.当前好感度', { defaults: 0 });
_%>
<%_ if (affectionVal <= 30) { _%>low<%_ } else if (affectionVal <= 70) { _%>mid<%_ } else { _%>high<%_ } _%>
"""

    rendered = EJSEngine.render(template, {"stat_data": {"伶伶": {"当前好感度": 55}}})

    assert rendered.strip() == "mid"


def test_ejs_getwi_resolves_controlled_worldbook_lookup():
    rendered = EJSEngine.render(
        "<%- await getwi(null, '试探期机制') %>",
        {"__wi_entries": {"试探期机制": "entry content"}},
    )

    assert rendered == "entry content"


def test_worldbook_injector_exposes_entry_lookup_to_ejs_getwi():
    activated = [
        ActiveEntry(
            entry={"comment": "controller"},
            worldbook_id="1",
            worldbook_name="book",
            position=0,
            depth=4,
            order=100,
            role="system",
            outlet_name=None,
            content="<%- await getwi(null, '试探期机制') %>",
            entry_lookup={"试探期机制": "entry content"},
        )
    ]

    messages = [{"role": "system", "content": "", "_anchor": "char_desc"}]
    rendered = WorldbookInjector.inject(messages, activated, 1, scope={"local": {}})

    assert rendered == [{"role": "system", "content": "entry content"}]


def test_mvu_initial_state_uses_opening_over_initvar_over_static_defaults():
    card_data = {
        "spec": "chara_card_v3",
        "data": {
            "extensions": {
                "tavern_helper": {
                    "scripts": [
                        {
                            "name": "MVU",
                            "content": """
registerMvuSchema({
  stat_data: z.object({
    user: z.object({
      hp: z.number().default(1),
      wounded: z.boolean().default(false),
    })
  })
})
""",
                        }
                    ]
                }
            },
            "character_book": {
                "entries": [
                    {
                        "comment": "[initvar] base",
                        "enabled": False,
                        "content": "user:\n  hp: 5\n  mood: calm\n",
                    },
                    {
                        "comment": "[opening] opening",
                        "enabled": False,
                        "content": "user:\n  hp: 7\n",
                    },
                ]
            },
        },
    }

    initial = build_initial_state(card_data=card_data)

    assert initial["stat_data"]["user"]["hp"] == 7
    assert initial["stat_data"]["user"]["mood"] == "calm"
    assert initial["stat_data"]["user"]["wounded"] is False
    assert initial["compatibility"]["features"]["opening_entries"] == 1
    assert initial["compatibility"]["features"]["initvar_entries"] == 1


def test_mvu_initial_state_missing_only_merge_keeps_existing_values():
    initial = {"stat_data": {"user": {"hp": 7, "mood": "calm"}}, "sources": []}

    merged, filled = merge_initial_state_missing_only(
        {"stat_data": {"user": {"hp": 99}}},
        initial,
        reloaded=True,
    )

    assert merged["stat_data"]["user"]["hp"] == 99
    assert merged["stat_data"]["user"]["mood"] == "calm"
    assert filled == ["stat_data.user.mood"]
    assert merged["_mvu"]["reloaded_at"]


def test_mvu_initial_state_yaml_dates_are_jsonb_serializable():
    initial = build_initial_state(
        card_data={
            "data": {
                "character_book": {
                    "entries": [
                        {
                            "comment": "[initvar] dates",
                            "enabled": False,
                            "content": "伶伶:\n  初遇日期: 2026-07-02\n",
                        }
                    ]
                }
            }
        }
    )

    merged, _ = merge_initial_state_missing_only({}, initial)

    assert merged["stat_data"]["伶伶"]["初遇日期"] == "2026-07-02"
    json.dumps(merged)


def test_mvu_diagnostics_report_unsupported_runtime_js_without_executing():
    report = analyze_card_compatibility({
        "data": {
            "extensions": {
                "tavern_helper": {
                    "scripts": [
                        {
                            "name": "MVU",
                            "content": "registerMvuSchema({ x: z.string().default(() => fetch('/x')) })",
                        }
                    ]
                },
                "regex_scripts": [{"scriptName": "display"}],
            }
        }
    })

    assert report["is_mvu_card"] is True
    assert "tavern_helper_runtime_js" in report["unsupported"]
    assert "dynamic_zod_default" in report["unsupported"]
    assert "regex_scripts_import" in report["supported"]
    detail_by_code = {d["code"]: d for d in report["details"]}
    assert detail_by_code["regex_scripts_import"]["status"] == "supported"
    assert detail_by_code["tavern_helper_runtime_js"]["status"] == "unsupported"
    assert detail_by_code["dynamic_zod_default"]["evidence"] == ["MVU"]


def test_mvu_diagnostics_detail_lists_initialization_sources():
    report = analyze_card_compatibility({
        "data": {
            "character_book": {
                "entries": [
                    {"comment": "[initvar] base stats", "content": "user:\n  hp: 1\n"},
                    {"comment": "[opening] opening stats", "content": "user:\n  hp: 2\n"},
                ]
            }
        }
    })

    detail_by_code = {d["code"]: d for d in report["details"]}

    assert detail_by_code["initvar_worldbook_seed"]["count"] == 1
    assert detail_by_code["initvar_worldbook_seed"]["evidence"] == ["[initvar] base stats"]
    assert detail_by_code["opening_worldbook_seed"]["count"] == 1
    assert detail_by_code["opening_worldbook_seed"]["status"] == "supported"


# ─── ADR-0003 双管线：prompt 真相版 vs 显示版 ───

from app.services.regex_processor import RegexProcessor  # noqa: E402


def _mk_script(name, find, repl, *, prompt_only=False, markdown_only=False):
    return {
        "scriptName": name,
        "findRegex": find,
        "replaceString": repl,
        "placement": [2],  # AI_OUTPUT
        "promptOnly": prompt_only,
        "markdownOnly": markdown_only,
        "disabled": False,
    }


def test_two_pipeline_split_by_script_flags():
    """content=neither（promptOnly 留给 build）；display=not promptOnly（含美化）。"""
    text = "u<U>x</U> b<B>y</B> n<N>z</N>"
    strip = _mk_script(
        "strip-promptonly", r"/<U>[\s\S]*?<\/U>/", "", prompt_only=True,
    )
    beautify = _mk_script(
        "fold-markdownonly", r"/<B>[\s\S]*?<\/B>/", "[B]", markdown_only=True,
    )
    both = _mk_script("both-sides", r"/<N>[\s\S]*?<\/N>/", "[N]")  # neither flag
    scripts = [strip, beautify, both]

    # 与 message_pipeline.process_assistant_message_text 的划分保持一致
    prompt_scripts = [
        s for s in scripts
        if not s.get("markdownOnly", False) and not s.get("promptOnly", False)
    ]
    display_scripts = [s for s in scripts if not s.get("promptOnly", False)]

    content = RegexProcessor.apply_reply_to_text(text, prompt_scripts)
    display = RegexProcessor.apply_reply_to_text(text, display_scripts)

    # content(prompt 真相版)：只烘 neither；promptOnly 的 <U> 原样保留（交给 build
    # 阶段 apply_prompt_only 按 depth 处理），markdownOnly 的 <B> 不进来
    assert content == "u<U>x</U> b<B>y</B> n[N]"
    # display(显示版)：markdownOnly + neither 都生效；promptOnly 的 <U> 保留
    assert display == "u<U>x</U> b[B] n[N]"


def test_apply_reply_to_text_now_applies_passed_promptonly_scripts():
    """回归护栏：apply_reply_to_text 不再内部过滤 promptOnly，忠实应用传入集合。"""
    text = "keep <opt>menu</opt> tail"
    prompt_only = _mk_script(
        "hide-options", r"/<opt>[\s\S]*?<\/opt>/", "", prompt_only=True
    )

    out = RegexProcessor.apply_reply_to_text(text, [prompt_only])

    assert out == "keep  tail"


# ─── ADR-0003 拦截：MVU 指令条目不被尾部模板兜底误当输出模板 ───

from app.services.langgraph.nodes import (  # noqa: E402
    _detect_output_templates,
    _extract_template_entries,
)


def test_tail_template_skips_mvu_tagged_entries():
    wi = [
        {  # [mvu_update]：含 <UpdateVariable>/<Analysis>/<JSONPatch> 自定义标签，
           # 旧逻辑会误命中 has_custom_tag → 被当成输出模板
            "comment": "[mvu_update]变量输出格式",
            "content": "<UpdateVariable><Analysis>x</Analysis>"
                       "<JSONPatch>[]</JSONPatch></UpdateVariable>",
            "order": 10,
        },
        {  # [mvu_status]：状态读数，不是 LLM 要回填的模板
            "comment": "[mvu_status]变量列表",
            "content": "<status_current_variables>a: 1</status_current_variables>",
            "order": 20,
        },
        {  # 真正的输出模板（非 MVU 标签）应保留
            "comment": "状态栏模板",
            "content": "<details><summary>【状态栏】</summary>"
                       "<StatusBlock>{名字}</StatusBlock></details>",
            "order": 30,
        },
    ]

    entries = _extract_template_entries(wi)
    markers = _detect_output_templates(wi)

    # 只保留真正的输出模板；两条 MVU 指令/状态条目被排除
    assert [e["comment"] if "comment" in e else e["marker"] for e in entries]  # not empty
    assert markers == ["【状态栏】"]


# ─── ADR-0003 §3：MVU 诊断运行时视图 ───

from app.services.mvu_runtime import build_runtime_view  # noqa: E402


def test_build_runtime_view_classifies_activated_mvu_entries():
    wi = [
        {"comment": "[mvu_update]变量输出格式", "content": "x" * 10,
         "worldbook_id": "1", "worldbook_name": "b"},
        {"comment": "[mvu_status]变量列表", "content": "y" * 20,
         "worldbook_id": "1", "worldbook_name": "b"},
        {"comment": "03_角色扮演注意[mvu_plot]", "content": "z" * 30,
         "worldbook_id": "1", "worldbook_name": "b"},
        {"comment": "普通剧情条目", "content": "n",
         "worldbook_id": "1", "worldbook_name": "b"},
    ]

    view = build_runtime_view(wi)

    assert view["is_mvu"] is True
    assert view["counts"] == {"update": 1, "status": 1, "plot": 1}
    assert [e["role"] for e in view["entries"]] == ["update", "status", "plot"]
    assert all(e["injected_as_prompt"] is True for e in view["entries"])
    assert any("尾部模板" in d for d in view["diagnostics"])


def test_build_runtime_view_empty_for_non_mvu():
    assert build_runtime_view([{"comment": "普通", "content": "x"}])["is_mvu"] is False
    assert build_runtime_view(None)["is_mvu"] is False


def test_build_runtime_view_includes_update_tool_meta():
    view = build_runtime_view(
        [{"comment": "[mvu_update] rules", "content": "score: 0~100"}],
        update_diag={"applied": 0, "dropped": [], "coerced": [], "clamped": []},
        update_channel="none",
        update_meta={
            "enabled_flag": True,
            "persona_uses_mvu": True,
            "tools_sent": True,
            "tool_count": 1,
            "mvu_update_entries": 1,
            "tool_calls_received": 0,
            "tool_call_names": [],
        },
    )

    assert view["update"]["meta"]["enabled_flag"] is True
    assert view["update"]["meta"]["tools_sent"] is True
    assert view["update"]["meta"]["tool_calls_received"] == 0
    assert any("tool_calls=0" in d for d in view["diagnostics"])


# ─── ADR-0005：更新校验核心 + 约束提取 ───

from app.services.mvu_runtime import (  # noqa: E402
    extract_constraints_from_entries,
    validate_ops,
)


def test_validate_ops_rejects_readonly_underscore_paths():
    stat = {"_storyState": {"idx": 0}, "好感度": 40}
    ops = [
        {"op": "replace", "path": "/_storyState/idx", "value": 9},
        {"op": "replace", "path": "/好感度", "value": 45},
    ]
    accepted, diag = validate_ops(stat, ops)
    assert [o["path"] for o in accepted] == ["/好感度"]
    assert diag["dropped"][0]["reason"].startswith("只读")


def test_validate_ops_coerces_to_current_value_type():
    stat = {"存在创口": False, "好感度": 40}
    ops = [
        {"op": "replace", "path": "/存在创口", "value": "true"},
        {"op": "replace", "path": "/好感度", "value": "45"},
    ]
    accepted, diag = validate_ops(stat, ops)
    by = {o["path"]: o["value"] for o in accepted}
    assert by["/存在创口"] is True
    assert by["/好感度"] == 45
    assert len(diag["coerced"]) == 2


def test_validate_ops_clamps_range_and_drops_bad_enum():
    stat = {"好感度": 40, "情绪": "平静"}
    constraints = {
        "好感度": {"type": "number", "min": 0, "max": 100},
        "情绪": {"type": "string", "enum": ["开心", "平静", "发情"]},
    }
    ops = [
        {"op": "replace", "path": "/好感度", "value": 250},
        {"op": "replace", "path": "/情绪", "value": "暴躁"},
    ]
    accepted, diag = validate_ops(stat, ops, constraints)
    assert {o["path"]: o["value"] for o in accepted} == {"/好感度": 100}
    assert diag["clamped"][0]["to"] == 100
    assert any("枚举" in d["reason"] for d in diag["dropped"])


def test_validate_ops_rejects_readonly_source_paths_for_move():
    stat = {"_storyState": {"idx": 1}, "score": 40}
    ops = [{"op": "move", "from": "/_storyState/idx", "path": "/score"}]

    accepted, diag = validate_ops(stat, ops)

    assert accepted == []
    assert diag["dropped"][0]["path"] == "/_storyState/idx"


def test_delta_update_clamps_result_after_application():
    stat = {"score": 40}
    constraints = {"score": {"type": "number", "min": 0, "max": 100}}
    diag = {"applied": 0, "dropped": [], "coerced": [], "clamped": []}

    _apply_json_patch_ops(
        stat,
        [{"op": "delta", "path": "/score", "value": 100}],
        constraints,
        diag,
    )

    assert stat["score"] == 100
    assert diag["clamped"][0]["path"] == "/score"
    assert diag["clamped"][0]["to"] == 100


def test_initvar_update_uses_validation_before_replace():
    text = """
<UpdateVariable>
<initvar>
score: "250"
_storyState:
  idx: 2
</initvar>
</UpdateVariable>
"""
    scope = {"local": {"stat_data": {"score": 40, "keep": "removed"}}}
    constraints = {"score": {"type": "number", "min": 0, "max": 100}}
    diag = {"applied": 0, "dropped": [], "coerced": [], "clamped": []}

    updated = _apply_update_variable_to_scope(text, scope, constraints, diag)

    assert updated["local"]["stat_data"] == {"score": 100}
    assert diag["coerced"][0]["path"] == "/score"
    assert diag["clamped"][0]["path"] == "/score"
    assert diag["dropped"][0]["path"] == "/_storyState/idx"


def test_extract_constraints_from_mvu_update_yaml():
    content = """变量更新规则:
  伶伶:
    当前好感度:
      type: number
      range: 0~100
    当前情绪:
      type: string
      check:
        - 必须且只能从以下7个词汇中选择一个：开心、平静、伤心、发情、生气、害羞、诱惑
"""
    wi = [{"comment": "[mvu_update]变量更新规则", "content": content}]

    c = extract_constraints_from_entries(wi)

    assert c["伶伶.当前好感度"] == {"type": "number", "min": 0, "max": 100}
    assert c["伶伶.当前情绪"]["enum"] == ["开心", "平静", "伤心", "发情", "生气", "害羞", "诱惑"]


# ─── ADR-0005：tool 通道 + 流式累积 ───

from app.services.mvu_runtime.tools import (  # noqa: E402
    build_update_variables_tool,
    extract_update_ops_from_tool_calls,
)
from app.services.llm_service import _accumulate_tool_call_deltas  # noqa: E402
from app.services.mvu_runtime import run_update_pass  # noqa: E402


def test_build_update_variables_tool_uses_mvu_update_desc():
    wi = [
        {"comment": "[mvu_update]变量更新规则", "content": "好感度: 0~100"},
        {"comment": "普通剧情", "content": "无关内容"},
    ]
    tool = build_update_variables_tool(wi)
    assert tool["function"]["name"] == "update_variables"
    assert "好感度: 0~100" in tool["function"]["description"]
    assert "无关内容" not in tool["function"]["description"]
    assert tool["function"]["parameters"]["properties"]["patch"]["type"] == "array"


def test_extract_update_ops_from_tool_calls():
    tool_calls = [
        {"function": {"name": "update_variables",
                      "arguments": '{"patch":[{"op":"replace","path":"/好感度","value":45}]}'}},
        {"function": {"name": "other", "arguments": '{"x":1}'}},
        {"function": {"name": "update_variables", "arguments": "not-json"}},
    ]
    ops = extract_update_ops_from_tool_calls(tool_calls)
    assert ops == [{"op": "replace", "path": "/好感度", "value": 45}]


def test_accumulate_tool_call_deltas_concatenates_arguments():
    acc: dict = {}
    _accumulate_tool_call_deltas(acc, [{"index": 0, "id": "call_1", "type": "function",
                                        "function": {"name": "update_variables", "arguments": '{"pa'}}])
    _accumulate_tool_call_deltas(acc, [{"index": 0, "function": {"arguments": 'tch":[]}'}}])
    assert acc[0]["id"] == "call_1"
    assert acc[0]["function"]["name"] == "update_variables"
    assert acc[0]["function"]["arguments"] == '{"patch":[]}'


async def test_run_update_pass_extracts_forced_tool_ops(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MVU_UPDATE_FORCE_TOOL", True)

    async def _fake_call(**kwargs):
        assert kwargs["tool_choice"] == {
            "type": "function",
            "function": {"name": "update_variables"},
        }
        return "", [
            {
                "function": {
                    "name": "update_variables",
                    "arguments": json.dumps({
                        "patch": [{"op": "replace", "path": "/score", "value": 45}]
                    }),
                }
            }
        ]

    monkeypatch.setattr(
        "app.services.mvu_runtime.update_pass.call_deepseek_tools_non_stream",
        _fake_call,
    )

    ops, meta = await run_update_pass(
        reply="She smiles.",
        wi_activated=[{"comment": "[mvu_update] rules", "content": "score: 0~100"}],
        stat_data={"score": 40},
    )

    assert ops == [{"op": "replace", "path": "/score", "value": 45}]
    assert meta["mode"] == "double_ai"
    assert meta["tool_calls"] == 1
    assert meta["ops"] == 1


async def test_run_update_pass_text_fallback(monkeypatch):
    async def _fake_call(**kwargs):
        return '{"patch":[{"op":"delta","path":"/score","value":1}]}', []

    monkeypatch.setattr(
        "app.services.mvu_runtime.update_pass.call_deepseek_tools_non_stream",
        _fake_call,
    )

    ops, meta = await run_update_pass(
        reply="She warms up.",
        wi_activated=[],
        stat_data={"score": 40},
    )

    assert ops == [{"op": "delta", "path": "/score", "value": 1}]
    assert meta["fallback"] == "text"
    assert meta["ops"] == 1


async def test_run_update_pass_empty_reply_is_noop(monkeypatch):
    async def _fail_call(**kwargs):
        raise AssertionError("should not call LLM for empty replies")

    monkeypatch.setattr(
        "app.services.mvu_runtime.update_pass.call_deepseek_tools_non_stream",
        _fail_call,
    )

    ops, meta = await run_update_pass(reply="   ", wi_activated=[], stat_data={})

    assert ops == []
    assert meta["mode"] == "double_ai"
    assert meta["ops"] == 0


# ─── ADR-0006：宽容解析裸 JSONPatch 数组 + tool 引导 ───

from app.services.message_pipeline import _apply_update_variable_to_scope  # noqa: E402


def test_bare_jsonpatch_array_without_jsonpatch_tag_is_applied():
    # 复现日志：模型丢了 <JSONPatch> 标签，<Analysis> 后直接裸写数组
    text = """你把手伸向她……
<UpdateVariable>
<Analysis>
- user存在创口: true [still bleeding]
- 伶伶当前形态: 0->1
</Analysis>
[
  { "op": "replace", "path": "/伶伶/当前形态", "value": 1 },
  { "op": "replace", "path": "/伶伶/当前情绪", "value": "发情" },
  { "op": "delta", "path": "/伶伶/当前好感度", "value": 2 }
]
</UpdateVariable>"""
    scope = {"local": {"stat_data": {"伶伶": {"当前形态": 0, "当前情绪": "平静", "当前好感度": 15}}},
             "global": {}, "names": {}}

    out = _apply_update_variable_to_scope(text, scope)

    sd = out["local"]["stat_data"]["伶伶"]
    assert sd["当前形态"] == 1
    assert sd["当前情绪"] == "发情"
    assert sd["当前好感度"] == 17


def test_bare_array_still_respects_validation_layer():
    text = """<UpdateVariable>[
  { "op": "replace", "path": "/好感度", "value": 999 },
  { "op": "replace", "path": "/_readonly", "value": 1 }
]</UpdateVariable>"""
    scope = {"local": {"stat_data": {"好感度": 40, "_readonly": 0}}, "global": {}, "names": {}}
    constraints = {"好感度": {"type": "number", "min": 0, "max": 100}}
    diag = {"applied": 0, "dropped": [], "coerced": [], "clamped": []}

    out = _apply_update_variable_to_scope(text, scope, constraints, diag)

    sd = out["local"]["stat_data"]
    assert sd["好感度"] == 100          # clamp 生效
    assert sd["_readonly"] == 0         # 只读未被改
    assert any("只读" in d["reason"] for d in diag["dropped"])
