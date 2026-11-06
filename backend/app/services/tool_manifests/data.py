# -*- coding: utf-8 -*-
"""工具声明清单·数据检索域（数据边界查询/案例检索）（第 7 步工具声明面，2026-10-31 自 agent_tool_specs 迁入）。

条目 = 操作 + 契约（读写/确认/回读，MCP 注解命名）+ 画布产物卡 + 参数 schema。
本模块零 import：handler 用点串引用，注册时由 build_tool_registry 惰性解析。
"""
TOOLS = {
    "query_data": {

        "summary": "在数据边界内执行只读 SELECT，返回列名与行数据。只写单条 SELECT（支持 WITH/CTE；写操作与注释会被拒绝）；可读范围见 information_schema。",
       "category": "data",
        "default_enabled": False,
        "description": (
            "在数据边界内执行只读 SELECT，返回列名与行数据。规则：只写单条 SELECT（支持 WITH/CTE；写操作与注释会被拒绝）；可读表与列结构见 information_schema.tables / information_schema.columns；表不在白名单会返回错误；SQL 报错信息原样返回；价格等敏感列按数据边界脱敏（该列不返回）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "单条只读 SELECT 语句（PostgreSQL 方言）"},
                "limit": {"type": "integer", "description": "返回行数上限，默认 50（硬上限 200）"},
            },
            "required": ["sql"],
        },
        "handler": "app.services.agent_tool_handlers._tool_query_data",
    },
    "search_cases": {

        "summary": "检索选型配置案例库里与当前需求相似的历史案例（需求→机型/底盘配置 对照）。需求模糊或想参照同类已验证配置时调用；只读，不改案例库。",
       "category": "data",
        "default_enabled": True,
        "description": ("检索【选型配置案例库】里与当前需求相似的历史案例（需求→机型/底盘配置 对照），"
                        "作为接地参考。需求模糊、或想参照同类已验证配置（如「8卡GPU AI服务器一般配什么底盘/电源」）时调用。"
                        "只读，绝不改案例库。"),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "用于检索的需求/场景文本"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "场景标签过滤（可选），如 ['AI','8卡GPU','兆芯','4U']"},
            },
        },
        # handler 由 build_tool_registry 按 case 配置（case_source/top_k/match）注入
        "handler": None,
    },
}
