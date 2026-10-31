# -*- coding: utf-8 -*-
"""工具声明清单·商机域（建档/统计口径）（第 7 步工具声明面，2026-10-31 自 agent_tool_specs 迁入）。

条目 = 操作 + 契约（读写/确认/回读，MCP 注解命名）+ 画布产物卡 + 参数 schema。
本模块零 import：handler 用点串引用，注册时由 build_tool_registry 惰性解析。
"""
TOOLS = {
    "create_opportunity": {
        "contract": {"effects": "write", "confirm_policy": "none", "idempotent_hint": False,
                           "destructive_hint": False, "target_entity": "opportunity"},

        "summary": "创建商机记录（两阶段确认：首调只返回将要落库的字段预览，用户同意后带同一参数加 confirm=true 才创建）。customer_name 必须取用户最新明确说出的名称，系统对同名客户不做查重。",
       "category": "business",
        "default_enabled": False,
        "description": (
            "替用户创建一条商机记录，与商机列表页「新建商机」同一后端逻辑（权限与归属规则同源）。"
            "两阶段确认：首次调用只返回预览（客户名/归属业务的原样字段），用户明确同意后带同一参数加 "
            "confirm=true 重调才真正创建——客户名以用户最新说法为准，逐字使用，改写或沿用自己先前的"
            "猜测都会在预览里被用户看到。非 business 角色缺归属业务时会先被要求补齐，补齐后再出预览。"
            "创建成功返回 opportunity_id，后续可接 save_requirement_draft 填需求、import_cost_sheet 导成本表。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "客户名称（用户最新明确说出的原文，逐字使用）"},
                "sales_person": {"type": "string", "description": "归属业务姓名（business 角色=自己可省；其他角色必填，须为在册业务账号）"},
                "confirm": {"type": "boolean", "description": "用户明确同意预览后置 true 重调（参数须与预览完全一致）；首调不传"},
            },
            "required": ["customer_name"],
        },
        "handler": "app.services.agent_tool_handlers._tool_create_opportunity",
    },
    "opportunity_stats": {

        "summary": "商机统计：与商机线索页完全同口径的窗口统计数字（KPI/逐月序列/平台与机箱分布/销售榜/本周本月小窗）。报告中的商机统计数字一律以本工具返回为准。",
       "category": "data",
        "default_enabled": False,
        "description": (
            "商机统计口径工具：传入报告数据范围（start/end，YYYY-MM-DD），返回该窗口的确定性统计——"
            "KPI（累计商机/累计配置数/窗口新增商机/窗口新增配置数）、逐桶序列（各期新增商机/新增配置数/平台分布）、"
            "平台分布与机箱形态分布（按商机数，缺省计「未分类」）、销售人员排行，以及本周/本月小窗明细（周数据/月数据两节的数据源）。"
            "口径与商机线索页同一实现：status 排除 ai_office/deleted；平台/机箱读需求单 slots（current 优先、空则最新 draft）；"
            "配置数=每商机 status=active 最大 version 报价单的 config_count 求和。覆盖范围外的维度钻取走 query_data。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "统计窗口起始日 YYYY-MM-DD（= 报告契约的数据范围起始）"},
                "end": {"type": "string", "description": "统计窗口结束日 YYYY-MM-DD（= 报告契约的数据范围结束）"},
            },
            "required": ["start", "end"],
        },
        "handler": "app.services.agent_tool_handlers._tool_opportunity_stats",
    },
}
