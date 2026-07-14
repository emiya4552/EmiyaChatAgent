# -*- coding: utf-8 -*-
"""canonical section 注册表 + LLM abstract 规范化（ADR-2a）。

LLM 识别 full_document / inline 时，`abstract.sections` 的 name/marker 是自由文本
（常见中文名，例如 uid=13 的 ["章节号","正文","选项区块","后台日志","隐藏剧情"]，
且两个 <details> 常给同一个 marker "<details>"）。而 compiler 的受控映射
`_NAME_TO_KIND` 与 validator 的 `_SECTION_DETECTORS` 都按英文 canonical name
（chapter/body/options/backend_log/hidden_plot）工作，中文 name 匹配不上就退化成
narrative / diagnose_only，影响校验、修复与 strict 渲染。

本模块是 canonical section 的**单一定义源**，把自由 section 规范化为 canonical：
命中的用标准 name/marker/order 覆盖（丢弃 LLM 的乱 marker，两个 details 因此得到
不同 marker），未命中的原样保留（自定义 section → 下游 diagnose_only 降级）。
规范化在识别期为主（detector 写入前）、运行期兜底（extractor 消费旧数据）。

注册表的值以现有 5 处硬编码为准填充（detector 启发式 `_full_document`、
extractor._full_document_sections、compiler._NAME_TO_KIND、
validator._SECTION_DETECTORS、prompt/diagnostics labels）。本模块**不强迁**那些实现
（ADR-2a 决策：不强迁 5 处），只保证 name 对齐 canonical 后它们各自继续正确工作。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.output_contracts.types import SectionKind


@dataclass(frozen=True)
class CanonicalSection:
    name: str
    kind: str
    marker: str
    order: int
    aliases: tuple[str, ...]
    summary_keyword: str = ""   # details_summary 的 <summary> 关键词（定位 / 渲染）
    label: str = ""             # 中文展示名


# 单一定义源。aliases 用较完整的词，避免“隐藏 / 后台”单字误判；匹配取最长命中。
CANONICAL_SECTIONS: tuple[CanonicalSection, ...] = (
    CanonicalSection(
        "chapter", SectionKind.MARKDOWN_HEADING, "#", 10,
        aliases=("章节标题", "章节号", "章节", "chapter"), label="章节标题",
    ),
    CanonicalSection(
        "body", SectionKind.NARRATIVE, "", 20,
        aliases=("正文", "body"), label="正文",
    ),
    CanonicalSection(
        "options", SectionKind.CHOICE_SET, "> **A.**", 30,
        aliases=("选项区块", "选项", "options"), label="选项区块",
    ),
    CanonicalSection(
        "backend_log", SectionKind.DETAILS_SUMMARY, "后台日志", 40,
        aliases=("后台日志", "backend_log"), summary_keyword="后台日志", label="后台日志",
    ),
    CanonicalSection(
        "hidden_plot", SectionKind.DETAILS_SUMMARY, "隐藏剧情", 50,
        aliases=("隐藏剧情", "hidden_plot"), summary_keyword="隐藏剧情", label="隐藏剧情",
    ),
)

_BY_NAME: dict[str, CanonicalSection] = {cs.name: cs for cs in CANONICAL_SECTIONS}


def get_canonical(name: str) -> CanonicalSection | None:
    return _BY_NAME.get(name)


def match_canonical(*probes: str) -> CanonicalSection | None:
    """在若干文本线索（name / marker / summary）里找**最长命中别名**对应的 canonical。

    取最长命中别名，减少“隐藏 / 后台”这类短词误判；全不命中返回 None（自定义 section）。
    """
    text = " ".join(p for p in probes if p).lower()
    if not text.strip():
        return None
    best: CanonicalSection | None = None
    best_len = 0
    for cs in CANONICAL_SECTIONS:
        for alias in cs.aliases:
            if len(alias) > best_len and alias.lower() in text:
                best, best_len = cs, len(alias)
    return best


# 注：早期 ADR-2a 的 normalize_sections / normalize_abstract 已被 v2 Attachment 层的
# attachment.canonicalize_sections 取代（更完整：补 locator/span_strategy/capability），
# 故移除。本模块只保留 canonical 注册表与匹配原语，供 attachment 与 detector 复用。
