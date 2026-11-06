# -*- coding: utf-8 -*-
"""tool_contents —— 工具内容表（rules.tool_contents）。

工具中心/工具页展示文案的唯一权威源（2026-11-06 原型批准）：
卡片名称/描述/分类/标签/排序/上下架 + 工具页标题/副标题/说明区条目/导流条。
写入口只有后台编辑器（action.tools.content.manage）；计算数值不归这张表
（gpu-sizing 三软库照旧）。种子与降级同 agent_tool_text 范式：
种子行回填 ON CONFLICT DO NOTHING（不动已有编辑），前端常量只作降级兜底。
"""
import json
from typing import Dict, Optional

from sqlalchemy import text

from ..models.base import Rules_SessionLocal

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS rules.tool_contents (
    key        TEXT PRIMARY KEY,
    content    TEXT NOT NULL,
    updated_by VARCHAR,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

# 种子（与 frontend/src/constants/toolsRegistry.ts 的默认文案同源；改文案两处同步）。
# cta.target 只允许站内路由（编辑器下拉预设：/servers /catalog /strategies）。
DEFAULT_TOOL_CONTENTS: Dict[str, dict] = {
    "gpu-sizing": {
        "name": "GPU 显存计算器",
        "desc": "按大模型、量化精度、推理框架与并发估算显存需求；哪些卡装得下、装几张，一目了然。配套「模型与参数库」维护模型/框架/场景参数。",
        "category": "AI 算力选型",
        "tags": ["推理配置", "模型与参数库"],
        "order": 100,
        "visible": True,
        "page_title": "GPU 显存计算器",
        "page_sub": "选大模型与部署方式，估显存需求、匹配可用的卡。",
        "doc_visible": True,
        "doc_title": "公式是怎么算的",
        "doc_items": [
            {
                "title": "权重显存",
                "formula": "参数量(B) × 字节系数 × 框架系数",
                "text": "字节系数由量化精度决定（4bit≈0.5、8bit≈1、16bit≈2），框架系数取自推理框架库，可在「模型与参数库」中调整。",
            },
            {
                "title": "KV 缓存",
                "formula": "2 × 层数 × KV头数 × 头维 × 上下文 × 并发 × 字节",
                "text": "随上下文长度与并发数线性增长；注意力结构（GQA/MHA/MLA）决定 KV 头数。",
            },
            {
                "title": "卡型匹配",
                "formula": "可用显存 = 单卡容量 × 张数 − 框架开销 ≥ 需求总量",
                "text": "需求侧先算准、再对卡型批量试算；每张卡给出推荐张数与最低张数，可在卡砖上直接调张数重算。",
            },
        ],
        "cta_visible": True,
        "cta_text": "显存算准了？挑一台能装下这些卡的服务器，直接进配置向导。",
        "cta_button": "去配置服务器 →",
        "cta_target": "/servers",
    },
}


class ToolContentRepository:

    _ensured = False

    def __init__(self):
        self.session = Rules_SessionLocal()
        if not ToolContentRepository._ensured:
            self._ensure_table()
            self._seed_defaults()
            ToolContentRepository._ensured = True

    def _ensure_table(self):
        self.session.execute(text(_CREATE_SQL))
        self.session.commit()

    def _seed_defaults(self):
        for key, content in DEFAULT_TOOL_CONTENTS.items():
            self.session.execute(
                text("INSERT INTO rules.tool_contents (key, content) VALUES (:key, :content) "
                     "ON CONFLICT (key) DO NOTHING"),
                {"key": key, "content": json.dumps(content, ensure_ascii=False)},
            )
        self.session.commit()

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass

    def list_all(self) -> Dict[str, dict]:
        rows = self.session.execute(
            text("SELECT key, content FROM rules.tool_contents")
        ).fetchall()
        out: Dict[str, dict] = {}
        for key, raw in rows:
            try:
                out[str(key)] = json.loads(raw)
            except (TypeError, ValueError):
                continue
        return out

    def get(self, key: str) -> Optional[dict]:
        row = self.session.execute(
            text("SELECT content FROM rules.tool_contents WHERE key = :key"), {"key": key}
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except (TypeError, ValueError):
            return None

    def upsert(self, key: str, content: dict, updated_by: str = "") -> None:
        self.session.execute(
            text("INSERT INTO rules.tool_contents (key, content, updated_by) "
                 "VALUES (:key, :content, :updated_by) "
                 "ON CONFLICT (key) DO UPDATE SET content = :content, updated_by = :updated_by, "
                 "updated_at = now()"),
            {"key": key, "content": json.dumps(content, ensure_ascii=False),
             "updated_by": updated_by or ""},
        )
        self.session.commit()
