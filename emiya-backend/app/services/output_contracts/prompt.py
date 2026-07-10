# -*- coding: utf-8 -*-
"""可见输出契约的 prompt 提示文本生成。"""
from __future__ import annotations

from app.services.output_contracts.types import OutputContractMode, VisibleOutputContract


def build_output_contract_prompt(contract: VisibleOutputContract) -> str:
    """把契约渲染成紧凑的系统提示。"""
    if contract.mode == OutputContractMode.NONE:
        return ""

    lines: list[str] = ["[可见输出格式契约]"]
    if contract.mode == OutputContractMode.APPEND_TAIL:
        lines.append("本轮回复必须保留正文，并在尾部包含以下结构块：")
        for block in contract.required_tail_blocks:
            lines.append(f"- {block.marker}")
    elif contract.mode == OutputContractMode.FULL_DOCUMENT:
        lines.append("本轮回复必须按要求输出完整文档结构。")
        if contract.required_sections:
            sections = " -> ".join(section.name for section in contract.required_sections)
            lines.append(f"区块顺序：{sections}")
        if contract.required_tail_blocks:
            lines.append("同时保留以下尾部结构块：")
            for block in contract.required_tail_blocks:
                lines.append(f"- {block.marker}")

    return "\n".join(lines).strip()
