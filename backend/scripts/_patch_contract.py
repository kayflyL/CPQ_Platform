# -*- coding: utf-8 -*-
import io, os
ROOT = r"D:\CPQ_Platform_V1"
path = os.path.join(ROOT, "backend", "app", "repository", "reasoning_flow_repo.py")
text = io.open(path, encoding="utf-8").read()

old = '''"final_only_contract": ("直接给出需求槽位 JSON：{\\"requirement\\":{...槽位...},\\"summary\\":\\"一句话需求要点\\"}。"
                                     "requirement 字段含 server_type_name/server_type/form/series/gpu_count/raid_level/nic_speed/psu_signal/purchase_qty/gpu_groups/usage，缺省留空，不编造。"),'''
new = '''"final_only_contract": ("直接给出需求槽位 JSON，键名必须按下表，不得改名："
                                     '{"requirement": {"server_type_name":"服务器类型全名","server_type":"通用|AI|存储|边缘|GPU","form":"1U|2U|4U|8U",'
                                     '"series":"产品系列(可空)","gpu_count":0,"raid_level":"","nic_speed":"","purchase_qty":1,'
                                     '"gpu_groups":[{"kind":"GPU","qty":0}],"scope":"","usage":"用途简要"},'
                                     '"summary":"一句话需求要点"}。server_type_name/form/gpu_count 必须从需求里精确提取，无法确定就留空，禁止臆造。'),'''
assert old in text, "need_analysis contract anchor missing"
text = text.replace(old, new, 1)
io.open(path, "w", encoding="utf-8").write(text)
print("need_analysis contract tightened OK")
