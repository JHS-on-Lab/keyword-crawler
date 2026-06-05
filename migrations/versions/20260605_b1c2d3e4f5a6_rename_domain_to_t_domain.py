"""rename domain to t_domain

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-06-05

"""
from alembic import op

revision = 'b1c2d3e4f5a6'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table('domain', 't_domain')


def downgrade() -> None:
    op.rename_table('t_domain', 'domain')
