# -*- coding: utf-8 -*-
"""可见输出契约的 prompt 提示文本生成。"""
from __future__ import annotations

from app.services.output_contracts.types import OutputContractMode, VisibleOutputContract


_SECTION_LABELS = {
    "chapter": "章节标题",
    "body": "正文",
    "options": "选项区块",
    "backend_log": "后台日志",
    "hidden_plot": "隐藏剧情",
}


def _section_label(section) -> str:
    return _SECTION_LABELS.get(section.name, section.name)


def _full_document_rules(sections) -> list[str]:
    """按已知 section 语义给出硬性格式要求（过渡期按 name 推断，见 ADR-1e）。"""
    names = {s.name for s in sections}
    rules: list[str] = []
    if "chapter" in names:
        rules.append("章节标题使用 markdown 标题（如 `# 第一章`）")
    if "options" in names:
        rules.append("选项区块必须给出 A、B、C、D 四个选项，使用 `> **A.**` 等引用加粗格式")
    if "backend_log" in names:
        rules.append("后台日志用 `<details><summary>后台日志</summary>…</details>` 包裹并正确闭合")
    if "hidden_plot" in names:
        rules.append("隐藏剧情用 `<details><summary>隐藏剧情</summary>…</details>` 包裹并正确闭合")
    return rules


def build_output_contract_prompt(contract: VisibleOutputContract) -> str:
    """把契约渲染成紧凑的系统提示（生成前锚定，ADR-1e §2）。"""
    if contract.mode == OutputContractMode.NONE:
        return ""

    lines: list[str] = ["[可见输出格式契约]"]
    if contract.mode == OutputContractMode.APPEND_TAIL:
        lines.append("本轮回复必须保留正文，并在尾部包含以下结构块：")
        for block in contract.required_tail_blocks:
            lines.append(f"- {block.marker}")
    elif contract.mode == OutputContractMode.FULL_DOCUMENT:
        lines.append("本轮回复必须按固定结构输出，区块顺序如下（缺一不可，顺序不可颠倒）：")
        ordered = sorted(contract.required_sections, key=lambda s: s.order)
        for idx, section in enumerate(ordered, 1):
            marker = f"（标记：{section.marker}）" if section.marker else ""
            optional = "" if section.required else "（可选）"
            lines.append(f"{idx}. {_section_label(section)}{marker}{optional}")
        rules = _full_document_rules(ordered)
        if rules:
            lines.append("硬性要求：")
            lines.extend(f"- {rule}" for rule in rules)
        if contract.required_tail_blocks:
            lines.append("同时在尾部保留以下结构块：")
            for block in contract.required_tail_blocks:
                lines.append(f"- {block.marker}")
        lines.append(
            "以上结构要求优先于任何要求精简、单一标签或省略区块的通用格式文案；"
            "即便预设要求严格输出格式，也必须完整输出上述区块。"
        )

    return "\n".join(lines).strip()
