import json

from app.services.ejs_engine import EJSEngine
from app.services.message_pipeline import (
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
