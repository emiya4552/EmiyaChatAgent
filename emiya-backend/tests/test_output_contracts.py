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
    assert diagnostics_to_dict(diag) == {
        "mode": "none",
        "ok": True,
        "required": 0,
        "missing": [],
        "invalid_order": [],
        "forbidden_hits": [],
        "repaired": False,
        "repair_mode": None,
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


def test_prompt_renderer_is_empty_for_none_and_lists_tail_blocks():
    none_contract = build_visible_output_contract([])
    assert build_output_contract_prompt(none_contract) == ""

    contract = build_visible_output_contract([detected(STATUS_ENTRY)])
    prompt = build_output_contract_prompt(contract)
    assert "[可见输出格式契约]" in prompt
    assert "【状态栏】" in prompt


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
