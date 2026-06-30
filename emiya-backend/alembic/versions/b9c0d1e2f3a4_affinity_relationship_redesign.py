"""redesign relationships for affinity system: add affinity_score, affinity_history, user_persona_id; drop conversation_id; merge old records

Revision ID: b9c0d1e2f3a4
Revises: a7b8c9d0e1f2
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b9c0d1e2f3a4'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 新增列
    op.add_column('relationships',
        sa.Column('affinity_score', sa.Float(), nullable=True))
    op.add_column('relationships',
        sa.Column('affinity_history', postgresql.JSONB(), nullable=True))
    op.add_column('relationships',
        sa.Column('user_persona_id', postgresql.UUID(), nullable=True))

    # 2. 创建 user_persona_id 外键
    op.create_foreign_key(
        'fk_relationship_user_persona',
        'relationships', 'personas',
        ['user_persona_id'], ['id'],
        ondelete='SET NULL',
    )

    # 3. 初始化 affinity_score = 已有 intimacy_score
    op.execute("UPDATE relationships SET affinity_score = intimacy_score WHERE affinity_score IS NULL")

    # 4. 初始化 affinity_history 为空数组
    op.execute("UPDATE relationships SET affinity_history = '[]'::jsonb WHERE affinity_history IS NULL")

    # 5. 合并同一 (user_id, persona_id) 的旧记录（去掉 conversation_id 维度）
    # 按 (user_id, persona_id) 分组，保留第一条，合并其他记录的数据后删除
    op.execute("""
        WITH merged AS (
            SELECT
                user_id,
                persona_id,
                MAX(affinity_score) AS max_affinity,
                MAX(intimacy_score) AS max_intimacy,
                SUM(total_messages) AS sum_messages,
                SUM(deep_talk_count) AS sum_deep_talk,
                MIN(first_interaction) AS min_first,
                MAX(last_interaction) AS max_last,
                (ARRAY_AGG(id ORDER BY created_at ASC))[1] AS keep_id
            FROM relationships
            GROUP BY user_id, persona_id
            HAVING COUNT(*) > 1
        )
        UPDATE relationships r
        SET
            affinity_score = m.max_affinity,
            intimacy_score = m.max_intimacy,
            total_messages = m.sum_messages,
            deep_talk_count = m.sum_deep_talk,
            first_interaction = m.min_first,
            last_interaction = m.max_last
        FROM merged m
        WHERE r.id = m.keep_id
    """)

    # 删除被合并的旧记录
    op.execute("""
        DELETE FROM relationships
        WHERE id IN (
            SELECT r.id FROM relationships r
            JOIN (
                SELECT user_id, persona_id, (ARRAY_AGG(id ORDER BY created_at ASC))[1] AS keep_id
                FROM relationships
                GROUP BY user_id, persona_id
                HAVING COUNT(*) > 1
            ) grp ON r.user_id = grp.user_id
                   AND r.persona_id IS NOT DISTINCT FROM grp.persona_id
                   AND r.id != grp.keep_id
        )
    """)

    # 6. 删除旧唯一约束
    op.drop_constraint('uq_relationship_user_persona_conv', 'relationships', type_='unique')

    # 7. 删除 conversation_id 列
    op.drop_constraint('relationships_conversation_id_fkey', 'relationships', type_='foreignkey')
    op.drop_column('relationships', 'conversation_id')

    # 8. 创建新唯一约束（NULLS NOT DISTINCT 确保多行 NULL user_persona 不会重复）
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_relationship_user_upersona_persona
        ON relationships (user_id, user_persona_id, persona_id)
        NULLS NOT DISTINCT
    """)

    # 9. affinity_score 和 intimacy_score 设为 NOT NULL
    op.alter_column('relationships', 'affinity_score', nullable=False, server_default='0')
    op.alter_column('relationships', 'intimacy_score', nullable=False, server_default='0')


def downgrade() -> None:
    # 回退：恢复 conversation_id 列和旧约束（数据无法完全恢复）
    op.add_column('relationships',
        sa.Column('conversation_id', postgresql.UUID(), nullable=True))
    op.create_foreign_key(
        'relationships_conversation_id_fkey',
        'relationships', 'conversations',
        ['conversation_id'], ['id'],
        ondelete='SET NULL',
    )

    op.execute("DROP INDEX IF EXISTS uq_relationship_user_upersona_persona")
    op.create_unique_constraint(
        'uq_relationship_user_persona_conv',
        'relationships',
        ['user_id', 'persona_id', 'conversation_id'],
    )

    op.drop_constraint('fk_relationship_user_persona', 'relationships', type_='foreignkey')
    op.drop_column('relationships', 'user_persona_id')
    op.drop_column('relationships', 'affinity_history')
    op.drop_column('relationships', 'affinity_score')
