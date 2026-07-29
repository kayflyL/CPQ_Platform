"""One-shot migration: quotations 草稿/已导出状态机。

Adds exported_at + cost_snapshot columns and backfills exported_at from existing
sent_quote export attachments (so historical quotes that were already emailed show
as 已导出 instead of re-entering the workspace). cost_snapshot is NOT backfilled —
historical quotes have no capturable cost data; the drawer shows a placeholder.

Run once:  python -m backend.scripts.migrate_quotation_export
(或: python backend/scripts/migrate_quotation_export.py)
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def migrate() -> None:
    # 延迟导入，保证脚本可被直接 python 执行也能被 -m 调用
    from app.models.base import opp_engine

    statements = [
        # 1) 新列
        "ALTER TABLE opportunities.quotations ADD COLUMN IF NOT EXISTS exported_at VARCHAR",
        "ALTER TABLE opportunities.quotations ADD COLUMN IF NOT EXISTS cost_snapshot JSON",
        # 2) 回填 exported_at：有 sent_quote+export 归档的历史报价单 → 标为已导出（用最新归档时间）
        #    无归档的维持 NULL（仍当草稿）。cost_snapshot 不回填（抽屉显示占位）。
        """
        UPDATE opportunities.quotations q
        SET exported_at = sub.latest_export
        FROM (
            SELECT quotation_id, MAX(created_at) AS latest_export
            FROM opportunities.opportunity_attachments
            WHERE category = 'sent_quote'
              AND kind = 'export'
              AND deleted_at IS NULL
              AND quotation_id IS NOT NULL
            GROUP BY quotation_id
        ) AS sub
        WHERE q.quotation_id = sub.quotation_id
          AND q.exported_at IS NULL
        """,
    ]

    with opp_engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))

    # 统计回填结果（只读，单独连接）
    with opp_engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM opportunities.quotations")).scalar() or 0
        exported = conn.execute(
            text("SELECT COUNT(*) FROM opportunities.quotations WHERE exported_at IS NOT NULL")
        ).scalar() or 0
        with_snapshot = conn.execute(
            text("SELECT COUNT(*) FROM opportunities.quotations WHERE cost_snapshot IS NOT NULL")
        ).scalar() or 0

    logger.info("✅ migrations applied: columns added, exported_at backfilled")
    logger.info("   报价单总数: %s | 已导出(冻结): %s | 含成本快照: %s", total, exported, with_snapshot)
    logger.info("   草稿(可进工作台): %s", total - exported)


if __name__ == "__main__":
    migrate()
