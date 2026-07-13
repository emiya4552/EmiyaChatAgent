# -*- coding: utf-8 -*-
"""受控 kind → 确定性 HTML / Markdown 渲染（ADR-1e §4 / ADR-1g §阶段三）。

renderer 只接收槽位纯内容和 section 定义，输出符合受控 Render Profile 的结构外壳。
结构外壳（标签、选项字母、`<details>` 闭合、章节标题）由代码保证，模型不拼接最终
DOM。reconstructor 的槽位补写与 strict 的确定性渲染共用本模块，避免两套外壳规则。
"""
from __future__ import annotations

from app.services.output_contracts.types import SectionContract, SectionKind

# 选项字母表；超过时回退数字，保证 A/B/C/D… 稳定。
_CHOICE_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _choice_label(index: int) -> str:
    return _CHOICE_LETTERS[index] if index < len(_CHOICE_LETTERS) else str(index + 1)


def render_choice_set(choices: list[str] | None, *, min_items: int = 4) -> str:
    """渲染 `> **A.** 描述` 形式的选项区块，字母与数量由代码保证。"""
    choices = [str(c).strip() for c in (choices or [])]
    count = max(int(min_items or 0), len(choices))
    lines: list[str] = []
    for i in range(count):
        desc = choices[i] if i < len(choices) else ""
        lines.append(f"> **{_choice_label(i)}.** {desc}".rstrip())
    return "\n".join(lines)


def render_details(summary: str, content: str = "") -> str:
    """渲染并强制闭合 `<details><summary>…</summary>…</details>`。"""
    body = (content or "").strip()
    if not body:
        return f"<details><summary>{summary}</summary></details>"
    return f"<details><summary>{summary}</summary>\n{body}\n</details>"


def render_heading(text: str, *, level: int = 1) -> str:
    """渲染 markdown 章节标题。"""
    level = max(1, min(6, int(level or 1)))
    return f"{'#' * level} {(text or '').strip()}".rstrip()


def _details_summary(section: SectionContract, summary: str | None) -> str:
    if summary:
        return summary
    # backend_log/hidden_plot 的 marker 即 summary 关键词（见 extractor._full_document_sections）。
    return section.marker or section.name


def render_section(
    section: SectionContract,
    *,
    text: str = "",
    choices: list[str] | None = None,
    summary: str | None = None,
) -> str:
    """按 section.kind 渲染单个受控区块的最终结构。

    `narrative` 直出正文（无外壳）；`html_block` / `literal_block` 优先用世界书原文
    确定性提取的 `scaffold`，无 scaffold 时回退纯文本，绝不由模型拼最终标签。
    """
    kind = section.kind
    if kind == SectionKind.CHOICE_SET:
        items = choices if choices is not None else _split_choice_lines(text)
        return render_choice_set(items, min_items=section.min_items or 4)
    if kind == SectionKind.DETAILS_SUMMARY:
        return render_details(_details_summary(section, summary), text)
    if kind == SectionKind.MARKDOWN_HEADING:
        return render_heading(text)
    if kind in (SectionKind.HTML_BLOCK, SectionKind.LITERAL_BLOCK):
        return (section.scaffold or text or "").strip()
    # narrative：正文原样返回，永不加外壳。
    return text or ""


def _split_choice_lines(text: str) -> list[str]:
    """把多行文本按行拆成选项描述（去空行），供 text→choices 回退。"""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]
