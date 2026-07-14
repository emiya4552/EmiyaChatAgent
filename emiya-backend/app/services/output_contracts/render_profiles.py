# -*- coding: utf-8 -*-
"""可见输出契约的受控渲染能力注册表。"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.output_contracts.types import SectionKind, SpanStrategy


@dataclass(frozen=True)
class RenderProfile:
    """一个前端已验证可安全渲染、后端可确定性处理的结构集合。"""

    name: str
    supported_kinds: frozenset[str]
    supported_spans: frozenset[str]

    def supports(self, *, kind: str, span_strategy: str) -> bool:
        return kind in self.supported_kinds and span_strategy in self.supported_spans


DEFAULT_RENDER_PROFILE = "default-v1"

RENDER_PROFILES: dict[str, RenderProfile] = {
    DEFAULT_RENDER_PROFILE: RenderProfile(
        name=DEFAULT_RENDER_PROFILE,
        supported_kinds=frozenset({
            SectionKind.MARKDOWN_HEADING,
            SectionKind.NARRATIVE,
            SectionKind.CHOICE_SET,
            SectionKind.DETAILS_SUMMARY,
        }),
        supported_spans=frozenset({
            SpanStrategy.BALANCED_TAG,
            SpanStrategy.FIXED_LINE_SET,
            SpanStrategy.UNTIL_NEXT_ANCHOR,
            SpanStrategy.NONE,
        }),
    ),
}


def get_render_profile(name: str | None) -> RenderProfile:
    """返回已发布 Profile；未知值安全回退到默认配置。"""
    return RENDER_PROFILES.get(str(name or ""), RENDER_PROFILES[DEFAULT_RENDER_PROFILE])
