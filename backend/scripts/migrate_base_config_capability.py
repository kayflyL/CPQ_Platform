#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P1 选型配置重构 —— 给 l6.base_configs 加「机箱能力档案」字段（幂等）。

机箱物理上能装什么的边界，从散落的前端硬编码（L6ChassisConfig.SLOT_CAP /
DEFAULT_REAR_SLOTS、useServerConfig.psuQty=2）提到 base_config 表，做成数据：
  psu_bays   INTEGER  电源槽位数（默认 2）—— 驱动电源数量上限/默认
  rear_slots JSONB    后面板槽位布局 [{name, cap}, ...]（默认标准 2U：IO1~IO4 各 3 + OCP 1）
  gpu_slots  INTEGER  可装 GPU 数上限（默认 0，AI 机箱在管理面改）—— 驱动 GPU 数校验
  max_tdp    INTEGER  散热/供电承载的 TDP 上限(W)，可空 —— 供 PSU↔GPU 功率规则参考

幂等：ADD COLUMN IF NOT EXISTS；首跑时 PG 用 DEFAULT 回填存量行。无破坏性，纯增量列。
用法（backend 目录）：python -X utf8 scripts/migrate_base_config_capability.py
"""
import sys
import os

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_dir)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from sqlalchemy import text
from app.models.base import l6_engine

# 标准 2U 后面板布局：IO1~IO4 各容纳 3 张卡 + OCP 1 张（与原 L6ChassisConfig 硬编码一致）
DEFAULT_REAR_SLOTS = [
    {"name": "IO1", "cap": 3},
    {"name": "IO2", "cap": 3},
    {"name": "IO3", "cap": 3},
    {"name": "IO4", "cap": 3},
    {"name": "OCP", "cap": 1},
]
import json
DEFAULT_REAR_SLOTS_JSON = json.dumps(DEFAULT_REAR_SLOTS, ensure_ascii=False)

STATEMENTS = [
    "ALTER TABLE l6.base_configs ADD COLUMN IF NOT EXISTS psu_bays INTEGER NOT NULL DEFAULT 2",
    "ALTER TABLE l6.base_configs ADD COLUMN IF NOT EXISTS gpu_slots INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE l6.base_configs ADD COLUMN IF NOT EXISTS max_tdp INTEGER",
    f"ALTER TABLE l6.base_configs ADD COLUMN IF NOT EXISTS rear_slots JSONB DEFAULT '{DEFAULT_REAR_SLOTS_JSON}'::jsonb",
    # 存量行若 rear_slots 为空（老数据/被清过），回填标准布局
    f"UPDATE l6.base_configs SET rear_slots = '{DEFAULT_REAR_SLOTS_JSON}'::jsonb "
    "WHERE rear_slots IS NULL OR rear_slots = '[]'::jsonb",
]


def main():
    print("机箱能力档案迁移：psu_bays / rear_slots / gpu_slots / max_tdp")
    with l6_engine.begin() as c:
        for s in STATEMENTS:
            c.execute(text(s))
    # 校验
    with l6_engine.connect() as c:
        rows = c.execute(text(
            "SELECT id, name, series, form, psu_bays, gpu_slots, max_tdp, rear_slots "
            "FROM l6.base_configs ORDER BY id"
        )).mappings().all()
    print(f"\n✓ 完成，当前 base_configs {len(rows)} 行：")
    for r in rows:
        print(f"  id={r['id']} {r['series'] or '-'} {r['form'] or '-'} 「{r['name']}」  "
              f"psu_bays={r['psu_bays']} gpu_slots={r['gpu_slots']} max_tdp={r['max_tdp']}  "
              f"rear_slots={r['rear_slots']}")
    print("\nAI/高配机箱的 gpu_slots、max_tdp 请在管理面「机箱能力」标签按实际改。")


if __name__ == '__main__':
    main()
