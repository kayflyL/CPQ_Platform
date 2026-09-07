# -*- coding: utf-8 -*-
"""一次性归一化 kp_categories：把 GPU card / Raid Card 等零散分类合并到正式分类族。

跑法（backend 目录）：
  ./.venv/Scripts/python.exe -X utf8 scripts/normalize_kp_categories.py
  ./.venv/Scripts/python.exe -X utf8 scripts/normalize_kp_categories.py --commit

说明：
- 只合并 category_family() 能识别的已知分类族变体；未知分类原样保留。
- 配件会迁到正式分类，变体分类下的子分类会重挂到正式分类，再删除空变体。
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.kp import KPCategory, KPPart
from app.repository.kp_repo import KPRepository, canonical_category_name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="实际写库（默认 dry-run）")
    args = parser.parse_args()

    repo = KPRepository()
    session = repo.session
    mode = "COMMIT 写库" if args.commit else "DRY-RUN（不写库）"
    print("===", mode, "===")

    categories = session.query(KPCategory).order_by(KPCategory.id).all()
    canonical_by_name = {cat.name: cat for cat in categories}

    for cat in categories:
        target_name = canonical_category_name(cat.name)
        if target_name == cat.name:
            continue

        part_count = session.query(KPPart).filter(KPPart.category_id == cat.id).count()
        child_count = session.query(KPCategory).filter(KPCategory.parent_id == cat.id).count()
        target = canonical_by_name.get(target_name)

        if target is None:
            if not args.commit:
                print(
                    "[计划] 创建正式分类 %r <- 变体 %r（配件 %s，子分类 %s）"
                    % (target_name, cat.name, part_count, child_count)
                )
                continue
            target = KPCategory(
                name=target_name,
                parent_id=cat.parent_id,
                icon=cat.icon,
                sort_order=cat.sort_order,
                description=cat.description,
            )
            session.add(target)
            session.flush()
            canonical_by_name[target.name] = target

        if args.commit:
            label = "[执行] %r -> %r：迁移配件 %s，重挂子分类 %s"
        else:
            label = "[计划] %r -> %r：迁移配件 %s，重挂子分类 %s"
        print(label % (cat.name, target.name, part_count, child_count))

        if args.commit:
            session.query(KPPart).filter(KPPart.category_id == cat.id).update(
                {KPPart.category_id: target.id}, synchronize_session=False
            )
            session.query(KPCategory).filter(KPCategory.parent_id == cat.id).update(
                {KPCategory.parent_id: target.id}, synchronize_session=False
            )
            session.delete(cat)

    if args.commit:
        session.commit()
        print("\n[已写库] 分类归一化完成")
    else:
        print("\n[dry-run] 未写库；确认无误后加 --commit 执行")

    repo.close()


if __name__ == "__main__":
    main()
