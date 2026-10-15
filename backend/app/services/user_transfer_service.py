# -*- coding: utf-8 -*-
"""用户删除/合并的引用转接服务。

功能性引用（删号前必须转接，否则商机/流程/通知悬空）：
- opportunities.opportunities.owner_user_id / sales_person（姓名列，与 owner 配对）
- opportunities.opportunity_flows.assignees（JSON：值可能是 uid 或 legacy 姓名串）
- opportunities.notifications.user_id（收件人）
- rules.colleague_memories.user_id（公共域记忆归属）

历史留痕（刻意不转接）：created_by / operator 等姓名快照、attachments.uploader_user_id、
llm_trace.user_id、*_bak_rename0917 备份表——它们是「谁在什么时候做的」事实记录，
改写反而破坏审计语义；删号后以原样保留。
"""
import json
import logging
from typing import Optional

from sqlalchemy import text

from app.models.base import engine

logger = logging.getLogger(__name__)

# 功能性引用表（user_id 直存）
_FUNCTIONAL_UID_TABLES = (
    ("opportunities", "opportunities", "owner_user_id"),
    ("opportunities", "notifications", "user_id"),
    ("rules", "colleague_memories", "user_id"),
)


def _fetch_user(uid: str) -> Optional[dict]:
    from app.repository.feed_user_repo import FeedUserRepository
    repo = FeedUserRepository()
    try:
        return repo.get(uid)
    finally:
        repo.close()


def count_references(uid: str) -> dict:
    """删号确认弹窗数据：功能性引用必须转接，历史留痕仅展示。"""
    user = _fetch_user(uid)
    name = (user or {}).get("name") or ""
    out = {"functional": {}, "historical": {}}
    with engine.connect() as conn:
        for schema, table, col in _FUNCTIONAL_UID_TABLES:
            n = conn.execute(text(
                f"SELECT count(*) FROM {schema}.{table} WHERE {col} = :v"), {"v": uid}).scalar()
            if n:
                out["functional"][f"{schema}.{table}.{col}"] = int(n)
        n = conn.execute(text(
            "SELECT count(*) FROM opportunities.opportunities WHERE sales_person = :v"), {"v": name}).scalar()
        if n:
            out["functional"]["opportunities.opportunities.sales_person"] = int(n)
        # assignees：逐行解析 JSON（值=uid 或 legacy 姓名，单值或列表）
        flows = conn.execute(text(
            "SELECT opportunity_id, assignees FROM opportunities.opportunity_flows")).fetchall()
        n = 0
        for _, data in flows:
            if not isinstance(data, dict):
                continue
            for v in (data or {}).values():
                vals = v if isinstance(v, list) else [v]
                if any(isinstance(x, str) and x in (uid, name) for x in vals):
                    n += 1
        if n:
            out["functional"]["opportunities.opportunity_flows.assignees"] = n
        # 历史留痕（按名/uid 计数，仅展示）
        for schema, table, col, by in (
            ("opportunities", "opportunity_attachments", "uploader_user_id", "uid"),
            ("rules", "llm_trace", "user_id", "uid"),
            ("opportunities", "opportunity_requirements", "created_by", "name"),
            ("opportunities", "opportunity_bom_schemes", "created_by", "name"),
            ("opportunities", "opportunity_cost_sheets", "created_by", "name"),
            ("opportunities", "opportunity_flow_cards", "created_by", "name"),
        ):
            n = conn.execute(text(
                f"SELECT count(*) FROM {schema}.{table} WHERE {col} = :v"),
                {"v": uid if by == "uid" else name}).scalar()
            if n:
                out["historical"][f"{schema}.{table}.{col}"] = int(n)
    return out


def _transfer_assignees(conn, from_uid: str, from_name: str, to_uid: str) -> int:
    rows = conn.execute(text(
        "SELECT opportunity_id, assignees FROM opportunities.opportunity_flows "
        "WHERE assignees::text LIKE :pat"), {"pat": f"%{from_uid}%"}).fetchall()
    rows += conn.execute(text(
        "SELECT opportunity_id, assignees FROM opportunities.opportunity_flows "
        "WHERE assignees::text LIKE :pat AND assignees::text NOT LIKE :pat2"),
        {"pat": f"%{from_name}%", "pat2": f"%{from_uid}%"}).fetchall()
    changed = 0
    seen = set()
    for opp_id, data in rows:
        if opp_id in seen or not isinstance(data, dict):
            continue
        seen.add(opp_id)
        rewritten = False

        def walk(v):
            nonlocal rewritten
            if isinstance(v, list):
                return [walk(x) for x in v]
            if isinstance(v, str) and v in (from_uid, from_name):
                rewritten = True
                return to_uid
            return v

        new_data = {k: walk(v) for k, v in data.items()}
        if rewritten:
            conn.execute(text(
                "UPDATE opportunities.opportunity_flows SET assignees = CAST(:j AS json) "
                "WHERE opportunity_id = :oid"),
                {"j": json.dumps(new_data, ensure_ascii=False), "oid": opp_id})
            changed += 1
    return changed


def transfer_references(conn, from_uid: str, to_uid: str) -> dict:
    """单事务内把 from 的功能性引用全部改挂到 to。返回各项转移条数。"""
    to_user = _fetch_user(to_uid)
    if not to_user:
        raise ValueError("转接目标用户不存在")
    from_user = _fetch_user(from_uid)
    from_name = (from_user or {}).get("name") or ""
    transferred = {}
    for schema, table, col in _FUNCTIONAL_UID_TABLES:
        res = conn.execute(text(
            f"UPDATE {schema}.{table} SET {col} = :to WHERE {col} = :frm"),
            {"to": to_uid, "frm": from_uid})
        if res.rowcount:
            transferred[f"{schema}.{table}.{col}"] = res.rowcount
    res = conn.execute(text(
        "UPDATE opportunities.opportunities SET sales_person = :to_name WHERE sales_person = :frm_name"),
        {"to_name": to_user["name"], "frm_name": from_name})
    if res.rowcount:
        transferred["opportunities.opportunities.sales_person"] = res.rowcount
    n = _transfer_assignees(conn, from_uid, from_name, to_uid)
    if n:
        transferred["opportunities.opportunity_flows.assignees"] = n
    return transferred


def delete_user_with_transfer(from_uid: str, to_uid: Optional[str]) -> dict:
    """转接功能性引用并删除账号（单事务，原子）。返回转移明细。"""
    with engine.begin() as conn:
        transferred = {}
        if to_uid:
            transferred = transfer_references(conn, from_uid, to_uid)
        res = conn.execute(text(
            "DELETE FROM opportunities.feed_users WHERE user_id = :uid"), {"uid": from_uid})
        if not res.rowcount:
            raise ValueError("用户不存在")
    logger.info("user deleted uid=%s transfer_to=%s transferred=%s", from_uid, to_uid, transferred)
    return transferred
