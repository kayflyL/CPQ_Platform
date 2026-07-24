"""
迁移脚本：将 business_fields 表中的 Project/ProjectItem 命名更新为 Opportunity/OpportunityItem
"""
import sys
import os

# 添加 backend 到路径
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

from app.models.base import kp_engine
from app.models.business_field import BusinessField
from sqlalchemy.orm import Session


def migrate():
    session = Session(kp_engine)

    # 更新 source 和 category
    updated = 0

    # Project -> Opportunity
    fields = session.query(BusinessField).filter(BusinessField.source == 'Project').all()
    for field in fields:
        field.source = 'Opportunity'
        if field.category == 'project':
            field.category = 'opportunity'
        updated += 1

    # ProjectItem -> OpportunityItem
    fields = session.query(BusinessField).filter(BusinessField.source == 'ProjectItem').all()
    for field in fields:
        field.source = 'OpportunityItem'
        updated += 1

    session.commit()
    print(f"✓ 成功更新 {updated} 条业务字段的数据源命名")
    print(f"  - Project -> Opportunity")
    print(f"  - ProjectItem -> OpportunityItem")
    print(f"  - category: project -> opportunity")

    session.close()


if __name__ == "__main__":
    migrate()
