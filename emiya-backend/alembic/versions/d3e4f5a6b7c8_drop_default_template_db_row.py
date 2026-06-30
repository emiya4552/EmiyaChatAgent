"""drop persisted default template row

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-28

默认模板从 DB 持久化资源改为代码常量（DEFAULT_TEMPLATE_BLOCKS）：
- 删除 is_default=True 的所有行
- ON DELETE SET NULL 自动把 conversations.template_id 置 NULL
- nodes.py::node_build_prompt 在 conv.template_id is None 时直接用代码常量

is_default 列保留（无新代码读它，但删列代价不值；保留可作为未来扩展点）
"""
from typing import Sequence, Union
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 删 is_default=True 的所有行；conversations.template_id FK 是 ON DELETE
    # SET NULL（见 c2d3e4f5a6b7 之前已建立），引用方自动置 NULL
    op.execute("DELETE FROM prompt_templates WHERE is_default = TRUE")


def downgrade() -> None:
    # 不可逆：默认模板内容存在代码里，下次启动按需手动复制
    pass
