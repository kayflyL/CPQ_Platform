# -*- coding: utf-8 -*-
import io, os
ROOT = r"D:\CPQ_Platform_V1"
path = os.path.join(ROOT, "backend", "app", "repository", "reasoning_flow_repo.py")
text = io.open(path, encoding="utf-8").read()

old_graph = '''DEFAULT_REQUIREMENT_ANALYSIS_GRAPH = {
    "nodes": [
        {"id": "input", "type": "input", "label": "输入", "position": {"x": 0, "y": 200}},
        {"id": "agent_fill", "type": "agent_fill", "label": "智能对话填表 Agent", "position": {"x": 280, "y": 200}},
        {"id": "model_reason", "type": "model_reason", "label": "机型选型", "position": {"x": 580, "y": 200}},
        {"id": "kp_reason", "type": "kp_reason", "label": "配件选型", "position": {"x": 860, "y": 200}},
        {"id": "compose", "type": "compose", "label": "方案组装·BOM", "position": {"x": 1140, "y": 200}},
        {"id": "output", "type": "output", "label": "输出·BOM方案草稿", "position": {"x": 1420, "y": 200}},
    ],
    "edges": [
        {"id": "e1", "source": "input", "target": "agent_fill"},
        {"id": "e2", "source": "agent_fill", "target": "model_reason"},
        {"id": "e3", "source": "model_reason", "target": "kp_reason"},
        {"id": "e4", "source": "kp_reason", "target": "compose"},
        {"id": "e5", "source": "compose", "target": "output"},
    ],
}'''

new_graph = '''DEFAULT_REQUIREMENT_ANALYSIS_GRAPH = {
    "nodes": [
        {"id": "input", "type": "input", "label": "输入", "position": {"x": 0, "y": 200}},
        {"id": "need_analysis", "type": "agent", "label": "需求分析 Agent", "position": {"x": 300, "y": 200}},
        {"id": "model_choice", "type": "agent", "label": "机型选型 Agent", "position": {"x": 600, "y": 200}},
        {"id": "parts_proposal", "type": "agent", "label": "配件选配 Agent", "position": {"x": 900, "y": 200}},
        {"id": "bom_assemble", "type": "agent", "label": "BOM 组装 Agent", "position": {"x": 1200, "y": 200}},
        {"id": "output", "type": "output", "label": "输出·BOM方案草稿", "position": {"x": 1500, "y": 200}},
    ],
    "edges": [
        {"id": "e1", "source": "input", "target": "need_analysis"},
        {"id": "e2", "source": "need_analysis", "target": "model_choice"},
        {"id": "e3", "source": "model_choice", "target": "parts_proposal"},
        {"id": "e4", "source": "parts_proposal", "target": "bom_assemble"},
        {"id": "e5", "source": "bom_assemble", "target": "output"},
    ],
}'''

assert old_graph in text, "graph anchor missing"
text = text.replace(old_graph, new_graph, 1)

# 替换 _requirement_analysis_node_configs 的返回体
old_cfg_start = "def _requirement_analysis_node_configs() -> dict:"
idx = text.index(old_cfg_start)
cfg_old_template = text[idx:]
# 找到该函数末尾：下一个 "def " 之前
next_def = text.find("\ndef ", idx + 1)
cfg_old = cfg_old_template[:next_def-idx] if next_def != -1 else cfg_old_template

new_cfgs = r'''def _requirement_analysis_node_configs() -> dict:
    """需求分析 Skill 默认节点契约（AI 优先 5 节点链）。

    设计：AI 只做理解+编排，事实（目录/价格/兼容/BOM）全部由工具从规则库与目录读取；
    代码里不写死任何价格、兼容表、配件词表。每个 agent 节点用 enabled_tools 收窄工具，
    用 context_map 把上游结构化结果注入，用 result_key/result_mapping/action 写回 ctx。
    """
    return {
        "input": {
            "description": "接收客户自然语言需求与商机上下文",
            "deterministic": True,
        },
        "need_analysis": {
            "description": "智能体理解需求→读规则目录→输出结构化需求槽位（server_type/form/series/gpu/raid 等）",
            "enabled_tools": ["load_requirement_rules", "list_server_types", "list_server_models"],
            "system_prompt": (
                "你是【需求分析 Agent】。把客户自然语言需求转成结构化槽位，供后续选型/选配/报价使用。\n"
                "铁律：只做理解与编排，不记忆价格、兼容、BOM。凡涉及目录、系列、形态、配件、类型的事实，"
                "一律调用工具获取；不确定就调用工具确认，绝不编造。\n"
                "工具：load_requirement_rules（读需求规则/别名）、list_server_types/list_server_models（在售目录）。\n"
                "先调用 load_requirement_rules 读规则，再按规则把需求规范化。\n"
                "最终只输出一个 JSON 对象（不要多余文字），形如：\n"
                '{"requirement": {"server_type_name":"通用服务器","server_type":"通用","form":"2U","series":"",'
                '"gpu_count":2,"raid_level":"","nic_speed":"","psu_signal":{},"purchase_qty":1,"gpu_groups":[],'
                '"scope":"","usage":""}, "summary":"一句话需求要点"}'
            ),
            "result_key": "need_analysis",
            "result_mapping": {
                "requirement": "requirement",
                "ext": "requirement",
                "normalized_text": "summary",
            },
            "context_map": [],
            "max_iterations": 5,
            "allowed_effects": [],
            "rule_types": ["category_alias", "platform_series_map", "type_alias", "gpu_form_map",
                           "raid_level_map", "cpu_mem_generation", "workload_map"],
        },
        "model_choice": {
            "description": "智能体按需求从目录筛机型并用 validate_compat 校验；用户可选自配并收到机型卡片",
            "enabled_tools": ["select_models", "validate_compat", "load_requirement_rules"],
            "system_prompt": (
                "你是【机型选型 Agent】。上游已给需求槽位（见“需求槽位”）。任务：调用 select_models 从目录筛出候选机型，"
                "再调用 validate_compat 校验候选与需求是否可行，给出推荐。\n"
                "铁律：不背价格/兼容/目录，一切以工具返回为准；无匹配就如实说明并建议放宽。\n"
                "工具：select_models（按 server_type/form/series/usage 筛）、validate_compat（校验）。\n"
                "若用户明确表示“自己配/不要推荐/我要自己选”，则 action 置为 self_config，"
                "把候选机型放入 candidates，到此为止（系统会推送机型卡片让你进入自配页）。\n"
                "最终只输出一个 JSON 对象：\n"
                '{"action":"recommend|self_config","candidates":[...工具返回candidates...],'
                '"recommended":<推荐项，含baseline>,"recommended_index":0,"reason":"推荐理由",'
                '"baseline":<推荐项的baseline>}'
            ),
            "result_key": "model_choice",
            "result_mapping": {
                "candidates": "candidates",
                "baselines": "candidates",
                "recommended": "recommended",
                "baseline": "baseline",
                "recommended_index": "recommended_index",
                "model_choice_reason": "reason",
                "action": "action",
                "flow_exit": "flow_exit",
            },
            "context_map": [{"key": "requirement", "label": "需求槽位"}],
            "max_iterations": 6,
            "allowed_effects": ["self_config"],
        },
        "parts_proposal": {
            "description": "智能体按需求+已选机型从配件库挑配件，并校验兼容，输出 parts_proposal 契约",
            "enabled_tools": ["select_parts", "validate_compat"],
            "system_prompt": (
                "你是【配件选配 Agent】。已给需求槽位与已选机型（见“需求槽位/已选机型”）。任务："
                "调用 select_parts 按类目挑配件，再调用 validate_compat（用已选机型 baseline）校验兼容，"
                "必要时换件重选。\n"
                "铁律：不背配件型号/价格，全部以 select_parts 返回为准；无法命中就用工具给的代表件，并在 summary 说明。\n"
                "最终只输出一个 JSON 对象：\n"
                '{"baseline":<上游baseline>,"by_category":{"CPU":[...],"Memory":[...]},'
                '"parts":[...select_parts返回parts...],"summary":"配件规划要点"}'
            ),
            "result_key": "parts_proposal",
            "result_mapping": {
                "parts": "parts",
                "kp_parts": "parts",
                "by_category": "by_category",
                "baseline": "baseline",
                "part_summary": "summary",
            },
            "context_map": [{"key": "requirement", "label": "需求槽位"}, {"key": "baseline", "label": "已选机型"}],
            "max_iterations": 6,
            "allowed_effects": [],
        },
        "bom_assemble": {
            "description": "智能体用 validate_compat+compute_price 校验并算价，触发确定性 build_bom 产出整机方案",
            "enabled_tools": ["validate_compat", "compute_price", "select_parts", "select_models"],
            "system_prompt": (
                "你是【BOM 组装 Agent】。已给需求槽位、已选机型、配件清单。任务：调用 validate_compat 确认整体可行，"
                "调用 compute_price 取得真实成本，然后输出 action=build_bom 触发确定性 BOM 组装。\n"
                "铁律：不手拼 BOM、不估成本；成本/兼容事实全部来自工具返回，最终方案由系统按真实 BOM 模板组装。\n"
                "最终只输出一个 JSON 对象：\n"
                '{"action":"build_bom","baseline":<已选机型baseline>,"parts":<配件清单>,'
                '"cost":<compute_price返回cost>,"summary":"方案要点"}'
            ),
            "result_key": "bom_scheme",
            "result_mapping": {
                "baseline": "baseline",
                "parts": "parts",
                "bom_scheme": "bom_scheme",
                "requirement": "requirement",
                "ext": "requirement",
                "bom_cost": "cost",
                "bom_summary": "summary",
            },
            "context_map": [
                {"key": "requirement", "label": "需求槽位"},
                {"key": "baseline", "label": "已选机型"},
                {"key": "parts_proposal", "label": "配件选配"},
                {"key": "parts", "label": "配件清单"},
            ],
            "max_iterations": 6,
            "allowed_effects": ["build_bom"],
        },
        "output": {
            "description": "写回真实 requirement + bom_scheme，并交付 AI Office / 商机详情页",
            "output_kind": "bom_scheme_draft",
            "target": "bom_scheme",
            "payload_map": {"plans": "ctx.plans", "ext": "ctx.ext"},
            "actions": [],
            "deterministic": True,
        },
    }


'''

text = text[:idx] + new_cfgs + text[next_def:]
io.open(path, "w", encoding="utf-8").write(text)
print("reasoning_flow_repo graph+configs patched OK")
