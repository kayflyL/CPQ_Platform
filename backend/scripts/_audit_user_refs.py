# -*- coding: utf-8 -*-
"""只读盘点：opportunities.feed_users 每个账号在全库的引用点与数量。

动态扫 information_schema 找引用列（*_user_id / sales_person / operator / uploader_name /
created_by / sender_name / assignees JSON），再按账号计数。不写任何数据。
跑法：cd backend && ./.venv/Scripts/python.exe -X utf8 scripts/_audit_user_refs.py
"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from sqlalchemy import text
from app.models.base import engine

USER_ID_EXACT = {"user_id", "owner_user_id", "assignee_user_id", "uploader_user_id",
                 "recipient_user_id", "sender_user_id", "approver_user_id", "operator_user_id"}
NAME_COLS = {"sales_person", "operator", "uploader_name", "created_by", "sender_name"}
SKIP_SCHEMAS = {"pg_catalog", "information_schema"}


def main():
    with engine.connect() as conn:
        cols = conn.execute(text("""
            SELECT table_schema, table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
              AND (column_name IN ('user_id', 'owner_user_id', 'assignee_user_id',
                                   'uploader_user_id', 'recipient_user_id', 'sender_user_id',
                                   'approver_user_id', 'operator_user_id',
                                   'sales_person', 'operator', 'uploader_name',
                                   'created_by', 'sender_name')
                   OR column_name = 'assignees')
            ORDER BY table_schema, table_name
        """)).fetchall()

        users = conn.execute(text(
            "SELECT user_id, name, role, is_active FROM opportunities.feed_users ORDER BY name"
        )).fetchall()

    uid_cols, name_cols, json_cols = [], [], []
    for schema, table, col, dtype in cols:
        key = (schema, table, col)
        if col == "assignees":
            json_cols.append(key)
        elif col in USER_ID_EXACT or col.endswith("_user_id"):
            (uid_cols if dtype in ("character varying", "text", "character") else uid_cols).append(key)
        else:
            name_cols.append(key)

    print(f"引用列发现：user_id 类 {len(uid_cols)} 个、姓名类 {len(name_cols)} 个、assignees JSON {len(json_cols)} 个")
    for key in uid_cols:
        print("  uid:", ".".join(key))
    for key in name_cols:
        print("  name:", ".".join(key))
    for key in json_cols:
        print("  json:", ".".join(key))

    # assignees JSON 预取（opportunities 域唯一）
    assignee_rows = []
    for schema, table, col in json_cols:
        with engine.connect() as conn:
            rows = conn.execute(text(
                f"SELECT opportunity_id, {col} FROM {schema}.{table}"
            )).fetchall()
        assignee_rows.append(((schema, table, col), rows))

    print("\n==== 每账号引用计数 ====")
    report = []
    for uid, name, role, active in users:
        refs = {}
        for schema, table, col in uid_cols:
            with engine.connect() as conn:
                n = conn.execute(text(
                    f"SELECT count(*) FROM {schema}.{table} WHERE {col} = :v"
                ), {"v": uid}).scalar()
            if n:
                refs[f"{schema}.{table}.{col}"] = n
        for schema, table, col in name_cols:
            with engine.connect() as conn:
                n = conn.execute(text(
                    f"SELECT count(*) FROM {schema}.{table} WHERE {col} = :v"
                ), {"v": name}).scalar()
            if n:
                refs[f"{schema}.{table}.{col}(名)"] = n
        for (schema, table, col), rows in assignee_rows:
            n = 0
            for _, data in rows:
                if not isinstance(data, dict):
                    continue
                for v in (data or {}).values():
                    vals = v if isinstance(v, list) else [v]
                    if any(isinstance(x, str) and (x == uid or x == name) for x in vals):
                        n += 1
            if n:
                refs[f"{schema}.{table}.{col}(指派)"] = n
        total = sum(refs.values())
        report.append((name, uid, role, active, total, refs))

    for name, uid, role, active, total, refs in sorted(report, key=lambda r: r[4]):
        flag = "停用" if not active else "活跃"
        print(f"\n■ {name}  [{role}] {flag}  uid={uid[:8]}…  引用合计 {total}")
        if not refs:
            print("   （零引用——可直接删除）")
        for k, v in sorted(refs.items(), key=lambda kv: -kv[1]):
            print(f"   {v:>5}  {k}")

    print("\n==== 汇总 ====")
    zero = [r[0] for r in report if r[4] == 0]
    print(f"零引用可直接删：{len(zero)} 个 → {zero}")
    owned = [(r[0], r[5].get('opportunities.opportunities.owner_user_id', 0)) for r in report]
    print("有商机归属需转接：", [(n, c) for n, c in owned if c])


if __name__ == "__main__":
    main()
