from app.sql.execution import _apply_statement_timeout, run_bounded_select


def test_run_bounded_select_stops_fetching_after_limit() -> None:
    result = run_bounded_select(
        "sqlite://",
        "SELECT 1 AS value UNION ALL SELECT 2 UNION ALL SELECT 3",
        max_rows=2,
        timeout_ms=1_000,
    )

    assert result.rows == [{"value": 1}, {"value": 2}]
    assert result.truncated is True

    exact = run_bounded_select(
        "sqlite://",
        "SELECT 1 AS value UNION ALL SELECT 2",
        max_rows=2,
        timeout_ms=1_000,
    )
    assert exact.truncated is False


def test_statement_timeout_uses_database_native_setting() -> None:
    statements: list[str] = []
    connection = type(
        "Connection",
        (),
        {
            "dialect": type("Dialect", (), {"name": "postgresql"})(),
            "exec_driver_sql": statements.append,
        },
    )()

    _apply_statement_timeout(connection, 12_345)

    assert statements == ["SET LOCAL statement_timeout = 12345"]
