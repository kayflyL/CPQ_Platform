# -*- coding: utf-8 -*-
"""数据边界（步骤1）单测：归一化/价格派生/编辑糖 + SQL 校验各拒绝路径 + 只读执行器。

宪法断言：价格可见性只由 data_boundary 说了算；默认拒绝；物理校验先于执行。
"""
from app.services.data_boundary import (
    DEFAULT_BOUNDARY,
    apply_price_access,
    boundary_price_ok,
    colleague_price_ok,
    execute_read,
    normalize_boundary,
    normalize_colleague,
    validate_read_sql,
)

ALLOW = {"mode": "allow_read", "schemas": [], "tables_allow": ["kp.kp_records"],
         "masked_fields": []}


# ── 归一化与派生 ─────────────────────────────────────────────────────────────

def test_default_deny_when_nothing_configured():
    b = normalize_boundary({})
    assert b["mode"] == "deny_all"
    assert boundary_price_ok(b) is False
    assert colleague_price_ok({}) is False
    assert colleague_price_ok(None) is False


def test_legacy_price_access_true_migrates_to_readable():
    b = normalize_boundary({"price_access": True})
    assert b["mode"] == "allow_read"
    assert b["masked_fields"] == []
    assert boundary_price_ok(b) is True


def test_legacy_price_access_false_masks_price():
    b = normalize_boundary({"price_access": False})
    assert b["mode"] == "deny_all"
    assert "price" in b["masked_fields"]
    assert boundary_price_ok(b) is False


def test_boundary_dict_wins_over_legacy_bool():
    """边界 dict 是事实源：bool 与它冲突时以 dict 为准。"""
    b = normalize_boundary({"price_access": True,
                            "data_boundary": {"mode": "allow_read", "masked_fields": ["price"]}})
    assert boundary_price_ok(b) is False


def test_normalize_colleague_sets_derived_flag():
    c = normalize_colleague({"role_key": "assistant", "price_access": True})
    assert c["price_access"] is True and c["data_boundary"]["mode"] == "allow_read"
    c2 = normalize_colleague({"role_key": "x"})  # 无任何配置 → 默认拒绝
    assert c2["price_access"] is False and c2["data_boundary"]["mode"] == "deny_all"


def test_apply_price_access_keeps_table_grants():
    base = {"mode": "allow_read", "schemas": ["kp"], "tables_allow": ["l6.parts_master"],
            "masked_fields": []}
    off = apply_price_access(base, False)
    assert boundary_price_ok(off) is False
    assert off["schemas"] == ["kp"] and off["tables_allow"] == ["l6.parts_master"]  # 白名单不动
    on = apply_price_access(off, True)
    assert boundary_price_ok(on) is True and on["mode"] == "allow_read"


# ── SQL 校验 ─────────────────────────────────────────────────────────────────

def test_deny_all_rejects_everything():
    out = validate_read_sql("SELECT 1", normalize_boundary({}))
    assert out["ok"] is False


def test_non_select_rejected():
    for sql in ("INSERT INTO kp.kp_records VALUES (1)", "UPDATE kp.kp_records SET price=1",
                "DELETE FROM kp.kp_records", "DROP TABLE kp.kp_records",
                "TRUNCATE kp.kp_records"):
        assert validate_read_sql(sql, ALLOW)["ok"] is False, sql


def test_whitelisted_table_passes():
    out = validate_read_sql("SELECT part_number FROM kp.kp_records WHERE qty > 2", ALLOW)
    assert out["ok"] is True


def test_non_whitelisted_table_rejected():
    out = validate_read_sql("SELECT * FROM opportunities.quotations", ALLOW)
    assert out["ok"] is False and "白名单" in out["error"]


def test_schema_grant_allows_all_tables_in_schema():
    b = {"mode": "allow_read", "schemas": ["l6"], "tables_allow": [], "masked_fields": []}
    assert validate_read_sql("SELECT * FROM l6.parts_master", b)["ok"] is True
    assert validate_read_sql("SELECT * FROM l6.l6_records", b)["ok"] is True
    assert validate_read_sql("SELECT * FROM kp.kp_records", b)["ok"] is False  # 其他 schema 仍拒


def test_bare_table_name_needs_unique_whitelist_match():
    assert validate_read_sql("SELECT * FROM kp_records", ALLOW)["ok"] is True   # 唯一后缀命中
    two = {**ALLOW, "tables_allow": ["kp.kp_records", "l6.kp_records"]}
    assert validate_read_sql("SELECT * FROM kp_records", two)["ok"] is False    # 歧义拒绝


def test_information_schema_is_self_map():
    assert validate_read_sql(
        "SELECT table_schema, table_name FROM information_schema.tables", ALLOW)["ok"] is True
    assert validate_read_sql(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'kp_records'",
        ALLOW)["ok"] is True


def test_pg_catalog_and_unknown_schema_denied():
    assert validate_read_sql("SELECT * FROM pg_catalog.pg_tables", ALLOW)["ok"] is False
    assert validate_read_sql("SELECT * FROM pg_tables", ALLOW)["ok"] is False


def test_multi_statement_comments_dollar_rejected():
    for sql in ("SELECT 1; SELECT 2", "SELECT 1 -- comment", "SELECT /*x*/ 1",
                "SELECT $$foo$$"):
        assert validate_read_sql(sql, ALLOW)["ok"] is False, sql
    # 单条语句的收尾分号无害（执行前会被剥掉）
    assert validate_read_sql("SELECT 1;", ALLOW)["ok"] is True


def test_forbidden_keywords_rejected():
    for sql in ("SELECT pg_sleep(10)", "SELECT * FROM kp.kp_records LIMIT 1; SET x=1",
                "SELECT copy_from_dummy FROM kp.kp_records"):
        # copy_from_dummy 是合法列名——词边界匹配只打真关键词
        if "copy_from_dummy" in sql:
            assert validate_read_sql(sql, ALLOW)["ok"] is True
        else:
            assert validate_read_sql(sql, ALLOW)["ok"] is False, sql


def test_cte_allowed_but_recursive_rejected():
    assert validate_read_sql(
        "WITH t AS (SELECT 1 AS x) SELECT * FROM t", ALLOW)["ok"] is True
    assert validate_read_sql(
        "WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM t) SELECT * FROM t",
        ALLOW)["ok"] is False


# ── 只读执行器（假引擎）──────────────────────────────────────────────────────

class _FakeResult:
    def __init__(self, columns, rows):
        self._columns, self._rows = columns, rows

    def keys(self):
        return self._columns

    def fetchmany(self, n):
        return self._rows[:n]


class _FakeConn:
    def __init__(self, result=None, executed=None):
        self.result, self.executed = result, executed or []

    def execute(self, stmt):
        self.executed.append(str(stmt))
        return self.result

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeEngine:
    def __init__(self, result):
        self.conn = _FakeConn(result)
        self.result = result

    def connect(self):
        self.conn = _FakeConn(self.result, self.conn.executed)
        return self.conn


def test_execute_read_validates_first():
    eng = _FakeEngine(None)
    out = execute_read("DELETE FROM kp.kp_records", ALLOW, engine=eng)
    assert out["ok"] is False and out["rows"] == []


def test_execute_read_masks_price_columns():
    eng = _FakeEngine(_FakeResult(
        ["part_number", "price", "qty"],
        [["GPU-001", 1980.0, 2], ["NIC-002", 450.0, 4]]))
    b = {**ALLOW, "masked_fields": ["price"]}
    out = execute_read("SELECT part_number, price, qty FROM kp.kp_records", b, engine=eng)
    assert out["ok"] is True
    assert out["columns"] == ["part_number", "qty"]
    assert all("price" not in str(r) and "1980" not in str(r) for r in out["rows"])


def test_execute_read_caps_rows_and_wraps_limit():
    rows = [[i] for i in range(500)]
    eng = _FakeEngine(_FakeResult(["n"], rows))
    out = execute_read("SELECT n FROM kp.kp_records", ALLOW, limit=50, engine=eng)
    assert out["ok"] is True and out["row_count"] == 50
    wrapped = eng.conn.executed[-1]
    assert wrapped.startswith("SELECT * FROM (") and wrapped.endswith("LIMIT 50")


def test_execute_read_sets_readonly_transaction_and_timeout():
    eng = _FakeEngine(_FakeResult(["n"], [[1]]))
    execute_read("SELECT n FROM kp.kp_records", ALLOW, engine=eng, timeout_seconds=5)
    stmts = eng.conn.executed
    assert "SET TRANSACTION READ ONLY" in stmts
    assert any("statement_timeout" in s and "5000" in s for s in stmts)


def test_execute_read_wraps_db_errors_as_result():
    class _Boom:
        def connect(self):
            raise RuntimeError("connection refused")

    out = execute_read("SELECT 1", ALLOW, engine=_Boom())
    assert out["ok"] is False and "connection refused" in out["error"]
