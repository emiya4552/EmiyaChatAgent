# -*- coding: utf-8 -*-
"""世界书 Pydantic schemas。"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ─── 单条 entry ───


class WorldbookEntry(BaseModel):
    """单条世界书条目。

    字段约定见 docs/adr/0001 / CONTEXT.md。
    """

    uid: int = Field(..., description="书内自增 ID")
    comment: str = Field("", description="条目名称 / 备注")
    enabled: bool = True
    content: str = Field(..., description="注入到 Prompt 的实际文本")

    # 触发
    constant: bool = False
    # v3 spec: true=按关键词激活；false=历史上等同 constant，ST 实际不强制 gate（仅持久化保留语义）
    selective: bool = False
    # v3 spec: true 时 key/keysecondary 元素整体当 JS 正则解释（无需 /…/flags 包裹）
    use_regex: bool = False
    key: list[str] = Field(default_factory=list, description="主关键词；元素可为 /pattern/flags 正则")
    keysecondary: list[str] = Field(default_factory=list)
    selective_logic: int = Field(0, description="0=AND_ANY 1=NOT_ALL 2=NOT_ANY 3=AND_ALL")
    scan_depth: int | None = None
    case_sensitive: bool | None = None
    match_whole_words: bool | None = None

    # 定位
    position: int = Field(0, ge=0, le=7, description="0-7 对齐 ST 8 个位置")
    depth: int = 4
    order: int = 100
    role: str = Field("system", description="system/user/assistant")

    # 预算
    ignore_budget: bool = False

    # outlet
    outlet_name: str | None = None

    # 绑定在 entry 上的输出契约 Attachment；读取时兼容旧版平铺对象。
    output_contract: dict | None = None

    # 兜底字段
    extras: dict = Field(default_factory=dict, description="ST 未支持字段原样保留")


# ─── 世界书本体 ───


class WorldbookBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    scan_depth: int = 2
    case_sensitive: bool = False
    match_whole_words: bool = False


class WorldbookCreateRequest(WorldbookBase):
    entries: list[WorldbookEntry] = Field(default_factory=list)
    extensions: dict = Field(default_factory=dict)


class WorldbookUpdateRequest(BaseModel):
    """局部更新；任一字段缺失则不变。"""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    scan_depth: int | None = None
    case_sensitive: bool | None = None
    match_whole_words: bool | None = None
    entries: list[WorldbookEntry] | None = None
    extensions: dict | None = None


class WorldbookResponse(WorldbookBase):
    id: UUID
    user_id: UUID | None = None
    entries: list[WorldbookEntry]
    extensions: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorldbookListItem(BaseModel):
    """列表页用的精简表示，不带 entries 详情。"""

    id: UUID
    user_id: UUID | None = None
    name: str
    description: str | None = None
    entry_count: int
    is_template: bool  # user_id is None
    created_at: datetime
    updated_at: datetime


# ─── 输出契约声明 / canonical section（ADR-2b）───


class CanonicalSectionItem(BaseModel):
    """canonical section 注册表项，供前端“输出模板编辑器”列出可选区块。"""

    name: str
    label: str
    kind: str
    marker: str
    order: int


class OutputContractDeclareRequest(BaseModel):
    """用户显式声明单条 entry 的输出模板（→ source=manual, reviewed=true）。"""

    mode: str = Field("full_document", pattern="^(full_document|append_tail|none)$")
    section_names: list[str] = Field(
        default_factory=list, description="选中的 canonical section 有序列表（full_document 用）"
    )


class OutputContractUpdateRequest(BaseModel):
    """更新 entry 的契约定义或启用状态。

    definition 由后端 canonicalizer 收敛为受控 v2 schema；客户端不能直接写入
    provenance 与 lifecycle，避免伪造识别来源或确认状态。
    """

    definition: dict | None = None
    enabled: bool | None = None


# ─── 对话上的世界书绑定 / AN 更新 ───


class WorldbookBindingUpdate(BaseModel):
    worldbook_ids: list[UUID]


class AuthorNoteUpdate(BaseModel):
    author_note: str | None = None
    an_depth: int | None = Field(None, ge=0, le=100)
    an_role: str | None = Field(None, pattern="^(system|user|assistant)$")
    an_interval: int | None = Field(None, ge=1)
