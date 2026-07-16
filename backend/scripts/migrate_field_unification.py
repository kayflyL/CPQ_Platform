"""
字段统一方案 - 数据库迁移脚本
1. 新建 dynamic_source_fields 表
2. 给 business_fields 表添加 used_in_pages 字段
3. 插入动态数据源子字段初始数据（56 条）
"""
import sys
from pathlib import Path

# 添加 backend 到路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.models.base import kp_engine, KP_SessionLocal


def migrate():
    """执行迁移"""
    session = KP_SessionLocal()
    
    try:
        print("=== 字段统一方案 - 数据库迁移 ===\n")
        
        # 1. 创建 dynamic_source_fields 表
        print("1. 创建 dynamic_source_fields 表...")
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS dynamic_source_fields (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_key  TEXT NOT NULL,
                field_key   TEXT NOT NULL,
                field_label TEXT NOT NULL,
                sort_order  INTEGER DEFAULT 0,
                enabled     BOOLEAN DEFAULT 1,
                UNIQUE(source_key, field_key)
            )
        """))
        session.commit()
        print("   ✓ 表创建成功\n")
        
        # 2. 给 business_fields 表添加 used_in_pages 字段
        print("2. 给 business_fields 表添加 used_in_pages 字段...")
        try:
            session.execute(text("""
                ALTER TABLE business_fields 
                ADD COLUMN used_in_pages TEXT DEFAULT '[]'
            """))
            session.commit()
            print("   ✓ 字段添加成功\n")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("   ⚠ 字段已存在，跳过\n")
            else:
                raise
        
        # 3. 插入动态数据源子字段（56 条）
        print("3. 插入动态数据源子字段...")
        
        # 先清空旧数据（如果存在）
        session.execute(text("DELETE FROM dynamic_source_fields"))
        session.commit()
        
        # l6_details: 14 个子字段
        l6_fields = [
            ('item_no', '序号'),
            ('part_name', '零件名称'),
            ('spec', '规格'),
            ('qty', '数量'),
            ('base_price', '基础价'),
            ('confirmed_price', '确认价'),
            ('final_price', '成交价'),
            ('unit_price', '单价'),
            ('profit_margin', '利润率'),
            ('description', '描述'),
            ('config_name', '配置名称'),
            ('model_name', '机型'),
            ('server_model', '服务器型号'),
            ('category', '分类'),
        ]
        
        # kp_details: 14 个子字段（同 l6_details）
        kp_fields = l6_fields.copy()
        
        # warranty_details: 14 个子字段（同 l6_details）
        warranty_fields = l6_fields.copy()
        
        # config_summary: 7 个子字段
        config_summary_fields = [
            ('seq', '序号'),
            ('config_name', '配置名称'),
            ('server_model', '服务器型号'),
            ('description', '描述'),
            ('unit_price', '含税单价'),
            ('qty', '数量'),
            ('total_price', '含税总价'),
        ]
        
        # 插入数据
        insert_count = 0
        for sort_order, (field_key, field_label) in enumerate(l6_fields):
            session.execute(text("""
                INSERT INTO dynamic_source_fields (source_key, field_key, field_label, sort_order, enabled)
                VALUES (:source_key, :field_key, :field_label, :sort_order, 1)
            """), {
                'source_key': 'l6_details',
                'field_key': field_key,
                'field_label': field_label,
                'sort_order': sort_order
            })
            insert_count += 1
        
        for sort_order, (field_key, field_label) in enumerate(kp_fields):
            session.execute(text("""
                INSERT INTO dynamic_source_fields (source_key, field_key, field_label, sort_order, enabled)
                VALUES (:source_key, :field_key, :field_label, :sort_order, 1)
            """), {
                'source_key': 'kp_details',
                'field_key': field_key,
                'field_label': field_label,
                'sort_order': sort_order
            })
            insert_count += 1
        
        for sort_order, (field_key, field_label) in enumerate(warranty_fields):
            session.execute(text("""
                INSERT INTO dynamic_source_fields (source_key, field_key, field_label, sort_order, enabled)
                VALUES (:source_key, :field_key, :field_label, :sort_order, 1)
            """), {
                'source_key': 'warranty_details',
                'field_key': field_key,
                'field_label': field_label,
                'sort_order': sort_order
            })
            insert_count += 1
        
        for sort_order, (field_key, field_label) in enumerate(config_summary_fields):
            session.execute(text("""
                INSERT INTO dynamic_source_fields (source_key, field_key, field_label, sort_order, enabled)
                VALUES (:source_key, :field_key, :field_label, :sort_order, 1)
            """), {
                'source_key': 'config_summary',
                'field_key': field_key,
                'field_label': field_label,
                'sort_order': sort_order
            })
            insert_count += 1
        
        session.commit()
        print(f"   ✓ 插入 {insert_count} 条动态数据源子字段\n")
        
        # 4. 统计结果
        print("4. 迁移结果统计：")
        result = session.execute(text("SELECT COUNT(*) FROM dynamic_source_fields"))
        count = result.scalar()
        print(f"   - dynamic_source_fields 表：{count} 条记录")
        
        result = session.execute(text("SELECT COUNT(*) FROM business_fields"))
        count = result.scalar()
        print(f"   - business_fields 表：{count} 条记录")
        
        print("\n=== 迁移完成 ===")
        
    except Exception as e:
        session.rollback()
        print(f"\n❌ 迁移失败：{e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    migrate()
