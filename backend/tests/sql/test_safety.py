from app.sql.safety import SqlSafetyService


def test_select_ok():
    ok, reason = SqlSafetyService.validate("SELECT 1 AS one")
    assert ok is True
    assert reason == "ok"


def test_insert_rejected():
    ok, reason = SqlSafetyService.validate("INSERT INTO t VALUES (1)")
    assert ok is False


def test_multistatement_rejected():
    ok, reason = SqlSafetyService.validate("SELECT 1; SELECT 2")
    assert ok is False
