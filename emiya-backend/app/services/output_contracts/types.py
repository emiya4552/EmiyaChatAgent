# -*- coding: utf-8 -*-
"""可见输出契约的数据结构。

契约描述用户最终能看到的 assistant 回复结构；它只做识别、提示和校验，
不执行角色卡脚本，也不参与 MVU 状态更新。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class OutputContractMode:
    """可见输出契约支持的模式。"""

    NONE = "none"
    APPEND_TAIL = "append_tail"
    FULL_DOCUMENT = "full_document"


@dataclass(frozen=True)
class ContractSource:
    """契约规则的来源世界书条目。"""

    uid: str | int | None = None
    comment: str = ""
    worldbook_id: str | None = None
    worldbook_name: str = ""


@dataclass(frozen=True)
class TailBlockContract:
    """期望出现在可见回复尾部的结构块。"""

    marker: str
    content: str = ""
    summary: str = ""
    placement: str = "tail"
    once: bool = True
    order: int = 100
    template_type: str = "tail_html"
    abstract: dict[str, Any] | None = None
    repairable: bool = True
    source: ContractSource | None = None


@dataclass(frozen=True)
class SectionContract:
    """整篇结构模式中必须出现的章节。"""

    name: str
    marker: str = ""
    required: bool = True
    order: int = 0
    source: ContractSource | None = None


@dataclass(frozen=True)
class ForbiddenTermRule:
    """可见回复某个范围内不允许出现的词。"""

    term: str
    scope: str = "visible"
    source: ContractSource | None = None


@dataclass(frozen=True)
class VisibleOutputContract:
    """单轮回复编译出的可见输出契约。"""

    mode: str = OutputContractMode.NONE
    required_tail_blocks: list[TailBlockContract] = field(default_factory=list)
    required_sections: list[SectionContract] = field(default_factory=list)
    forbidden_terms: list[ForbiddenTermRule] = field(default_factory=list)
    source_entries: list[ContractSource] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.mode != OutputContractMode.NONE


@dataclass(frozen=True)
class ContractDiagnostics:
    """可见输出契约的校验结果。"""

    mode: str
    ok: bool
    required: int = 0
    missing: list[dict[str, Any]] = field(default_factory=list)
    invalid_order: list[dict[str, Any]] = field(default_factory=list)
    forbidden_hits: list[dict[str, Any]] = field(default_factory=list)
    repaired: bool = False
    repair_mode: str | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)
