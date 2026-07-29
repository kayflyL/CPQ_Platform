"""迁移：将线缆类料号的 specs.backplane 统一为 specs.bt。

背景：
- 背板本体料号已使用 bt (tri/dc)
- 线缆类料号历史使用 backplane (三模/直连 或 Pass-through/Tri-Mode)
- 需统一为 bt，值统一为 tri/dc

迁移逻辑：
1. 查询 category='前面板线缆' 或 'IO线缆' 的料号
2. 检查 specs.backplane 值，转换为 specs.bt
3. 值映射：三模/Tri-Mode → tri, 直连/Pass-through/Pass-thru → dc

用法：python scripts/migrate_backplane_to_bt.py
"""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from sqlalchemy import create_engine, text

# 值映射：中文/英文 → 标准英文
VALUE_MAP = {
    'tri': 'tri',
    'dc': 'dc',
    '三模': 'tri',
    'Tri-Mode': 'tri',
    'Tri Mode': 'tri',
    '直连': 'dc',
    'Pass-through': 'dc',
    'Pass-thru': 'dc',
    'Pass through': 'dc',
}


def migrate_backplane_to_bt():
    s = get_settings()
    engine = create_engine(s.DATABASE_URL)

    with engine.connect() as conn:
        # 查询需要迁移的料号（表在 l6 schema）
        rows = conn.execute(text("""
            SELECT pn, name, specs
            FROM l6.parts_master
            WHERE category IN ('前面板线缆', 'IO线缆')
              AND specs::text LIKE '%backplane%'
        """)).fetchall()

        if not rows:
            print("无需迁移的料号")
            return

        print(f"待迁移料号 {len(rows)} 条:")
        migrated = 0
        for pn, name, specs in rows:
            # specs 可能是 dict 或 JSON 字符串
            if isinstance(specs, str):
                specs = json.loads(specs)
            specs = specs or {}
            old_backplane = specs.get('backplane')
            if not old_backplane:
                continue

            # 数组值取第一个有效映射
            if isinstance(old_backplane, list):
                new_vals = []
                for v in old_backplane:
                    mapped = VALUE_MAP.get(v)
                    if mapped:
                        new_vals.append(mapped)
                # 取众数或第一个
                bt_val = new_vals[0] if new_vals else None
            else:
                bt_val = VALUE_MAP.get(str(old_backplane))

            if not bt_val:
                print(f"  ⚠️ {pn}: 无法映射 backplane={old_backplane}")
                continue

            # 更新 specs
            specs['bt'] = bt_val
            del specs['backplane']

            # 写回数据库
            conn.execute(
                text("UPDATE l6.parts_master SET specs = :specs WHERE pn = :pn"),
                {"specs": json.dumps(specs), "pn": pn}
            )
            print(f"  ✓ {pn}: backplane={old_backplane} → bt={bt_val}")
            migrated += 1

        conn.commit()
        print(f"\n迁移完成: {migrated} 条")


if __name__ == '__main__':
    migrate_backplane_to_bt()