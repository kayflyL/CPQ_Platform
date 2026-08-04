# -*- coding: utf-8 -*-
"""BOM案例库 建表（boot 幂等）。

2026-08-04：golden（回归用例）已随「回归中心」一并砍掉（业务侧改走对话 + 推理流 + 技术员审核），
本模块只负责 rules.bom_cases 建表。
"""
from sqlalchemy import text

from app.models.base import rules_engine


def ensure_bom_cases_table():
    with rules_engine.begin() as c:
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS rules.bom_cases (
                case_key varchar(40) PRIMARY KEY,
                name varchar NOT NULL DEFAULT '',
                scenario_tags jsonb NOT NULL DEFAULT '[]',
                model_id integer,
                base_config_id integer,
                bom_template_id integer,
                chassis_signals jsonb NOT NULL DEFAULT '{}',
                kp_lines jsonb NOT NULL DEFAULT '[]',
                l6_rows jsonb NOT NULL DEFAULT '[]',
                price_snapshot jsonb NOT NULL DEFAULT '{}',
                notes text,
                requirement text,
                version integer NOT NULL DEFAULT 1,
                enabled boolean NOT NULL DEFAULT true,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                created_by varchar NOT NULL DEFAULT 'system',
                updated_by varchar NOT NULL DEFAULT 'system'
            )
        """))
        c.execute(text("CREATE INDEX IF NOT EXISTS idx_bom_cases_enabled ON rules.bom_cases(enabled)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS idx_bom_cases_created ON rules.bom_cases(created_at)"))
        # 既有表补列（幂等）
        c.execute(text("ALTER TABLE rules.bom_cases ADD COLUMN IF NOT EXISTS notes text"))
        c.execute(text("ALTER TABLE rules.bom_cases ADD COLUMN IF NOT EXISTS requirement text"))
        c.execute(text("ALTER TABLE rules.bom_cases ADD COLUMN IF NOT EXISTS l6_config_desc text"))
        c.execute(text("ALTER TABLE rules.bom_cases ADD COLUMN IF NOT EXISTS l6_rows jsonb NOT NULL DEFAULT '[]'"))
        # 2026-08-04 用户决定：来源字段不必要，前后端数据都删（幂等）
        c.execute(text("ALTER TABLE rules.bom_cases DROP COLUMN IF EXISTS source_type"))
        c.execute(text("ALTER TABLE rules.bom_cases DROP COLUMN IF EXISTS source_ref"))
