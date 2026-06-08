"""rename article_url, keyword, collection_log to t_ prefix

Revision ID: c9d1e2f3a4b5
Revises: b1c2d3e4f5a6
Create Date: 2026-06-08

"""
from alembic import op

revision = 'c9d1e2f3a4b5'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table('article_url',    't_article_url')
    op.rename_table('keyword',        't_keyword')
    op.rename_table('collection_log', 't_collection_log')


def downgrade() -> None:
    op.rename_table('t_article_url',   'article_url')
    op.rename_table('t_keyword',       'keyword')
    op.rename_table('t_collection_log', 'collection_log')
