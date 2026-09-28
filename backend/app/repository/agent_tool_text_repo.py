# -*- coding: utf-8 -*-
"""agent_tool_text —— 工具目录文案表（rules.agent_tool_text）。

**DB 唯一权威源**（2026-09-15 定调，树干-枝叶）：启动时把种子行回填进表
（ON CONFLICT DO NOTHING，不动已有编辑），运行时（目录/注册表）只读这张表；
代码里的文案（agent_tool_display + summary）只作迁移种子与 DB 故障降级，
不是第二份活数据。「恢复默认」= 行内容重置为种子值（UPDATE，不删行）。

行不变量：每行四字段皆非空（编辑时清空某字段 = 写回该字段种子值），
因此运行时不存在「字段缺省回代码」的读路径。
"""
from typing import Dict, List, Optional

from sqlalchemy import text

from ..models.base import Rules_SessionLocal

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS rules.agent_tool_text (
    name         TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    one_liner    TEXT NOT NULL,
    description  TEXT NOT NULL,
    model_brief  TEXT NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


class AgentToolTextRepository:

    _ensured = False

    def __init__(self):
        self.session = Rules_SessionLocal()
        if not AgentToolTextRepository._ensured:
            self._ensure_table()
            AgentToolTextRepository._ensured = True

    def _ensure_table(self):
        self.session.execute(text(_CREATE_SQL))
        self.session.commit()

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass

    def get_overrides(self) -> Dict[str, Dict[str, str]]:
        """全部行：{tool_name: {field: value}}（行不变量保证四字段非空）。"""
        rows = self.session.execute(
            text("SELECT name, display_name, one_liner, description, model_brief FROM rules.agent_tool_text")
        ).fetchall()
        return {str(name): {"display_name": dn or "", "one_liner": ol or "",
                            "description": desc or "", "model_brief": brief or ""}
                for name, dn, ol, desc, brief in rows}

    def get_override(self, name: str) -> Dict[str, str]:
        return self.get_overrides().get(str(name or "").strip()) or {}

    def seed_defaults(self, rows: List[dict]) -> int:
        """启动种子回填：只补缺行，已有行（含用户编辑）一律不动。返回补了几个。"""
        if not rows:
            return 0
        result = self.session.execute(
            text("""
                INSERT INTO rules.agent_tool_text (name, display_name, one_liner, description, model_brief)
                VALUES (:name, :display_name, :one_liner, :description, :model_brief)
                ON CONFLICT (name) DO NOTHING
            """),
            [{"name": r.get("name"), "display_name": r.get("display_name"),
              "one_liner": r.get("one_liner"), "description": r.get("description"),
              "model_brief": r.get("model_brief")} for r in rows],
        )
        self.session.commit()
        return int(result.rowcount or 0)

    def write_row(self, name: str, fields: Dict[str, Optional[str]]) -> None:
        """整行覆盖写（调用方保证四字段完整；「恢复默认」也走这里写种子值）。"""
        tool = str(name or "").strip()
        self.session.execute(
            text("""
                INSERT INTO rules.agent_tool_text (name, display_name, one_liner, description, model_brief, updated_at)
                VALUES (:name, :display_name, :one_liner, :description, :model_brief, now())
                ON CONFLICT (name) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    one_liner    = EXCLUDED.one_liner,
                    description  = EXCLUDED.description,
                    model_brief  = EXCLUDED.model_brief,
                    updated_at   = now()
            """),
            {"name": tool,
             "display_name": fields.get("display_name"),
             "one_liner": fields.get("one_liner"),
             "description": fields.get("description"),
             "model_brief": fields.get("model_brief")},
        )
        self.session.commit()
