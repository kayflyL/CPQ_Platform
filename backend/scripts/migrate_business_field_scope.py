"""business_fields 修正 'all' 通用字段的 scope 归属（2026-09-15，幂等）。

背景：scope='all' 的 9 个字段被 get_fields_by_scope 并进每个分组返回，
模板编辑器左栏「商机级/配置项/系统字段」三组各重复出现这 9 个。
逐个按 source/used_in_pages 修正归属；result(业务结果) 与
opportunity_result(商机结果) 语义重复且无引用，禁用。
"""
import sys

import sqlalchemy as sa
from _localdb import db_url

ENG = sa.create_engine(
    db_url(),
    connect_args={"client_encoding": "UTF8"},
)

SCOPE_FIX = {
    # 配置级（source=config_summary，用于 cfg_ 前缀静态绑定）
    "cfg_unit_price": "config",
    "cfg_total_price": "config",
    # 商机级（source=Opportunity，页面归属 opportunity_detail）
    "delivery_cycle": "opportunity",
    "delivery_region": "opportunity",
    "industry": "opportunity",
    "order_type": "opportunity",
    "warranty_years": "opportunity",
    "opportunity_result": "opportunity",
}

DISABLE = {"result"}  # 与 opportunity_result 语义重复，used_in_pages 为空


def main() -> int:
    fixed = disabled = 0
    with ENG.begin() as c:
        for key, scope in SCOPE_FIX.items():
            res = c.execute(sa.text("""
                UPDATE rules.business_fields
                SET scope = :scope
                WHERE key = :key AND scope <> :scope
            """), {"scope": scope, "key": key})
            fixed += res.rowcount or 0
        for key in DISABLE:
            res = c.execute(sa.text("""
                UPDATE rules.business_fields
                SET enabled = FALSE
                WHERE key = :key AND enabled
            """), {"key": key})
            disabled += res.rowcount or 0

    print(f"✅ scope 归属修正 {fixed} 行；禁用 {disabled} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
