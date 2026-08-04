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


def load_active_rules() -> list:
    """读选型配置 active 规则（失败回退空表：方案不带规则派生/校验，不阻塞出方案）。"""
    try:
        repo = CompatibilityRuleRepository()
        try:
            return repo.list(status="active")
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

    - plan.chassis_signals.bp_type           背板类型（derive 赋值型首命中；无 → 前端 ?? 'dc' 兜底）
    - plan.chassis_signals.cable_qty_by_kind  各类型线缆根数（derive 算术型按 target 聚合，仅落 >0）
    - plan.selection_alerts                   require/exclude/recommend 命中动作（冲突/缺失/推荐）

    rules 缺省从 DB 读（测试可显式注入，避免依赖 DB）。
    """
    if rules is None:
        rules = load_active_rules()
    if not rules:
        plan.setdefault("chassis_signals", {})
        plan.setdefault("selection_alerts", [])
        return plan

    ctx = cre.plan_rule_context(kp_parts, baseline)
    fired_ids = [
        r.get("id") for r in rules
        if r.get("status") == "active" and cre.eval_when(ctx, cre._body(r).get("when"))
    ]
    actions = cre.evaluate_rules(rules, ctx)

    signals = plan.setdefault("chassis_signals", {})
    # 背板类型：赋值型 derive 首命中（eval_assign_value 按规则顺序 short-circuit）；无命中由消费端兜底
    bp_type = cre.eval_assign_value(rules, ctx, "config.bp_type")
    if bp_type:
        signals["bp_type"] = bp_type
    # 线缆根数：算术型 derive 按 target 聚合（只落 >0 的类型）
    cables = {}
    for a in actions:
        if a.get("action") == "derive" and a.get("deriveTarget") in CABLE_KINDS:
            cables[a["deriveTarget"]] = int(a.get("deriveQty") or 0)
    if cables:
        signals["cable_qty_by_kind"] = {k: v for k, v in cables.items() if v}

    # 校验告警：require/exclude/recommend（derive 只派生不告警，避免噪音）
    alerts = []
    for a in actions:
        if a.get("action") not in ("require", "exclude", "recommend"):
            continue
        alert = {
            "ruleId": a.get("ruleId"),
            "ruleName": a.get("ruleName") or "",
            "action": a.get("action"),
            "severity": a.get("severity") or "info",
            "desc": a.get("desc") or "",
        }
        if a.get("target"):
            alert["target"] = a["target"]
        if a.get("offenders"):
            alert["offenders"] = a["offenders"]
        alerts.append(alert)
    plan["selection_alerts"] = alerts

    if record_hits:
        _record_hits([i for i in fired_ids if i])
    return plan
