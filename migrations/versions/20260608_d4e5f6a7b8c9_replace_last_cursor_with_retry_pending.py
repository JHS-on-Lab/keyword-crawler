"""replace last_cursor with retry_pending

Revision ID: d4e5f6a7b8c9
Revises: c9d1e2f3a4b5
Create Date: 2026-06-08

last_cursor(VARCHAR) 는 실제 커서 값이 아닌 재시도 여부 flag 로만 쓰이므로
retry_pending(TINYINT) 으로 교체한다.
"""

from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c9d1e2f3a4b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        't_keyword',
        sa.Column(
            'retry_pending',
            sa.SmallInteger(),
            nullable=False,
            server_default='0',
            comment='다음 수집 시 full scan 필요 여부. 수집 중단(403 등) 시 1, 성공 완료 시 0',
        ),
    )
    # last_cursor 가 non-NULL 이던 행은 retry_pending=1 로 마이그레이션
    op.execute("UPDATE t_keyword SET retry_pending = 1 WHERE last_cursor IS NOT NULL")
    op.drop_column('t_keyword', 'last_cursor')


def downgrade() -> None:
    op.add_column(
        't_keyword',
        sa.Column('last_cursor', sa.String(512), nullable=True,
                  comment='페이지네이션 재개용 커서. 403 실패 시 저장, 성공 완료 시 NULL 리셋'),
    )
    op.execute("UPDATE t_keyword SET last_cursor = 'retry' WHERE retry_pending = 1")
    op.drop_column('t_keyword', 'retry_pending')
