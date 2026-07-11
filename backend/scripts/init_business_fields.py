"""
迁移脚本：初始化 business_fields 表
从硬编码的 32 个字段迁移到数据库配置表
"""
import sys
import os

# 添加 backend 到路径
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

from app.models.base import kp_engine, Base
from app.models.business_field import BusinessField
from sqlalchemy.orm import Session


def migrate():
    # 创建表
    Base.metadata.create_all(kp_engine)

    session = Session(kp_engine)

    # 检查是否已存在数据
    existing = session.query(BusinessField).count()
    if existing > 0:
        print(f"business_fields 表已存在 {existing} 条记录，跳过初始化")
        session.close()
        return

    # 硬编码的 32 个字段定义（从 export_templates.py 复制）
    fields_data = [
        # 商机级字段（封面静态区）
        {"key": "customer_name", "label": "客户名称", "category": "opportunity", "source": "Opportunity", "source_column": "customer_name", "sort_order": 1},
        {"key": "project_name", "label": "项目名称", "category": "opportunity", "source": "Opportunity", "source_column": "project_name", "sort_order": 2},
        {"key": "sales_person", "label": "销售人员", "category": "opportunity", "source": "Opportunity", "source_column": "sales_person", "sort_order": 3},
        {"key": "fae", "label": "FAE", "category": "opportunity", "source": "Opportunity", "source_column": "fae", "sort_order": 4},
        {"key": "platform_type", "label": "平台类型", "category": "opportunity", "source": "Opportunity", "source_column": "platform_type", "sort_order": 5},
        {"key": "chassis_form", "label": "机箱形态", "category": "opportunity", "source": "Opportunity", "source_column": "chassis_form", "sort_order": 6},
        {"key": "version", "label": "版本号", "category": "opportunity", "source": "Quotation", "source_column": "version", "sort_order": 7},
        {"key": "quotation_date", "label": "报价日期", "category": "opportunity", "source": "Quotation", "source_column": "quotation_date", "sort_order": 8},
        {"key": "total_price", "label": "含税总价", "category": "opportunity", "source": "Quotation", "source_column": "total_price", "sort_order": 9},
        {"key": "profit_margin", "label": "综合毛利率", "category": "opportunity", "source": "Quotation", "source_column": "profit_margin", "sort_order": 10},

        # 配置项字段（配置页行级）
        {"key": "config_name", "label": "配置名称", "category": "item", "source": "OpportunityItem", "source_column": "config_name", "sort_order": 11},
        {"key": "category", "label": "分类", "category": "item", "source": "OpportunityItem", "source_column": "category", "sort_order": 12},
        {"key": "part_name", "label": "部件名称", "category": "item", "source": "OpportunityItem", "source_column": "part_name", "sort_order": 13},
        {"key": "spec", "label": "规格", "category": "item", "source": "OpportunityItem", "source_column": "spec", "sort_order": 14},
        {"key": "qty", "label": "数量", "category": "item", "source": "OpportunityItem", "source_column": "qty", "sort_order": 15},
        {"key": "final_price", "label": "最终价", "category": "item", "source": "OpportunityItem", "source_column": "final_price", "sort_order": 16},
        {"key": "item_profit_margin", "label": "配置毛利率", "category": "item", "source": "OpportunityItem", "source_column": "item_profit_margin", "sort_order": 17},

        # L6 价格库字段
        {"key": "l6_chassis", "label": "L6-机箱", "category": "l6", "source": "L6Record", "source_column": "chassis", "sort_order": 18},
        {"key": "l6_model", "label": "L6-型号", "category": "l6", "source": "L6Record", "source_column": "model", "sort_order": 19},
        {"key": "l6_motherboard", "label": "L6-主板", "category": "l6", "source": "L6Record", "source_column": "motherboard", "sort_order": 20},
        {"key": "l6_backplane", "label": "L6-背板", "category": "l6", "source": "L6Record", "source_column": "backplane", "sort_order": 21},
        {"key": "l6_gpu_expansion", "label": "L6-GPU扩展", "category": "l6", "source": "L6Record", "source_column": "gpu_expansion", "sort_order": 22},
        {"key": "l6_psu", "label": "L6-电源", "category": "l6", "source": "L6Record", "source_column": "psu", "sort_order": 23},
        {"key": "l6_drive_bays", "label": "L6-盘位", "category": "l6", "source": "L6Record", "source_column": "drive_bays", "sort_order": 24},
        {"key": "l6_price", "label": "L6-价格", "category": "l6", "source": "L6Record", "source_column": "price", "sort_order": 25},

        # KP 价格库字段
        {"key": "kp_category", "label": "KP-分类", "category": "kp", "source": "KPRecord", "source_column": "category", "sort_order": 26},
        {"key": "kp_model", "label": "KP-型号", "category": "kp", "source": "KPRecord", "source_column": "model", "sort_order": 27},
        {"key": "kp_price", "label": "KP-价格", "category": "kp", "source": "KPRecord", "source_column": "price", "sort_order": 28},
        {"key": "kp_currency", "label": "KP-币种", "category": "kp", "source": "KPRecord", "source_column": "currency", "sort_order": 29},

        # 系统字段（运行时生成）
        {"key": "export_date", "label": "导出日期", "category": "system", "source": "System", "source_column": None, "sort_order": 30},
        {"key": "export_user", "label": "导出人", "category": "system", "source": "System", "source_column": None, "sort_order": 31},
        {"key": "export_timestamp", "label": "导出时间戳", "category": "system", "source": "System", "source_column": None, "sort_order": 32},
    ]

    # 批量插入
    for data in fields_data:
        field = BusinessField(**data)
        session.add(field)

    session.commit()
    print(f"✓ 成功初始化 {len(fields_data)} 个业务字段到 business_fields 表")
    session.close()


if __name__ == "__main__":
    migrate()
