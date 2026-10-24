# -*- coding: utf-8 -*-
"""agent_tool_specs —— 工具元数据 + registry 构建。声明 schema，不含业务实现。"""
from typing import List, Optional
from app.services.agent_tool_registry import ToolRegistry
from app.services.agent_tool_handlers import (
    _search_cases_handler, _tool_ask_user, _tool_catalog_search,
    _tool_choose_model, _tool_colleague_memory, _tool_create_opportunity,
    _tool_fill_requirement, _tool_import_cost_sheet, _tool_inspect_parts,
    _tool_opportunity_stats, _tool_query_data, _tool_query_parts,
    _tool_save_requirement_draft, _tool_select_parts, _tool_set_quote_margin,
    _tool_share_quote, _tool_import_bom_scheme, _tool_derive_cost_from_scheme,
    _tool_set_cost_prices, _tool_submit_cost_sheet, _tool_suggest_workflow)

# ── 工具元数据全集（name/description/parameters + handler）—— 画布可勾选启用 ──
_TOOL_SPECS = {
   "fill_requirement": {
        "summary": "登记客户已明确表达的需求到线索登记表（基础字段+部件清单）。仅在需求登记环节使用；关键信息缺时才反问客户，不臆造字段值。",
       "description": ("【需求分析·登记环节】把客户已明确表达的需求逐项登记到线索登记表："
                        "基础字段（服务器类型/平台类型/机箱形态/机型/数量/保修）与部件清单 kp_rows。"
                        "目录字段（服务器类型/平台类型/机箱形态/机型型号）取值来自在售目录，"
                        "客户明说的原样登记；未被明说的目录字段记为待确认（确认后才用于配件选型）。"
                        "非目录字段（数量/维保等）只登记客户真实表达/确认过的信息，缺失时才反问。"
                        "客户改口过的项带 replace=true。需求分析流程外不可用。"),
        "default_enabled": False,
        "handler": _tool_fill_requirement,
        # 参数 schema 从登记表字段契约动态生成（前端改登记表配置这里自动跟随，不写死字段词表）
        "parameters_factory": "app.services.skill_tools_fill.fill_tool_parameters",
    },
   "choose_model": {
        "summary": "在售机型候选选择：需求分析流程内用 model/model_id 从系统候选池锁定一台（接地，池外拒绝）；日常对话可只用 usage/type/series/form 浏览在售机型候选。无法决断时不锁定。",
        "description": ("【统一模型工具】需求分析流程·机型选配环节：从系统候选池锁定一个机型并说明理由，"
                        "model/model_id 只能取候选池内的值，池外取值一律拒绝；无法决断时不锁定。"
                        "同事对话/参考时可用 usage/server_type_name/series/form 浏览在售机型候选清单。日常对话只有浏览能力。"),
        "default_enabled": True,
        "handler": _tool_choose_model,
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "锁定时：候选池中的机型名（与 model_id 二选一）"},
                "model_id": {"type": "string", "description": "锁定时：候选池中的机型 id（优先）"},
                "reason": {"type": "string", "description": "锁定时：选定理由（一句话，面向客户）"},
                "usage": {"type": "string", "description": "浏览时：用途/场景关键词，如 web/数据库/虚拟化"},
                "server_type_name": {"type": "string", "description": "浏览时：服务器类型全名（从在售类型清单选）"},
                "series": {"type": "string", "description": "浏览时：产品系列 Orion/Polaris/Intel；不确定可省略"},
                "form": {"type": "string", "description": "浏览时：机箱形态 1U/2U/4U；不确定可省略"},
                "limit": {"type": "integer", "description": "浏览时：返回条数上限，默认 8"},
            },
        },
    },
   "colleague_memory": {
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
        "handler": _tool_colleague_memory,
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
        "handler": _tool_suggest_workflow,
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
   "query_parts": {
        "summary": "配件库候选检索：按品类+结构化规格(required_specs)/关键词收窄，返回有界候选（part_id/name/price/specs，price 按 price_access 门控）。需求分析流程内=选配通道（可 rows 按行批量召回）；流程外=日常只读浏览（limit 收窄）。锁定选料用 select_parts（仅流程内）。",
        "description": ("配件库取件/查价的精确通道：category 必填（已知要配哪一类件）；"
                        "required_specs 传结构化规格过滤（[{spec_key, op, value}]，AND，op 支持 >= <= > < = in）"
                        "把候选收窄到「真能对上需求」的料；keywords 传型号/规格关键词（如「50000」「DDR5」「6T」「LSI 9361-8i」）。"
                        "返回 {ok,mode,total,offset,next_offset,truncated,results}，results 只含 part_id/name/price/specs。截断时用 offset 翻页或加 required_specs 再收窄。"
                        "双模式：需求分析流程内=选配模式（mode=task，rows 传行清单 row_id 或 \"all\" 按行批量召回，每行用自己的类目+行描述去库召回）；"
                        "流程外=日常浏览模式（mode=browse，同参数只读检索，limit 上限 10，rows 不开放，不带回行清单状态）。"
                        "锁定选料走 select_parts(picks)（仅流程内），按料号名回库核对不上就拒绝。"
                        "库内 specs 字段因类目而异（NIC：Link Speed/Ports/接口；Memory：Capacity/Type/Speed；"
                        "Raid card：Cache/Ports/电容；SSD/HDD：Capacity/Media/Type）。库内带宽词以数值/型号词命名（1G/10G）；返回 spec_keys/note 里给出该类目可用字段。"
                        "命中 0 且返回 scope_note/out_of_scope 时：那是「库里有这个料，但不适配当前机型平台」"
                        "（附各料适配的平台）——这些料库内存在，不是「库里没有」。"),
        "default_enabled": False,
        "handler": _tool_query_parts,
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "行类目（如 Memory/NIC/CPU，取行清单里的 category；传 rows 时可不传）"},
                "required_specs": {"type": "array",
                    "items": {"type": "object",
                        "properties": {"spec_key": {"type": "string", "description": "库内 specs 字段"}, "op": {"type": "string", "enum": [">=", "<=", ">", "<", "=", "in"], "description": "比较符"}, "value": {"description": "比较值"}},
                        "required": ["spec_key", "op", "value"]},
                    "description": "结构化规格过滤（AND），如 [{spec_key:'Capacity',op:'>=',value:'6T'}]"},
                "keywords": {"type": "string", "description": "型号/规格关键词收窄（如「50000」「DDR5」「6T」「LSI 9361-8i」；可空=类目内按规格过滤）"},
                "series": {"type": "string", "description": "平台系列（流程内默认继承已锁定机箱；日常浏览忽略）"},
                "rows": {"type": ["string", "array"], "description": "批量按行召回（仅需求分析流程内）：rows=\"all\" 或行清单 row_id 列表；一次覆盖多行，传 rows 时 category 省略"},
                "limit": {"type": "integer", "description": "返回条数上限（流程内默认 8/上限 20；日常浏览默认 6/上限 10）"},
                "offset": {"type": "integer", "description": "跳过前 N 条用于翻页（默认 0；truncated=true 时翻页或加 required_specs）"},
                "response_format": {"type": "string", "enum": ["concise", "detailed"], "description": "concise=精简规格（默认），detailed=完整规格"},
            },
            "required": [],
        },
    },
   "inspect_parts": {
        "summary": "配件库统一只读钻取：action=part 看单件完整规格；row 看单行决策上下文；category 看类目字段/值域/命名；grep 按字面或正则扫全库定位。命中与样例均非候选，锁定仍走 query_parts + select_parts。",
        "description": ("【需求分析·配件选配】把 query_parts 检索不到或看不全的信息钻取出来。"
                        "一个工具四个动作，避免「看单件/看单行/看类目/扫库定位」各占一个工具："
                        "action=part：name 或 part_id 打开一颗料，回完整 specs/价格/类目；跨类目同名时用 category 收窄。"
                        "action=row：row_id 或 row 打开一行待选型行，回描述/数量/specified/当前结局/库内按该行描述实时召回的紧凑候选。"
                        "action=category：category 打开类目目录页，回库内名/别名/件数/specs 字段与取值样例/价格区间/命名样例/适配件数；不确定字段值怎么写时先看它。"
                        "action=grep：pattern 扫全库（默认字面，regex=true 正则），回命中类目、料号与命中片段；不做语义等价，词翻不出时先看 action=category。"
                        "只读：零写入，返回内容不登记候选；锁定必须 query_parts 取候选后 select_parts 按料号名落行。"),
        "default_enabled": False,
        "handler": _tool_inspect_parts,
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["part", "row", "category", "grep"], "description": "钻取动作：part 看单件 / row 看单行 / category 看类目 / grep 扫全库"},
                "part_id": {"type": "string", "description": "action=part：库内行号（一般用 name；历史记录里带 id 时才用）"},
                "name": {"type": "string", "description": "action=part：料号名（库内真实料号名，如 LSI 9361-8i；与 part_id 二选一）"},
                "category": {"type": "string", "description": "action=part/category/grep：类目（库内名如 NIC/Memory，或中文别名如 网卡/内存）；part 跨类目同名时限定，category 传空回全部真实类目，grep 不传扫全库"},
                "row_id": {"type": "string", "description": "action=row：该行的公开编号（行清单里给出的 row_id 原文）；解析不到回 row_unknown 并附 available 行清单"},
                "row": {"type": "string", "description": "action=row：该行的行键（与 row_id 二选一；同样只能用清单里的原文）"},
                "pattern": {"type": "string", "description": "action=grep：要搜的词（如 9361 / CX6 / NVMe / LSI）；多个词用空白或 | 分隔 = 任一命中"},
                "fields": {"type": "string", "enum": ["both", "name", "specs"], "description": "action=grep：搜名称 / 规格值 / 两者（默认 both）"},
                "spec_key": {"type": "string", "description": "action=grep：只在某个 specs 字段的值里搜（如 Capacity、接口）"},
                "regex": {"type": "boolean", "description": "action=grep：true = pattern 按正则解释（大小写不敏感）；默认 false = 字面串"},
                "limit": {"type": "integer", "description": "action=grep：返回命中件数上限（默认 20，硬上限 100）"},
                "offset": {"type": "integer", "description": "action=grep：跳过前 N 件用于翻页（默认 0）"},
            },
            "required": ["action"],
        },
    },
   "select_parts": {
        "summary": "配件落地锁定：把 AI 选定的料号逐行落为库内真实料号（按「类目+料号名」回库核对，核对不上就拒绝）。同一行可提交多条 picks（组合）；每行要么锁定、要么由客户确认。",
        "description": ("【需求分析·配件选配落地】把未匹配的登记部件行批量锁定为库内真实料号。"
                        "落料凭据是**料号名**：服务端按「类目+名称」回库精确核对（库里没有业务料号），"
                        "唯一命中才落行、价格取库里最新值；库内同名多行回候选让你确认（不猜）；"
                        "库里根本没有就回 no_such_part——大脑无权凭空指定料号，客户端更不能。"
                        "选定按行身份（row_id）写入本节点私有状态、跨轮持久（描述改写不换身份，内容变了才失效重选）；"
                        "行键取自线索登记表原文、稳定不变。picks 每项：row_id（行清单原文，定位既有行）；要新增一行（同类目第二种需求）必须显式 new_row=true 并给 category+spec；"
                        "qty 组合件数，substitute=true 标近替代（须向客户说明）。"
                        "行清单里 specified=true 且非替代（库内有精确料）→ 直接锁定；"
                        "specified=true 但标了 substitute（库内无精确料）→ 只登记推荐=recommended，并立即调 ask_user 问替代/缺失处理；"
                        "specified=false（客户未写明）→ 你按需求代选一颗，只登记推荐=recommended，并立即调 ask_user 问客户选哪颗（推荐作默认项）"
                        "；recommended 不能当作已锁定、也不能静默丢弃。需求分析流程外不可用。"),
        "default_enabled": False,
        "handler": _tool_select_parts,
        "parameters": {
            "type": "object",
            "properties": {
                "picks": {
                    "type": "array",
                    "description": "逐行选定；同一行可多件（组合）",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row_id": {"type": "string", "description": "该行的公开编号：**必须取行清单里给出的 row_id 原文**（引擎铸造的身份，描述改写也不变）。解析不到回 row_unknown 并附可用 row_id 清单"},
                            "row": {"type": "string", "description": "row_id 的等价别名（行键原文）"},
                            "category": {"type": "string", "description": "新增行必填（配合 new_row=true）；既有行不必传"},
                            "description": {"type": "string", "description": "新增行必填：这一行要什么（与 spec 同义）。只给类目名会被拒（spec_required）——不铸幽灵行"},
                            "spec": {"type": "string", "description": "新增行要什么（与 description 同义；二者填一个）"},
                            "new_row": {"type": "boolean", "description": "显式声明要新增一行（如同类目第二种需求）。缺省 false：row_id 解析不到就拒收（row_unknown），绝不靠措辞相似度认领、也不悄悄铸新行"},
                            "part_id": {"type": "string", "description": "库内行号（一般用 name 报料号名）"},
                            "name": {"type": "string", "description": "料号名（库内真实料号名：query_parts/inspect_parts(action=part) 返回的 name；跨类目同名时带 category）"},
                            "reason": {"type": "string", "description": "该行匹配依据（一句话）；specified=false 的必填行只登记推荐，勿声称锁定"},
                            "qty": {"type": "integer", "description": "该行件数（组合需求必填，如 64G×12 → qty=12）。在上下文「已锁定机型扩展能力」的物理上限内推荐（GPU 位/内存槽/盘位/CPU 路）；超界会被拒，换更大单条容量凑总量"},
                            "substitute": {"type": "boolean", "description": "近替代申报：true=非精确匹配的替代件"},
                        },
                        "required": ["reason"],
                    },
                },
            },
            "required": ["picks"],
        },
    },
   "ask_user": {
        "summary": "把需要客户决策的问题升格为结构化选项卡（question 一句话 + options 2-4 个）。一回合一卡；需求分析流程内的客户拍板场景使用。",
       "description": ("【需求分析·大脑回合】把需要客户决策的问题升格为结构化选项卡"
                        "（question 一句话 + options 2-4 个 label）。问题绑定某一部件行时带 row=行键原文，"
                        "客户点击后：选项带 pick 即锁定该料号，带 pick_all 即批量锁定全部推荐行，否则答案记进该行的补充回答；"
                        "确认目录字段（服务器类型/平台类型/机箱形态）时绑定 slot=字段 key（如 server_type），"
                        "选项带 value=规范值 时按 value 落库（label 只作展示）。"
                        "行卡（带 row）的出路选项由引擎补齐：「换近替代」（pick=库内候选料）与"
                        "「保持原需求」（waived=true：行保留 + 标注「库内无料、客户已知悉」，终检放行）；"
                        "客户不需要这个类目时用 absent。"
                        "row 取行清单给出的 row_id 原文（等价别名会被归一）：解析不到回 row_unknown，"
                        "已锁定/已了结的行也会被拒收（确需重开该行再问时带 reopen=true）。"
                        "需求分析流程外不可用。"),
        "default_enabled": False,
        "handler": _tool_ask_user,
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "向客户确认的问题（一句话，用客户的语言）"},
                "options": {
                    "type": "array",
                    "description": "2-4 个互斥选项；某选项就是库内候选料时把该料带上 pick（并把推荐数量带上 qty），客户点选即落地",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "选项文案（客户点选的值）"},
                            "description": {"type": "string", "description": "选项补充说明（可选）"},
                            "recommended": {"type": "boolean", "description": "该选项是否是你的推荐项（客户界面上会标「推荐」）"},
                            "qty": {"type": "integer", "description": "该选项推荐数量（客户可在卡上步进调整）。按已锁定机型扩展能力的物理上限与需求总量推荐（如 768GB÷64G=12 条），别只报型号不报数量"},
                            "qty_max": {"type": "integer", "description": "数量上限（可选；不填则取行申报量与机型物理边界的较大值）"},
                            "pick": {"type": "object",
                                     "description": "该选项对应的库内候选料（取 query_parts 返回的 part_id/name/price）。带上后客户点选即锁定该料号；不带则点击只作该行的补充说明、不会落地。",
                                     "properties": {"part_id": {"type": "string"}, "name": {"type": "string"},
                                                    "price": {"type": "number"}, "qty": {"type": "integer"}}},
                            "absent": {"type": "string", "description": "类目级逃生选项：客户不需要这个类目（如 GPU 不配/自备）时填类目名"},
                            "pick_all": {"type": "boolean", "description": "套装整体接受项：该选项=接受当前全部推荐态行（≥2 行 AI 推荐待确认时用）；点选后所有推荐行一次性批量锁定"},
                            "waived": {"type": "boolean", "description": "行的第三结局选项：库内确实没有该行要的料，客户已知悉并保持原需求（行保留 + 标注，终检放行）。与 row 一起用"},
                            "slot": {"type": "string", "description": "该选项写入的登记表字段 key（目录字段确认用，如 platform_type）"},
                            "value": {"type": "string", "description": "该选项对应的规范值（目录字段确认用；label 是给客户看的文案，value 是落库值）"},
                        },
                        "required": ["label"],
                    },
                },
                "row": {"type": "string", "description": "该问题绑定的部件行（可选）：行清单里的 row_id 原文"},
                "reopen": {"type": "boolean", "description": "该行已锁定/已了结时是否仍然发问（默认 false：拒收，避免把同一行反复问客户）。仅当你确实要重开这一行时置 true"},
                "slot": {"type": "string", "description": "该问题绑定的登记表字段 key（可选）。目录字段（server_type/platform_type/chassis_form）必须绑定，客户点选后系统自动登记确认值"},
            },
            "required": ["question", "options"],
        },
    },
   "catalog_search": {
        "summary": "查询在售目录：kind=types/models/parts/meta 取类型、机型、配件或元候选清单；是目录字段与价格的事实来源。",
       "description": ("查询在售目录：kind=types 查类型清单；kind=models 按类型/系列/形态查机型（含价格）；"
                        "kind=parts 按品类查配件清单（可带 series 过滤适配平台）；"
                        "kind=meta 一次返回类型/系列/形态三个候选清单（轻量，推荐用来对目录字段做初判）"
                        "——推荐的事实来源"),
        "default_enabled": False,
        "handler": _tool_catalog_search,
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["types", "models", "parts", "meta"], "description": "查询种类"},
                "type_name": {"type": "string", "description": "服务器类型全名（kind=models 时可选）"},
                "category": {"type": "string", "description": "配件品类（kind=parts 时必填，如 CPU/Memory/GPU/HDD SSD/Raid card）"},
                "series": {"type": "string", "description": "平台系列（可选；kind=parts 时按适配过滤）"},
                "form": {"type": "string", "description": "机箱形态如 2U/4U（可选）"},
                "limit": {"type": "integer", "description": "返回条数上限，默认 8"},
            },
            "required": ["kind"],
        },
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
                "tags": {"type": "array", "items": {"type": "string"}, "description": "场景标签过滤（可选），如 ['AI','8卡GPU','Polaris','4U']"},
            },
        },
        # handler 由 build_tool_registry 按 case 配置（case_source/top_k/match）注入
        "handler": None,
    },
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
        "handler": _tool_query_data,
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
        "handler": _tool_opportunity_stats,
    },
   "create_opportunity": {
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
        "handler": _tool_create_opportunity,
    },
   "save_requirement_draft": {
        "summary": "把整理好的客户需求存为商机需求单草稿（不提交、不影响当前版本）。商机可用 customer_name 指认（缺省用会话绑定商机）；slots 传结构化字段，requirement_text 传需求原文。",
       "category": "business",
        "default_enabled": False,
        "description": (
            "把对话中确认的客户需求落到商机的需求单草稿：slots 放结构化字段（server_type/server_model/"
            "platform_type/chassis_form/purchase_qty/warranty_years 等登记表契约键），requirement_text 放需求原文整理。"
            "只生成/更新草稿，不推进流程、不覆盖当前版本；字段值只登记用户真实表达或确认过的内容，缺什么向用户问什么，不臆造。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "opportunity_id": {"type": "string", "description": "商机ID（缺省用当前会话绑定的商机）"},
                "requirement_text": {"type": "string", "description": "客户需求的原文整理（保留型号/数量/参数细节）"},
                "slots": {"type": "object", "description": "登记表字段键值（可选，按需求登记表契约键）"},
            },
            "required": ["requirement_text"],
        },
        "handler": _tool_save_requirement_draft,
    },
   "import_cost_sheet": {
        "summary": "处理附件：不带商机=仅解析预览（零落库，先把识别结果给用户）；带 customer_name/opportunity_id=解析并成本草稿+归档原件；archive_only 纯归档到环节桶。附件缺省取本人会话暂存或商机桶最新；支持 parse_overrides 修正与 sheet_id 原地重导。",
        # 产物卡=工具的属性（成功落草稿才发，仅解析预览静默）：一次声明，所有挂此工具的工作流通用
        "artifact_card": {"on_tool": "import_cost_sheet", "artifact_type": "cost_sheet_parse",
                          "title": "成本表解析结果", "summary": "$result.note",
                          "refs": {"opportunity_id": "$view.opp.opportunity_id",
                                   "sheet_id": "$result.sheet_id"}},
       "category": "business",
        "default_enabled": False,
        "description": (
            "两段式：先看后落。不带商机调用=仅解析预览（返回配置/机型/行数摘要，零副作用），"
            "大脑把识别结果转述给用户、商机由用户确认；带 customer_name 或 opportunity_id 首调="
            "解析预览+确认卡（needs_confirmation），用户在卡片上点确认后带同一参数加 confirm=true "
            "重调才落草稿+原件归档进「成本核算」桶。解析不对时带 parse_overrides 修正"
            "（{skip_rows, col_binds, region_ends}），重导传 sheet_id 原地更新草稿。"
            "archive_only=true 是纯归档动词（必须有商机，category：lead_requirement/technical/"
            "requirement/sent_quote）。只生成草稿不提交不发通知；解析失败原因原样带回。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "opportunity_id": {"type": "string", "description": "商机ID（可选；不带=仅解析预览不落草稿）"},
                "customer_name": {"type": "string", "description": "客户名称（用户口中的叫法即可，工具自行解析；歧义时返回候选）。带上=落草稿+归档"},
                "attachment_id": {"type": "string", "description": "附件ID（可选；缺省取商机桶最新表格，没有则取本人会话暂存最新）"},
                "archive_only": {"type": "boolean", "description": "true=纯归档不解析（把附件挂到商机环节桶）"},
                "category": {"type": "string", "enum": ["lead_requirement", "technical", "requirement", "sent_quote"], "description": "商机环节桶（archive_only 时用）：线索登记/BOM方案/成本核算/报价单；缺省未分类"},
                "parse_overrides": {"type": "object", "description": "解析修正补丁 {skip_rows:[行号], col_binds:{字段:列字母}, region_ends:{区域:结束行}}（来自用户纠正或同事记忆）"},
                "sheet_id": {"type": "integer", "description": "上次导入返回的成本表ID（修正重导时原地更新草稿，不产生新版本）"},
            },
            "required": [],
        },
        "handler": _tool_import_cost_sheet,
    },
   "submit_cost_sheet": {
        # 不发产物卡：报价单卡只留最终一张（加价完成后由 set_quote_margin 发），
        # 草稿/最终两张卡打开同一个查看器=重复打扰（2026-10-22 用户定）
        "summary": "提交成本表并转为报价单草稿（两阶段：首次调用只返回 preview，向用户转述并等明确同意后带同一参数加 confirm=true 重调才执行）。执行会推进流程并通知相关人。",
       "category": "business",
        "default_enabled": False,
        "description": (
            "「提交到报价单」动作：提交成本核算草稿，生成成本口径的报价单草稿并转为可编辑报价单，"
            "流程推进到报价单节点，报价处理人与商机归属人收到通知。两阶段确认：首次调用不带 confirm，"
            "只返回 preview（表名/配置数/将发生的事）；用户明确同意后带同一参数加 confirm=true 重调执行，"
            "用户拒绝或要改参数时，本次流程在预览处终止。前置条件（有已提交的 BOM 方案、流程阶段到位）"
            "不满足时错误原样带回。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "opportunity_id": {"type": "string", "description": "商机ID（与 customer_name 二选一；都缺省用会话绑定商机）"},
                "customer_name": {"type": "string", "description": "客户名称（用户口中的叫法即可，工具自行解析；歧义时返回候选）"},
                "sheet_id": {"type": "integer", "description": "成本表数字ID（import_cost_sheet 结果里有）"},
                "assignee_name": {"type": "string", "description": "报价节点处理人姓名（可选；缺省用现有指派/默认规则）"},
                "confirm": {"type": "boolean", "description": "用户明确同意后置 true 重调（参数须与预览时完全一致）；首调不传"},
            },
            "required": ["sheet_id"],
        },
        "handler": _tool_submit_cost_sheet,
    },
   "set_quote_margin": {
        "artifact_card": {"on_tool": "set_quote_margin", "artifact_type": "quotation",
                          "title": "最终报价单", "summary": "$result.note",
                          "refs": {"opportunity_id": "$view.opp.opportunity_id",
                                   "quotation_id": "$result.quotation_id"}},
        "summary": "对报价单统一设置加价率并按工作台同口径重算价格（两阶段确认）。需要价格权限（price_access×用户RBAC，无权直接拒绝）；quotation_id 缺省取该商机最新报价单。",
       "category": "business",
        "default_enabled": False,
        "description": (
            "「告诉利率、自动加价」动作：把 Key Parts 行加价率与各配置 L6 加价率统一设为指定值，"
            "final_price 与整单快照按报价工作台完全相同的公式重算后保存。两阶段确认：首次调用只返回改前/改后"
            "总额对比；用户同意后带同一参数加 confirm=true 重调才写库。价格权限双重门控：同事未开 "
            "price_access 或当前账号无价格权限时直接拒绝。报价单处于外发审批中时会被锁定（错误带回），"
            "已有外发许可的单改价后许可自动失效需重新审批——这是保护，不是故障。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "opportunity_id": {"type": "string", "description": "商机ID（与 customer_name 二选一；都缺省用会话绑定商机）"},
                "customer_name": {"type": "string", "description": "客户名称（用户口中的叫法即可，工具自行解析；歧义时返回候选）"},
                "quotation_id": {"type": "string", "description": "报价单ID（可选；缺省取该商机最新一份）"},
                "margin_pct": {"type": "number", "description": "加价率百分数（如 15 表示加价 15%）"},
                "apply_to": {"type": "string", "enum": ["kp", "l6", "kp+l6"], "description": "作用范围，缺省 kp+l6（KP 配件行 + L6 整机）"},
                "confirm": {"type": "boolean", "description": "用户明确同意后置 true 重调（参数须与预览时完全一致）；首调不传"},
            },
            "required": ["margin_pct"],
        },
        "handler": _tool_set_quote_margin,
    },
   "set_cost_prices": {
        "summary": "把用户在聊天里报来的价格回写进成本表草稿行（配置名+Catalogue 定位行，页面同源保存）。",
        "category": "business",
        "default_enabled": False,
        "description": (
            "「缺价补充」动作：案台显示成本表缺价、用户直接在聊天里报价格时，"
            "把价格写进成本表草稿的对应行。prices=[{config_name, catalogue, base_price}]，"
            "一行一条；catalogue 按行首列去空格精确匹配，对不上的行原样列回（missed）。"
            "只写草稿不提交；价格补齐后案台探针放行，流程继续。另一条等效通道："
            "成本表产物卡的编辑模式（页面同源保存）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "opportunity_id": {"type": "string", "description": "商机ID（与 customer_name 二选一；都缺省用会话绑定商机）"},
                "customer_name": {"type": "string", "description": "客户名称（用户口中的叫法即可，工具自行解析）"},
                "sheet_id": {"type": "number", "description": "成本表ID（缺省取该商机最新未归档成本表）"},
                "prices": {"type": "array", "items": {"type": "object",
                            "properties": {"config_name": {"type": "string"},
                                           "catalogue": {"type": "string"},
                                           "base_price": {"type": "number"}},
                            "required": ["config_name", "catalogue", "base_price"]},
                            "description": "要补的价格清单，一项=一行"},
            },
            "required": ["prices"],
        },
        "handler": _tool_set_cost_prices,
    },
   "ask_user": {
        "summary": "向用户提问（反问的一种结构化形式）：描述问题的形状，系统渲染成选择卡或表单卡并等待回答。",
        "category": "business",
        "default_enabled": False,
        "description": (
            "「向人提问」动作：需要用户给信息或做选择时调用。载荷即问题的形状："
            "有 options（2~4 个 {label,description?,recommended?}）渲染成单选卡（系统自动追加"
            "「Other」自由输入，recommended 的排首位带推荐标记）；有 fields（1~8 个 "
            "{key,label,type?,placeholder?}）渲染成表单卡；二者只能给一个。一次只问一个问题——"
            "已有未回答的问题时本工具会报错。用户回答后内容结构化回流对话，据此调用后续工具。"
            "有明确候选且说得出名字就用 options，开放信息才用 fields；都不合适直接文本反问，不必调本工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "问题正文（如：CF1 的 L6 整机价是多少？）"},
                "hint": {"type": "string", "description": "给用户的补充说明（一句话）"},
                "options": {"type": "array", "items": {"type": "object",
                            "properties": {"label": {"type": "string"},
                                           "description": {"type": "string"},
                                           "recommended": {"type": "boolean"}},
                            "required": ["label"]},
                            "description": "候选项，2~4 个；recommended=true 的排首位带推荐标记"},
                "fields": {"type": "array", "items": {"type": "object",
                            "properties": {"key": {"type": "string"},
                                           "label": {"type": "string"},
                                           "placeholder": {"type": "string"},
                                           "type": {"type": "string", "enum": ["text", "number"]}},
                            "required": ["key", "label"]},
                            "description": "输入字段清单，1~8 个；与 options 二选一"},
            },
            "required": ["title"],
        },
        "handler": _tool_ask_user,
    },
   "share_quote": {
        "artifact_card": {"on_tool": "share_quote", "artifact_type": "share_link",
                          "title": "分享链接已生成", "summary": "$result.note",
                          "refs": {"opportunity_id": "$view.opp.opportunity_id",
                                   "share_path": "$result.share_path",
                                   "quotation_id": "$result.quotation_id"}},
        "summary": "生成报价单的免登录分享链接（服务端渲染 xlsx 并归档）。view 只开放 scheme/internal/cost；customer 视角=报价外发，一律拒绝并指引走外发审批闸。",
       "category": "business",
        "default_enabled": False,
        "description": (
            "「返回一张报价单」动作：对商机最新（或指定）报价单生成免登录分享链接，服务端渲染 xlsx 并归档到商机附件。"
            "view=scheme 只出方案价、internal 含对内价格、cost 含成本价（需对内导出权限）；"
            "customer 视角是正式外发，必须走外发审批闸（商机详情页发起、总监批准），本工具一律拒绝代办。"
            "链接可过期（缺省 7 天，上限 30）、可撤销、下载留痕。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "opportunity_id": {"type": "string", "description": "商机ID（与 customer_name 二选一；都缺省用会话绑定商机）"},
                "customer_name": {"type": "string", "description": "客户名称（用户口中的叫法即可，工具自行解析；歧义时返回候选）"},
                "quotation_id": {"type": "string", "description": "报价单ID（可选；缺省取该商机最新一份）"},
                "view": {"type": "string", "enum": ["scheme", "internal", "cost"], "description": "视角，缺省 internal"},
                "expiry_days": {"type": "integer", "description": "有效期天数，缺省 7，上限 30"},
            },
            "required": [],
        },
        "handler": _tool_share_quote,
    },
    "import_bom_scheme": {
        "summary": "把用户上传的方案表（无价格列的结构表）落位为商机名下的方案表草稿。商机未绑定时先提供建商机或挂已有。",
        "artifact_card": {"on_tool": "import_bom_scheme", "artifact_type": "bom_scheme",
                          "title": "方案表已落草稿", "summary": "$result.note",
                          "refs": {"opportunity_id": "$view.opp.opportunity_id",
                                   "bom_scheme_id": "$result.bom_scheme_id"}},
        "category": "business",
        "default_enabled": False,
        "description": (
            "「方案表落位」动作：解析方案表结构（不要求价格列），落成商机名下的方案表草稿，"
            "附件随单归档。与成本表导入共用结构解析，价格列缺失不报错。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "opportunity_id": {"type": "string", "description": "商机ID（与 customer_name 二选一；都缺省用会话绑定商机）"},
                "customer_name": {"type": "string", "description": "客户名称（用户口中的叫法即可，工具自行解析）"},
                "attachment_id": {"type": "string", "description": "方案表附件 ID（缺省取该商机最新可解析表格）"},
            },
            "required": [],
        },
        "handler": _tool_import_bom_scheme,
    },
    "derive_cost_from_scheme": {
        "summary": "成本核算：由商机名下的方案表推导成本表草稿，关键配件行按配件库价填充（未命中标注待核）。方案自动提交推进到成本核算。",
        "artifact_card": {"on_tool": "derive_cost_from_scheme", "artifact_type": "cost_sheet_parse",
                          "title": "成本表已由方案推导", "summary": "$result.note",
                          "refs": {"opportunity_id": "$view.opp.opportunity_id",
                                   "sheet_id": "$result.sheet_id"}},
        "category": "business",
        "default_enabled": False,
        "description": (
            "「库价推导」动作：取商机名下的方案表（缺省最新草稿/当前方案），提交推进到成本核算节点，"
            "并生成挂接该方案的成本表草稿；Key Parts 行按名称匹配配件库最新价填充，未命中行标注「库价待核」。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "opportunity_id": {"type": "string", "description": "商机ID（与 customer_name 二选一；都缺省用会话绑定商机）"},
                "customer_name": {"type": "string", "description": "客户名称（用户口中的叫法即可，工具自行解析）"},
                "bom_scheme_id": {"type": "string", "description": "方案表ID（可选；缺省取最新草稿/当前方案）"},
            },
            "required": [],
        },
        "handler": _tool_derive_cost_from_scheme,
    },
}

# 全部可用工具名（给画布抽屉候选 + 默认值用）
ALL_TOOL_NAMES = list(_TOOL_SPECS.keys())


def _default_tool_text(name: str, spec: dict) -> dict:
    """某工具的四字段默认文本（= agent_tool_text 的种子值）。"""
    from app.services.agent_tool_display import default_display
    d = default_display(name)
    return {
        "display_name": d["display_name"],
        "one_liner": d["one_liner"],
        "description": d["description"] or spec["description"],
        "model_brief": spec.get("summary") or spec["description"],
    }


def tool_text_seed_rows() -> List[dict]:
    """agent_tool_text 的启动种子（DB 唯一权威源的迁移种子，运行时不读这里）：
    人类层默认值（agent_tool_display）+ 模型契约默认值（summary）。"""
    return [dict({"name": name}, **_default_tool_text(name, spec))
            for name, spec in _TOOL_SPECS.items()]


def _tool_text_overrides() -> dict:
    """rules.agent_tool_text 覆盖行（fail-safe：DB 异常时回代码默认，不影响回合）。"""
    try:
        from app.repository.agent_tool_text_repo import AgentToolTextRepository
        repo = AgentToolTextRepository()
        try:
            return repo.get_overrides()
        finally:
            repo.close()
    except Exception:
        import logging
        logging.getLogger(__name__).warning("tool text overrides 读取失败，回代码默认", exc_info=True)
        return {}


def _spec_parameters(spec: dict) -> dict:
    """取工具参数 schema：带 parameters_factory 的惰性解析（如 fill_requirement 的 schema
    从登记表字段契约实时生成——导入期不读 DB，每次取用拿最新配置），否则用静态声明。"""
    factory_path = str(spec.get("parameters_factory") or "").strip()
    if factory_path:
        try:
            import importlib
            module_name, _, func_name = factory_path.rpartition(".")
            return getattr(importlib.import_module(module_name), func_name)()
        except Exception:
            import logging
            logging.getLogger(__name__).exception("工具参数工厂解析失败 %s", factory_path)
    return spec.get("parameters") or {"type": "object", "properties": {}}


# ── 工具轨迹记录（通用渲染，不认任何工具名）─────────────────────────────
# 大脑跨回合注入的工作记录由这里生成：只从调用实参/结果里抽事实（标量保留、
# 长串截断、列表只报条数），不写任何按工具名分支的文案。新增工具零改动即可被记录。
_TRACE_STR_MAX = 60
_TRACE_LIST_MAX = 8
_TRACE_DEPTH_MAX = 2
_TRACE_SKIP_KEYS = frozenset({"ok", "error", "current", "rows", "results", "message", "answer"})


def _trace_trim(value, depth: int = 0):
    """把一次调用的实参压到可读体量：长串截断、长列表只留前几项、深对象折叠。"""
    if isinstance(value, str):
        return value if len(value) <= _TRACE_STR_MAX else value[:_TRACE_STR_MAX] + "…"
    if isinstance(value, dict):
        if depth >= _TRACE_DEPTH_MAX:
            return "{…}"
        return {str(k): _trace_trim(v, depth + 1) for k, v in list(value.items())[:12]}
    if isinstance(value, (list, tuple)):
        if depth >= _TRACE_DEPTH_MAX:
            return len(value)
        return [_trace_trim(v, depth + 1) for v in list(value)[:_TRACE_LIST_MAX]]
    return value


def trace_note(call: dict) -> Optional[dict]:
    """一次工具调用的工作记录（通用；引擎侧不认识工具名）。

    形状：{"tool": 名, "args": 截断实参, "ok": …, "error": …, "result": 标量/条数摘要}。
    用途：跨回合注入「你已做过什么」，避免大脑每轮从零开始重复检索/重复提问。
    """
    c = call if isinstance(call, dict) else {}
    name = str(c.get("name") or "").strip()
    if not name:
        return None
    args = c.get("args") if isinstance(c.get("args"), dict) else {}
    res = c.get("result") if isinstance(c.get("result"), dict) else {}
    note: dict = {"tool": name}
    trimmed = {k: v for k, v in args.items() if v not in (None, "", [], {})}
    if trimmed:
        note["args"] = _trace_trim(trimmed)
    if "ok" in res:
        note["ok"] = bool(res.get("ok"))
    if res.get("error"):
        note["error"] = str(res["error"])[:80]
    extra = {}
    for key, value in res.items():
        if str(key) in _TRACE_SKIP_KEYS:
            continue
        if isinstance(value, (int, float, bool)) or (isinstance(value, str) and len(value) <= _TRACE_STR_MAX):
            extra[str(key)] = value
        elif isinstance(value, (list, tuple)):
            extra[str(key)] = len(value)
    if extra:
        note["result"] = extra
    message = str(res.get("message") or "").strip()
    if message:
        note["message"] = message[:80]
    return note


def tool_catalog() -> List[dict]:
    """全量工具目录（无 handler），供前端「AI 工具」目录页与节点抽屉渲染。

    每个条目：name / category(selection|data) / display_name / one_liner（人类层）/
    summary（模型 FC 契约，DB 行说了算）/ description（人话详解）/ parameters / default_enabled /
    custom（与种子值不同的字段名，供前端标「已自定义」与恢复默认）。
    """
    overrides = _tool_text_overrides()
    out: List[dict] = []
    for name, spec in _TOOL_SPECS.items():
        defaults = _default_tool_text(name, spec)
        entry = {
            "name": name,
            "category": spec.get("category") or "workflow",
            "display_name": defaults["display_name"],
            "one_liner": defaults["one_liner"],
            "summary": defaults["model_brief"],
            "description": defaults["description"],
            "parameters": _spec_parameters(spec),
            "default_enabled": bool(spec.get("default_enabled", True)),
            "custom": [],
        }
        row = overrides.get(name) or {}
        for field in ("display_name", "one_liner", "description", "model_brief"):
            value = row.get(field)
            if not value:
                continue
            if field == "model_brief":
                entry["summary"] = value
            else:
                entry[field] = value
            if value != defaults[field]:
                entry["custom"].append(field)
        out.append(entry)
    return out


def registered_tool_ids() -> List[str]:
    """返回 agent_tools 注册表里所有工具 ID（供能力 spec 校验 / 默认工具取用）。"""
    return list(_TOOL_SPECS.keys())


def build_tool_registry(config: dict, allowed_tool_ids: list = None) -> ToolRegistry:
    """按节点 config 启用的工具集建 registry。

    config.enabled_tools: list[str] —— 启用的工具名（画布抽屉勾选）；
    未配置或空 → 默认启用全集（向后兼容）。
    allowed_tool_ids: list[str] —— AI 同事的 tool_ids 白名单；传 None 不限制，
    传 [] 表示同事不允许任何工具。
    """
    cfg = config or {}
    # 默认全集 = default_enabled=True 的工具；default_enabled=False（如 query_data）
    # 不进任何节点默认配置，需要时由调用方显式启用（避免改变现有推理流行为）
    enabled = cfg.get("enabled_tools") or [
        name for name, spec in _TOOL_SPECS.items() if spec.get("default_enabled", True)
    ]
    if allowed_tool_ids is not None:
        allowed_set = set(allowed_tool_ids)
        enabled = [name for name in enabled if name in allowed_set]
    reg = ToolRegistry()
    overrides = _tool_text_overrides()
    for name in enabled:
        spec = _TOOL_SPECS.get(name)
        if not spec:
            continue
        handler = spec["handler"]
        # search_cases 需要用户可配的 case 参数（case_source/top_k/match）→ 闭包注入
        if name == "search_cases":
            handler = _search_cases_handler(cfg)
        if handler is None:
            continue
        # 模型 FC 契约文本（原 summary）：DB 覆盖行优先，无覆盖用代码默认
        brief = (overrides.get(name) or {}).get("model_brief") or spec.get("summary")
        if name == "query_data":
            # schemas() 只暴露 summary——白名单必须挂进 brief 模型才看得见；
            # 模型看不到清单会裸写表名/猜表名，白名单外一律报错。
            from app.services.data_boundary import query_tables_allow
            tables = query_tables_allow()
            if tables:
                brief += "可读表（仅这些）：" + "、".join(tables) + "。"
        reg.register(name, spec["description"], _spec_parameters(spec), handler, summary=brief)
    return reg
