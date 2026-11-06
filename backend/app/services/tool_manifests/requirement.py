# -*- coding: utf-8 -*-
"""工具声明清单·需求分析域（登记/选型/目录查询/需求草稿）（第 7 步工具声明面，2026-10-31 自 agent_tool_specs 迁入）。

条目 = 操作 + 契约（读写/确认/回读，MCP 注解命名）+ 画布产物卡 + 参数 schema。
本模块零 import：handler 用点串引用，注册时由 build_tool_registry 惰性解析。
"""
TOOLS = {
    "fill_requirement": {
        "contract": {"effects": "write", "confirm_policy": "none", "idempotent_hint": True,
                         "destructive_hint": False, "target_entity": "requirement_slots"},

        "summary": "登记客户已明确表达的需求到线索登记表（基础字段+部件清单）。仅在需求登记环节使用；关键信息缺时才反问客户，不臆造字段值。",
       "description": ("【需求分析·登记环节】把客户已明确表达的需求逐项登记到线索登记表："
                        "基础字段（服务器类型/平台类型/机箱形态/机型/数量/保修）与部件清单 kp_rows。"
                        "目录字段（服务器类型/平台类型/机箱形态/机型型号）取值来自在售目录，"
                        "客户明说的原样登记；未被明说的目录字段记为待确认（确认后才用于配件选型）。"
                        "非目录字段（数量/维保等）只登记客户真实表达/确认过的信息，缺失时才反问。"
                        "客户改口过的项带 replace=true。需求分析流程外不可用。"),
        "default_enabled": False,
        "handler": "app.services.agent_tool_handlers._tool_fill_requirement",
        # 参数 schema 从登记表字段契约动态生成（前端改登记表配置这里自动跟随，不写死字段词表）
        "parameters_factory": "app.services.skill_tools_fill.fill_tool_parameters",
    },
    "choose_model": {
        "contract": {"effects": "write", "confirm_policy": "none", "idempotent_hint": True,
                     "destructive_hint": False, "target_entity": "server_model"},

        "summary": "在售机型候选选择：需求分析流程内用 model/model_id 从系统候选池锁定一台（接地，池外拒绝）；日常对话可只用 usage/type/series/form 浏览在售机型候选。无法决断时不锁定。",
        "description": ("【统一模型工具】需求分析流程·机型选配环节：从系统候选池锁定一个机型并说明理由，"
                        "model/model_id 只能取候选池内的值，池外取值一律拒绝；无法决断时不锁定。"
                        "同事对话/参考时可用 usage/server_type_name/series/form 浏览在售机型候选清单。日常对话只有浏览能力。"),
        "default_enabled": True,
        "handler": "app.services.agent_tool_handlers._tool_choose_model",
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "锁定时：候选池中的机型名（与 model_id 二选一）"},
                "model_id": {"type": "string", "description": "锁定时：候选池中的机型 id（优先）"},
                "reason": {"type": "string", "description": "锁定时：选定理由（一句话，面向客户）"},
                "usage": {"type": "string", "description": "浏览时：用途/场景关键词，如 web/数据库/虚拟化"},
                "server_type_name": {"type": "string", "description": "浏览时：服务器类型全名（从在售类型清单选）"},
                "series": {"type": "string", "description": "浏览时：产品系列 AMD/兆芯/Intel；不确定可省略"},
                "form": {"type": "string", "description": "浏览时：机箱形态 1U/2U/4U；不确定可省略"},
                "limit": {"type": "integer", "description": "浏览时：返回条数上限，默认 8"},
            },
        },
    },
    "select_parts": {
        "contract": {"effects": "write", "confirm_policy": "none", "idempotent_hint": True,
                     "destructive_hint": False, "target_entity": "kp_rows"},

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
        "handler": "app.services.agent_tool_handlers._tool_select_parts",
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
        "handler": "app.services.agent_tool_handlers._tool_query_parts",
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
        "handler": "app.services.agent_tool_handlers._tool_inspect_parts",
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
    "catalog_search": {

        "summary": "查询在售目录：kind=types/models/parts/meta 取类型、机型、配件或元候选清单；是目录字段与价格的事实来源。",
       "description": ("查询在售目录：kind=types 查类型清单；kind=models 按类型/系列/形态查机型（含价格）；"
                        "kind=parts 按品类查配件清单（可带 series 过滤适配平台）；"
                        "kind=meta 一次返回类型/系列/形态三个候选清单（轻量，推荐用来对目录字段做初判）"
                        "——推荐的事实来源"),
        "default_enabled": False,
        "handler": "app.services.agent_tool_handlers._tool_catalog_search",
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
    "save_requirement_draft": {
        "contract": {"effects": "write", "confirm_policy": "none", "idempotent_hint": True,
                               "destructive_hint": False, "target_entity": "requirement_draft"},

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
        "handler": "app.services.agent_tool_handlers._tool_save_requirement_draft",
    },
}
