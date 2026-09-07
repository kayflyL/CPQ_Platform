# -*- coding: utf-8 -*-
"""技能提示词 & 推理节点默认契约的 DB 引导（一次性空库播种；DB 运行后唯一权威）。

职责：在 rules.skill_prompt_template / rules.reasoning_node_default 为空时，把
旧的 system_config.skill_prompts（已存在的字段值）与「需求分析节点默认契约」写入新表。
只补缺失行，不覆盖已有行；运行后业务代码一律只读这两张表，绝不回退到本模块常量。
"""
from __future__ import annotations
import json
from datetime import datetime

from app.models.base import Rules_SessionLocal
from app.models.skill_config import SkillPromptTemplate, ReasoningNodeDefault
from app.models.system_config import SystemConfig

DEFAULT_SKILL_KEY = "requirement_analysis"

# 提示词面板字段顺序与界面 label（仅空库引导用；界面已有同名行则不动）
SKILL_PROMPT_SLOTS: list[dict] = [
  {"slot_key": "role_prompt", "name": "需求收集规则（role_prompt）", "sort_order": 1},
  {"slot_key": "extract_contract", "name": "抽取契约（extract_contract）", "sort_order": 2},
  {"slot_key": "gap_ask_prompt", "name": "缺口转述规则（gap_ask_prompt）", "sort_order": 3},
  {"slot_key": "price_rule_ok", "name": "价格可看规则（price_rule_ok）", "sort_order": 4,
   "template": "推荐必须带理由（价格/形态/场景匹配），不知道就查，禁止编造型号价格。"},
  {"slot_key": "price_rule_no", "name": "价格不可看规则（price_rule_no）", "sort_order": 5,
   "template": "你没有价格查看权限：目录查询结果不含价格，回复中禁止出现任何价格、金额、报价数字（凭记忆编造也不行）；推荐理由基于产品定位/形态/场景匹配。客户主动问价时，引导其联系成本核算或方案助手。"},
  {"slot_key": "data_rule", "name": "数据查询规则（data_rule）", "sort_order": 6,
   "template": "\n7. 需要业务数据（商机/报价/目录明细）时，用 query_data 执行只读 SELECT：先查 information_schema.tables / information_schema.columns 看清可读表与列，再写查询；工具返回的报错信息是修正提示，改 SQL 重试；被数据边界拒绝的表不要反复尝试。"},
  {"slot_key": "plan_rule", "name": "流程步骤规则（plan_rule）", "sort_order": 7,
   "template": "\n8. 【配置流程步骤】客户确认开始后引擎按固定流程执行：\n<<STEPS>>\n提议时用一两句自然预告这个流程（画布描述是你的素材，不必逐字罗列），让客户知道接下来会发生什么。\n"},
  {"slot_key": "gap_ack_template", "name": "选项卡点选确认语（gap_ack_template）", "sort_order": 8,
   "template": "客户刚在选项卡上点选确认了：<<CLICKS>>。请先用一句话自然确认收到（像「收到，GPU 就定 10× 曙云C550」），然后再转入下面的缺口确认，两段话合成一次回复。"},
  {"slot_key": "stream_chat_contract", "name": "流式输出协议（stream_chat_contract）", "sort_order": 9,
   "template": "\n\n【输出格式（流式对话）】\n- 你的正文会实时展示给用户：直接面向用户写自然中文，不要输出 JSON，不要用 action/final 等字段包装。\n- 需要调用工具时：先用一两句话告诉用户你要做什么，然后另起一行输出工具块，工具块必须是本轮输出的最后内容（其后不要再写字）：\n```tool\n{\"name\": \"工具名\", \"args\": {}}\n```\n- 工具结果会以「工具 X 返回：{...}」回传，据此继续：可以再调工具，也可以直接写最终回复。\n- 最终回复要完整成段、面向用户；工具未返回的数据（型号/价格/规格）严禁编造。\n"},
]

# 需求分析节点默认契约（唯一真源搬进 DB；仅空表播种，运行后以 DB 为准）
DEFAULT_REASONING_NODE_CONTRACT: dict = json.loads(r'''{
  "input": {
    "description": "接收客户自然语言需求与商机上下文",
    "goal": "记录并规范化客户原始需求",
    "output_artifact": "requirement_text",
    "deterministic": true
  },
  "agent_fill": {
    "description": "理解客户需求并登记结构化线索，信息不足时只问最关键问题",
    "goal": "把用户原话中的基础需求字段与部件（CPU/内存/盘/GPU/RAID/网卡/电源）逐项登记进线索登记表；保留用户原字面，不自行到目录匹配型号；信息不足时只问最关键问题",
    "output_artifact": "ext / requirement",
    "enabled_tools": [],
    "prompt": {
      "system_prompt": "你是需求理解助手。任务：把用户原始需求逐项登记到「线索登记表」：基础需求字段（服务器类型/系列/机箱形态/数量/保修）与部件（CPU/内存/硬盘/GPU/RAID/网卡/电源）。严格按用户原话登记，保留字面（型号、数量、单位、RAID 级别等不改写、不丢）；不自行到目录匹配或改写型号，型号匹配交给下游选型节点。用户没提到的字段留空；若缺“必填且未委托”的关键字段，只用一句自然中文问最关键的那一个；用户已委托（随便/都行）则留空交下游。只输出约定 JSON，不调用工具、不用 Markdown。特别注意：硬盘/存储容量必须写带单位的原文串（如 \"1.92T\"、\"48T\"，禁止只写 1.92 这种纯数字）；电源必须写瓦数+数量（如 3000W*2）；客户提到硬盘/固态/机械/存储/电源/GPU 时，必须逐类登记进对应字段，不要漏。"
    }
  },
  "model_reason": {
    "description": "按需求从在售目录中选定一台机型骨架",
    "goal": "先确认正确的服务器类型；调用 select_models 获取候选；若 type+form/series 无候选，则去掉 form 或 series 再查一次；只能从工具返回候选中选定一台，禁止编造",
    "output_artifact": "baselines / model_selection",
    "enabled_tools": [
      "select_models"
    ]
  },
  "kp_reason": {
    "description": "按原文与登记表缓存补全关键配件信号，工具落地真实料号",
    "goal": "原文决定覆盖范围，登记表仅作缓存；把原文提到的每一类配件都转为 select_parts 信号，多个盘组/GPU 组必须逐行列出；工具落地真实 SKU，禁止编造料号",
    "output_artifact": "kp_parts / kp_by_model",
    "enabled_tools": [
      "list_kp_categories",
      "select_parts",
      "resolve_part_alias",
      "compose_memory"
    ]
  },
  "compose": {
    "description": "按真实 BOM 模板组装 bom_scheme.configs",
    "goal": "把已锁机型与已落地配件组装成 plans",
    "output_artifact": "plans",
    "kp_source": "per_baseline",
    "psu_override_enabled": true,
    "psu_wattage_source": "ext.psu.wattage",
    "psu_qty_source": "ext.psu.qty",
    "deterministic": true
  },
  "output": {
    "description": "写回真实 requirement + bom_scheme，并交付给 AI Office/商机详情页",
    "goal": "确定性落库并交接 BOM 草稿",
    "output_artifact": "bom_scheme_draft",
    "output_kind": "bom_scheme_draft",
    "target": "bom_scheme",
    "payload_map": {
      "plans": "ctx.plans",
      "ext": "ctx.ext"
    },
    "deterministic": true,
    "final_contract": "完成工具调用后，最终回复必须以 JSON 结尾：{\"done\":true,\"selected_model_name\":\"实际选中的机型名\"}；若信息不足需要反问用户，则输出 {\"done\":false,\"question\":\"用一句话问最关键的信息\"}。"
  }
}''')


def _legacy_skill_prompts(session) -> dict:
    row = session.query(SystemConfig).filter(SystemConfig.key == "skill_prompts").first()
    if not row or row.type != "json":
        return {}
    try:
        return json.loads(row.value) if row.value else {}
    except Exception:
        return {}


def ensure_skill_prompt_templates(session=None) -> int:
    """空库时按 SKILL_PROMPT_SLOTS 播种；已有的行不覆盖。返回新建行数。"""
    own = session is None
    s = session or Rules_SessionLocal()
    created = 0
    try:
        legacy = _legacy_skill_prompts(s)
        now = datetime.now().isoformat()
        for meta in SKILL_PROMPT_SLOTS:
            exists = s.query(SkillPromptTemplate).filter(
                SkillPromptTemplate.skill_key == DEFAULT_SKILL_KEY,
                SkillPromptTemplate.slot_key == meta["slot_key"],
            ).first()
            if exists:
                continue
            # 优先级：旧 system_config.skill_prompts（已存在的字段值）> SKILL_PROMPT_SLOTS 模板
            template = str(legacy.get(meta["slot_key"]) or meta.get("template") or "")
            s.add(SkillPromptTemplate(
                skill_key=DEFAULT_SKILL_KEY,
                slot_key=meta["slot_key"],
                name=meta["name"],
                template=template,
                enabled=True,
                sort_order=meta["sort_order"],
                version=1,
                updated_at=now,
                updated_by="bootstrap",
            ))
            created += 1
        if created:
            s.commit()
    finally:
        if own:
            s.close()
    return created


def ensure_reasoning_node_defaults(session=None) -> int:
    """空库时按 DEFAULT_REASONING_NODE_CONTRACT 播种；已有的行不覆盖。返回新建行数。"""
    own = session is None
    s = session or Rules_SessionLocal()
    created = 0
    try:
        now = datetime.now().isoformat()
        for node_key, cfg in DEFAULT_REASONING_NODE_CONTRACT.items():
            exists = s.query(ReasoningNodeDefault).filter(
                ReasoningNodeDefault.skill_key == DEFAULT_SKILL_KEY,
                ReasoningNodeDefault.node_key == node_key,
            ).first()
            if exists:
                continue
            s.add(ReasoningNodeDefault(
                skill_key=DEFAULT_SKILL_KEY,
                node_key=str(node_key),
                config=json.dumps(cfg or {}, ensure_ascii=False),
                version=1,
                updated_at=now,
                updated_by="bootstrap",
            ))
            created += 1
        if created:
            s.commit()
    finally:
        if own:
            s.close()
    return created
