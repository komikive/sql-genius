"""AST-based SQL safety gate (SELECT-only; rejects mutations and multi-statement batches)."""

from __future__ import annotations

import sqlglot
from sqlglot import exp


class SqlSafetyService:
    """集中式 SQL 安全门：仅允许单条 SELECT，拒绝 DML/DDL 与多语句。

    调用方：
    - Agent 工具 execute_query
    - REST POST /api/v1/execution/run（Workbench 手工执行）
    """

    _FORBIDDEN = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.TruncateTable,
        exp.Merge,
        exp.Alter,
        exp.Command,
    )

    @classmethod
    def validate(cls, sql: str) -> tuple[bool, str]:
        """返回 (是否通过, 原因码)。通过时 reason 为 ok。"""
        text = (sql or "").strip()
        if not text:
            return False, "empty_sql"

        # 兼容 Postgres / MySQL 方言解析；二者任一成功即可
        statements: list[exp.Expression] | None = None
        last_exc: Exception | None = None
        for dialect in ("postgres", "mysql"):
            try:
                statements = sqlglot.parse(text, dialect=dialect)
                break
            except Exception as exc:  # pragma: no cover - dialect-specific parse failures
                last_exc = exc
                statements = None
        if statements is None:
            return False, f"parse_error:{last_exc.__class__.__name__ if last_exc else 'unknown'}"

        if len(statements) != 1:
            return False, "multiple_statements"

        stmt = statements[0]
        # 遍历 AST，禁止任何变更类节点（含子查询内的 DELETE 等）
        for node in stmt.walk():
            if isinstance(node, cls._FORBIDDEN):
                return False, "mutation_or_ddl_forbidden"

        if stmt.find(exp.Select) is None:
            return False, "no_select"

        return True, "ok"
