# -*- coding: utf-8 -*-
import io, os
ROOT = r"D:\CPQ_Platform_V1"
path = os.path.join(ROOT, "backend", "app", "repository", "reasoning_flow_repo.py")
text = io.open(path, encoding="utf-8").read()

def after(anchor, add):
    global text
    assert anchor in text, "missing: " + anchor
    text = text.replace(anchor, anchor + add, 1)

after('"result_key": "need_analysis",', '''\n            "final_only": true,\n            "final_only_contract": ("直接给出需求槽位 JSON：{\\"requirement\\":{...槽位...},\\"summary\\":\\"一句话需求要点\\"}。"
                                     "requirement 字段含 server_type_name/server_type/form/series/gpu_count/raid_level/nic_speed/psu_signal/purchase_qty/gpu_groups/usage，缺省留空，不编造。"),
            "pre_tools": [{"tool": "load_requirement_rules", "args": {}}],''')

after('"result_key": "model_choice",', '''\n            "final_only": true,\n            "final_only_contract": ("直接给出机型决策 JSON：{\\"action\\":\\"recommend|self_config\\",\\"candidates\\":[select_models候选digest],"
                                     "\\"recommended\\":<建议候选含baseline>,\\"baseline\\":<建议候选的baseline>,\\"reason\\":\\"推荐理由\\"}。"
                                     "用户表示自配时 action=self_config。"),
            "pre_tools": [{"tool": "select_models", "args": {"server_type_name": "req.server_type_name", "form": "req.form", "series": "req.series", "usage": "req.usage", "limit": 6}}],''')

after('"result_key": "parts_proposal",', '''\n            "final_only": true,\n            "final_only_contract": ("直接给出配件契约 JSON：{\\"baseline\\":<已选机型baseline>,\\"by_category\\":{...},\\"parts\\":[select_parts返回parts...],"
                                     "\\"summary\\":\\"配件规划要点\\"}。baseline 取上游已选机型，不要改价格/型号。"),
            "pre_tools": [{"tool": "select_parts", "args": {"categories": ["CPU", "Memory", "HDD/SSD", "GPU", "NIC", "RAID"], "server_type_name": "req.server_type_name"}}],''')

after('"result_key": "bom_scheme",', '''\n            "final_only": true,\n            "final_only_contract": ("直接给出 BOM 组装 JSON：{\\"action\\":\\"build_bom\\",\\"baseline\\":<已选机型baseline>,\\"parts\\":<配件清单>,"
                                     "\\"cost\\":<compute_price返回cost>,\\"summary\\":\\"方案要点\\"}。cost 必须用工具返回值，禁止估算。"),
            "pre_tools": [
                {"tool": "validate_compat", "args": {"baseline": "ctx.baseline", "parts": "ctx.parts", "requirement": "ctx.requirement"}},
                {"tool": "compute_price", "args": {"baseline": "ctx.baseline", "parts": "ctx.parts"}},
            ],''')

io.open(path, "w", encoding="utf-8").write(text)
print("node final_only/pre_tools injected OK")
