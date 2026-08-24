"""一次性回填：把 opportunities 旧列 platform_type/chassis_form/purchase_qty 迁入需求单 slots。

原则：
1. 只补 slots 中缺失/为空的字段，不覆盖需求单里已有的值；
2. 有需求记录则更新最新一条；没有则创建一条 current 快照；
3. 不处理 flow.current_node，商机详情打开时会按现有逻辑自愈创建流程。
"""
import json

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main() -> None:
    engine = create_engine(get_settings().DATABASE_URL)
    with engine.begin() as c:
        opps = c.execute(text("""
            select opportunity_id, platform_type, chassis_form, purchase_qty, extra_fields
            from opportunities.opportunities
            where coalesce(platform_type, '') <> ''
               or coalesce(chassis_form, '') <> ''
               or coalesce(purchase_qty, 0) <> 0
               or coalesce(extra_fields::json ->> 'warranty_years', '') <> ''
            order by opportunity_id
        """)).mappings().all()

        updated = 0
        created = 0
        skipped = 0
        for o in opps:
            oid = o["opportunity_id"]
            row = c.execute(text("""
                select id, slots, status
                from opportunities.opportunity_requirements
                where opportunity_id = :oid
                order by case status when 'current' then 0 when 'draft' then 1 else 2 end,
                         version desc
                limit 1
            """), {"oid": oid}).mappings().first()

            slots = {}
            if row and isinstance(row["slots"], dict):
                slots = dict(row["slots"])
            elif row and isinstance(row["slots"], str):
                try:
                    slots = json.loads(row["slots"]) or {}
                except Exception:
                    slots = {}

            changed = False
            for key, col in (("platform_type", "platform_type"), ("chassis_form", "chassis_form")):
                old = o[col]
                if old and not slots.get(key):
                    slots[key] = old
                    changed = True
            old_qty = o["purchase_qty"]
            if old_qty and not slots.get("purchase_qty"):
                slots["purchase_qty"] = int(old_qty)
                changed = True
            if o["extra_fields"]:
                try:
                    extra = json.loads(o["extra_fields"])
                    old_warranty = extra.get("warranty_years")
                    if old_warranty and not slots.get("warranty_years"):
                        slots["warranty_years"] = str(old_warranty)
                        changed = True
                except (json.JSONDecodeError, TypeError):
                    pass

            if not changed:
                skipped += 1
                continue

            if row:
                c.execute(text("""
                    update opportunities.opportunity_requirements
                    set slots = :slots, status = 'current'
                    where id = :id
                """), {"slots": json.dumps(slots, ensure_ascii=False), "id": row["id"]})
                updated += 1
            else:
                c.execute(text("""
                    insert into opportunities.opportunity_requirements
                        (opportunity_id, version, slots, requirement_text, status, created_by, created_at)
                    values (:oid, 1, :slots, '', 'current', 'migration', now())
                """), {"oid": oid, "slots": json.dumps(slots, ensure_ascii=False)})
                created += 1

        print(f"migrated updated={updated} created={created} skipped={skipped}")


if __name__ == "__main__":
    main()
