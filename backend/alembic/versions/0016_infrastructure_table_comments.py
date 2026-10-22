"""add comments for infrastructure and legacy local tables

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.models.schema_comments import SCHEMA_COMMENTS

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

INFRASTRUCTURE_OR_LEGACY_TABLES = {
    "alembic_version",
    "checkpoint_blobs",
    "checkpoint_migrations",
    "checkpoint_writes",
    "checkpoints",
}


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _comment_sql(
    bind: sa.engine.Connection,
    *,
    table_name: str,
    column_name: str | None,
    comment: str | None,
) -> str:
    preparer = bind.dialect.identifier_preparer
    table_ref = preparer.quote(table_name)
    comment_sql = "NULL" if comment is None else _quote_literal(comment)
    if column_name is None:
        return f"COMMENT ON TABLE {table_ref} IS {comment_sql}"
    column_ref = preparer.quote(column_name)
    return f"COMMENT ON COLUMN {table_ref}.{column_ref} IS {comment_sql}"


def _apply_comments(*, clear: bool = False) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    existing_columns = {
        table_name: {column["name"] for column in inspector.get_columns(table_name)}
        for table_name in existing_tables
        if table_name in INFRASTRUCTURE_OR_LEGACY_TABLES
    }

    for table_name in sorted(INFRASTRUCTURE_OR_LEGACY_TABLES):
        if table_name not in existing_tables:
            continue
        table_comments = SCHEMA_COMMENTS.get(table_name)
        if not isinstance(table_comments, dict):
            continue
        table_comment = None if clear else str(table_comments.get("table") or "")
        bind.exec_driver_sql(
            _comment_sql(bind, table_name=table_name, column_name=None, comment=table_comment)
        )
        columns = table_comments.get("columns")
        if not isinstance(columns, dict):
            continue
        for column_name, comment in columns.items():
            if column_name not in existing_columns[table_name]:
                continue
            bind.exec_driver_sql(
                _comment_sql(
                    bind,
                    table_name=table_name,
                    column_name=column_name,
                    comment=None if clear else str(comment),
                )
            )


def upgrade() -> None:
    _apply_comments(clear=False)


def downgrade() -> None:
    _apply_comments(clear=True)
