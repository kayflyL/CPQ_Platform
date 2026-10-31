# -*- coding: utf-8 -*-
"""工具声明清单·办公协作域（同事记忆/流程建议）（第 7 步工具声明面，2026-10-31 自 agent_tool_specs 迁入）。

条目 = 操作 + 契约（读写/确认/回读，MCP 注解命名）+ 画布产物卡 + 参数 schema。
本模块零 import：handler 用点串引用，注册时由 build_tool_registry 惰性解析。
"""
TOOLS = {
    "colleague_memory": {
        "contract": {"effects": "write", "confirm_policy": "none", "idempotent_hint": False,
                         "destructive_hint": False, "target_entity": "colleague_memory"},

       "category": "self",
        "summary": "维护你自己的同事长期记忆：write 记住跨会话长期有效的事实与偏好（仅当前用户可见），retire 失效过时条目，list/view 查询。一次性任务、本轮会话状态不写入。",
        "description": ("【同事长期记忆】你是哪个同事，这份记忆就归谁（自动绑定当前角色）。"
                        "写入的记忆仅对当前用户可见（该用户的对话独享），不是全员共享知识。"
                        "何时 write：对话中出现值得跨会话长期记住的用户画像/偏好反馈/业务事实/行为指引"
                        "（如「客户王工偏好周三沟通」「张总那边要求全国产化交付」）。"
                        "何时不写：一次性任务、本轮会话状态、临时上下文、客套话——这些不是长期记忆。"
                        "写入是一条提炼过的事实句，不是对话摘录；拿不准分型先 list 查看现有记忆。"
                        "信息变化时：write 新事实 + retire 旧条目（新旧矛盾用 retire 解决，不硬覆盖）。"
                        "用户明说「忘掉/别记这个」时立即 retire。置顶/手工/公共域条目无权失效。"),
        "default_enabled": False,
        "handler": "app.services.agent_tool_handlers._tool_colleague_memory",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "view", "write", "retire"],
                           "description": "list=看自己的记忆清单；view=看单条详情；write=写入一条；retire=失效一条"},
                "type": {"type": "string", "enum": ["user_profile", "preference", "business_fact", "guide"],
                         "description": "write 时：记忆分型（user_profile=用户画像/preference=偏好反馈/business_fact=业务事实/guide=行为指引）"},
                "content": {"type": "string", "description": "write 时：提炼后的事实句（一句，长期有效）"},
                "id": {"type": "integer", "description": "view/retire 时：记忆条目 id（来自 list 结果）"},
                "reason": {"type": "string", "description": "retire 时：失效原因（一句话）"},
            },
            "required": ["action"],
        },
    },
    "suggest_workflow": {

       "category": "self",
        "summary": "把对话中确认的完整需求整理为原文（requirement_text）并指定 workflow_key，向用户发起一张工作流启动确认卡。仅在用户消息构成你职责工作流内的完整需求、且用户尚未显式发起时调用；闲聊、零散提问、信息残缺时不调用。",
        "description": ("【工作流发起确认】对话中出现属于你职责工作流的完整需求时，把需求整理成原文并发起确认卡。"
                        "workflow_key 只能取当前角色可发起的工作流（取值不在清单内会被拒绝，结果给出 available 清单）；"
                        "requirement_text 是工作流首轮的实际输入，保留型号/数量/参数等细节，尽量贴近用户原话，不改写不缩水。"),
        "default_enabled": False,
        "handler": "app.services.agent_tool_handlers._tool_suggest_workflow",
        "parameters": {
            "type": "object",
            "properties": {
                "workflow_key": {"type": "string", "description": "要发起的工作流 key（只能取当前角色可发起清单内的值）"},
                "requirement_text": {"type": "string", "description": "用户需求的原文整理：保留型号/数量/参数细节，尽量贴近用户原话"},
                "reason": {"type": "string", "description": "发起理由（一句话，面向用户）"},
            },
            "required": ["workflow_key", "requirement_text"],
        },
    },
}
