"""selection_gate 测试:对拍夹具(与 legacy evaluate_rules 同输入同输出)+ 新约束语义。

直跑:backend/.venv/Scripts/python.exe -X utf8 tests/test_selection_gate.py
(pytest 兼容:全部 test_* 函数,断言风格一致)
规则用显式列表注入,不依赖 DB(与 test_requirement_rules 同口径)。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import selection_engine as legacy
from app.services.selection_gate import (build_context, resolve, fired_rule_ids)

# ── 夹具:选型域存量规则原样(DB 导出,body 同 JSON)──
R_BACKPLANE = {"id": 17, "name": "背板类型:含 NVMe 盘→三模", "status": "active", "priority": None,
               "body": {"when": {"field": "config.drive_kinds", "op": "contains", "value": "NVMe"},
                        "then": {"action": "derive", "field": "config.bp_type", "value": "tri"},
                        "desc": "配置含 NVMe 盘 → 三模背板"}}
R_NVME_CABLE = {"id": 20, "name": "NVMe 线缆根数", "status": "active",
                "body": {"when": {"field": "config.nvme_qty", "op": ">=", "value": 1},
                         "then": {"action": "derive", "target": "NVMe", "basis": "config.nvme_qty",
                                  "per": 2, "round": "ceil"}}}
R_MEM_EXCLUDE = {"id": 22, "name": "内存同型号不混搭", "status": "active",
                 "body": {"when": {"field": "kp.Memory.qty", "op": ">=", "value": 2},
                          "then": {"action": "exclude", "target": "kp.Memory", "unique_field": "pn"}}}

# 库内 CPU 件(剥价后的候选行形状)
P_KH = {"id": 126, "model": "KH50000 48C", "brand": "兆芯",
        "applicable": {"series": ["兆芯"]}, "specs": {"Socket": None, "tdp": "150"}}
P_AMD = {"id": 111, "model": "AMD EPYC 9354", "brand": "AMD",
         "applicable": {"series": ["AMD"]}, "specs": {"Socket": "SP5", "tdp": "280"}}
P_GENERIC = {"id": 900, "model": "通用万兆网卡", "brand": "Intel", "applicable": None,
             "specs": {"Interface": "PCIe x8"}}
P_EMPTY_SERIES = {"id": 901, "model": "空系列隐藏件", "brand": "X", "applicable": {"series": []},
                  "specs": {}}


def _ctx_zhaoxin(selected=None, candidates=None, compat=None):
    model = {"series": "兆芯", "model": "ZS25V2-P", "form": "2U", "bays": 12, "psu_bays": 2,
             "gpu_slots": 0, "max_cpu": 2, "max_dimm": 24, "psu_wattages": []}
    return build_context(model, selected or {}, candidates=candidates, compat_by_part=compat or {})


def test_cable_derive_matches_legacy():
    """对拍:derive 线缆根数与 legacy evaluate_rules 同输出。"""
    selected = {"HDD/SSD": [{"pn": "NV1", "name": "3.84T NVMe SSD", "qty": 5,
                             "specs": {"Interface": "NVMe"}}]}
    ctx = _ctx_zhaoxin(selected)
    rules = [R_NVME_CABLE]
    legacy_actions = legacy.evaluate_rules(rules, ctx)
    out = resolve(rules, ctx)
    got = [d for d in out["derived"] if d.get("action") == "derive"
           and d.get("deriveTarget") == "NVMe"]
    leg = [a for a in legacy_actions if a.get("action") == "derive"
           and a.get("deriveTarget") == "NVMe"]
    assert got and leg, (got, leg)
    assert got[0]["deriveQty"] == leg[0]["deriveQty"] == 3  # ceil(5/2)
    assert out["budget"]["slots"]["max_dimm"] == {"used": 0, "max": 24}


def test_assign_derive_priority_tie_is_model_error():
    """赋值型 derive:同字段同 priority 并列 = 模型警告并拒绝求值(不静默取先)。"""
    a = dict(R_BACKPLANE, id=1)
    b = {"id": 2, "name": "另一条背板", "status": "active",
         "body": {"when": {"field": "config.drive_kinds", "op": "contains", "value": "NVMe"},
                  "then": {"action": "derive", "field": "config.bp_type", "value": "dc"}}}
    ctx = _ctx_zhaoxin({"HDD/SSD": [{"pn": "NV1", "name": "NVMe SSD", "qty": 1,
                                     "specs": {"Interface": "NVMe"}}]})
    out = resolve([a, b], ctx)
    assert any(w.get("reason_code") == "assign_priority_tie" for w in out["model_warnings"])
    # 有 priority 区分时,高者胜
    a2 = {"id": 1, "name": "高优", "status": "active",
          "body": {"priority": 10, "when": {"field": "config.drive_kinds", "op": "contains", "value": "NVMe"},
                   "then": {"action": "derive", "field": "config.bp_type", "value": "tri"}}}
    b2 = {"id": 2, "name": "低优", "status": "active",
          "body": {"priority": 1, "when": {"field": "config.drive_kinds", "op": "contains", "value": "NVMe"},
                   "then": {"action": "derive", "field": "config.bp_type", "value": "dc"}}}
    out2 = resolve([a2, b2], ctx)
    assigns = [d for d in out2["derived"] if d.get("assignField") == "config.bp_type"]
    assert len(assigns) == 1 and assigns[0]["assignValue"] == "tri"


def test_exclude_legacy_vs_homogeneous():
    """exclude(legacy)与 homogeneous(同类一致 plural)同语义输出。"""
    selected = {"Memory": [{"pn": "A", "name": "32G", "qty": 8}, {"pn": "B", "name": "64G", "qty": 4}]}
    ctx = _ctx_zhaoxin(selected)
    legacy_out = resolve([R_MEM_EXCLUDE], ctx)
    assert any(v.get("severity") == "conflict" and v.get("offenders") == ["A", "B"]
               for v in legacy_out["violations"])
    homo = {"id": 40, "name": "同类一致", "status": "active",
            "body": {"then": {"action": "homogeneous", "categories": ["Memory", "CPU", "GPU"],
                              "field": "pn"}}}
    homo_out = resolve([homo], ctx)
    assert any(v.get("target") == "Memory" and v.get("offenders") == ["A", "B"]
               for v in homo_out["violations"])
    # 同型号不触发
    ok_ctx = _ctx_zhaoxin({"Memory": [{"pn": "A", "name": "32G", "qty": 16}]})
    assert not resolve([homo], ok_ctx)["violations"]


def test_resource_budget_rule():
    """resource:功耗 ×1.2 ≤ PSU 容量;缺数据跳过并记 model_warnings。"""
    rule = {"id": 50, "name": "PSU 容量冗余", "status": "active",
            "body": {"then": {"action": "resource",
                              "check": {"lhs": {"field": "config.tdp_sum", "scale": 1.2},
                                        "op": "<=", "rhs": {"field": "config.psu_capacity"}},
                              "desc": "PSU 容量不足"}}}
    over = _ctx_zhaoxin({"CPU": [{"pn": "C1", "name": "CPU", "qty": 2, "specs": {"tdp": "280"}}],
                         "PSU": [{"pn": "PS1", "name": "300W", "qty": 2, "specs": {"wattage": "300"}}]})
    out = resolve([rule], over)
    assert any(v.get("ruleId") == 50 and v.get("severity") == "conflict"
               for v in out["violations"]), out["violations"]
    assert out["budget"]["psu_load_w"] == 560 and out["budget"]["psu_capacity_w"] == 600
    ok = _ctx_zhaoxin({"CPU": [{"pn": "C1", "name": "CPU", "qty": 2, "specs": {"tdp": "280"}}],
                       "PSU": [{"pn": "PS1", "name": "1300W", "qty": 2, "specs": {"wattage": "1300"}}]})
    assert not resolve([rule], ok)["violations"]
    nodata = _ctx_zhaoxin({"CPU": [{"pn": "C1", "name": "CPU", "qty": 1}]})  # 无 tdp/psu
    out2 = resolve([rule], nodata)
    assert not out2["violations"] and out2["model_warnings"]


def test_slot_clamps_data_driven():
    """数据钳制:超 max_dimm → conflict;gpu_slots=0(未录)不钳;空上限不钳。"""
    selected = {"Memory": [{"pn": "M1", "name": "32G", "qty": 30}]}
    out = resolve([], _ctx_zhaoxin(selected))
    clamps = [v for v in out["violations"] if v.get("action") == "clamp"]
    assert len(clamps) == 1 and "24" in clamps[0]["desc"]
    gpu = _ctx_zhaoxin({"GPU": [{"pn": "G1", "name": "GPU", "qty": 4}]})
    assert not [v for v in resolve([], gpu)["violations"] if v.get("action") == "clamp"]


def test_platform_fit_two_tier():
    """平台适配两级(S1 拍板②):compat 机型级优先,没填按 applicable.series,缺省=通用件。"""
    candidates = {"CPU": [P_KH, P_AMD], "NIC": [P_GENERIC, P_EMPTY_SERIES]}
    # 机型级:compat 里录了 AMD 9354(id 111)的机型清单 → 当前机型 ZS25V2-P 不在其中,被挡;
    # KH 件 compat 没填 → 落系列层,兆芯系列适配,放行
    compat = {111: ["ES220 V3", "ESA240 V3"]}
    ctx = _ctx_zhaoxin({}, candidates={"CPU": [P_KH, P_AMD]}, compat=compat)
    out = resolve([], ctx)
    cpu_opts = out["options"]["CPU"]
    allowed_models = [a["model"] for a in cpu_opts["allowed"]]
    assert allowed_models == ["KH50000 48C"], cpu_opts
    assert cpu_opts["blocked"][0]["reasons"][0]["ruleName"] == "平台适配"
    # compat 没填的件 → 系列兜底:兆芯系列下 AMD 件被挡,通用件通过,空系列件隐藏
    ctx2 = _ctx_zhaoxin({}, candidates=candidates)
    out2 = resolve([], ctx2)
    nic_allowed = [a["model"] for a in out2["options"]["NIC"]["allowed"]]
    assert "通用万兆网卡" in nic_allowed and "空系列隐藏件" not in nic_allowed
    assert "AMD EPYC 9354" not in [a["model"] for a in out2["options"]["CPU"]["allowed"]]
    # 未锁机型 → 不过滤
    ctx3 = build_context(None, {}, candidates={"CPU": [P_KH, P_AMD]})
    out3 = resolve([], ctx3)
    assert len(out3["options"]["CPU"]["allowed"]) == 2


def test_excludes_candidate_predicate():
    """excludes 候选谓词规则:part. 前缀寻址候选件结构化属性。"""
    rule = {"id": 60, "name": "RAID 需带电容", "status": "active",
            "body": {"when": {"field": "kp.HDD/SSD.qty", "op": ">=", "value": 1},
                     "then": {"action": "excludes", "target": "kp.Raid card",
                              "candidate": {"field": "part.spec.电容", "op": "not_exists"},
                              "desc": "全闪配置 RAID 卡须带电容"}}}
    cands = {"Raid card": [
        {"id": 1, "model": "9361-8i 带电容", "specs": {"电容": "2G"}},
        {"id": 2, "model": "9361-8i 无电容", "specs": {}},
    ]}
    ctx = _ctx_zhaoxin({"HDD/SSD": [{"pn": "NV1", "name": "NVMe", "qty": 8}]}, candidates=cands)
    out = resolve([rule], ctx)
    opts = out["options"]["Raid card"]
    assert [a["model"] for a in opts["allowed"]] == ["9361-8i 带电容"]
    assert opts["blocked"][0]["reasons"][0]["ruleId"] == 60


def test_fired_rule_ids():
    ctx = _ctx_zhaoxin({"HDD/SSD": [{"pn": "NV1", "name": "NVMe SSD", "qty": 5,
                                     "specs": {"Interface": "NVMe"}}]})
    ids = fired_rule_ids([R_BACKPLANE, R_NVME_CABLE, R_MEM_EXCLUDE], ctx)
    assert ids == [17, 20]


def test_selected_part_platform_violation():
    """已选件平台校验:过滤只拦再选,进单的不合规件(导入/切机型残留)在 resolve 报出。"""
    ctx = _ctx_zhaoxin({"CPU": [{"pn": "AMD EPYC 9354", "name": "AMD EPYC 9354", "qty": 1, "id": 111}]})
    ctx["catalog_by_id"] = {111: {"applicable": {"series": ["AMD"]}}}
    out = resolve([], ctx)
    hits = [v for v in out["violations"] if v.get("ruleName") == "平台适配"]
    assert len(hits) == 1 and hits[0]["severity"] == "conflict" and "AMD EPYC 9354" in hits[0]["desc"]
    # 目录里没有的件(无 id / 未录)不误报
    ctx2 = _ctx_zhaoxin({"CPU": [{"pn": "老件", "name": "老件", "qty": 1}]})
    ctx2["catalog_by_id"] = {111: {"applicable": {"series": ["AMD"]}}}
    assert not [v for v in resolve([], ctx2)["violations"] if v.get("ruleName") == "平台适配"]


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {name}: {e}")
    print(f"{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
