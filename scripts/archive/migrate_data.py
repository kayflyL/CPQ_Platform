#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration Script: SQLite (Legacy) -> New DB (SQLite/MySQL)
Reads from D:\Quotation_Automation\Reference\projects.db
Writes to backend/data/cpq_platform.db
"""
import sys
import os
import sqlite3
import json
from datetime import datetime

# Ensure we use the Hermes Agent venv (or whatever has sqlalchemy)
HERMES_VENV_LIB = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'hermes', 'hermes-agent', 'venv', 'Lib', 'site-packages')
if os.path.exists(HERMES_VENV_LIB):
    sys.path.insert(0, HERMES_VENV_LIB)

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.core.database import Base, engine, SessionLocal
from app.models.models import Project, ProjectItem

# Legacy DB Path
LEGACY_DB_PATH = r"D:\Quotation_Automation\Reference\projects.db"

def parse_items_data(row):
    """
    Extract items from the legacy DB. 
    Legacy DB usually stores items in 'items' column as JSON or similar.
    Or in a separate 'project_items' table.
    """
    # Check if items column exists in row
    if 'items' in row.keys():
        try:
            return json.loads(row['items'])
        except:
            return None
    return None

def migrate():
    print("Starting Migration to New Database...")
    
    # Create new tables
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    
    try:
        legacy_conn = sqlite3.connect(LEGACY_DB_PATH)
        legacy_conn.row_factory = sqlite3.Row
        cursor = legacy_conn.cursor()
        
        # 1. Migrate Projects
        cursor.execute("SELECT * FROM projects")
        projects = cursor.fetchall()
        print(f"Found {len(projects)} projects in legacy DB.")
        
        # Map old TEXT project_id -> new INTEGER id
        id_map = {}
        
        count = 0
        for p in projects:
            p_dict = dict(p) # Convert Row to Dict for safe .get()
            
            # Create Project Object
            proj = Project(
                project_id=p_dict['project_id'],
                project_name=p_dict.get('project_name', ''),
                model_name=p_dict.get('model_name', ''),
                platform_type=p_dict.get('platform_type', ''),
                chassis_form=p_dict.get('chassis_form', ''),
                fae=p_dict.get('fae', ''),
                sales_person=p_dict.get('sales_person', ''),
                company=p_dict.get('company', ''),
                total_qty=p_dict.get('total_qty', 0),
                config_count=p_dict.get('config_count', 0),
                l6_spec=p_dict.get('l6_spec', ''),
                status=p_dict.get('feedback_status', '待报价'),
                created_at=datetime.fromisoformat(p_dict['created_at']) if p_dict['created_at'] else datetime.utcnow(),
            )
            session.add(proj)
            session.flush()
            
            # Map: Old TEXT ID -> New Integer ID
            id_map[p_dict['project_id']] = proj.id
            count += 1
        
        print(f"✅ Mapped {count} projects.")

        # 2. Migrate Items
        cursor.execute("SELECT * FROM project_items")
        items = cursor.fetchall()
        print(f"Found {len(items)} items in legacy DB.")
        
        item_count = 0
        for item in items:
            old_pid = item['project_id']
            new_pid = id_map.get(old_pid)
            
            if not new_pid:
                print(f"⚠️ Warning: Item {item['item_id']} has orphaned project_id {old_pid}")
                continue

            new_item = ProjectItem(
                project_id=new_pid, # Use the new Integer ID
                config_name=item.get('config_name', 'CFG1'),
                part_name=item.get('part_name', ''),
                spec=item.get('spec', ''),
                category=item.get('category', ''),
                # model_name=item.get('model', ''), # Not in legacy schema
                qty=item.get('qty', 1),
                base_price=item.get('base_price', 0), # Use base_price
                profit_margin=item.get('profit_margin', 10.0),
                final_price=item.get('final_price', 0),
            )
            session.add(new_item)
            item_count += 1
            
        session.commit()
        print(f"✅ Successfully migrated {count} projects and {item_count} items.")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    migrate()
