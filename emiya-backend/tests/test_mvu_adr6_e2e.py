# -*- coding: utf-8 -*-
"""ADR-0006 端到端复现：用日志里的真实载荷跑一遍解析+校验+应用。"""
from app.services.message_pipeline import _apply_update_variable_to_scope
from app.services.mvu_runtime import extract_constraints_from_entries

# 日志 SYSTEM #10 的真实 [mvu_update]变量更新规则（取涉及断言的字段，原样结构）
MVU_UPDATE_RULES = """变量更新规则:
  user:
    存在创口:
      type: boolean
      check:
        - 发生受伤、流血时为true；伤口愈合为false
  伶伶:
    当前形态:
      type: number
      range: 0~1
      check:
        - 0代表常态，1代表吸血态
    当前好感度:
      type: number
      range: 0~100
      check:
        - 根据互动适当调整，单次增减建议不超过5点。
    当前情绪:
      type: string
      check:
        - 必须且只能从以下7个词汇中选择一个最符合当前剧情情绪：开心、平静、伤心、发情、生气、害羞、诱惑
    心里话:
      type: string
      check:
        - 用第一人称简短表述，用括号包裹
"""

# 日志「LLM 原始回复」里模型实际吐的块：叙事 + 丢了 <JSONPatch> 标签的裸数组
REAL_REPLY = """你把手伸向她。她接过你的手腕，低头看着那道还在渗血的伤口……
“……谢谢哥哥。”

<UpdateVariable>
<Analysis>
- Time passed: about 2-3 minutes since last update.
- Dramatic updates allowed: no, just a routine interaction.
- user存在创口: true, remains true.
- 伶伶当前形态: 0->1, she ingested blood, must be updated to 1.
- 伶伶当前情绪: from平静 to 发情.
- 伶伶当前好感度: +2.
- 伶伶心里话: updated.
</Analysis>
[
  { "op": "replace", "path": "/伶伶/当前形态", "value": 1 },
  { "op": "replace", "path": "/伶伶/当前情绪", "value": "发情" },
  { "op": "delta", "path": "/伶伶/当前好感度", "value": 2 },
  { "op": "replace", "path": "/伶伶/心里话", "value": "（还想…再尝一口…）" }
]
</UpdateVariable>"""


def test_adr6_real_lireng_round_applies_and_validates():
    # 1) 约束从真实 [mvu_update] YAML 提取
    constraints = extract_constraints_from_entries(
        [{"comment": "[mvu_update]变量更新规则", "content": MVU_UPDATE_RULES}]
    )
    assert constraints["伶伶.当前形态"] == {"type": "number", "min": 0, "max": 1}
    assert constraints["伶伶.当前好感度"]["max"] == 100
    assert "发情" in constraints["伶伶.当前情绪"]["enum"]

    # 2) 初始状态 = 日志 SYSTEM #8 状态读数
    scope = {"local": {"stat_data": {
        "user": {"存在创口": True},
        "伶伶": {"当前形态": 0, "当前情绪": "平静", "当前好感度": 15, "心里话": "血的味道..."},
        "琳娜": {"当前在场": False},
    }}, "global": {}, "names": {}}
    diag = {"applied": 0, "dropped": [], "coerced": [], "clamped": []}

    # 3) 跑真实回复（宽容解析裸数组 + 校验 + 应用）
    out = _apply_update_variable_to_scope(REAL_REPLY, scope, constraints, diag)

    ll = out["local"]["stat_data"]["伶伶"]
    assert ll["当前形态"] == 1            # Fix1：裸数组被解析；range 0~1 内不裁剪
    assert ll["当前情绪"] == "发情"        # enum 命中
    assert ll["当前好感度"] == 17          # delta +2
    assert ll["心里话"] == "（还想…再尝一口…）"
    assert diag["applied"] == 4
    assert diag["dropped"] == []
    print("\n[ADR-0006 E2E] 应用后 伶伶 =", ll, "\n诊断 =", diag)


def test_adr6_tool_mode_filter_keeps_desc_and_directive():
    from app.services.langgraph.nodes import _MVU_TOOL_DIRECTIVE
    from app.services.mvu_runtime.runtime_view import classify_mvu_comment
    from app.services.mvu_runtime.tools import build_update_variables_tool

    wi = [
        {"comment": "[mvu_update]变量更新规则", "content": "RULES_R"},
        {"comment": "[mvu_status]变量列表", "content": "S"},
        {"comment": "♀️琳奈 [Pro]", "content": "P"},
    ]
    # node_build_prompt 的注入过滤谓词：tool 模式下摘掉 [mvu_update]
    injected = [e for e in wi if classify_mvu_comment(e.get("comment")) != "update"]
    assert [e["comment"] for e in injected] == ["[mvu_status]变量列表", "♀️琳奈 [Pro]"]

    # 但 [mvu_update] 内容仍进 tool description（wi_activated 不动）
    tool = build_update_variables_tool(wi)
    assert "RULES_R" in tool["function"]["description"]

    # 引导文案：让模型调用工具、别写文本
    assert "update_variables" in _MVU_TOOL_DIRECTIVE
    assert "UpdateVariable" in _MVU_TOOL_DIRECTIVE
