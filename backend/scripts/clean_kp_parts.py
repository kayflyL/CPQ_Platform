"""KP 配件库安全去重脚本。

只处理「名称归一后完全相同」的重复配件（忽略大小写、空格、连字符、标点）：
- 保留信息最完整的一条作为 canonical
- 把重复件的规格、价格历史、兼容机型合并到 canonical
- 删除重复件及其语义索引
- 默认 dry-run，加 --apply 才真正写库
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime

import psycopg2
from _localdb import db_password  # 2026-09-14 安全加固：密码不再硬编码


DSN = {
    "host": "localhost",
    "dbname": "cpq_platform",
    "user": "postgres",
    "password": db_password(),
}


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value)


def fetch_parts(cur) -> list[dict]:
    cur.execute(
        """
        select id, category_id, oem_sku, alt_sku, brand, name, short_desc, full_desc,
               condition, lead_time, image_url, datasheet_url, moq, applicable
        from kp.kp_parts
        order by id
        """
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def child_counts(cur, part_id: int) -> dict:
    counts = {}
    for table, col in [
        ("kp.kp_part_specs", "part_id"),
        ("kp.kp_price_history", "part_id"),
        ("kp.kp_part_compat", "part_id"),
    ]:
        cur.execute(f"select count(*) from {table} where {col} = %s", (part_id,))
        counts[table] = cur.fetchone()[0]
    return counts


def choose_canonical(ids: list[int], parts_by_id: dict[int, dict], counts_by_id: dict[int, dict]) -> int:
    def score(pid: int) -> tuple:
        p = parts_by_id[pid]
        c = counts_by_id[pid]
        completeness = 0
        for key in ("brand", "oem_sku", "alt_sku", "short_desc", "full_desc", "image_url", "datasheet_url"):
            if p.get(key):
                completeness += 1
        if p.get("applicable") is not None:
            completeness += 1
        weighted = completeness + c["kp.kp_part_specs"] * 2 + c["kp.kp_part_compat"] * 2 + c["kp.kp_price_history"]
        # 优先旧 id，避免误删长期使用的主数据
        return weighted, -pid

    return max(ids, key=score)


def merge_fields(canonical: dict, duplicate: dict) -> bool:
    changed = False
    for key in (
        "brand", "oem_sku", "alt_sku", "short_desc", "full_desc",
        "condition", "lead_time", "image_url", "datasheet_url",
    ):
        if not canonical.get(key) and duplicate.get(key):
            canonical[key] = duplicate[key]
            changed = True
    if canonical.get("moq") in (None, 0) and duplicate.get("moq"):
        canonical["moq"] = duplicate["moq"]
        changed = True
    if canonical.get("applicable") is None and duplicate.get("applicable") is not None:
        canonical["applicable"] = duplicate["applicable"]
        changed = True
    if canonical.get("category_id") is None and duplicate.get("category_id") is not None:
        canonical["category_id"] = duplicate["category_id"]
        changed = True
    return changed


def write_canonical(cur, part: dict) -> None:
    applicable_json = (
        json.dumps(part["applicable"], ensure_ascii=False)
        if part.get("applicable") is not None
        else None
    )
    cur.execute(
        """
        update kp.kp_parts
        set category_id = %s, oem_sku = %s, alt_sku = %s, brand = %s, name = %s,
            short_desc = %s, full_desc = %s, condition = %s, lead_time = %s,
            image_url = %s, datasheet_url = %s, moq = %s, applicable = %s,
            updated_at = %s
        where id = %s
        """,
        (
            part.get("category_id"),
            part.get("oem_sku"),
            part.get("alt_sku"),
            part.get("brand"),
            part.get("name"),
            part.get("short_desc"),
            part.get("full_desc"),
            part.get("condition"),
            part.get("lead_time"),
            part.get("image_url"),
            part.get("datasheet_url"),
            part.get("moq"),
            applicable_json,
            datetime.now(),
            part["id"],
        ),
    )


def merge_specs(cur, canonical_id: int, duplicate_id: int) -> None:
    cur.execute(
        """
        insert into kp.kp_part_specs (part_id, spec_key, spec_value, sort_order)
        select %s, d.spec_key, d.spec_value, d.sort_order
        from kp.kp_part_specs d
        where d.part_id = %s
          and not exists (
              select 1
              from kp.kp_part_specs c
              where c.part_id = %s
                and c.spec_key = d.spec_key
          )
        """,
        (canonical_id, duplicate_id, canonical_id),
    )
    cur.execute("delete from kp.kp_part_specs where part_id = %s", (duplicate_id,))


def merge_compat(cur, canonical_id: int, duplicate_id: int) -> None:
    cur.execute(
        """
        insert into kp.kp_part_compat (part_id, server_model)
        select %s, server_model
        from kp.kp_part_compat
        where part_id = %s
        on conflict (part_id, server_model) do nothing
        """,
        (canonical_id, duplicate_id),
    )
    cur.execute("delete from kp.kp_part_compat where part_id = %s", (duplicate_id,))


def merge_history(cur, canonical_id: int, duplicate_id: int) -> None:
    cur.execute(
        "update kp.kp_price_history set part_id = %s where part_id = %s",
        (canonical_id, duplicate_id),
    )


def merge_related(cur, canonical_id: int, duplicate_id: int) -> None:
    cur.execute(
        "update kp.kp_part_related set source_part_id = %s where source_part_id = %s",
        (canonical_id, duplicate_id),
    )
    cur.execute(
        "update kp.kp_part_related set target_part_id = %s where target_part_id = %s",
        (canonical_id, duplicate_id),
    )
    cur.execute(
        "delete from kp.kp_part_related where source_part_id = target_part_id"
    )


def drop_search_index(cur, duplicate_id: int) -> None:
    cur.execute("delete from kp.kp_part_search_index where part_id = %s", (duplicate_id,))


def drop_part(cur, duplicate_id: int) -> None:
    cur.execute("delete from kp.kp_parts where id = %s", (duplicate_id,))


def backup_affected(cur, duplicate_ids: list[int]) -> None:
    """在写库前把受影响的配件及关联子表备份到 *_bak_20260912。"""
    ids_csv = ",".join(str(pid) for pid in duplicate_ids)
    backups = [
        ("kp.kp_parts", "id", "kp.kp_parts_bak_20260912", "id"),
        ("kp.kp_part_specs", "part_id", "kp.kp_part_specs_bak_20260912", "part_id"),
        ("kp.kp_price_history", "part_id", "kp.kp_price_history_bak_20260912", "part_id"),
        ("kp.kp_part_compat", "part_id", "kp.kp_part_compat_bak_20260912", "part_id"),
        ("kp.kp_part_related", "source_part_id", "kp.kp_part_related_bak_20260912", "source_part_id"),
        ("kp.kp_part_search_index", "part_id", "kp.kp_part_search_index_bak_20260912", "part_id"),
    ]
    for source_table, source_col, backup_table, _backup_col in backups:
        cur.execute(f"drop table if exists {backup_table}")
        if source_table == "kp.kp_part_related":
            cur.execute(
                f"create table {backup_table} as select * from {source_table} "
                f"where source_part_id in ({ids_csv}) or target_part_id in ({ids_csv})"
            )
        else:
            cur.execute(
                f"create table {backup_table} as select * from {source_table} "
                f"where {source_col} in ({ids_csv})"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="真正写入数据库；默认只预览")
    args = parser.parse_args()

    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()
    try:
        parts = fetch_parts(cur)
        parts_by_id = {p["id"]: p for p in parts}
        counts_by_id = {p["id"]: child_counts(cur, p["id"]) for p in parts}

        groups: dict[str, list[int]] = {}
        for p in parts:
            groups.setdefault(normalize_name(p["name"]), []).append(p["id"])

        duplicate_groups = {k: v for k, v in groups.items() if len(v) > 1}
        duplicate_ids = sorted({pid for ids in duplicate_groups.values() for pid in ids})
        print(f"配件总数: {len(parts)}")
        print(f"归一化重复组: {len(duplicate_groups)}")
        print(f"涉及重复配件: {sum(len(v) for v in duplicate_groups.values())}")
        print("模式:", "APPLY" if args.apply else "DRY-RUN")
        print("=" * 80)

        if args.apply:
            backup_affected(cur, duplicate_ids)
            print("已创建备份表: kp.kp_*_bak_20260912")

        total_deleted = 0
        for key in sorted(duplicate_groups, key=lambda k: -len(duplicate_groups[k])):
            ids = sorted(duplicate_groups[key])
            canonical_id = choose_canonical(ids, parts_by_id, counts_by_id)
            duplicate_ids = [pid for pid in ids if pid != canonical_id]
            print(
                f"[{key}] canonical={canonical_id} {parts_by_id[canonical_id]['name']!r} "
                f"duplicates={duplicate_ids}"
            )
            for dup_id in duplicate_ids:
                dup_name = parts_by_id[dup_id]["name"]
                print(f"  - 删除 {dup_id} {dup_name!r}")
                total_deleted += 1
                if args.apply:
                    merge_fields(parts_by_id[canonical_id], parts_by_id[dup_id])
                    write_canonical(cur, parts_by_id[canonical_id])
                    merge_specs(cur, canonical_id, dup_id)
                    merge_compat(cur, canonical_id, dup_id)
                    merge_history(cur, canonical_id, dup_id)
                    merge_related(cur, canonical_id, dup_id)
                    drop_search_index(cur, dup_id)
                    drop_part(cur, dup_id)

        print("=" * 80)
        print("计划删除重复配件:", total_deleted)
        if args.apply:
            conn.commit()
            print("已提交。")
        else:
            conn.rollback()
            print("未写入数据库。确认无误后用 --apply 执行。")
        return 0
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
