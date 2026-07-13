# -*- coding: utf-8 -*-
"""可见输出契约核心测试。"""
import json
import uuid

import pytest

from app.services.output_contracts import (
    ForbiddenTermRule,
    OutputContractMode,
    VisibleOutputContract,
    build_output_contract_prompt,
    build_template_scaffold,
    build_visible_output_contract,
    continue_missing_tail_blocks,
    detect_entry_heuristic,
    diagnostics_to_dict,
    find_missing_tail_blocks,
    validate_visible_output,
)


# 一段满足章节 -> 选项 -> 后台日志 -> 隐藏剧情顺序的完整回复。
FULL_DOCUMENT_REPLY = """# 第一章
这里是正文内容。
> **A.** 选项一
> **B.** 选项二
> **C.** 选项三
> **D.** 选项四
<details><summary>后台日志</summary>日志内容</details>
<details><summary>隐藏剧情</summary>剧情内容</details>
"""


def _full_document_contract(**overrides) -> VisibleOutputContract:
    """从整篇格式样例构建 full_document 契约，便于附加 forbidden_terms。"""
    contract = build_visible_output_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    if overrides:
        from dataclasses import replace

        return replace(contract, **overrides)
    return contract


STATUS_ENTRY = {
    "uid": 1,
    "comment": "状态栏",
    "content": """
# 此为'状态栏'，只允许输出在最底部。
<details>
<summary><b>【状态栏】</b></summary>
<StatusBlock>
姓名:{{char name}}
</StatusBlock>
</details>
""",
    "worldbook_id": "wb-1",
    "worldbook_name": "测试世界书",
}


FULL_DOCUMENT_ENTRY = {
    "uid": 2,
    "comment": "格式要求",
    "content": """
# 格式要求
- 回复必须严格按照以下顺序生成：
1. 章节号（例：# 第一章）
2. 正文
3. 选项区块
4. 后台日志（details标签）
5. 隐藏剧情（details标签）

# 选项区块格式
> **A.** [选项描述]
> **B.** [选项描述]
> **C.** [选项描述]
> **D.** [选项描述]

# 后台日志格式
<details><summary>后台日志（正在生成）</summary></details>
<details><summary>隐藏剧情</summary></details>
""",
}


def detected(entry: dict) -> dict:
    """模拟导入/编辑期已经完成启发式识别的 entry。"""
    e = dict(entry)
    e["output_contract"] = detect_entry_heuristic(e)
    return e


def test_empty_entries_build_none_contract():
    contract = build_visible_output_contract([], {})

    assert contract.mode == OutputContractMode.NONE
    assert contract.required_tail_blocks == []
    diag = validate_visible_output("普通回复", contract)
    assert diag.ok is True
    # diagnostics_to_dict 现为内部调试用途；SSE 协议改走 build_contract_sse（ADR-1f）。
    assert diagnostics_to_dict(diag) == {
        "mode": "none",
        "ok": True,
        "required": 0,
        "issues": [],
    }


def test_status_block_entry_builds_append_tail_contract():
    contract = build_visible_output_contract([detected(STATUS_ENTRY)], {})

    assert contract.mode == OutputContractMode.APPEND_TAIL
    assert len(contract.required_tail_blocks) == 1
    block = contract.required_tail_blocks[0]
    assert block.marker == "【状态栏】"
    assert block.summary == "【状态栏】"
    assert block.source is not None
    assert block.source.comment == "状态栏"


def test_full_document_entry_builds_full_document_contract():
    contract = build_visible_output_contract([detected(FULL_DOCUMENT_ENTRY)], {})

    assert contract.mode == OutputContractMode.FULL_DOCUMENT
    assert [s.name for s in contract.required_sections] == [
        "chapter",
        "body",
        "options",
        "backend_log",
        "hidden_plot",
    ]


def test_append_tail_validator_reports_missing_marker():
    contract = build_visible_output_contract([detected(STATUS_ENTRY)], {})

    diag = validate_visible_output("这里只是正文，没有尾部结构。", contract)

    assert diag.ok is False
    assert diag.missing == [{
        "type": "tail_block",
        "marker": "【状态栏】",
        "source": "状态栏",
        "reason": "missing_marker",
    }]
    assert diagnostics_to_dict(diag)["required"] == 1


def test_append_tail_validator_accepts_existing_marker():
    contract = build_visible_output_contract([detected(STATUS_ENTRY)], {})

    diag = validate_visible_output(
        "正文\n\n<details><summary>【状态栏】</summary>姓名：伶伶</details>",
        contract,
    )

    assert diag.ok is True
    assert diag.missing == []


def test_append_tail_validator_rejects_unclosed_details():
    contract = build_visible_output_contract([detected(STATUS_ENTRY)], {})

    diag = validate_visible_output(
        "正文\n\n<details><summary>【状态栏】</summary>姓名：伶伶",
        contract,
    )

    assert diag.ok is False
    assert diag.missing[0]["reason"] == "unclosed_details"


def test_full_document_validator_accepts_complete_structure():
    contract = _full_document_contract()

    diag = validate_visible_output(FULL_DOCUMENT_REPLY, contract)

    assert diag.ok is True
    assert diag.required == 5
    assert diag.missing == []
    assert diag.invalid_order == []


def test_full_document_validator_reports_missing_option():
    contract = _full_document_contract()
    reply = FULL_DOCUMENT_REPLY.replace("> **D.** 选项四\n", "")

    diag = validate_visible_output(reply, contract)

    assert diag.ok is False
    assert {"section": "options"} in diag.missing


def test_full_document_validator_reports_missing_hidden_plot():
    contract = _full_document_contract()
    reply = FULL_DOCUMENT_REPLY.replace(
        "<details><summary>隐藏剧情</summary>剧情内容</details>\n", ""
    )

    diag = validate_visible_output(reply, contract)

    assert diag.ok is False
    assert {"section": "hidden_plot"} in diag.missing


def test_full_document_validator_reports_invalid_order():
    contract = _full_document_contract()
    # 后台日志被挪到选项之前，顺序违反契约。
    reply = """# 第一章
正文。
<details><summary>后台日志</summary>日志</details>
> **A.** 一
> **B.** 二
> **C.** 三
> **D.** 四
<details><summary>隐藏剧情</summary>剧情</details>
"""

    diag = validate_visible_output(reply, contract)

    assert diag.ok is False
    assert {"before": "backend_log", "after": "options"} in diag.invalid_order


def test_full_document_validator_reports_forbidden_term_in_visible_body():
    contract = _full_document_contract(
        forbidden_terms=[ForbiddenTermRule(term="阶梯钩子", scope="visible")],
    )
    reply = FULL_DOCUMENT_REPLY.replace("这里是正文内容。", "这里是正文内容，含阶梯钩子。")

    diag = validate_visible_output(reply, contract)

    assert diag.ok is False
    assert {"term": "阶梯钩子", "section": "visible"} in diag.forbidden_hits


def test_full_document_validator_ignores_forbidden_term_hidden_in_details():
    contract = _full_document_contract(
        forbidden_terms=[ForbiddenTermRule(term="阶梯钩子", scope="visible")],
    )
    # 禁词只出现在后台日志折叠块内，visible 作用范围不应命中。
    reply = FULL_DOCUMENT_REPLY.replace(
        "<details><summary>后台日志</summary>日志内容</details>",
        "<details><summary>后台日志</summary>日志内容 阶梯钩子</details>",
    )

    diag = validate_visible_output(reply, contract)

    assert diag.ok is True
    assert diag.forbidden_hits == []


def test_full_document_validator_flags_unclosed_details():
    contract = _full_document_contract()
    reply = FULL_DOCUMENT_REPLY.replace("</details>\n", "\n", 1)

    diag = validate_visible_output(reply, contract)

    assert diag.ok is False
    assert {"code": "unclosed_details"} in diag.warnings


def test_mvu_control_entries_are_not_visible_output_contracts():
    contract = build_visible_output_contract([
        {
            "uid": 3,
            "comment": "[mvu_update]变量输出格式",
            "content": "<details><summary>不是用户可见模板</summary></details>",
        }
    ])

    assert contract.mode == OutputContractMode.NONE


def test_detector_skips_mvu_tagged_entries_keeps_real_template():
    # [mvu_update] 指令条目含类 HTML 自定义标签，但不是用户可见输出模板，
    # 导入期启发式识别应判为 none。
    mvu_entry = {
        "comment": "[mvu_update]变量输出格式",
        "content": "<UpdateVariable><Analysis>x</Analysis>"
                   "<JSONPatch>[]</JSONPatch></UpdateVariable>",
        "order": 10,
    }
    assert detect_entry_heuristic(mvu_entry)["type"] == "none"

    # 真正的状态栏模板仍被识别为尾部 HTML 模板。
    status = detect_entry_heuristic(dict(STATUS_ENTRY))
    assert status["type"] == "tail_html"
    assert status["status"] == "detected"


def test_heuristic_detect_marks_trigger_auto_import():
    oc = detect_entry_heuristic(dict(STATUS_ENTRY))
    assert oc["trigger"] == "auto_import"


@pytest.mark.asyncio
async def test_detect_single_entry_marks_trigger_manual(monkeypatch):
    # 手动触发识别（detect_single_entry）必须标 trigger=manual，区别于自动导入识别。
    from app.services import output_contracts as oc_pkg

    async def fake_llm(messages, **kwargs):
        return '{"type": "tail_html", "confidence": 0.9, "reason": "x", "abstract": {}}'

    monkeypatch.setattr(
        "app.services.output_contracts.detector.call_deepseek_non_stream", fake_llm
    )
    result = await oc_pkg.detect_single_entry(dict(STATUS_ENTRY))
    oc = result["output_contract"]
    assert oc["trigger"] == "manual"
    assert oc["type"] == "tail_html"


def test_prompt_renderer_is_empty_for_none_and_lists_tail_blocks():
    none_contract = build_visible_output_contract([])
    assert build_output_contract_prompt(none_contract) == ""

    contract = build_visible_output_contract([detected(STATUS_ENTRY)])
    prompt = build_output_contract_prompt(contract)
    assert "[可见输出格式契约]" in prompt
    assert "【状态栏】" in prompt


@pytest.mark.asyncio
async def test_executor_passes_complete_document():
    from app.services.output_contracts import (
        compile_contract,
        enforce_visible_output_contract,
    )

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    result = await enforce_visible_output_contract(
        content=FULL_DOCUMENT_REPLY,
        display_content=FULL_DOCUMENT_REPLY,
        contract=contract,
    )

    assert result.outcome == "passed"
    assert result.method == "initial"
    # body 是 narrative（diagnose_only），故契约覆盖率为 partial
    assert result.coverage == "partial"


@pytest.mark.asyncio
async def test_executor_reconstructs_unclosed_details():
    from app.services.output_contracts import (
        compile_contract,
        enforce_visible_output_contract,
    )

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    # 内容齐全但隐藏剧情的 </details> 缺失
    display = (
        "# 第一章\n正文\n"
        "> **A.** 一\n> **B.** 二\n> **C.** 三\n> **D.** 四\n"
        "<details><summary>后台日志</summary>日志</details>\n"
        "<details><summary>隐藏剧情</summary>剧情"
    )

    result = await enforce_visible_output_contract(
        content=display, display_content=display, contract=contract
    )

    assert result.method == "reconstructed"
    assert result.outcome == "passed"
    assert any(a["action"] == "close_details" for a in result.actions)
    assert result.diagnostics["initial"]["ok"] is False
    assert result.diagnostics["final"]["ok"] is True


@pytest.mark.asyncio
async def test_executor_off_mode_skips_repair():
    from app.services.output_contracts import (
        compile_contract,
        enforce_visible_output_contract,
    )

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    broken = (
        "# 第一章\n正文\n> **A.** 一\n> **B.** 二\n> **C.** 三\n> **D.** 四\n"
        "<details><summary>后台日志</summary>日志</details>\n"
        "<details><summary>隐藏剧情</summary>剧情"  # 缺闭合
    )

    result = await enforce_visible_output_contract(
        content=broken,
        display_content=broken,
        contract=contract,
        policy={"mode": "off"},
    )

    assert result.outcome == "disabled"
    assert result.effective_mode == "off"
    assert result.actions == []
    assert result.display_content == broken  # 未修复，原样返回


@pytest.mark.asyncio
async def test_executor_guide_mode_validates_without_repair():
    from app.services.output_contracts import (
        compile_contract,
        enforce_visible_output_contract,
    )

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    broken = (
        "# 第一章\n正文\n> **A.** 一\n> **B.** 二\n> **C.** 三\n> **D.** 四\n"
        "<details><summary>后台日志</summary>日志</details>\n"
        "<details><summary>隐藏剧情</summary>剧情"  # 缺闭合
    )

    result = await enforce_visible_output_contract(
        content=broken,
        display_content=broken,
        contract=contract,
        policy={"mode": "guide"},
    )

    assert result.outcome == "failed"
    assert result.method == "initial"
    assert result.actions == []
    assert result.display_content == broken  # guide 不修复
    assert result.diagnostics["initial"]["ok"] is False


@pytest.mark.asyncio
async def test_executor_strict_unavailable_falls_back_to_repair():
    from app.services.output_contracts import (
        compile_contract,
        enforce_visible_output_contract,
    )

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    broken = (
        "# 第一章\n正文\n> **A.** 一\n> **B.** 二\n> **C.** 三\n> **D.** 四\n"
        "<details><summary>后台日志</summary>日志</details>\n"
        "<details><summary>隐藏剧情</summary>剧情"  # 缺闭合
    )

    # strict 预算不足 → 不可用 → 按 strict_fallback（默认 repair）降级，如实反映 effective_mode。
    result = await enforce_visible_output_contract(
        content=broken,
        display_content=broken,
        contract=contract,
        policy={"mode": "strict", "requested_mode": "strict", "strict_budget_ok": False},
    )

    assert result.requested_mode == "strict"
    assert result.effective_mode == "repair"
    assert result.outcome == "passed"
    assert result.method == "reconstructed"


@pytest.mark.asyncio
async def test_executor_conflict_only_diagnoses():
    from app.services.output_contracts import (
        compile_contract,
        enforce_visible_output_contract,
    )

    a = _fd_entry(1, [
        {"name": "options", "marker": "> **A.**", "order": 30},
        {"name": "backend_log", "marker": "后台日志", "order": 40},
    ], comment="卡A")
    b = _fd_entry(2, [
        {"name": "backend_log", "marker": "后台日志", "order": 30},
        {"name": "options", "marker": "> **A.**", "order": 40},
    ], comment="卡B")
    contract = compile_contract([a, b])
    assert contract.has_conflict is True

    result = await enforce_visible_output_contract(
        content=FULL_DOCUMENT_REPLY,
        display_content=FULL_DOCUMENT_REPLY,
        contract=contract,
    )

    assert result.outcome == "conflict"
    assert result.actions == []
    assert result.diagnostics.get("conflicts")


# 缺失后台日志 / 隐藏剧情两个折叠块的回复（正文 + 选项齐全）。
_REPLY_MISSING_DETAILS = (
    "# 第一章\n正文内容。\n"
    "> **A.** 一\n> **B.** 二\n> **C.** 三\n> **D.** 四\n"
)


@pytest.mark.asyncio
async def test_executor_slot_completion_fills_missing_details(monkeypatch):
    from app.services.output_contracts import (
        compile_contract,
        enforce_visible_output_contract,
    )

    async def fake_llm(messages, **kwargs):
        return '{"slots": {"backend_log": "日志内容", "hidden_plot": "剧情内容"}}'

    monkeypatch.setattr(
        "app.services.output_contracts.slotfill.call_deepseek_non_stream", fake_llm
    )
    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})

    result = await enforce_visible_output_contract(
        content=_REPLY_MISSING_DETAILS,
        display_content=_REPLY_MISSING_DETAILS,
        contract=contract,
        policy={"mode": "repair"},
    )

    assert result.method == "slot_completed"
    assert result.outcome == "passed"
    assert "<details><summary>后台日志</summary>" in result.display_content
    assert "<details><summary>隐藏剧情</summary>" in result.display_content
    # 补出的两块顺序正确：后台日志在隐藏剧情之前
    assert result.display_content.index("后台日志") < result.display_content.index("隐藏剧情")
    assert any(a["action"] == "fill_slot" for a in result.actions)


@pytest.mark.asyncio
async def test_executor_rewrite_fallback_when_authorized(monkeypatch):
    from app.services.output_contracts import (
        compile_contract,
        enforce_visible_output_contract,
    )

    async def empty_slots(messages, **kwargs):
        return '{"slots": {}}'

    async def full_rewrite(messages, **kwargs):
        return FULL_DOCUMENT_REPLY

    monkeypatch.setattr(
        "app.services.output_contracts.slotfill.call_deepseek_non_stream", empty_slots
    )
    monkeypatch.setattr(
        "app.services.output_contracts.rewrite.call_deepseek_non_stream", full_rewrite
    )
    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})

    result = await enforce_visible_output_contract(
        content=_REPLY_MISSING_DETAILS,
        display_content=_REPLY_MISSING_DETAILS,
        contract=contract,
        policy={"mode": "repair", "allow_full_rewrite": True},
    )

    assert result.method == "rewritten"
    assert result.outcome == "passed"
    assert any(a.get("action") == "full_rewrite" for a in result.actions)


@pytest.mark.asyncio
async def test_executor_no_rewrite_without_authorization(monkeypatch):
    from app.services.output_contracts import (
        compile_contract,
        enforce_visible_output_contract,
    )

    called = {"rewrite": False}

    async def empty_slots(messages, **kwargs):
        return '{"slots": {}}'

    async def rewrite_spy(messages, **kwargs):
        called["rewrite"] = True
        return FULL_DOCUMENT_REPLY

    monkeypatch.setattr(
        "app.services.output_contracts.slotfill.call_deepseek_non_stream", empty_slots
    )
    monkeypatch.setattr(
        "app.services.output_contracts.rewrite.call_deepseek_non_stream", rewrite_spy
    )
    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})

    result = await enforce_visible_output_contract(
        content=_REPLY_MISSING_DETAILS,
        display_content=_REPLY_MISSING_DETAILS,
        contract=contract,
        policy={"mode": "repair"},  # 未授权 rewrite
    )

    assert called["rewrite"] is False
    assert result.method != "rewritten"
    assert result.outcome == "failed"


def test_apply_slots_replaces_empty_details_shell():
    from app.services.output_contracts import apply_slots, compile_contract

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    text = (
        "# 第一章\n正文\n"
        "<details><summary>后台日志</summary></details>\n"
    )
    out, actions = apply_slots(text, contract, {"backend_log": "日志X"})

    assert "<details><summary>后台日志</summary>\n日志X\n</details>" in out
    assert actions[0]["mode"] == "replace"


@pytest.mark.asyncio
async def test_strict_renders_structure_from_prose_draft(monkeypatch):
    from app.services.output_contracts import (
        compile_contract,
        enforce_visible_output_contract,
    )

    # 主模型草稿只有正文（无任何结构标签）——strict 仍要渲染出完整结构外壳。
    draft = "夜色下，她推开门，屋里空无一人。"

    async def fake_slots(messages, **kwargs):
        return (
            '{"slots": {"chapter": "第一章 归来", '
            '"options": ["搜查房间", "呼喊名字", "离开", "报警"], '
            '"backend_log": "location=旧宅", "hidden_plot": "有人先一步来过"}}'
        )

    monkeypatch.setattr(
        "app.services.output_contracts.slotfill.call_deepseek_non_stream", fake_slots
    )
    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})

    result = await enforce_visible_output_contract(
        content=draft,
        display_content=draft,
        contract=contract,
        policy={"mode": "strict", "requested_mode": "strict"},
    )

    assert result.effective_mode == "strict"
    assert result.method == "strict_rendered"
    assert result.outcome == "passed"
    doc = result.display_content
    # 结构外壳由 renderer 硬保证：章节标题、四个选项、两个折叠块、顺序
    assert "# 第一章 归来" in doc
    assert "> **A.** 搜查房间" in doc
    assert "> **D.** 报警" in doc
    assert "<details><summary>后台日志</summary>" in doc
    assert doc.index("后台日志") < doc.index("隐藏剧情")
    # 草稿正文保留在文档中
    assert "夜色下" in doc


@pytest.mark.asyncio
async def test_strict_unavailable_falls_back_per_policy(monkeypatch):
    from app.services.output_contracts import (
        compile_contract,
        enforce_visible_output_contract,
    )

    # 两个互斥 full_document → 冲突 → strict 不可用 → 按 strict_fallback 降级。
    a = _fd_entry(1, [
        {"name": "options", "marker": "> **A.**", "order": 30},
        {"name": "backend_log", "marker": "后台日志", "order": 40},
    ])
    b = _fd_entry(2, [
        {"name": "backend_log", "marker": "后台日志", "order": 30},
        {"name": "options", "marker": "> **A.**", "order": 40},
    ])
    contract = compile_contract([a, b])

    result = await enforce_visible_output_contract(
        content="正文",
        display_content="正文",
        contract=contract,
        policy={"mode": "strict", "requested_mode": "strict", "strict_fallback": "guide"},
    )

    # 冲突短路优先：strict 不启动，只诊断
    assert result.outcome == "conflict"
    assert result.effective_mode != "strict"


def test_strict_available_gating():
    from app.services.output_contracts import compile_contract, strict_available

    ok_contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    available, reason = strict_available(ok_contract, {})
    assert available is True and reason == ""

    # 预算不足时不可用
    available, reason = strict_available(ok_contract, {"strict_budget_ok": False})
    assert available is False and reason == "insufficient_budget"


def test_reconstruct_closes_unbalanced_details():
    from app.services.output_contracts import compile_contract, reconstruct

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    broken = "# 第一章\n正文\n<details><summary>后台日志</summary>日志"  # 缺 </details>

    fixed, actions = reconstruct(broken, contract)

    assert _DETAILS_OPEN_COUNT(fixed) == _DETAILS_CLOSE_COUNT(fixed)
    assert actions and actions[0]["action"] == "close_details"


def test_reconstruct_normalizes_choice_labels():
    from app.services.output_contracts import compile_contract, reconstruct

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    # 缺引用前缀 / 缺点号 / 缩进 —— 都应规范成 `> **A.** 描述`。
    broken = (
        "# 第一章\n正文\n"
        "**A.** 去码头\n"
        "> **B** 回家\n"
        "  **C.** 等待\n"
        "> **D.** 报警\n"
    )
    fixed, actions = reconstruct(broken, contract)

    assert "> **A.** 去码头" in fixed
    assert "> **B.** 回家" in fixed
    assert "> **C.** 等待" in fixed
    assert any(a["action"] == "normalize_choices" for a in actions)


def test_reconstruct_dedup_identical_empty_shells():
    from app.services.output_contracts import compile_contract, reconstruct

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    dup = (
        "# 第一章\n正文\n"
        "<details><summary>后台日志</summary></details>\n"
        "<details><summary>后台日志</summary></details>\n"
    )
    fixed, actions = reconstruct(dup, contract)

    assert fixed.count("<details><summary>后台日志</summary></details>") == 1
    assert any(a["action"] == "dedup_empty_details" for a in actions)


def test_reconstruct_reorders_adjacent_details_by_contract_order():
    from app.services.output_contracts import compile_contract, reconstruct

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    # 隐藏剧情(order 50) 排在后台日志(order 40) 之前，且两块相邻仅空白分隔 → 可安全重排。
    swapped = (
        "<details><summary>隐藏剧情</summary>剧情</details>\n"
        "<details><summary>后台日志</summary>日志</details>\n"
    )
    fixed, actions = reconstruct(swapped, contract)

    assert fixed.index("后台日志") < fixed.index("隐藏剧情")
    assert any(a["action"] == "reorder_details" for a in actions)


def test_reconstruct_keeps_order_when_narrative_between_blocks():
    from app.services.output_contracts import compile_contract, reconstruct

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    # 两块之间夹着正文 → 边界有歧义，不重排（narrative 永不切割）。
    ambiguous = (
        "<details><summary>隐藏剧情</summary>剧情</details>\n"
        "一段正文夹在中间。\n"
        "<details><summary>后台日志</summary>日志</details>\n"
    )
    fixed, actions = reconstruct(ambiguous, contract)

    assert fixed.index("隐藏剧情") < fixed.index("后台日志")  # 顺序保持不变
    assert all(a["action"] != "reorder_details" for a in actions)


def test_reconstruct_noop_when_balanced():
    from app.services.output_contracts import compile_contract, reconstruct

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    fixed, actions = reconstruct(FULL_DOCUMENT_REPLY, contract)

    assert actions == []
    assert fixed == FULL_DOCUMENT_REPLY


def _DETAILS_OPEN_COUNT(text: str) -> int:
    import re
    return len(re.findall(r"<details\b", text, re.IGNORECASE))


def _DETAILS_CLOSE_COUNT(text: str) -> int:
    import re
    return len(re.findall(r"</details\s*>", text, re.IGNORECASE))


def test_compile_contract_fills_controlled_kinds():
    from app.services.output_contracts import compile_contract, SectionKind, SpanStrategy

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    by_name = {s.name: s for s in contract.required_sections}

    assert by_name["chapter"].kind == SectionKind.MARKDOWN_HEADING
    assert by_name["body"].kind == SectionKind.NARRATIVE
    assert by_name["options"].kind == SectionKind.CHOICE_SET
    assert by_name["options"].span_strategy == SpanStrategy.FIXED_LINE_SET
    assert by_name["options"].content_policy == "non_empty"
    assert by_name["options"].min_items == 4
    assert by_name["backend_log"].kind == SectionKind.DETAILS_SUMMARY
    assert by_name["backend_log"].span_strategy == SpanStrategy.BALANCED_TAG
    assert by_name["backend_log"].repair_policy == "deterministic"
    # narrative / heading 不可确定性重排，降级为诊断
    assert by_name["body"].repair_policy == "diagnose_only"
    assert by_name["chapter"].span_strategy == SpanStrategy.UNTIL_NEXT_ANCHOR


def test_compiled_contract_flags_empty_choice_set():
    # 选项区块四个标签都在，但 D 只有 marker 没有描述 → empty_section。
    from app.services.output_contracts import compile_contract

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    reply = FULL_DOCUMENT_REPLY.replace("> **D.** 选项四", "> **D.**")

    diag = validate_visible_output(reply, contract)

    assert diag.ok is False
    assert {"section": "options", "code": "empty_section"} in diag.missing


def test_compiled_contract_flags_empty_details_shell():
    # 后台日志外壳齐全、正确闭合，但内部无内容 → empty_section（空壳不算通过）。
    from app.services.output_contracts import compile_contract

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    reply = FULL_DOCUMENT_REPLY.replace(
        "<details><summary>后台日志</summary>日志内容</details>",
        "<details><summary>后台日志</summary></details>",
    )

    diag = validate_visible_output(reply, contract)

    assert diag.ok is False
    assert {"section": "backend_log", "code": "empty_section"} in diag.missing


def test_uncompiled_contract_allows_empty_shell():
    # 未编译契约默认 allow_empty，空壳不应触发 empty_section（保持 ADR-1d 行为）。
    contract = _full_document_contract()
    reply = FULL_DOCUMENT_REPLY.replace(
        "<details><summary>后台日志</summary>日志内容</details>",
        "<details><summary>后台日志</summary></details>",
    )

    diag = validate_visible_output(reply, contract)

    assert all(m.get("code") != "empty_section" for m in diag.missing)


def _fd_entry(
    uid,
    sections,
    *,
    source="heuristic",
    trigger="auto_import",
    reviewed=False,
    confidence=0.9,
    comment="fd",
):
    """构造一条已识别的 full_document entry（直接给定 abstract sections）。"""
    return {
        "uid": uid,
        "comment": comment,
        "content": "整篇格式要求",
        "output_contract": {
            "type": "full_document",
            "status": "detected",
            "source": source,
            "trigger": trigger,
            "reviewed": reviewed,
            "confidence": confidence,
            "abstract": {"placement": "full_document", "sections": sections},
        },
    }


def test_compiler_merges_compatible_full_documents_without_conflict():
    from app.services.output_contracts import compile_contract

    # 两条 full_document 序列一致（章节→选项），属常见拆分卡结构，应并入不冲突。
    a = _fd_entry(1, [
        {"name": "chapter", "marker": "#", "order": 10},
        {"name": "options", "marker": "> **A.**", "order": 30},
    ])
    b = _fd_entry(2, [
        {"name": "chapter", "marker": "#", "order": 10},
        {"name": "options", "marker": "> **A.**", "order": 30},
    ])

    contract = compile_contract([a, b])

    assert contract.has_conflict is False
    assert {s.name for s in contract.required_sections} == {"chapter", "options"}


def test_compiler_detects_full_document_order_conflict():
    from app.services.output_contracts import compile_contract

    # A：选项在后台日志之前；B：后台日志在选项之前 —— 序列互斥。
    a = _fd_entry(1, [
        {"name": "options", "marker": "> **A.**", "order": 30},
        {"name": "backend_log", "marker": "后台日志", "order": 40},
    ], comment="卡A")
    b = _fd_entry(2, [
        {"name": "backend_log", "marker": "后台日志", "order": 30},
        {"name": "options", "marker": "> **A.**", "order": 40},
    ], comment="卡B")

    contract = compile_contract([a, b])

    assert contract.has_conflict is True
    assert contract.conflicts[0]["code"] == "contract_conflict"


def test_compiler_selects_main_by_authority():
    from app.services.output_contracts import compile_contract

    # A 启发式（低权威），B 用户已确认（reviewed）——主契约取 B，其 sections 决定整篇。
    a = _fd_entry(1, [
        {"name": "chapter", "marker": "#", "order": 10},
        {"name": "options", "marker": "> **A.**", "order": 30},
    ], source="heuristic", comment="启发式卡")
    b = _fd_entry(2, [
        {"name": "chapter", "marker": "#", "order": 10},
        {"name": "backend_log", "marker": "后台日志", "order": 40},
        {"name": "hidden_plot", "marker": "隐藏剧情", "order": 50},
    ], source="llm", reviewed=True, comment="已确认卡")

    contract = compile_contract([a, b])

    names = {s.name for s in contract.required_sections}
    # 取主契约 B 的 sections；次要 full_document A 独有的 options 不并入。
    assert names == {"chapter", "backend_log", "hidden_plot"}
    assert "options" not in names


def test_build_contract_sse_stable_shape_and_rule_split():
    from app.services.output_contracts import build_contract_sse, compile_contract

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    sse = build_contract_sse(
        contract=contract,
        contract_mode="full_document",
        requested_mode="auto",
        effective_mode="repair",
        outcome="passed",
        coverage="partial",
        method="reconstructed",
        initial=None,
        final=None,
        actions=[{"action": "close_details"}],
        latency_ms=12,
        extra_calls=1,
    )

    # 稳定结构的键齐全（ADR-1f）
    for key in (
        "contract_mode", "requested_mode", "effective_mode", "outcome", "coverage",
        "method", "initial", "actions", "final", "guaranteed_rules", "soft_rules",
        "conflicts", "latency_ms", "extra_calls", "token_usage",
    ):
        assert key in sse
    # body(narrative, diagnose_only) 归入软规则；选项/日志等硬结构归入 guaranteed
    assert any("正文" in r for r in sse["soft_rules"])
    assert any("选项区块" in r or "后台日志" in r for r in sse["guaranteed_rules"])
    assert sse["extra_calls"] == 1


def test_resolve_policy_auto_dispatches_by_contract_type():
    from app.services.output_contracts import build_visible_output_contract, resolve_policy

    fd = build_visible_output_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    tail = build_visible_output_contract([detected(STATUS_ENTRY)], {})

    # auto（默认）：full_document → guide，tail → repair，strict 永不自动。
    fd_policy = resolve_policy(fd, account_defaults={"output_contract_default_mode": "auto"})
    tail_policy = resolve_policy(tail, account_defaults={"output_contract_default_mode": "auto"})

    assert fd_policy["mode"] == "guide"
    assert fd_policy["requested_mode"] == "auto"
    assert tail_policy["mode"] == "repair"


def test_resolve_policy_conversation_override_beats_account_default():
    from app.services.output_contracts import build_visible_output_contract, resolve_policy

    fd = build_visible_output_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    policy = resolve_policy(
        fd,
        account_defaults={"output_contract_default_mode": "auto"},
        conversation_overrides={"output_contract_mode": "repair"},
    )
    assert policy["mode"] == "repair"
    assert policy["requested_mode"] == "repair"


def test_resolve_policy_inherit_falls_back_to_account():
    from app.services.output_contracts import build_visible_output_contract, resolve_policy

    fd = build_visible_output_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    policy = resolve_policy(
        fd,
        account_defaults={
            "output_contract_default_mode": "repair",
            "output_contract_allow_full_rewrite": True,
            "output_contract_strict_fallback": "guide",
        },
        conversation_overrides={
            "output_contract_mode": "inherit",
            "output_contract_allow_full_rewrite": None,
            "output_contract_strict_fallback": "inherit",
        },
    )
    assert policy["mode"] == "repair"
    assert policy["allow_full_rewrite"] is True
    assert policy["strict_fallback"] == "guide"


def test_full_document_prompt_lists_ordered_sections_and_rules():
    contract = _full_document_contract()
    prompt = build_output_contract_prompt(contract)

    assert "[可见输出格式契约]" in prompt
    # 按 order 列出区块，且章节在选项之前、选项在后台日志之前
    assert prompt.index("章节") < prompt.index("选项区块") < prompt.index("后台日志")
    assert "隐藏剧情" in prompt
    # 硬规则 + 结构优先说明
    assert "A、B、C、D" in prompt
    assert "优先于" in prompt


def test_renderer_choice_set_enforces_labels_and_count():
    from app.services.output_contracts import render_choice_set

    # 只给两个描述，min_items=4 → 补足 4 个标签，字母由代码保证。
    out = render_choice_set(["去码头", "回家"], min_items=4)

    lines = out.splitlines()
    assert lines[0] == "> **A.** 去码头"
    assert lines[1] == "> **B.** 回家"
    assert lines[2] == "> **C.**"
    assert lines[3] == "> **D.**"


def test_renderer_details_always_closes():
    from app.services.output_contracts import render_details

    assert render_details("后台日志", "x=1") == (
        "<details><summary>后台日志</summary>\nx=1\n</details>"
    )
    assert render_details("隐藏剧情") == "<details><summary>隐藏剧情</summary></details>"


def test_render_section_dispatches_by_kind():
    from app.services.output_contracts import (
        compile_contract,
        render_section,
    )

    contract = compile_contract([detected(FULL_DOCUMENT_ENTRY)], {})
    by_name = {s.name: s for s in contract.required_sections}

    assert render_section(by_name["chapter"], text="第一章") == "# 第一章"
    assert render_section(by_name["backend_log"], text="日志内容") == (
        "<details><summary>后台日志</summary>\n日志内容\n</details>"
    )
    opts = render_section(by_name["options"], choices=["一", "二", "三", "四"])
    assert opts.splitlines()[3] == "> **D.** 四"
    # narrative 直出，无外壳
    assert render_section(by_name["body"], text="正文段落") == "正文段落"


def test_tail_scaffold_keeps_minimal_details_prefix():
    scaffold = build_template_scaffold(STATUS_ENTRY["content"])

    assert scaffold == """<details>
<summary><b>【状态栏】</b></summary>
<StatusBlock>"""


def test_find_missing_tail_blocks_sorts_by_worldbook_order():
    first = {**STATUS_ENTRY, "uid": 10, "comment": "后置", "order": 30}
    second = {
        **STATUS_ENTRY,
        "uid": 11,
        "comment": "前置",
        "content": STATUS_ENTRY["content"].replace("【状态栏】", "【前置栏】"),
        "order": 10,
    }
    contract = build_visible_output_contract([detected(first), detected(second)])

    missing = find_missing_tail_blocks("正文", contract.required_tail_blocks)

    assert [block.marker for block in missing] == ["【前置栏】", "【状态栏】"]


@pytest.mark.asyncio
async def test_continue_missing_tail_blocks_yields_sse_and_updates_reply(monkeypatch):
    async def fake_prefix_stream(**kwargs):
        assert kwargs["stop"] == ["</details>"]
        yield "姓名：伶伶"

    monkeypatch.setattr(
        "app.services.output_contracts.tail.call_deepseek_stream_prefix",
        fake_prefix_stream,
    )
    contract = build_visible_output_contract([detected(STATUS_ENTRY)])
    updated: dict[str, str] = {}

    chunks = [
        chunk async for chunk in continue_missing_tail_blocks(
            reply="正文",
            contract=contract,
            messages=[{"role": "user", "content": "hi"}],
            conversation_id=uuid.uuid4(),
            chat_config={},
            update_reply=lambda reply: updated.__setitem__("reply", reply),
        )
    ]

    deltas = []
    for chunk in chunks:
        data_line = next(line for line in chunk.splitlines() if line.startswith("data: "))
        deltas.append(json.loads(data_line[6:])["content"])

    assert deltas[0].startswith("\n\n<details>")
    assert deltas[1] == "姓名：伶伶"
    assert deltas[2] == "\n</details>"
    assert updated["reply"].endswith("姓名：伶伶\n</details>")
