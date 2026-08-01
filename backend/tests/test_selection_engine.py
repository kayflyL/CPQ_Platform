"""选型规则求值引擎单测 —— 与 frontend/src/stores/selectionEngine.test.ts 对齐（锁双端语义一致）。

跑法（backend 目录）：
  python -X utf8 -m pytest tests/test_selection_engine.py -q

覆盖五种 action 的求值正确性，以及 when 解析 / 字段寻址 / 取整方向等易错点。
这里锁住的是选型正确性下限：互斥判定、必配数量、派生取整一旦错，会直接产出不可交付的报价。
"""
import math
import re

from app.services.selection_engine import (
    eval_op, resolve_field, resolve_value, eval_when, eval_then,
    evaluate_rules, eval_assign_value, parse_cat, normalize_drive_kind,
)


# ── 测试夹具：构造一条兼容性规则（仅给引擎用到的字段）──
def rule(**partial):
    base = {"id": 1, "name": "r", "status": "active",
            "body": {"when": None, "then": None, "desc": None}}
    base.update(partial)
    return base


def sample_ctx():
    """2 条不同型号内存 + 1 块 GPU + 4 块 NVMe 盘的常用 ctx。"""
    return {
        "kp": {
            "Memory": {
                "qty": 2,
                "items": [{"pn": "MEM-3200-16", "spec": {}}, {"pn": "MEM-4800-16", "spec": {}}],
                "spec": {},
            },
            "GPU": {"qty": 1, "items": [{"pn": "GPU-A", "spec": {}}], "spec": {}},
            "HDD/SSD": {
                "qty": 4,
                "items": [{"pn": "SSD-NVMe-1", "spec": {"interface": "NVMe"}}],
                "spec": {"interface": "NVMe"},
            },
        },
        "config": {"series": "Polaris", "sata_qty": 8},
        "opportunity": {"platform_type": "Polaris"},
    }


# ============================================================
# eval_op —— 操作符语义
# ============================================================
def test_eval_op_compare_numeric():
    assert eval_op(3, ">=", 2) is True
    assert eval_op(2, ">=", 2) is True
    assert eval_op(1, ">=", 2) is False
    assert eval_op(5, "<=", 5) is True
    assert eval_op(6, ">", 5) is True
    assert eval_op(5, "<", 5) is False


def test_eval_op_loose_eq():
    assert eval_op("3", "==", 3) is True      # 字符串/数字宽松相等
    assert eval_op("Polaris", "==", "Polaris") is True
    assert eval_op("A", "!=", "B") is True
    assert eval_op("A", "!=", "A") is False


def test_eval_op_in():
    assert eval_op("Polaris", "in", ["Polaris", "Orion"]) is True
    assert eval_op("Zen", "in", ["Polaris", "Orion"]) is False
    assert eval_op("Polaris", "in", "Polaris") is False  # expected 非数组安全失败


def test_eval_op_contains():
    assert eval_op(["NVMe", "SATA"], "contains", "NVMe") is True
    assert eval_op("tri-mode backplane", "contains", "tri-mode") is True
    assert eval_op("abc", "contains", "z") is False


def test_eval_op_exists():
    assert eval_op("x", "exists", None) is True
    assert eval_op("", "exists", None) is False
    assert eval_op(None, "exists", None) is False


def test_eval_op_unknown_returns_false():
    assert eval_op(1, "~=", 1) is False


# ============================================================
# resolve_field / resolve_value —— 字段寻址
# ============================================================
def test_resolve_field_kp():
    ctx = sample_ctx()
    assert resolve_field(ctx, "kp.Memory.qty") == 2
    assert resolve_field(ctx, "kp.HDD/SSD.spec.interface") == "NVMe"
    assert resolve_field(ctx, "kp.NotExist.qty") is None
    assert resolve_field(ctx, "kp.Memory.spec.nokey") is None


def test_resolve_field_config_opportunity():
    ctx = sample_ctx()
    assert resolve_field(ctx, "config.series") == "Polaris"
    assert resolve_field(ctx, "config.sata_qty") == 8
    assert resolve_field(ctx, "opportunity.platform_type") == "Polaris"
    assert resolve_field(ctx, "config.missing") is None


def test_resolve_field_drive_counts():
    ctx = {"kp": {}, "config": {"sata_qty": 8, "sas_qty": 4, "nvme_qty": 2}, "opportunity": {}}
    assert resolve_field(ctx, "config.sata_qty") == 8
    assert resolve_field(ctx, "config.sas_qty") == 4
    assert resolve_field(ctx, "config.nvme_qty") == 2


def test_resolve_value():
    ctx = sample_ctx()
    assert resolve_value(ctx, "kp.GPU.qty") == 1            # 字段路径
    assert resolve_value(ctx, "NVMe") == "NVMe"             # 字面量
    assert resolve_value(ctx, 3) == 3                       # 非字符串
    assert resolve_value(ctx, "kp.NoCat.qty") == "kp.NoCat.qty"  # 解析不到 → 退回字面量


def test_parse_cat():
    assert parse_cat("kp.GPU供电线") == "GPU供电线"
    assert parse_cat("GPU") == "GPU"
    assert parse_cat(None) == ""


def test_normalize_drive_kind():
    assert normalize_drive_kind("3.84T NVME SSD Gen4") == "NVMe"
    assert normalize_drive_kind({"interface": "SATA"}) == "SATA"   # str() 后仍命中
    assert normalize_drive_kind("SAS3 12G") == "SAS"
    assert normalize_drive_kind("unknown") is None


# ============================================================
# eval_when —— all / any / 单条件 / 空
# ============================================================
def test_eval_when_all():
    ctx = sample_ctx()
    assert eval_when(ctx, {"all": [
        {"field": "kp.GPU.qty", "op": ">=", "value": 1},
        {"field": "config.series", "op": "==", "value": "Polaris"},
    ]}) is True
    assert eval_when(ctx, {"all": [
        {"field": "kp.GPU.qty", "op": ">=", "value": 1},
        {"field": "config.series", "op": "==", "value": "Orion"},
    ]}) is False


def test_eval_when_any():
    ctx = sample_ctx()
    assert eval_when(ctx, {"any": [
        {"field": "config.series", "op": "==", "value": "Orion"},
        {"field": "config.series", "op": "==", "value": "Polaris"},
    ]}) is True


def test_eval_when_single_and_empty():
    ctx = sample_ctx()
    assert eval_when(ctx, {"field": "kp.GPU.qty", "op": ">=", "value": 1}) is True
    assert eval_when(ctx, None) is True
    assert eval_when(ctx, {}) is True


# ============================================================
# eval_then —— exclude（互斥：同 unique_field 不同值）
# ============================================================
def test_eval_then_exclude_conflict():
    ctx = sample_ctx()  # Memory 有 2 条不同 pn
    out = eval_then(ctx, rule(name="内存同型号不混搭",
                               body={"then": {"action": "exclude", "target": "kp.Memory", "unique_field": "pn"}}))
    assert len(out) == 1
    assert out[0]["action"] == "exclude"
    assert out[0]["severity"] == "conflict"
    assert out[0]["offenders"] == ["MEM-3200-16", "MEM-4800-16"]


def test_eval_then_exclude_no_conflict():
    ctx = {"kp": {"Memory": {"qty": 2, "items": [{"pn": "MEM-X", "spec": {}}, {"pn": "MEM-X", "spec": {}}], "spec": {}}},
            "config": {}, "opportunity": {}}
    assert len(eval_then(ctx, rule(body={"then": {"action": "exclude", "target": "kp.Memory", "unique_field": "pn"}}))) == 0
    ctx["kp"]["Memory"] = {"qty": 1, "items": [{"pn": "MEM-X", "spec": {}}], "spec": {}}
    assert len(eval_then(ctx, rule(body={"then": {"action": "exclude", "target": "kp.Memory", "unique_field": "pn"}}))) == 0


def test_eval_then_exclude_default_field_and_no_prefix():
    ctx = sample_ctx()
    out = eval_then(ctx, rule(body={"then": {"action": "exclude", "target": "Memory"}}))
    assert len(out) == 1  # 缺省 unique_field=pn 仍命中


# ============================================================
# eval_then —— require（必配：数量 + spec 约束）
# ============================================================
def test_eval_then_require_qty():
    ctx = sample_ctx()  # GPU 1 个，GPU供电线 没有
    r = rule(body={"then": {"action": "require", "target": "kp.GPU供电线", "min_qty": 1}})
    assert len(eval_then(ctx, r)) == 1
    ctx["kp"]["GPU供电线"] = {"qty": 1, "items": [{"pn": "CBL-GPU", "spec": {}}], "spec": {}}
    assert len(eval_then(ctx, r)) == 0


def test_eval_then_require_min_qty_field_path():
    ctx = sample_ctx()  # GPU.qty=1
    r = rule(body={"then": {"action": "require", "target": "kp.GPU供电线", "min_qty": "kp.GPU.qty"}})
    out = eval_then(ctx, r)
    assert len(out) == 1
    assert re.search(r"需 1", out[0]["desc"])
    ctx["kp"]["GPU"] = {"qty": 2, "items": [{"pn": "GPU-A", "spec": {}}, {"pn": "GPU-B", "spec": {}}], "spec": {}}
    out2 = eval_then(ctx, r)
    assert len(out2) == 1
    assert re.search(r"需 2", out2[0]["desc"])


def test_eval_then_require_spec_constraint():
    ctx = sample_ctx()
    r = rule(body={"then": {"action": "require", "target": "kp.背板", "spec_constraint": {"support": "tri-mode"}}})
    assert len(eval_then(ctx, r)) == 1
    ctx["kp"]["背板"] = {"qty": 1, "items": [{"pn": "BP-TRI", "spec": {"support": "tri-mode"}}], "spec": {}}
    assert len(eval_then(ctx, r)) == 0
    ctx["kp"]["背板"] = {"qty": 1, "items": [{"pn": "BP-SATA", "spec": {"support": "sata-only"}}], "spec": {}}
    assert len(eval_then(ctx, r)) == 1


# ============================================================
# eval_then —— derive（派生数量：basis ÷ per，ceil/floor）
# ============================================================
def test_eval_then_derive_ceil():
    ctx = sample_ctx()  # sata_qty=8
    out = eval_then(ctx, rule(body={"then": {"action": "derive", "target": "kp.前置背板",
                                              "basis": "config.sata_qty", "per": 8, "round": "ceil"}}))
    assert len(out) == 1
    assert out[0]["deriveQty"] == 1
    assert out[0]["derivePer"] == 8
    assert out[0]["action"] == "derive"


def test_eval_then_derive_ceil_carry():
    ctx = sample_ctx()
    ctx["config"]["sata_qty"] = 9
    out = eval_then(ctx, rule(body={"then": {"action": "derive", "basis": "config.sata_qty",
                                              "per": 8, "target": "kp.前置背板", "round": "ceil"}}))
    assert out[0]["deriveQty"] == 2


def test_eval_then_derive_floor_default():
    ctx = sample_ctx()
    ctx["config"]["sata_qty"] = 9
    out = eval_then(ctx, rule(body={"then": {"action": "derive", "basis": "config.sata_qty",
                                              "per": 8, "target": "kp.前置背板"}}))
    assert out[0]["deriveQty"] == 1  # floor(9/8)=1


def test_eval_then_derive_skip_when_enough_or_basis_zero():
    ctx = sample_ctx()
    r = rule(body={"then": {"action": "derive", "basis": "config.sata_qty", "per": 8,
                             "target": "kp.前置背板", "round": "ceil"}})
    ctx["kp"]["前置背板"] = {"qty": 1, "items": [{"pn": "X"}], "spec": {}}
    assert len(eval_then(ctx, r)) == 0  # 够了
    ctx["config"]["sata_qty"] = 0
    ctx["kp"]["前置背板"]["qty"] = 0
    assert len(eval_then(ctx, r)) == 0  # basis<=0 跳过


# ============================================================
# eval_then —— filter / recommend（总是返回动作）
# ============================================================
def test_eval_then_filter_resolves_value():
    ctx = sample_ctx()  # platform_type=Polaris
    out = eval_then(ctx, rule(body={"then": {"action": "filter", "scope": "server_model",
                                              "field": "series", "op": "==",
                                              "value": "opportunity.platform_type"}}))
    assert len(out) == 1
    assert out[0]["action"] == "filter"
    assert out[0]["filterValue"] == "Polaris"


def test_eval_then_recommend():
    ctx = sample_ctx()
    out = eval_then(ctx, rule(body={"then": {"action": "recommend", "target": "Polaris-G6", "desc": "主推"}}))
    assert len(out) == 1
    assert out[0]["action"] == "recommend"
    assert out[0]["target"] == "Polaris-G6"


# ============================================================
# evaluate_rules —— 多规则编排：status 过滤 + when 不命中跳过
# ============================================================
def test_evaluate_rules_status_filter():
    ctx = sample_ctx()
    rules = [
        rule(id=1, status="draft", body={"then": {"action": "recommend", "target": "X"}}),
        rule(id=2, status="archived", body={"then": {"action": "recommend", "target": "Y"}}),
        rule(id=3, status="active", body={"then": {"action": "recommend", "target": "Z"}}),
    ]
    out = evaluate_rules(rules, ctx)
    assert len(out) == 1
    assert out[0]["target"] == "Z"


def test_evaluate_rules_when_gates():
    ctx = sample_ctx()  # series=Polaris
    rules = [
        rule(id=1, body={"when": {"field": "config.series", "op": "==", "value": "Orion"},
                         "then": {"action": "recommend", "target": "Orion-only"}}),
        rule(id=2, body={"when": {"field": "config.series", "op": "==", "value": "Polaris"},
                         "then": {"action": "recommend", "target": "Polaris-rec"}}),
    ]
    out = evaluate_rules(rules, ctx)
    assert len(out) == 1
    assert out[0]["target"] == "Polaris-rec"


def test_evaluate_rules_default_seed_integration():
    """复刻后端 DEFAULT_RULES（bp_type 赋值 / SATA·SAS·NVMe·GPU线 derive），锁定 seed 与引擎的契约。"""
    ctx = {
        "kp": {"GPU": {"qty": 1, "items": [{"pn": "GPU-A", "spec": {}}], "spec": {}}},
        "config": {"sata_qty": 8, "sas_qty": 0, "nvme_qty": 2, "drive_kinds": ["SATA", "NVMe"]},
        "opportunity": {"platform_type": "Polaris"},
    }
    seed_rules = [
        rule(id=1, name="背板类型：含 NVMe 盘→三模",
             body={"when": {"field": "config.drive_kinds", "op": "contains", "value": "NVMe"},
                   "then": {"action": "derive", "field": "config.bp_type", "value": "tri"}}),
        rule(id=2, name="SATA 线缆根数",
             body={"when": {"field": "config.sata_qty", "op": ">=", "value": 1},
                   "then": {"action": "derive", "target": "SATA", "basis": "config.sata_qty", "per": 8, "round": "ceil"}}),
        rule(id=3, name="SAS 线缆根数",
             body={"when": {"field": "config.sas_qty", "op": ">=", "value": 1},
                   "then": {"action": "derive", "target": "SAS", "basis": "config.sas_qty", "per": 8, "round": "ceil"}}),
        rule(id=4, name="NVMe 线缆根数",
             body={"when": {"field": "config.nvme_qty", "op": ">=", "value": 1},
                   "then": {"action": "derive", "target": "NVMe", "basis": "config.nvme_qty", "per": 2, "round": "ceil"}}),
        rule(id=5, name="GPU 供电线根数",
             body={"when": {"field": "kp.GPU.qty", "op": ">=", "value": 1},
                   "then": {"action": "derive", "target": "GPU线", "basis": "kp.GPU.qty", "per": 1, "round": "ceil"}}),
    ]
    out = evaluate_rules(seed_rules, ctx)
    # 命中：bp_type + SATA(1) + NVMe(1) + GPU线(1) = 4；SAS 因 sas_qty=0 不命中
    assert len(out) == 4
    qty = {a["deriveTarget"]: a["deriveQty"] for a in out if a["action"] == "derive" and a.get("deriveTarget")}
    assert qty["SATA"] == 1
    assert qty["NVMe"] == 1
    assert qty["GPU线"] == 1
    assert "SAS" not in qty
    bp = next((a for a in out if a.get("assignField") == "config.bp_type"), None)
    assert bp is not None and bp["assignValue"] == "tri"


# ============================================================
# eval_assign_value —— 条件→固定值（背板类型），short-circuit
# ============================================================
def test_eval_then_derive_assign():
    ctx = sample_ctx()
    out = eval_then(ctx, rule(body={"then": {"action": "derive", "field": "config.bp_type", "value": "tri"}}))
    assert len(out) == 1
    assert out[0]["action"] == "derive"
    assert out[0]["assignField"] == "config.bp_type"
    assert out[0]["assignValue"] == "tri"
    assert "deriveQty" not in out[0]


def test_eval_assign_value_short_circuit():
    ctx = {"kp": {}, "config": {"drive_kinds": ["NVMe"]}, "opportunity": {}}
    rules = [
        rule(id=1, body={"when": {"field": "config.drive_kinds", "op": "contains", "value": "NVMe"},
                         "then": {"action": "derive", "field": "config.bp_type", "value": "tri"}}),
        rule(id=2, body={"when": {"any": [{"field": "config.drive_kinds", "op": "contains", "value": "SATA"},
                                          {"field": "config.drive_kinds", "op": "contains", "value": "NVMe"}]},
                         "then": {"action": "derive", "field": "config.bp_type", "value": "dc"}}),
    ]
    assert eval_assign_value(rules, ctx, "config.bp_type") == "tri"  # 规则1先命中


def test_eval_assign_value_no_hit_returns_none():
    ctx = {"kp": {}, "config": {"drive_kinds": []}, "opportunity": {}}
    rules = [rule(id=1, body={"when": {"field": "config.drive_kinds", "op": "contains", "value": "SATA"},
                              "then": {"action": "derive", "field": "config.bp_type", "value": "tri"}})]
    assert eval_assign_value(rules, ctx, "config.bp_type") is None


def test_eval_assign_value_skips_arithmetic_and_inactive():
    ctx = sample_ctx()
    rules = [
        rule(id=1, status="draft", body={"then": {"action": "derive", "field": "config.bp_type", "value": "tri"}}),
        rule(id=2, body={"then": {"action": "derive", "basis": "config.sata_qty", "per": 8, "target": "kp.前置背板"}}),
    ]
    assert eval_assign_value(rules, ctx, "config.bp_type") is None
