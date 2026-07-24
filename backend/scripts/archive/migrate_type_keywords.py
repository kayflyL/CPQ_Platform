"""
将 type_keywords 硬编码迁移到 rules 表
"""
import sys
from pathlib import Path

# 添加 backend 到路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.models.base import rules_engine, Rules_SessionLocal
import json


def migrate():
    """执行迁移"""
    session = Rules_SessionLocal()
    
    try:
        print("=== type_keywords 迁移到 rules 表 ===\n")
        
        # type_keywords 数据（合并 pricing_engine.py 和 preview_data_loader.py 的版本）
        type_keywords = {
            "cpu": ["cpu", "processor", "处理器", "epyc", "xeon"],
            "memory": ["memory", "ram", "内存", "ddr", "dimm"],
            "hdd": ["hdd", "硬盘", "disk", "storage"],
            "ssd": ["ssd", "固态"],
            "gpu": ["gpu", "显卡", "graphics", "nvidia", "radeon"],
            "nic": ["nic", "网卡", "network", "ethernet"],
            "raid": ["raid"],
            "psu": ["psu", "电源", "power supply"],
            "front_backplane": ["front backplane", "front_bp", "背板"],
            "rear_backplane": ["rear backplane", "rear_bp"]
        }
        
        rule_value = json.dumps(type_keywords, ensure_ascii=False)
        
        # 检查是否已存在
        result = session.execute(
            text("SELECT id FROM matching_rules WHERE rule_name = :name"),
            {"name": "type_keywords"}
        )
        existing = result.fetchone()
        
        if existing:
            # 更新
            session.execute(
                text("UPDATE matching_rules SET rule_value = :value WHERE rule_name = :name"),
                {"value": rule_value, "name": "type_keywords"}
            )
            print("✓ 更新 type_keywords 到 rules 表")
        else:
            # 插入
            session.execute(
                text("""
                    INSERT INTO matching_rules (rule_name, rule_value, description)
                    VALUES (:name, :value, :desc)
                """),
                {
                    "name": "type_keywords",
                    "value": rule_value,
                    "desc": "部件类型关键词映射（用于描述生成）"
                }
            )
            print("✓ 插入 type_keywords 到 rules 表")
        
        session.commit()
        
        # 验证
        result = session.execute(
            text("SELECT rule_value FROM matching_rules WHERE rule_name = :name"),
            {"name": "type_keywords"}
        )
        row = result.fetchone()
        if row:
            data = json.loads(row[0])
            print(f"✓ 验证成功：{len(data)} 个部件类型")
        
        print("\n=== 迁移完成 ===")
        
    except Exception as e:
        session.rollback()
        print(f"\n❌ 迁移失败：{e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    migrate()
