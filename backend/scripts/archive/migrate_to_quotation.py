#!/usr/bin/env python3
"""
数据迁移脚本：Project → Project + Quotation

将现有的 Project 表拆分为：
- Project（项目基本信息）
- Quotation（报价单，一对多关系）
- ProjectItem（配置项，关联到 quotation_id）

执行方式：
    cd backend
    python scripts/migrate_to_quotation.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from app.models.base import Base, Proj_SessionLocal
from app.models.project import Project
from app.models.quotation import Quotation
from app.models.project_item import ProjectItem
from datetime import datetime

def check_existing_data():
    """检查现有数据"""
    session = Proj_SessionLocal()
    try:
        # 检查旧表结构
        inspector = inspect(session.bind)
        columns = [col['name'] for col in inspector.get_columns('projects')]
        print(f"当前 projects 表字段: {columns}")
        
        # 检查数据量
        project_count = session.query(Project).count()
        print(f"现有项目数: {project_count}")
        
        return project_count
    finally:
        session.close()

def migrate():
    """执行迁移"""
    print("=" * 60)
    print("数据迁移：Project → Project + Quotation")
    print("=" * 60)
    
    # 1. 检查现有数据
    project_count = check_existing_data()
    if project_count == 0:
        print("无数据需要迁移")
        return True
    
    # 2. 创建新表（如果不存在）
    print("\n[1/4] 创建 quotations 表...")
    engine = Proj_SessionLocal().bind
    Quotation.__table__.create(engine, checkfirst=True)
    
    # 3. 迁移数据
    print("[2/4] 迁移项目数据到报价单...")
    session = Proj_SessionLocal()
    try:
        # 获取所有项目
        projects = session.query(Project).all()
        
        for proj in projects:
            # 为每个项目创建一个 v1 报价单
            quotation_id = f"QUO-{proj.project_id.replace('PRJ-', '')}"
            
            # 检查是否已存在
            existing = session.query(Quotation).filter(
                Quotation.quotation_id == quotation_id
            ).first()
            
            if not existing:
                quotation = Quotation(
                    quotation_id=quotation_id,
                    project_id=proj.project_id,
                    version="v1",
                    file_path=None,
                    l6_price=getattr(proj, 'l6_price', 0.0) or 0.0,
                    total_qty=getattr(proj, 'total_qty', 0) or 0,
                    config_count=getattr(proj, 'config_count', 1) or 1,
                    created_at=proj.created_at,
                    updated_at=proj.updated_at,
                    status=proj.status
                )
                session.add(quotation)
        
        session.commit()
        print(f"  ✓ 创建了 {len(projects)} 个报价单")
        
    except Exception as e:
        session.rollback()
        print(f"  ✗ 迁移失败: {e}")
        return False
    finally:
        session.close()
    
    # 4. 更新 ProjectItem 关联
    print("[3/4] 更新配置项关联...")
    session = Proj_SessionLocal()
    try:
        # 检查 ProjectItem 表结构
        inspector = inspect(session.bind)
        columns = [col['name'] for col in inspector.get_columns('project_items')]
        
        if 'project_id' in columns and 'quotation_id' not in columns:
            # 需要添加 quotation_id 字段并迁移数据
            print("  添加 quotation_id 字段...")
            session.execute(text("""
                ALTER TABLE project_items 
                ADD COLUMN quotation_id VARCHAR
            """))
            session.commit()
            
            # 更新 quotation_id
            print("  更新 quotation_id 关联...")
            session.execute(text("""
                UPDATE project_items 
                SET quotation_id = 'QUO-' || REPLACE(project_id, 'PRJ-', '')
                WHERE quotation_id IS NULL
            """))
            session.commit()
            print("  ✓ 配置项关联已更新")
        else:
            print("  ✓ 配置项表结构已正确")
            
    except Exception as e:
        session.rollback()
        print(f"  ✗ 更新失败: {e}")
        return False
    finally:
        session.close()
    
    # 5. 验证
    print("[4/4] 验证迁移结果...")
    session = Proj_SessionLocal()
    try:
        quotation_count = session.query(Quotation).count()
        print(f"  ✓ 报价单数量: {quotation_count}")
        
        # 检查关联
        result = session.execute(text("""
            SELECT COUNT(*) FROM project_items WHERE quotation_id IS NOT NULL
        """)).scalar()
        print(f"  ✓ 已关联配置项: {result}")
        
    finally:
        session.close()
    
    print("\n" + "=" * 60)
    print("迁移完成！")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
