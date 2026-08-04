"""整机方案 × 选型配置规则打通 单测 —— plan_rule_context 聚合 + apply_plan_selection_rules 派生/校验。

跑法（backend 目录）：
  python -X utf8 -m pytest tests/test_plan_rule_apply.py -q

覆盖：盘类型计数 / GPU·Memory 品类规范 / 背板 tri·dc / 线缆 per 取整 / 互斥告警 / 命中计数埋点。
"""
from app.services import plan_rule_apply
from app.services.selection_engine import plan_rule_context


def rule(**partial):
    base = {"id": 1, "name": "r", "status": "active",
            "body": {"when": None, "then": None, "desc": None}}
    base.update(partial)
    return base


def bp_rule(rid=10):
    return rule(id=rid, name="背板类型：含 NVMe 盘→三模", body={
        "when": {"field": "config.drive_kinds", "op": "contains", "value": "NVMe"},
        "then": {"action": "derive", "field": "config.bp_type", "value": "tri"},
        "desc": "含 NVMe 盘 → tri 背板",
    })


def cable_rules():
    return [
        rule(id=11, name="SATA 线缆根数", body={
            "when": {"field": "config.sata_qty", "op": ">=", "value": 1},
            "then": {"action": "derive", "target": "SATA", "basis": "config.sata_qty", "per": 8, "round": "ceil"},
            "desc": "SATA 盘数 ÷ 8",
        }),
        rule(id=12, name="NVMe 线缆根数", body={
            "when": {"field": "config.nvme_qty", "op": ">=", "value": 1},
            "then": {"action": "derive", "target": "NVMe", "basis": "config.nvme_qty", "per": 2, "round": "ceil"},
            "desc": "NVMe 盘数 ÷ 2",
        }),
        rule(id=13, name="GPU 供电线根数", body={
            "when": {"field": "kp.GPU.qty", "op": ">=", "value": 1},
            "then": {"action": "derive", "target": "GPU线", "basis": "kp.GPU.qty", "per": 1, "round": "ceil"},
            "desc": "GPU 数量 ÷ 1",
        }),
    ]


def exclude_memory_rule(rid=20):
    return rule(id=rid, name="内存同型号不混搭", body={
        "when": {"field": "kp.Memory.qty", "op": ">=", "value": 2},
        "then": {"action": "exclude", "target": "kp.Memory", "unique_field": "pn",
                 "desc": "内存须同型号，禁止不同 PN 混插"},
    })


def sample_kp():
    """12 SATA + 4 NVMe + 2 GPU + 2 条不同 PN 内存 的典型方案 KP。"""
    return [
        {"category": "GPU", "pn": "GPU-A", "name": "RTX 5090", "qty": 2, "matched_spec": "型号 RTX 5090"},
        {"category": "Memory", "pn": "MEM-3200-16", "name": "DDR5 32G", "qty": 1},
        {"category": "Memory", "pn": "MEM-4800-16", "name": "DDR5 32G", "qty": 1},
        {"category": "HDD/SSD", "pn": "SSD-NVMe", "name": "NVMe 7.68T", "qty": 4, "matched_spec": "容量 7.68T · NVMe"},
        {"category": "HDD/SSD", "pn": "SATA-960", "name": "SATA 960G", "qty": 12, "matched_spec": "容量 960G · SATA"},
    ]


def test_plan_rule_context_drive_signals():
    ctx = plan_rule_context(sample_kp(), {"series": "KH", "form": "2U"})
    assert ctx["kp"]["GPU"]["qty"] == 2
    assert ctx["kp"]["Memory"]["qty"] == 2
    assert ctx["config"]["sata_qty"] == 12
    assert ctx["config"]["nvme_qty"] == 4
    assert ctx["config"]["drive_kinds"] == ["NVMe", "SATA"]
    assert ctx["config"]["series"] == "KH"
    assert ctx["config"]["form"] == "2U"
    assert ctx["opportunity"] == {}


def test_plan_rule_context_unknown_drive_protocol_defaults_sata():
    ctx = plan_rule_context([
        {"category": "HDD/SSD", "pn": "D-1", "name": "480G", "qty": 2, "matched_spec": "容量 480G"},
    ])
    assert ctx["config"]["drive_kinds"] == ["SATA"]
    assert ctx["config"]["sata_qty"] == 0  # 协议不明不计入任何类型数量，只给集合兜底


def test_apply_derives_backplane_and_cables_plus_exclude():
    plan = {"config_id": 1, "chassis_signals": {"psu_wattage": "2000"}}
    plan_rule_apply.apply_plan_selection_rules(
        plan, sample_kp(), {"series": "KH"},
        rules=[bp_rule(), *cable_rules(), exclude_memory_rule()],
        record_hits=False,
    )
    assert plan["chassis_signals"]["bp_type"] == "tri"
    assert plan["chassis_signals"]["cable_qty_by_kind"] == {"SATA": 2, "NVMe": 2, "GPU线": 2}
    alerts = plan["selection_alerts"]
    assert any(a["action"] == "exclude" and a["severity"] == "conflict" for a in alerts)
    mem_alert = next(a for a in alerts if a["action"] == "exclude")
    assert set(mem_alert["offenders"]) == {"MEM-3200-16", "MEM-4800-16"}


def test_apply_no_nvme_no_bp_type_rule():
    kp = [
        {"category": "HDD/SSD", "pn": "SATA-960", "name": "SATA 960G", "qty": 12, "matched_spec": "容量 960G · SATA"},
    ]
    plan = {"chassis_signals": {}}
    plan_rule_apply.apply_plan_selection_rules(
        plan, kp, rules=[bp_rule(), *cable_rules()], record_hits=False,
    )
    assert "bp_type" not in plan["chassis_signals"]          # 无 NVMe → 不触发 tri，前端 ?? 'dc' 兜底
    assert plan["chassis_signals"]["cable_qty_by_kind"] == {"SATA": 2}
    assert plan["selection_alerts"] == []


def test_apply_empty_rules_sets_defaults():
    plan = {}
    plan_rule_apply.apply_plan_selection_rules(plan, sample_kp(), rules=[], record_hits=False)
    assert plan["chassis_signals"] == {}
    assert plan["selection_alerts"] == []


def test_apply_records_hits_for_fired_rules(monkeypatch):
    captured = {}
    monkeypatch.setattr(plan_rule_apply, "_record_hits", lambda ids: captured.update(ids=list(ids)))
    plan = {}
    plan_rule_apply.apply_plan_selection_rules(
        plan, sample_kp(),
        rules=[bp_rule(), cable_rules()[1], exclude_memory_rule()],  # NVMe 线 + 背板 + 内存互斥
        record_hits=True,
    )
    # 背板规则（drive_kinds 含 NVMe）、NVMe 线规则（nvme_qty>=1）、内存互斥（qty>=2）都命中
    assert set(captured["ids"]) == {10, 12, 20}
