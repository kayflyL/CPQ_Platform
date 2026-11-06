"""selection_gate — 选型配置引擎 v2:后端单点判定服务(resolve 协议)。

设计方案:docs/需求分析/01_架构与契约/选型配置引擎-设计方案.md(S1 盘点同目录)。
- resolve(rules, ctx) 是唯一求值出口:人工三面(报价工作台/机箱弹窗/公开向导)与二期 AI
  闸全部消费同一端点,不存在第二份求值逻辑(前端 selectionEngine 求值已随 S3 退役)。
- 纯函数不碰 DB,ctx 由调用方装配(build_context / legacy.plan_rule_context);API 层负责
  取数并剥价格(匿名可达,不带价)。
- 约束语义三层(数据→规则→账本):
  1. 数据钳制(无规则、无配置入口):槽位上限直接来自 base_config(bays/max_cpu/
     max_dimm/psu_bays/gpu_slots);空值/0=未录=不钳(S1 拍板③)。基准配置编辑器就是录入面。
  2. 候选过滤:平台适配两级查找(kp_part_compat 机型级优先,没填按 applicable.series 兜底,
     S1 拍板②;applicable 缺省=通用件,语义同 part_specs._series_ok)+ excludes 候选谓词
     规则(part. 前缀寻址候选件的结构化属性;不兼容件不出现,blocked 明细仅供治理面)。
  3. 方案校验规则:require / exclude / homogeneous(同类一致,类目级 plural,取代逐类目
     exclude ×3)/ resource(资源预算,两侧表达式可含字段路径与倍率)。
- derive 沿用 selection_engine 语义(算术/赋值),赋值型次序改显式 priority:同字段同
  priority 并列命中 = 模型错误进 model_warnings,绝不静默取先(S1 拍板:剔除次序依赖)。
- 降级纪律:规则/数据缺失=引擎放行(violations 为空);调用方自行留白盒痕迹。
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from app.services import selection_engine as legacy
from app.services.part_specs import _series_ok

# 库内同义规格键的读取层归一(不改库;治理面可扩):接口/Interface、TDP/tdp
SPEC_KEY_ALIASES = {"接口": "Interface", "TDP": "tdp"}

# 数据钳制映射:KP 类目 → base_config 槽位字段(引擎内置算子,上限数值来自数据,零业务值)
SLOT_CLAMPS = (("CPU", "max_cpu"), ("Memory", "max_dimm"),
               ("HDD/SSD", "bays"), ("GPU", "gpu_slots"))

_HARD_SEVERITY = "conflict"


def normalize_specs(specs: Optional[dict]) -> dict:
    """规格键名归一(同义键合并到标准键,值不动)。"""
    return {SPEC_KEY_ALIASES.get(k, k): v for k, v in (specs or {}).items()}


def _body(rule: dict) -> dict:
    return legacy._body(rule)


def _priority(rule: dict) -> float:
    p = _body(rule).get("priority")
    return legacy._num(p) if p is not None else 0.0


# ── ctx 装配(调用方直给数据的场景;AI 侧 plan_rule_context 继续用 legacy 装配) ──
_DRIVE_CAT_MARKS = ("HDD", "SSD", "盘")
# 盘协议首命中优先级(与 legacy DRIVE_KIND_KEYS 同序:一件盘只记一种协议)
_DRIVE_KIND_ORDER = (("NVME", "NVMe"), ("SAS", "SAS"), ("SATA", "SATA"))


def build_context(model_row: Optional[dict], selected: Optional[dict],
                  candidates: Optional[dict] = None,
                  compat_by_part: Optional[dict] = None,
                  opportunity: Optional[dict] = None) -> dict:
    """base_config 行 + 已选件 → resolve ctx。

    model_row: l6.base_configs 行(BaseConfigRepository.get 的 dict,psu_wattages 已解 JSON)。
    selected:  {类目: [{pn, name, qty, id?, specs:{原始键:值}}]};PSU 类可带 specs.wattage。
    candidates:{类目: [get_by_category_with_specs 行(剥价后)]},不传=只做方案校验不出候选。
    compat_by_part: {part_id: [server_model…]}(kp_part_compat 展开,机型级适配,优先层)。
    """
    config: dict = {}
    if model_row:
        for k in ("series", "model", "form", "bays", "psu_bays", "gpu_slots",
                  "max_cpu", "max_dimm", "mem_channels", "max_tdp"):
            v = model_row.get(k)
            if v not in (None, ""):
                config[k] = int(v) if isinstance(v, (int, float)) and k != "series" else v
        pw = model_row.get("psu_wattages")
        if isinstance(pw, list) and pw:
            config["psu_wattages"] = pw

    kp: dict = {}
    tdp_sum = 0.0
    psu_capacity = 0.0
    psu_qty = 0
    kind_qty = {"NVMe": 0, "SAS": 0, "SATA": 0}
    drive_kinds: set = set()
    has_drive = False
    for cat, items in (selected or {}).items():
        node = kp.setdefault(cat, {"qty": 0, "items": [], "spec": {}})
        is_drive = any(m in cat.upper() for m in ("HDD", "SSD")) or "盘" in cat
        is_psu = cat.upper() == "PSU" or "电源" in cat
        for it in items or []:
            qty = int(it.get("qty") or 1)
            specs = normalize_specs(it.get("specs"))
            node["qty"] += qty
            node["items"].append({"pn": it.get("pn") or "", "name": it.get("name") or "",
                                  "id": it.get("id"), "qty": qty, "specs": specs})
            tdp = legacy._num(specs.get("tdp"))
            if tdp == tdp:
                tdp_sum += tdp * qty
            watt = legacy._num(specs.get("wattage"))
            if watt == watt and watt > 0:
                psu_capacity += watt * qty
            if is_psu:
                psu_qty += qty
            if is_drive:
                has_drive = True
                hay = f"{str(specs.get('Interface') or '').upper()} {str(it.get('name') or '').upper()}"
                for token, kind in _DRIVE_KIND_ORDER:
                    if token in hay:
                        kind_qty[kind] += qty
                        drive_kinds.add(kind)
                        break
    if has_drive:
        if not drive_kinds:
            drive_kinds.add("SATA")  # 协议不明默认 SATA(与 legacy.plan_rule_context 同口径)
            kind_qty["SATA"] = sum(int(i.get("qty") or 1)
                                   for c, its in (selected or {}).items()
                                   if any(m in c.upper() for m in _DRIVE_CAT_MARKS) or "盘" in c
                                   for i in its or [])
        config.update({"nvme_qty": kind_qty["NVMe"], "sas_qty": kind_qty["SAS"],
                       "sata_qty": kind_qty["SATA"], "drive_kinds": sorted(drive_kinds)})
    if psu_qty:
        config["psu_qty"] = psu_qty
    if tdp_sum:
        config["tdp_sum"] = tdp_sum
    if psu_capacity:
        config["psu_capacity"] = psu_capacity
    elif isinstance(config.get("psu_wattages"), list) and len(config["psu_wattages"]) == 1:
        w = legacy._num(config["psu_wattages"][0])
        if w == w:
            config["psu_capacity"] = w
    return {"kp": kp, "config": config, "opportunity": opportunity or {},
            "candidates": candidates or {}, "compat_by_part": compat_by_part or {}}


# ── 候选级寻址(part. 前缀 → 候选件;其余沿用 legacy:kp./config./opportunity.) ──
def resolve_candidate_field(part: dict, field: Optional[str]) -> Any:
    if not field:
        return None
    if field.startswith("part."):
        rest = field[5:]
        if rest.startswith("spec."):
            return (part.get("specs") or {}).get(rest[5:])
        return part.get(rest)
    return None


def platform_fit(part: dict, ctx: dict) -> tuple[bool, Optional[str]]:
    """两级平台适配(S1 拍板②):kp_part_compat 机型级优先,没填按 applicable.series 兜底。

    - 未锁机型(无 series 且无 model)= 不过滤(通用装配);
    - compat 有该件记录 → 机型级判定(显式数据优先于系列推断);
    - compat 没填 → 系列层:_series_ok 语义(applicable 缺省=通用件;空列表=全隐藏)。
    """
    cfg = ctx.get("config") or {}
    series = str(cfg.get("series") or "").strip()
    model = str(cfg.get("model") or "").strip()
    if not series and not model:
        return True, None
    compat = (ctx.get("compat_by_part") or {}).get(part.get("id"))
    if compat:  # 机型级清单存在(非空列表才算"填了")
        if model and model in compat:
            return True, None
        if model:
            return False, f"机型 {model} 不在该件适配清单"
        # 只锁了系列没锁机型名 → 退系列层
    ok = _series_ok(part.get("applicable"), series)
    return ok, None if ok else f"系列 {series} 不适配"


def _eval_candidate_cond(ctx: dict, cond: Any) -> bool:
    """excludes 候选条件(命中即排除该候选件):value 可为字段路径(config.* 等)或字面量;
    field 走候选件寻址(part. 前缀),op 额外支持 not_exists(缺属性=命中)。"""
    field = cond.get("field") if isinstance(cond, dict) else None
    if not field:
        return True
    if field.startswith("part."):
        actual = resolve_candidate_field(ctx.get("_candidate") or {}, field)
    else:
        actual = legacy.resolve_field(ctx, field)
    if cond.get("op") == "not_exists":
        return not legacy.eval_op(actual, "exists", None)
    expected = legacy.resolve_value(ctx, cond.get("value"))
    return legacy.eval_op(actual, cond.get("op"), expected)


def candidate_blocked(rules: Iterable[dict], ctx: dict, cat: str, part: dict) -> list[dict]:
    """候选件被哪些 excludes 规则过滤(供 blocked.reasons;配置面不渲染 blocked)。"""
    reasons: list[dict] = []
    ctx = dict(ctx)
    ctx["_candidate"] = {**part, "specs": normalize_specs(part.get("specs"))}
    for r in rules:
        if r.get("status") != "active":
            continue
        then = _body(r).get("then") or {}
        if then.get("action") != "excludes":
            continue
        target = str(then.get("target") or "")
        if legacy.parse_cat(target) != cat:
            continue
        if not legacy.eval_when(ctx, _body(r).get("when")):
            continue
        cond = then.get("candidate")
        if isinstance(cond, list):
            hit = all(_eval_candidate_cond(ctx, c) for c in cond)
        else:
            hit = _eval_candidate_cond(ctx, cond)
        if hit:
            reasons.append({"ruleId": r.get("id"), "ruleName": r.get("name") or "",
                            "desc": then.get("desc") or _body(r).get("desc") or r.get("name") or ""})
    return reasons


def _resolve_expr(ctx: dict, expr: Any) -> Optional[float]:
    """resource 表达式:数字字面量 | {field, scale?}。解析不出(缺数据)= None。"""
    if isinstance(expr, (int, float)):
        return float(expr)
    if isinstance(expr, dict) and expr.get("field"):
        base = legacy.resolve_field(ctx, expr["field"])
        n = legacy._num(base)
        if n != n:  # NaN = 缺数据
            return None
        scale = expr.get("scale")
        if scale is not None:
            s = legacy._num(scale)
            n = n * s if s == s else None
        return n
    return None


def _selected_platform_violations(ctx: dict) -> list[dict]:
    """已选件平台校验:过滤只拦「再选」,已进单的不合规件(Excel 导入/切机型残留)
    在这里归因报出。catalog_by_id 由 API 层装配(候选目录的 id→applicable 映射)。"""
    out: list[dict] = []
    catalog = ctx.get("catalog_by_id") or {}
    if not catalog:
        return out
    for cat, node in (ctx.get("kp") or {}).items():
        for it in node.get("items") or []:
            pid = it.get("id")
            row = catalog.get(pid)
            if not row:
                continue
            ok, why = platform_fit({"id": pid, "applicable": row.get("applicable")}, ctx)
            if not ok:
                pn = it.get("pn") or it.get("name") or str(pid)
                out.append({
                    "ruleId": None, "ruleName": "平台适配", "action": "require",
                    "severity": _HARD_SEVERITY,
                    "desc": f"{cat}「{pn}」与当前机型不符({why});换兼容件或移除该行",
                    "target": cat, "caused_by": [f"{cat} {pn}"],
                })
    return out


def _slot_violations(ctx: dict) -> list[dict]:
    """数据钳制(第 1 层,无规则):已选数量 > 槽位上限 → conflict。上限空/0=未录=不钳。"""
    out: list[dict] = []
    cfg = ctx.get("config") or {}
    for cat, cap_key in SLOT_CLAMPS:
        cap = cfg.get(cap_key)
        if not cap or int(cap) <= 0:
            continue
        used = (ctx.get("kp", {}).get(cat) or {}).get("qty") or 0
        if used > int(cap):
            out.append({
                "ruleId": None, "ruleName": "基准配置槽位", "action": "clamp",
                "severity": _HARD_SEVERITY,
                "desc": f"{cat} 已选 {used} 件,超过机型槽位上限 {int(cap)}(基准配置 {cap_key})",
                "target": cat, "caused_by": [f"{cat} ×{used}"],
            })
    psu_bays = cfg.get("psu_bays")
    psu_qty = cfg.get("psu_qty")
    if psu_bays and int(psu_bays) > 0 and psu_qty and int(psu_qty) > int(psu_bays):
        out.append({
            "ruleId": None, "ruleName": "基准配置槽位", "action": "clamp",
            "severity": _HARD_SEVERITY,
            "desc": f"电源数量 {int(psu_qty)} 超过电源槽位 {int(psu_bays)}",
            "target": "PSU", "caused_by": [f"PSU ×{int(psu_qty)}"],
        })
    return out


def _assign_value(rules: list[dict], ctx: dict, field: str,
                  model_warnings: list) -> tuple[Any, Optional[dict]]:
    """赋值型 derive,priority 显式:最高优先级唯一命中才生效;并列 = 模型错误,不静默取先。"""
    hits = []
    for r in rules:
        if r.get("status") != "active":
            continue
        then = _body(r).get("then") or {}
        if then.get("action") != "derive" or then.get("field") != field or "value" not in then:
            continue
        if legacy.eval_when(ctx, _body(r).get("when")):
            hits.append(r)
    if not hits:
        return None, None
    hits.sort(key=_priority, reverse=True)
    top = _priority(hits[0])
    tied = [r for r in hits if _priority(r) == top]
    if len(tied) > 1:
        model_warnings.append({
            "reason_code": "assign_priority_tie",
            "message": f"字段 {field} 有 {len(tied)} 条同优先级赋值规则命中"
                       f"({','.join(str(r.get('id')) for r in tied)}),已拒绝求值,请给规则设 priority",
        })
        return None, None
    return _body(tied[0]).get("then", {}).get("value"), tied[0]


def resolve(rules: list[dict], ctx: dict, with_trace: bool = False) -> dict:
    """resolve 协议(引擎唯一输出形状)。硬违规 severity=conflict/require;derived/recommends 为软输出。"""
    kp = ctx.get("kp") or {}
    model_warnings: list = []
    violations: list = []
    derived: list = []
    recommends: list = []
    trace: list = []
    assign_fields: list = []  # 赋值型 derive 字段(去重保序),循环后统一按 priority 求值

    # 1) 数据钳制(第 1 层)
    violations.extend(_slot_violations(ctx))
    # 1.5) 已选件平台校验(残留场景兜底:过滤只管再选,进单的不合规件在这里报出)
    violations.extend(_selected_platform_violations(ctx))

    # 2) 方案校验规则(第 3 层;require/exclude/derive/recommend 复用 legacy eval_then 语义)
    for r in rules or []:
        if r.get("status") != "active":
            continue
        body = _body(r)
        then = body.get("then") or {}
        action = then.get("action")
        when_hit = legacy.eval_when(ctx, body.get("when"))
        fired = []
        if when_hit:
            if action == "homogeneous":
                cats = then.get("categories") or ([legacy.parse_cat(then.get("target"))]
                                                  if then.get("target") else [])
                field = then.get("field") or "pn"
                for cat in cats:
                    vals = []
                    for it in (kp.get(cat) or {}).get("items") or []:
                        v = it.get(field)
                        if v not in (None, ""):
                            vals.append(str(v))
                    uniq = list(dict.fromkeys(vals))
                    if len(uniq) > 1:
                        fired.append({
                            "ruleId": r.get("id"), "ruleName": r.get("name") or "",
                            "action": "exclude", "severity": _HARD_SEVERITY,
                            "desc": then.get("desc") or body.get("desc")
                                    or f"{cat} 须同型号(同类一致),出现 {len(uniq)} 种",
                            "target": cat, "offenders": uniq,
                            "caused_by": [f"{cat} {v}" for v in uniq],
                        })
            elif action == "resource":
                chk = then.get("check") or {}
                lhs = _resolve_expr(ctx, chk.get("lhs"))
                rhs = _resolve_expr(ctx, chk.get("rhs"))
                if lhs is None or rhs is None:
                    model_warnings.append({
                        "reason_code": "resource_missing_data",
                        "message": f"规则「{r.get('name')}」表达式缺数据(lhs={lhs}, rhs={rhs}),本轮跳过",
                    })
                else:
                    ok = legacy.eval_op(lhs, chk.get("op", "<="), rhs)
                    if not ok:
                        fired.append({
                            "ruleId": r.get("id"), "ruleName": r.get("name") or "",
                            "action": "require", "severity": _HARD_SEVERITY,
                            "desc": (then.get("desc") or body.get("desc") or
                                     f"资源约束不满足:{chk.get('lhs')} {chk.get('op')} {chk.get('rhs')}"
                                     f"(实际 {lhs:g} vs {rhs:g})"),
                            "caused_by": [],
                        })
            elif action == "derive" and then.get("field") and "value" in then:
                if then.get("field") not in assign_fields:
                    assign_fields.append(then["field"])
            else:
                fired.extend(legacy.eval_then(ctx, r))
        if with_trace:
            trace.append({"ruleId": r.get("id"), "name": r.get("name") or "",
                          "when_hit": when_hit, "actions": fired})
        for a in fired:
            act = a.get("action")
            if act in ("require", "exclude"):
                a.setdefault("caused_by", [])
                violations.append(a)
            elif act == "derive":
                derived.append(a)
            elif act == "recommend":
                recommends.append(a)
            # filter:声明型,候选过滤由 excludes 承担;保留在 recommends 里供治理面可见
            elif act == "filter":
                recommends.append(a)
    # 赋值型 derive:按 priority 单点生效(同字段并列命中 = 模型错误)
    for field in assign_fields:
        value, winner = _assign_value(rules, ctx, field, model_warnings)
        if value is not None and winner is not None:
            derived.append({"ruleId": winner.get("id"), "ruleName": winner.get("name") or "",
                            "action": "derive", "severity": "info",
                            "assignField": field, "assignValue": value})
            if with_trace:
                for t in trace:
                    if t.get("ruleId") == winner.get("id"):
                        t.setdefault("actions", []).append({"action": "derive", "assignField": field,
                                                            "assignValue": value})

    # 3) 候选过滤(第 2 层):平台适配 + excludes 谓词;blocked 只给治理面,配置面只取 allowed
    options: dict = {}
    for cat, parts in (ctx.get("candidates") or {}).items():
        allowed, blocked = [], []
        for p in parts or []:
            reasons = []
            ok, why = platform_fit(p, ctx)
            if not ok:
                reasons.append({"ruleId": None, "ruleName": "平台适配",
                                "desc": why or "平台不适配"})
            reasons.extend(candidate_blocked(rules, ctx, cat, p))
            if reasons:
                blocked.append({"id": p.get("id"), "model": p.get("model") or "",
                                "reasons": reasons})
            else:
                allowed.append({"id": p.get("id"), "model": p.get("model") or "",
                                "brand": p.get("brand") or "",
                                "specs": normalize_specs(p.get("specs"))})
        options[cat] = {"allowed": allowed, "blocked": blocked}

    # 4) 账本(第 1 层的常显投影)
    cfg = ctx.get("config") or {}
    slots = {}
    for cat, cap_key in SLOT_CLAMPS:
        cap = cfg.get(cap_key)
        slots[cap_key] = {"used": (kp.get(cat) or {}).get("qty") or 0,
                          "max": int(cap) if cap else None}
    slots["psu"] = {"used": int(cfg.get("psu_qty") or 0),
                    "max": int(cfg["psu_bays"]) if cfg.get("psu_bays") else None}
    budget = {
        "psu_load_w": cfg.get("tdp_sum"),
        "psu_capacity_w": cfg.get("psu_capacity"),
        "slots": slots,
    }

    out = {"options": options, "violations": violations, "derived": derived,
           "recommends": recommends, "budget": budget,
           "model_warnings": model_warnings}
    if with_trace:
        out["trace"] = trace
    return out


def fired_rule_ids(rules: list[dict], ctx: dict) -> list[int]:
    """when 命中的规则 id(命中计数「越跑越聪明」用)。"""
    out = []
    for r in rules or []:
        if r.get("status") == "active" and legacy.eval_when(ctx, _body(r).get("when")):
            rid = r.get("id")
            if rid:
                out.append(rid)
    return out
