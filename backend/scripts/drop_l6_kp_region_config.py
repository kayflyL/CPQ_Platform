#!/usr/bin/env python3
"""
迁移脚本：DROP 旧的 rules.l6_region_config / rules.kp_region_config 表。

这两张表已被规则驱动的 parse_regions / parse_field_rules（ExcelParser）取代，
pricing_engine 不再读写它们。代码层（models / rules_repo / rules API / startup）
已全部清理，此处 drop 物理表收尾。

幂等（DROP ... IF EXISTS），可重复执行。

运行方式:
    cd backend && python -X utf8 -m scripts.drop_l6_kp_region_config
"""
import sys
from pathlib import Path

# 把 backend 加到 path，以便 import app.*
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.models.base import rules_engine


def main():
    print("=" * 60)
    print("DROP 旧的 rules.l6_region_config / rules.kp_region_config")
    print("=" * 60)
    with rules_engine.begin() as conn:
        for table in ("l6_region_config", "kp_region_config"):
            conn.execute(text(f'DROP TABLE IF EXISTS rules."{table}" CASCADE'))
            print(f"  ✓ dropped rules.{table}")
    print("完成。")


if __name__ == "__main__":
    main()
