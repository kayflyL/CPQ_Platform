"""一次性迁移/清理脚本：历史报价单 -> BOM/成本流程实体。

用法：
  python backend/scripts/migrate_legacy_flow_artifacts.py --mode backfill [--apply]
  python backend/scripts/migrate_legacy_flow_artifacts.py --mode cleanup [--apply]

默认 dry-run，仅打印将执行的动作；加 --apply 才真正写库。
"""
import argparse

from app.models.base import Opportunity_SessionLocal
from app.models.flow import OpportunityBomScheme, OpportunityCostSheet


def run_backfill(apply: bool) -> None:
    if not apply:
        print("[dry-run] 不执行回填；使用 --apply 实际迁移。")
        return
    from app.core.startup import backfill_bom_schemes_from_quotations
    result = backfill_bom_schemes_from_quotations()
    print(f"legacy backfill done: {result}")


def run_cleanup(apply: bool) -> None:
    db = Opportunity_SessionLocal()
    try:
        legacy_sheets = (
            db.query(OpportunityCostSheet)
            .filter(OpportunityCostSheet.name.like("成本-存量-%"))
            .order_by(OpportunityCostSheet.id.desc())
            .all()
        )
        delete_sheet_ids = []
        delete_scheme_ids = []

        for sheet in legacy_sheets:
            other_sheet = (
                db.query(OpportunityCostSheet)
                .filter(
                    OpportunityCostSheet.opportunity_id == sheet.opportunity_id,
                    OpportunityCostSheet.id != sheet.id,
                    ~OpportunityCostSheet.name.like("成本-存量-%"),
                )
                .first()
            )
            if not other_sheet:
                continue
            delete_sheet_ids.append(sheet.id)
            if sheet.bom_scheme_id:
                scheme = (
                    db.query(OpportunityBomScheme)
                    .filter(OpportunityBomScheme.id == sheet.bom_scheme_id)
                    .first()
                )
                if scheme and scheme.name.startswith("存量-"):
                    delete_scheme_ids.append(scheme.id)

        for scheme_id in sorted(set(delete_scheme_ids)):
            scheme = db.query(OpportunityBomScheme).filter(OpportunityBomScheme.id == scheme_id).first()
            if scheme:
                print(f"{'DELETE' if apply else '[dry-run] DELETE'} BOM scheme id={scheme.id} name={scheme.name} opp={scheme.opportunity_id}")
                if apply:
                    db.delete(scheme)

        for sheet_id in delete_sheet_ids:
            sheet = db.query(OpportunityCostSheet).filter(OpportunityCostSheet.id == sheet_id).first()
            if sheet:
                print(f"{'DELETE' if apply else '[dry-run] DELETE'} cost sheet id={sheet.id} name={sheet.name} opp={sheet.opportunity_id}")
                if apply:
                    db.delete(sheet)

        if apply:
            db.commit()
        print(f"cleanup {'applied' if apply else 'dry-run'}: sheets={len(delete_sheet_ids)} schemes={len(set(delete_scheme_ids))}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Legacy flow artifacts migration/cleanup")
    parser.add_argument("--mode", choices=["backfill", "cleanup"], required=True)
    parser.add_argument("--apply", action="store_true", help="actually write to database")
    args = parser.parse_args()
    if args.mode == "backfill":
        run_backfill(args.apply)
    else:
        run_cleanup(args.apply)


if __name__ == "__main__":
    main()
