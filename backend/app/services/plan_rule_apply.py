"""整机方案 × 选型配置规则 打通 —— build_plan 产出方案后应用 active 兼容性规则。

把「如何配线 / 硬盘线 / 背板类型」等本属选型配置管辖的规则，从需求分析侧的硬编码
（前端 usePlanBom 镜像）收编到选型配置：这里跑同一套 selection_engine，派生
chassis_signals（bp_type / cable_qty_by_kind）+ 校验告警 selection_alerts，并记录命中
（hit_count「越跑越聪明」真正落地）。

纯求值逻辑在 selection_engine（无 DB）；本模块只负责接线（读规则 / 记命中）。
规则读取/命中失败一律降级（方案不带派生/校验继续出），绝不阻塞推理管线。
"""
import logging

from app.repository.compatibility_rule_repo import CompatibilityRuleRepository
from app.services import selection_engine as cre

logger = logging.getLogger(__name__)

CABLE_KINDS = ("SATA", "SAS", "NVMe", "GPU线")


def load_active_rules(domain: str = "selection") -> list:
    """读某域 active 规则（失败回退空表：方案不带规则派生/校验，不阻塞出方案）。
    domain=selection 选型配置（物理合法性）；domain=requirement 需求分析（业务准确性）。"""
    try:
        repo = CompatibilityRuleRepository()
        try:
            return repo.list(status="active", domain=domain)
        finally:
            repo.close()
    except Exception as e:
        logger.warning("读兼容性规则失败，方案跳过规则校验: %s", e)
        return []


def _record_hits(rule_ids: list) -> None:
    """WHEN 命中的规则批量记命中（推理管线逐方案调用，量小，同步落库可接受）。"""
    if not rule_ids:
        return
    try:
        repo = CompatibilityRuleRepository()
        try:
            repo.record_hits(rule_ids)
        finally:
            repo.close()
    except Exception:
        logger.warning("记录兼容性规则命中失败", exc_info=True)


def apply_plan_selection_rules(plan: dict, kp_parts: list, baseline: dict = None,
                               rules: list = None, record_hits: bool = True) -> dict:
    """在方案上补选型配置规则派生/校验结果（原地改 plan 并返回）。

    2026-11-06 S2 起内部改走 selection_gate.resolve（引擎 v2 单点），**输出契约冻结**：
    - plan.chassis_signals.bp_type           背板类型（赋值型 derive，priority 最高唯一命中）
    - plan.chassis_signals.cable_qty_by_kind  各类型线缆根数（derive 算术型按 target 聚合，仅落 >0）
    - plan.selection_alerts                   require/exclude/recommend 告警（槽位数据钳制映射为
                                              action=recommend/severity=warning，与原数量上限规则
                                              告警同形，消费端零改动）
    """
    if rules is None:
        rules = load_active_rules()
    if not rules:
        plan.setdefault("chassis_signals", {})
        plan.setdefault("selection_alerts", [])
        return plan

    from app.services import selection_gate as gate
    ctx = cre.plan_rule_context(kp_parts, baseline)
    result = gate.resolve(rules, ctx)
    for w in result.get("model_warnings") or []:
        logger.warning("selection_gate 模型告警: %s", w.get("message"))

    signals = plan.setdefault("chassis_signals", {})
    cables = {}
    for d in result.get("derived") or []:
        if d.get("assignField") == "config.bp_type":
            signals["bp_type"] = d.get("assignValue")
        elif d.get("deriveTarget") in CABLE_KINDS:
            cables[d["deriveTarget"]] = int(d.get("deriveQty") or 0)
    if cables:
        signals["cable_qty_by_kind"] = {k: v for k, v in cables.items() if v}

    alerts = []
    for a in (result.get("violations") or []) + (result.get("recommends") or []):
        action = a.get("action")
        if action == "clamp":  # 数据钳制 → 原数量上限规则同形(消费端契约冻结)
            action, sev = "recommend", "warning"
        elif action not in ("require", "exclude", "recommend"):
            continue  # filter/derive 不进告警(derive 只派生,filter 由候选过滤承担)
        else:
            sev = a.get("severity") or "info"
        alert = {
            "ruleId": a.get("ruleId"),
            "ruleName": a.get("ruleName") or "",
            "action": action,
            "severity": sev,
            "desc": a.get("desc") or "",
        }
        if a.get("target"):
            alert["target"] = a["target"]
        if a.get("offenders"):
            alert["offenders"] = a["offenders"]
        alerts.append(alert)
    plan["selection_alerts"] = alerts

    if record_hits:
        _record_hits(gate.fired_rule_ids(rules, ctx))
    return plan


# 登记阶段目录字段接线：CRE 赋值字段 → 线索登记表槽位（机制映射，登记表插头属性）
REGISTRATION_DERIVE_FIELDS = (("opportunity.platform_type", "platform_type"),)


def catalog_derivations_for_registration(ext: dict, rules: list = None) -> list:
    """登记阶段目录字段推导（词典卡求值器）：对空缺目录槽跑 CRE 赋值型 derive 首命中。

    知识化注入后（2026-09-14）地位从「主路径（摆桌）」降为「影子校验器 +
    LLM 不可用兜底」——主路径见 requirement_knowledge（规则渲染成知识块注入 brain）。
    返回 [(slot, value)]；只推导空缺槽（已登记值以登记表为准），规则读取失败降级为空。
    推导值属推断，确认口径住在任务规则 8 + 前提闸门。
    """
    from app.services.selection_engine import eval_assign_value, registration_rule_context
    if rules is None:
        rules = load_active_rules(domain="requirement")
    if not rules:
        return []
    ctx = registration_rule_context(ext)
    out = []
    for cre_field, slot in REGISTRATION_DERIVE_FIELDS:
        if str((ext.get(slot) or "")).strip():
            continue
        val = eval_assign_value(rules, ctx, cre_field)
        if val not in (None, ""):
            out.append((slot, str(val)))
    return out
