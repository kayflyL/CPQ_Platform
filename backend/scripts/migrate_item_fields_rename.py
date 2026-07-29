"""一次性迁移：quotation_items 字段去重载 —— part_name/spec → catalogue/description/part_category

语义（与 preview_data_loader 既有展示逻辑对齐，保证迁移后渲染不变）：
  - L6 / 整机:   catalogue=part_name, description=spec,             part_category=NULL
  - Key Parts:   catalogue=COALESCE(NULLIF(spec,''),part_name),     part_category=part_name, description=''
  - Warranty:    catalogue=COALESCE(NULLIF(spec,''),part_name),     part_category=NULL,      description=''
  - 其它/NULL:   catalogue=part_name, description=spec,             part_category=NULL   （L6 兜底）

新增 3 列；旧列 part_name/spec **保留**（ORM 不再声明即忽略，作回滚兜底）。

同时迁移 4 处嵌入了 part_name/spec 键的持久化数据：
  1. opportunities.quotations.extra_fields -> config_l6_picks[*].bom_excel_rows[*]（按行 category 改键）
  2. opportunities.univer_templates.bindings[*].fieldMapping（按 binding 的 region 改键 —— kp_details 换位！）
  3. rules.dynamic_source_fields（l6_details: pn→catalogue/sp→description; kp_details: pn→part_category/sp→catalogue）
  4. rules.business_fields（part_name→catalogue, spec→description）

用法：
  python -X utf8 scripts/migrate_item_fields_rename.py            # dry-run，只打印计数+样本
  python -X utf8 scripts/migrate_item_fields_rename.py --apply    # 事务化执行
幂等：可重复执行（列已存在则跳过，键已改则跳过）。
"""
import sys, json, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
from app.core.config import get_settings


def conn_ctx():
    s = get_settings()
    return psycopg2.connect(
        host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
        user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8",
    )


# ── 行级改键（适用于 items 行与 bom_excel_rows 行，按 category 决定）──────────────
def remap_row_keys(row: dict) -> dict:
    """原地按 category 把 part_name/spec 改写为 catalogue/description/part_category。
    保留旧键（回滚兜底）；若无 part_name/spec 键则不动（已迁移过）。"""
    if not isinstance(row, dict):
        return row
    if "part_name" not in row and "spec" not in row:
        return row  # 已迁移
    pn = row.get("part_name") or ""
    sp = row.get("spec") or ""
    cat = (row.get("category") or "").strip()
    if cat in ("L6", "整机") or not cat:
        catalogue, description, part_category = pn, sp, None
    elif cat == "Key Parts":
        catalogue = sp or pn
        description = ""
        part_category = pn or None
    elif cat == "Warranty":
        catalogue = sp or pn
        description = ""
        part_category = None
    else:
        catalogue, description, part_category = pn, sp, None
    row["catalogue"] = catalogue
    row["description"] = description
    if part_category is not None:
        row["part_category"] = part_category
    return row


# ── fieldMapping 改键（按 binding region；kp_details 换位）──────────────────────────
def remap_field_mapping(fm: dict, region: str) -> dict:
    if not isinstance(fm, dict) or not region:
        return fm
    if region in ("l6_details", "warranty_details"):
        keymap = {"part_name": "catalogue", "spec": "description"}
    elif region == "kp_details":
        keymap = {"part_name": "part_category", "spec": "catalogue"}
    else:
        return fm  # config_summary 等不含这两个键
    changed = False
    new_fm = {}
    for k, v in fm.items():
        if k in keymap:
            new_fm[keymap[k]] = v
            changed = True
        else:
            new_fm[k] = v
    return new_fm if changed else fm


def migrate(cur, apply: bool):
    stats = {}

    # ── 1. 加列 ─────────────────────────────────────────────────────────────────
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='opportunities' AND table_name='quotation_items'
    """)
    existing = {r[0] for r in cur.fetchall()}
    for col in ("catalogue", "description", "part_category"):
        if col not in existing:
            if apply:
                cur.execute(f"ALTER TABLE opportunities.quotation_items ADD COLUMN {col} VARCHAR")
            print(f"  [1] ADD COLUMN quotation_items.{col}")
        else:
            print(f"  [1] (skip) quotation_items.{col} already exists")
    stats["add_columns"] = 3 - sum(c in existing for c in ("catalogue", "description", "part_category"))

    # ── 2. 回填 items（SQL CASE，原子）─────────────────────────────────────────
    if "catalogue" in existing:
        cur.execute("SELECT COUNT(*) FROM opportunities.quotation_items WHERE catalogue IS NULL")
        pending = cur.fetchone()[0]
    else:
        # 列还没加（dry-run 首跑）—— 全表都是待回填
        cur.execute("SELECT COUNT(*) FROM opportunities.quotation_items")
        pending = cur.fetchone()[0]
    print(f"  [2] items rows to backfill (catalogue IS NULL): {pending}")
    stats["items_backfill"] = pending
    if apply and pending:
        cur.execute("""
            UPDATE opportunities.quotation_items SET
              catalogue = CASE
                WHEN category IN ('L6','整机') OR category IS NULL THEN COALESCE(part_name,'')
                ELSE COALESCE(NULLIF(spec,''), part_name, '')
              END,
              description = CASE
                WHEN category IN ('L6','整机') OR category IS NULL THEN COALESCE(spec,'')
                ELSE ''
              END,
              part_category = CASE
                WHEN category = 'Key Parts' THEN part_name
                ELSE NULL
              END
            WHERE catalogue IS NULL
        """)

    # ── 3. quotations.extra_fields bom_excel_rows ───────────────────────────────
    cur.execute("""
        SELECT quotation_id, extra_fields FROM opportunities.quotations
        WHERE extra_fields IS NOT NULL AND extra_fields::text LIKE '%bom_excel_rows%'
    """)
    quo_rows = cur.fetchall()
    quo_changed = 0
    for qid, ef in quo_rows:
        extra = json.loads(ef) if isinstance(ef, str) else ef
        if not isinstance(extra, dict):
            continue
        picks = extra.get("config_l6_picks") or {}
        row_touched = False
        for cfg, p in picks.items():
            if not isinstance(p, dict):
                continue
            exrows = p.get("bom_excel_rows")
            if not isinstance(exrows, list):
                continue
            for r in exrows:
                if not isinstance(r, dict):
                    continue
                had = ("part_name" in r or "spec" in r)
                remap_row_keys(r)
                if had:
                    row_touched = True
        if row_touched:
            quo_changed += 1
            if apply:
                cur.execute(
                    "UPDATE opportunities.quotations SET extra_fields=%s WHERE quotation_id=%s",
                    (json.dumps(extra, ensure_ascii=False), qid),
                )
    print(f"  [3] quotations.extra_fields with bom_excel_rows needing remap: {quo_changed}")
    stats["quotations_extra"] = quo_changed

    # ── 4. univer_templates.bindings[*].fieldMapping ────────────────────────────
    cur.execute("SELECT id, name, bindings FROM opportunities.univer_templates")
    tpl_rows = cur.fetchall()
    tpl_changed = 0
    for tid, name, b in tpl_rows:
        bindings = json.loads(b) if isinstance(b, str) else (b or [])
        if not isinstance(bindings, list):
            continue
        touched = False
        for binding in bindings:
            if not isinstance(binding, dict) or binding.get("dataType") != "dynamic":
                continue
            region = binding.get("regionFieldKey") or binding.get("fieldKey")
            fm = binding.get("fieldMapping")
            new_fm = remap_field_mapping(fm, region)
            if new_fm is not fm:
                binding["fieldMapping"] = new_fm
                touched = True
        if touched:
            tpl_changed += 1
            if apply:
                cur.execute(
                    "UPDATE opportunities.univer_templates SET bindings=%s WHERE id=%s",
                    (json.dumps(bindings, ensure_ascii=False), tid),
                )
    print(f"  [4] univer_templates with dynamic fieldMapping needing remap: {tpl_changed}")
    stats["templates"] = tpl_changed

    # ── 5. rules.dynamic_source_fields（按 source_key 区分）──────────────────────
    # 先删 l6/kp 预存的 config 级 'description' 字段(label='描述')——它原先把 config_descriptions
    # 注入到每个 item 行(与 config_summary.description 重复),且与 spec→description 改名后撞键。
    # 用 field_label='描述' 精确识别,绝不误删从 spec 改名而来的(label='规格')那行。幂等。
    if apply:
        cur.execute("""
            DELETE FROM rules.dynamic_source_fields
            WHERE source_key IN ('l6_details','kp_details')
              AND field_key='description' AND field_label='描述'
        """)
        dsf_deleted = cur.rowcount
    else:
        cur.execute("""
            SELECT COUNT(*) FROM rules.dynamic_source_fields
            WHERE source_key IN ('l6_details','kp_details')
              AND field_key='description' AND field_label='描述'
        """)
        dsf_deleted = cur.fetchone()[0]
    print(f"  [5a] dynamic_source_fields config-level '描述' rows to delete: {dsf_deleted}")

    dsf_changed = 0
    if apply:
        cur.execute("""
            UPDATE rules.dynamic_source_fields SET field_key='catalogue'
            WHERE source_key='l6_details' AND field_key='part_name'
        """); dsf_changed += cur.rowcount
        cur.execute("""
            UPDATE rules.dynamic_source_fields SET field_key='description'
            WHERE source_key='l6_details' AND field_key='spec'
        """); dsf_changed += cur.rowcount
        cur.execute("""
            UPDATE rules.dynamic_source_fields SET field_key='part_category'
            WHERE source_key='kp_details' AND field_key='part_name'
        """); dsf_changed += cur.rowcount
        cur.execute("""
            UPDATE rules.dynamic_source_fields SET field_key='catalogue'
            WHERE source_key='kp_details' AND field_key='spec'
        """); dsf_changed += cur.rowcount
    else:
        cur.execute("""
            SELECT source_key, field_key FROM rules.dynamic_source_fields
            WHERE (source_key='l6_details' AND field_key IN ('part_name','spec'))
               OR (source_key='kp_details' AND field_key IN ('part_name','spec'))
        """)
        dsf_changed = len(cur.fetchall())
    print(f"  [5b] dynamic_source_fields rows to rename: {dsf_changed}")
    stats["dsf"] = dsf_changed

    # ── 6. rules.business_fields（列名是 key，非 field_key）─────────────────────
    bf_changed = 0
    if apply:
        cur.execute("""
            UPDATE rules.business_fields SET key='catalogue', source_column='catalogue'
            WHERE key='part_name'
        """); bf_changed += cur.rowcount
        cur.execute("""
            UPDATE rules.business_fields SET key='description', source_column='description'
            WHERE key='spec'
        """); bf_changed += cur.rowcount
    else:
        cur.execute("SELECT COUNT(*) FROM rules.business_fields WHERE key IN ('part_name','spec')")
        bf_changed = cur.fetchone()[0]
    print(f"  [6] business_fields rows to rename: {bf_changed}")
    stats["bf"] = bf_changed

    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际执行（默认 dry-run）")
    args = ap.parse_args()

    print(f"=== migrate_item_fields_rename {'APPLY' if args.apply else 'DRY-RUN'} ===")
    conn = conn_ctx()
    try:
        cur = conn.cursor()
        stats = migrate(cur, apply=args.apply)
        if args.apply:
            conn.commit()
            print("\n✅ COMMITTED")
        else:
            conn.rollback()
            print("\n⚪ DRY-RUN (rolled back, nothing written) — re-run with --apply to commit")
        print("summary:", stats)
    except Exception as e:
        conn.rollback()
        print(f"\n❌ ERROR (rolled back): {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
