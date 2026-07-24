"""Data migration script: Project → Project + Quotation

Migrates existing project data to the new one-to-many relationship:
- Each existing project gets a v1 quotation
- ProjectItem.project_id → ProjectItem.quotation_id
- Project table loses quotation-specific fields
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = "data/cpq_platform.db"

def migrate():
    """Execute migration"""
    if not os.path.exists(DB_PATH):
        print(f"Database not found: {DB_PATH}")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # 1. Create quotations table
        print("Creating quotations table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quotations (
                quotation_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT 'v1',
                file_path TEXT,
                l6_price REAL DEFAULT 0.0,
                total_qty INTEGER DEFAULT 0,
                config_count INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT,
                status TEXT DEFAULT 'active'
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_quotation_project ON quotations(project_id)")
        
        # 2. Create new project_items table with quotation_id
        print("Creating new project_items structure...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_items_new (
                item_id INTEGER PRIMARY KEY,
                quotation_id TEXT NOT NULL,
                config_name TEXT,
                category TEXT,
                part_name TEXT,
                spec TEXT,
                qty INTEGER DEFAULT 0,
                confirmed_price REAL DEFAULT 0.0,
                base_price REAL DEFAULT 0.0,
                final_price REAL DEFAULT 0.0,
                profit_margin REAL DEFAULT 0.0
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_item_quotation ON project_items_new(quotation_id)")
        
        # 3. For each existing project, create a v1 quotation
        print("Creating quotations for existing projects...")
        cursor.execute("SELECT project_id, l6_price, total_qty, config_count FROM projects")
        projects = cursor.fetchall()
        
        now = datetime.now().isoformat()
        for proj in projects:
            project_id, l6_price, total_qty, config_count = proj
            quotation_id = f"QUO-{project_id.replace('PRJ-', '')}"
            
            cursor.execute("""
                INSERT OR IGNORE INTO quotations 
                (quotation_id, project_id, version, l6_price, total_qty, config_count, 
                 created_at, updated_at, status)
                VALUES (?, ?, 'v1', ?, ?, ?, ?, ?, 'active')
            """, (quotation_id, project_id, l6_price or 0.0, total_qty or 0, 
                  config_count or 1, now, now))
        
        # 4. Migrate project_items to use quotation_id
        print("Migrating project_items...")
        cursor.execute("""
            INSERT INTO project_items_new 
            SELECT item_id, 'QUO-' || REPLACE(project_id, 'PRJ-', ''), 
                   config_name, category, part_name, spec, qty,
                   confirmed_price, base_price, final_price, profit_margin
            FROM project_items
        """)
        
        # 5. Replace old table
        print("Replacing old tables...")
        cursor.execute("DROP TABLE IF EXISTS project_items")
        cursor.execute("ALTER TABLE project_items_new RENAME TO project_items")
        
        # 6. Create new projects table without quotation fields
        print("Creating new projects structure...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects_new (
                project_id TEXT PRIMARY KEY,
                folder_name TEXT,
                project_name TEXT,
                customer_name TEXT,
                model_name TEXT,
                platform_type TEXT,
                chassis_form TEXT,
                fae TEXT,
                sales_person TEXT,
                l6_spec TEXT,
                created_at TEXT,
                updated_at TEXT,
                status TEXT DEFAULT 'active'
            )
        """)
        
        # 7. Copy project data (without quotation fields)
        cursor.execute("""
            INSERT INTO projects_new
            SELECT project_id, folder_name, project_name, customer_name,
                   model_name, platform_type, chassis_form, fae, sales_person,
                   l6_spec, created_at, updated_at, status
            FROM projects
        """)
        
        # 8. Replace old projects table
        cursor.execute("DROP TABLE IF EXISTS projects")
        cursor.execute("ALTER TABLE projects_new RENAME TO projects")
        
        conn.commit()
        print(f"Migration completed successfully!")
        print(f"  - Migrated {len(projects)} projects")
        print(f"  - Created {len(projects)} quotations")
        
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
