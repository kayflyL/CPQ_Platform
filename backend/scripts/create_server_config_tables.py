"""阶段①（数据层）· 建服务器配置新表

新表分布：
  parts schema  : parts_master          （统一料号主表，L6+KP 归并）
  l6   schema   : server_types          （服务器类型：通用/AI/存储）
                  server_models         （机型目录）
                  base_configs_new      （基准配置，重写为引用 parts_master）
                  base_config_parts_new （基准配置公共底盘件清单，引用 pn）
                  config_schemes        （配置方案 / 无价 BOM）
  rules schema  : derivation_rules      （推导规则，可配置）

注意：旧的 l6.base_configs / l6.base_config_parts 此处不动（保留原数据供迁移），
      迁移脚本 migrate_to_parts_master.py 会把数据搬进 _new 表后，DROP 旧表并 RENAME。

用法：python scripts/create_server_config_tables.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
from app.core.config import get_settings

s = get_settings()
conn = psycopg2.connect(
    host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
    user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8",
)
cur = conn.cursor()

STMTS = [
    "CREATE SCHEMA IF NOT EXISTS parts",

    # ===== parts.parts_master：统一料号主表 =====
    """CREATE TABLE IF NOT EXISTS parts.parts_master (
        pn           VARCHAR(200) PRIMARY KEY,
        name         VARCHAR(500) NOT NULL,
        category     VARCHAR(100) NOT NULL,
        sub_type     VARCHAR(100),
        specs        JSONB DEFAULT '{}'::jsonb,
        unit_price   DECIMAL(15,2) DEFAULT 0,
        supplier     VARCHAR(200),
        applicable   JSONB DEFAULT '{}'::jsonb,
        sort_order   INTEGER DEFAULT 0,
        created_at   TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_parts_master_cat ON parts.parts_master(category)",

    # ===== l6.server_types =====
    """CREATE TABLE IF NOT EXISTS l6.server_types (
        id           SERIAL PRIMARY KEY,
        name         VARCHAR(100) NOT NULL,
        description  TEXT,
        sort_order   INTEGER DEFAULT 0
    )""",

    # ===== l6.server_models（机型目录；卡片只显 name/form/bays/use）=====
    """CREATE TABLE IF NOT EXISTS l6.server_models (
        id              SERIAL PRIMARY KEY,
        name            VARCHAR(100) NOT NULL,
        server_type_id  INTEGER REFERENCES l6.server_types(id),
        form            VARCHAR(20),
        bays            INTEGER,
        use             VARCHAR(100),
        base_config_id  INTEGER,
        sort_order      INTEGER DEFAULT 0
    )""",

    # ===== l6.base_configs_new（基准配置，引用 parts_master）=====
    """CREATE TABLE IF NOT EXISTS l6.base_configs_new (
        id                SERIAL PRIMARY KEY,
        name              VARCHAR(200) NOT NULL,
        server_type_id    INTEGER REFERENCES l6.server_types(id),
        series            VARCHAR(50),
        model             VARCHAR(100),
        form              VARCHAR(20),
        bays              INTEGER,
        bp_tri_pn         VARCHAR(200) REFERENCES parts.parts_master(pn),
        bp_dc_pn          VARCHAR(200) REFERENCES parts.parts_master(pn),
        gpu_arch_default  VARCHAR(20) DEFAULT 'none',
        sort_order        INTEGER DEFAULT 0,
        created_at        TIMESTAMP DEFAULT NOW()
    )""",

    # ===== l6.base_config_parts_new（公共底盘件清单，引用 pn，带 locked）=====
    """CREATE TABLE IF NOT EXISTS l6.base_config_parts_new (
        id          SERIAL PRIMARY KEY,
        config_id   INTEGER NOT NULL,
        pn          VARCHAR(200) NOT NULL REFERENCES parts.parts_master(pn),
        quantity    INTEGER DEFAULT 1,
        locked      BOOLEAN DEFAULT TRUE,
        sort_order  INTEGER DEFAULT 0
    )""",
    "CREATE INDEX IF NOT EXISTS idx_bcp_new_config ON l6.base_config_parts_new(config_id)",

    # ===== l6.config_schemes（配置方案 / 无价 BOM，服务器页产物）=====
    """CREATE TABLE IF NOT EXISTS l6.config_schemes (
        id          SERIAL PRIMARY KEY,
        name        VARCHAR(200),
        model_id    INTEGER REFERENCES l6.server_models(id),
        payload     JSONB,
        created_at  TIMESTAMP DEFAULT NOW()
    )""",

    # ===== rules.derivation_rules（推导规则，可配置）=====
    """CREATE TABLE IF NOT EXISTS rules.derivation_rules (
        id         SERIAL PRIMARY KEY,
        rule_key   VARCHAR(100) NOT NULL UNIQUE,
        params     JSONB DEFAULT '{}'::jsonb,
        scope      VARCHAR(20) DEFAULT 'global',
        scope_ref  VARCHAR(100),
        enabled    BOOLEAN DEFAULT TRUE,
        note       TEXT
    )""",
]

for st in STMTS:
    cur.execute(st)
    print("✓", st.split("\n")[0][:70])

conn.commit()
cur.close()
conn.close()
print("\n阶段①建表完成。下一步：运行 migrate_to_parts_master.py 迁移数据。")
