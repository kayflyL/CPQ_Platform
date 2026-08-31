# -*- coding: utf-8 -*-
"""数据边界=AI 角色的权限系统（2026-08-29 步骤1）。

宪法：
- 单一事实源：价格可见性只由 data_boundary 说了算。price_access 布尔是编辑糖——
  入参可以传布尔（API/前端开关），落库前一律折算进 data_boundary，读侧派生返回；
- 默认拒绝：没有 data_boundary 的角色什么都读不了（含价格）；
- 物理强制：校验+只读事务在执行层（execute_read），提示词只描述不承诺；
- 纯 AI 层：不碰外层账户系统的价格遮罩（price_mask），外层权限归外层管。

敏感盘点（2026-08-29 实库扫描 information_schema）：
  kp.kp_records.price, kp.kp_price_history.price, l6.l6_records.price,
  l6.parts_master.unit_price, l6.l6_psu_options.unit_price,
  l6.l6_rear_panel_items.unit_price, l6_history.l6_price_history.price,
  opportunities.quotations.{total_price,l6_price,cost_snapshot,profit_margin},
  opportunities.quotation_items.{base_price,final_price,profit_margin},
  rules.bom_cases.price_snapshot
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

MODE_DENY_ALL = "deny_all"
MODE_ALLOW_READ = "allow_read"
PRICE_DOMAIN = "price"

DEFAULT_BOUNDARY: dict = {
    "mode": MODE_DENY_ALL,
    "schemas": [],
    "tables_allow": [],
    "masked_fields": [PRICE_DOMAIN],
}

# 价格域列模式（masked_fields 含 "price" 时全部命中脱敏）
_PRICE_COL_RE = re.compile(r"(?:^|_)(?:price|cost|margin|profit)(?:$|_)", re.IGNORECASE)

# SQL 校验：只读白名单外的关键词（大小写不敏感，词边界匹配）
_FORBIDDEN_SQL_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|vacuum|"
    r"analyze|call|do|execute|merge|replace|set|reindex|cluster|listen|notify|load|"
    r"pg_sleep|pg_read_file|pg_read_binary_file|pg_ls_dir|pg_terminate_backend|"
    r"dblink|lo_import|lo_export)\b",
    re.IGNORECASE,
)
_MULTI_STMT_CHARS = (";", "$$")
_COMMENT_MARKERS = ("--", "/*", "*/")
_WITH_CTE_RE = re.compile(r"\bwith\s+recursive\b", re.IGNORECASE)
# CTE 定义名（WITH a AS (...) [, b AS (...)]）：FROM/JOIN 引用它不是查物理表
_CTE_DEF_RE = re.compile(r"\b([A-Za-z_]\w*)\s+as\s*\(", re.IGNORECASE)
_FROM_JOIN_RE = re.compile(
    r"\b(?:from|join)\s+((?:\"[^\"]+\"|[A-Za-z_][\w$]*)\s*\.\s*)?(\"[^\"]+\"|[A-Za-z_][\w$]*)",
    re.IGNORECASE,
)

MAX_ROWS_HARD_CAP = 200
DEFAULT_TIMEOUT_SECONDS = 8.0


# ── 归一化与派生 ─────────────────────────────────────────────────────────────

def normalize_boundary(source: Any, *, price_access: Optional[bool] = None) -> dict:
    """归一化 data_boundary。

    优先级：source 里的 data_boundary dict > price_access 布尔 > 默认拒绝。
    price_access=True → allow_read 不脱敏价格；False/None → deny_all 屏蔽价格域。
    """
    raw = None
    if isinstance(source, dict):
        raw = source.get("data_boundary")
        if price_access is None:
            price_access = source.get("price_access")
    if isinstance(raw, dict):
        mode = str(raw.get("mode") or "").strip()
        if mode not in (MODE_ALLOW_READ, MODE_DENY_ALL):
            mode = MODE_DENY_ALL
        return {
            "mode": mode,
            "schemas": _str_list(raw.get("schemas")),
            "tables_allow": _str_list(raw.get("tables_allow")),
            "masked_fields": _str_list(raw.get("masked_fields")),
        }
    if price_access is True:
        return {"mode": MODE_ALLOW_READ, "schemas": [], "tables_allow": [], "masked_fields": []}
    return dict(DEFAULT_BOUNDARY)


def boundary_price_ok(boundary: dict) -> bool:
    """价格可见性唯一判定：读权限开启且价格域未屏蔽。"""
    if not isinstance(boundary, dict) or boundary.get("mode") != MODE_ALLOW_READ:
        return False
    masked = {str(m).strip().lower() for m in boundary.get("masked_fields") or []}
    return PRICE_DOMAIN not in masked and "*" not in masked


def colleague_price_ok(colleague: Any) -> bool:
    """同事级便捷入口：skill_chat / 引擎上下文统一从这里取价格可见性。"""
    return boundary_price_ok(normalize_boundary(colleague))


_RETIRED_COLLEAGUE_KEYS = ("memory", "mood", "schedule", "preferences", "permission_policy")
_RELATION_KEEP_KEYS = ("team_role", "reports_to")


def normalize_colleague(colleague: Any) -> dict:
    """读侧归一化：确保 data_boundary 物理存在，price_access 永远是派生值。

    存量配置无 data_boundary 时从旧 price_access 布尔懒迁移（随下次配置写盘固化）。
    同时静默剥离已退役的死键（memory/mood/schedule/preferences 及其派生），
    DB 存量 JSON 无需刷库即可在前端消失。
    """
    if not isinstance(colleague, dict):
        return colleague
    for key in _RETIRED_COLLEAGUE_KEYS:
        colleague.pop(key, None)
    relations = colleague.get("relations")
    if isinstance(relations, dict):
        colleague["relations"] = {k: v for k, v in relations.items() if k in _RELATION_KEEP_KEYS}
    policy = colleague.get("memory_policy")
    if isinstance(policy, dict):
        policy.pop("long_term_store", None)
    boundary = normalize_boundary(colleague)
    colleague["data_boundary"] = boundary
    colleague["price_access"] = boundary_price_ok(boundary)
    return colleague


def apply_price_access(boundary: dict, allow: bool) -> dict:
    """编辑糖：价格开关折算进边界（保留已有表白名单，只动价格域）。"""
    base = normalize_boundary({"data_boundary": boundary}) if isinstance(boundary, dict) \
        else dict(DEFAULT_BOUNDARY)
    masked = [m for m in base.get("masked_fields") or [] if m.lower() != PRICE_DOMAIN]
    if not allow:
        masked = [PRICE_DOMAIN] + masked
        return {**base, "masked_fields": masked}
    # 开价格必然要读模式（白名单不动，deny→allow 只解锁白名单本身）
    return {**base, "mode": MODE_ALLOW_READ, "masked_fields": masked}


def _str_list(value: Any) -> list:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


# ── 读取校验（物理执行前的第一道门）─────────────────────────────────────────

def _extract_tables(sql: str) -> list:
    """提取 FROM/JOIN 后的表引用，返回 [(schema|None, table)]（CTE 名不算物理表）。"""
    cte_names = {m.group(1).lower() for m in _CTE_DEF_RE.finditer(sql)}
    tables = []
    for match in _FROM_JOIN_RE.finditer(sql):
        schema, table = match.group(1), match.group(2)
        if schema:
            schema = schema.strip().strip('"').rstrip(".")
        table = table.strip('"')
        # FROM 子句里跟在表名后的常见非表 token
        if table.lower() in ("select", "lateral", "unnest", "values", "only"):
            continue
        if table.lower() in cte_names:
            continue
        tables.append((schema or None, table))
    return tables


def _table_allowed(schema: Optional[str], table: str, boundary: dict) -> bool:
    s = (schema or "").lower()
    # 自带地图：information_schema 纯元数据恒放行；显式 pg_catalog 拒绝
    if s == "information_schema":
        return True
    if s == "pg_catalog":
        return False
    schemas = {str(x).lower() for x in boundary.get("schemas") or []}
    if s in schemas:
        return True
    allowed_tables = {str(t).lower() for t in boundary.get("tables_allow") or []}
    if f"{s}.{table.lower()}" in allowed_tables:
        return True
    # 裸表名（无 schema 前缀）：白名单里存在唯一同名后缀才放行（fail closed）
    if schema is None:
        matches = [t for t in allowed_tables if t.endswith(f".{table.lower()}")]
        if len(matches) == 1:
            return True
    return False


def validate_read_sql(sql: str, boundary: dict) -> dict:
    """SELECT-only 严格校验。返回 {ok, error, tables}——物理执行前的必经关口。"""
    if not isinstance(sql, str) or not sql.strip():
        return {"ok": False, "error": "SQL 为空", "tables": []}
    text = sql.strip()
    for marker in _COMMENT_MARKERS:
        if marker in text:
            return {"ok": False, "error": f"不允许注释（{marker}）", "tables": []}
    if "$" in text:
        return {"ok": False, "error": "不允许 $ 引号/占位符", "tables": []}
    if ";" in text.rstrip().rstrip(";"):
        return {"ok": False, "error": "不允许多语句", "tables": []}
    first = re.match(r"\s*(\w+)", text)
    if not first or first.group(1).lower() not in ("select", "with"):
        return {"ok": False, "error": "只允许 SELECT 查询", "tables": []}
    forbidden = _FORBIDDEN_SQL_RE.search(text)
    if forbidden:
        return {"ok": False, "error": f"禁用关键词：{forbidden.group(1)}", "tables": []}
    if _WITH_CTE_RE.search(text):
        return {"ok": False, "error": "不允许 WITH RECURSIVE", "tables": []}
    if not isinstance(boundary, dict) or boundary.get("mode") != MODE_ALLOW_READ:
        return {"ok": False, "error": "数据边界为拒绝模式（deny_all），无读取权限", "tables": []}
    tables = _extract_tables(text)
    for schema, table in tables:
        if not _table_allowed(schema, table, boundary):
            shown = f"{schema}.{table}" if schema else table
            return {"ok": False,
                    "error": f"表 {shown} 不在数据边界白名单内（可用 information_schema.tables/columns 查看可读范围）",
                    "tables": tables}
    return {"ok": True, "error": "", "tables": tables}


def _wrap_with_limit(sql: str, limit: int) -> str:
    cap = max(1, min(int(limit), MAX_ROWS_HARD_CAP))
    inner = sql.strip().rstrip(";").strip()
    return f"SELECT * FROM ({inner}) AS _boundary_sub LIMIT {cap}"


def _masked_column_indices(columns: Iterable[str], boundary: dict) -> set:
    masked = {str(m).strip().lower() for m in (boundary or {}).get("masked_fields") or []}
    if not masked:
        return set()
    drop = set()
    for i, col in enumerate(columns):
        name = str(col or "").strip().lower()
        qualified = name.split(".")[-1]
        if "*" in masked or PRICE_DOMAIN in masked and _PRICE_COL_RE.search(qualified):
            drop.add(i)
            continue
        if name in masked or any(name == m.split(".")[-1] and "." in m for m in masked):
            drop.add(i)
    return drop


# ── 只读执行（第二道门：只读事务+超时+截断+脱敏）─────────────────────────────

def execute_read(sql: str, boundary: dict, *, limit: int = 50,
                 timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
                 engine=None) -> dict:
    """在只读事务里执行白名单 SELECT；错误原样返回（上层回传模型自纠）。"""
    check = validate_read_sql(sql, boundary)
    if not check["ok"]:
        return {"ok": False, "error": check["error"], "columns": [], "rows": [], "row_count": 0}
    if engine is None:
        from app.models.base import engine as base_engine
        engine = base_engine
    wrapped = _wrap_with_limit(sql, limit)
    cap = max(1, min(int(limit), MAX_ROWS_HARD_CAP))
    from sqlalchemy import text as _text
    try:
        with engine.connect() as conn:
            conn.execute(_text("SET TRANSACTION READ ONLY"))
            conn.execute(_text(f"SET LOCAL statement_timeout = {int(timeout_seconds * 1000)}"))
            result = conn.execute(_text(wrapped))
            columns = list(result.keys())
            rows = [list(r) for r in result.fetchmany(cap + 1)]
            truncated = len(rows) > cap
            rows = rows[:cap]
    except Exception as exc:  # noqa: BLE001 —— SQL/数据库错误一律转结果对象，由模型自纠
        return {"ok": False, "error": f"查询执行失败：{exc}", "columns": [], "rows": [], "row_count": 0}
    drop = _masked_column_indices(columns, boundary)
    if drop:
        keep = [i for i in range(len(columns)) if i not in drop]
        columns = [columns[i] for i in keep]
        rows = [[r[i] for i in keep] for r in rows]
    # 行值序列化（datetime/Decimal 等转字符串，JSON 化给模型）
    rows = [[_jsonable(v) for v in r] for r in rows]
    return {"ok": True, "error": "", "columns": columns, "rows": rows,
            "row_count": len(rows), "truncated": truncated}


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)
