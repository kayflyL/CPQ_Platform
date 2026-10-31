# -*- coding: utf-8 -*-
"""工具声明清单·报价交付域（第 7 步首样本，2026-10-31 自 agent_tool_specs 整体迁入）。

每个条目 = 操作 + 读写/确认/回读契约（MCP 注解命名）+ 画布产物卡 + 参数 schema。
本模块零 import：handler 用点串引用，注册时由 build_tool_registry 惰性解析。
新增域工具：在这里加一条 + 视需要补契约，引擎零改动（MANIFEST_MODULES 已挂本模块）。
"""
TOOLS = {
    "import_cost_sheet": {
        "contract": {"effects": "write", "confirm_policy": "stage+consent", "idempotent_hint": True,
                          "destructive_hint": False, "target_entity": "cost_sheet"},

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
        "handler": "app.services.agent_tool_handlers._tool_import_cost_sheet",
    },
    "submit_cost_sheet": {
        "contract": {"effects": "write", "confirm_policy": "stage+consent", "idempotent_hint": False,
                          "destructive_hint": False, "target_entity": "quotation"},

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
        "handler": "app.services.agent_tool_handlers._tool_submit_cost_sheet",
    },
    "set_quote_margin": {
        "contract": {"effects": "write", "confirm_policy": "stage+consent", "idempotent_hint": True,
                         "destructive_hint": False, "target_entity": "quotation",
                         "verify": "skill_tools_write.verify_set_quote_margin"},

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
        "handler": "app.services.agent_tool_handlers._tool_set_quote_margin",
    },
    "set_cost_prices": {
        "contract": {"effects": "write", "confirm_policy": "none", "idempotent_hint": True,
                        "destructive_hint": False, "target_entity": "cost_prices"},

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
        "handler": "app.services.agent_tool_handlers._tool_set_cost_prices",
    },
    "share_quote": {
        "contract": {"effects": "write", "confirm_policy": "none", "idempotent_hint": False,
                    "destructive_hint": False, "target_entity": "share_link",
                    "note": "customer 视角外发走独立人审闸（商机详情页发起审批，AI 不代办）"},

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
        "handler": "app.services.agent_tool_handlers._tool_share_quote",
    },
    "derive_cost_from_scheme": {
        "contract": {"effects": "write", "confirm_policy": "none", "idempotent_hint": True,
                                "destructive_hint": False, "target_entity": "cost_sheet"},

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
        "handler": "app.services.agent_tool_handlers._tool_derive_cost_from_scheme",
    },
    "import_bom_scheme": {
        "contract": {"effects": "write", "confirm_policy": "none", "idempotent_hint": True,
                          "destructive_hint": False, "target_entity": "bom_scheme"},

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
        "handler": "app.services.agent_tool_handlers._tool_import_bom_scheme",
    },
}
