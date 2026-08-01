"""选型规则求值引擎（后端）—— frontend/src/stores/selectionEngine.ts 的等价 Python 移植。

声明式 WHEN(条件)→THEN(动作) 规则求值。与前端 selectionEngine **共用同一份规则数据(DB)**，
求值器双端维护、由对齐的测试（backend/tests/test_selection_engine.py ↔ selectionEngine.test.ts）锁语义一致。
body schema 见 backend/app/repository/compatibility_rule_repo.DEFAULT_RULES：
  when: { all?:[cond], any?:[cond] } | cond     cond = { field, op, value }
  then: { action, ... }     action ∈ require/exclude/derive/filter/recommend
  字段寻址：kp.<category>.qty / kp.<category>.spec.<key> / config.series / config.sata_qty / opportunity.platform_type

纯求值、无副作用、不碰 DB —— 规则由调用方注入（先 list active 规则，再传入）。
设计目的：让 reasoning-flow / 服务端校验也能跑同一套选型规则，消除「规则只在前端生效」的割裂。
"""
from __future__ import annotations

import json
import math
from typing import Any, Iterable, Optional

# 与前端 selectionEngine.ts 对齐的常量
FIELD_PATH_PREFIXES = ("kp.", "config.", "opportunity.")
DRIVE_KIND_KEYS = ("SATA", "SAS", "NVMe")  # 顺序即优先级：返回首个命中


def _is_field_path(v: Any) -> bool:
    return isinstance(v, str) and v.startswith(FIELD_PATH_PREFIXES)


def _num(v: Any) -> float:
    """对齐 TS Number()：转 float；None/""/不可解析 → nan（供 isfinite/真值判定）。"""
    if v is None or v == "":
        return float("nan")
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _loose_eq(a: Any, b: Any) -> bool:
    """复刻 TS == 宽松相等：两侧都能转数则按数比（'3'==3 → True），否则按字符串比。"""
    na, nb = _num(a), _num(b)
    if not (math.isnan(na) or math.isnan(nb)):
        return na == nb
    return str(a) == str(b)


def _body(rule: dict) -> dict:
    """读 rule['body']：DB 里存的是 JSON 字符串，内存 dict 里可能是 dict；统一成 dict。"""
    body = rule.get("body")
    if body is None:
        return {}
    if isinstance(body, str):
        try:
            return json.loads(body) or {}
        except (TypeError, ValueError):
            return {}
    return body if isinstance(body, dict) else {}


# ── 字段寻址 ──────────────────────────────────────────────────────────────
def resolve_field(ctx: dict, field: Optional[str]) -> Any:
    """解析字段路径 → context 实际值。kp.GPU.qty / config.series / opportunity.platform_type"""
    if not field:
        return None
    parts = field.split(".")
    root = parts[0]
    if root == "kp":
        if len(parts) < 2:
            return None
        node = ctx.get("kp", {}).get(parts[1])
        if not node:
            return None
        if len(parts) >= 3 and parts[2] == "qty":
            return node.get("qty")
        if len(parts) >= 4 and parts[2] == "spec":
            return (node.get("spec") or {}).get(parts[3])
        return None
    if root == "config":
        return ctx.get("config", {}).get(parts[1]) if len(parts) >= 2 else None
    if root == "opportunity":
        return ctx.get("opportunity", {}).get(parts[1]) if len(parts) >= 2 else None
    return None


def resolve_value(ctx: dict, v: Any) -> Any:
    """若 v 是字段路径则取 context 值（解析不到退回字面量），否则原样返回。"""
    if _is_field_path(v):
        resolved = resolve_field(ctx, v)
        if resolved is not None:
            return resolved
    return v


# ── 操作符语义 ────────────────────────────────────────────────────────────
def eval_op(actual: Any, op: str, expected: Any) -> bool:
    if op == "exists":
        return actual is not None and actual != ""
    if op == ">=":
        return _num(actual) >= _num(expected)
    if op == "<=":
        return _num(actual) <= _num(expected)
    if op == ">":
        return _num(actual) > _num(expected)
    if op == "<":
        return _num(actual) < _num(expected)
    if op == "==":
        return _loose_eq(actual, expected)
    if op == "!=":
        return not _loose_eq(actual, expected)
    if op == "in":
        return isinstance(expected, (list, tuple, set)) and actual in expected
    if op == "contains":
        if isinstance(actual, (list, tuple, set)):
            return expected in actual
        return str(expected) in str(actual if actual is not None else "")
    return False


def eval_condition(ctx: dict, cond: Any) -> bool:
    if not cond or not isinstance(cond, dict) or not cond.get("field"):
        return True
    return eval_op(
        resolve_field(ctx, cond.get("field")),
        cond.get("op"),
        resolve_value(ctx, cond.get("value")),
    )


def eval_when(ctx: dict, when: Any) -> bool:
    if not when:
        return True
    if isinstance(when, dict):
        if isinstance(when.get("all"), list):
            return all(eval_condition(ctx, c) for c in when["all"])
        if isinstance(when.get("any"), list):
            return any(eval_condition(ctx, c) for c in when["any"])
        if when.get("field"):
            return eval_condition(ctx, when)
    return True


def parse_cat(target: Optional[str]) -> str:
    if not target:
        return ""
    return target[3:] if target.startswith("kp.") else target


def normalize_drive_kind(raw: Any) -> Optional[str]:
    """盘类型规范化：任意来源字符串 → SATA/SAS/NVMe（大小写无关），无法识别返回 None。"""
    up = str(raw if raw is not None else "").upper()
    for k in DRIVE_KIND_KEYS:
        if k.upper() in up:
            return k
    return None


def read_item_field(item: Any, field: str) -> Any:
    if not field or not isinstance(item, dict):
        return None
    if field.startswith("spec."):
        return (item.get("spec") or {}).get(field[5:])
    return item.get(field)


# ── THEN 求值 ─────────────────────────────────────────────────────────────
def eval_then(ctx: dict, rule: dict) -> list[dict]:
    body = _body(rule)
    then = body.get("then")
    if not then:
        return []
    desc = body.get("desc") or rule.get("name")
    base = {"ruleId": rule.get("id"), "ruleName": rule.get("name"), "desc": desc}
    action = then.get("action")

    if action == "exclude":
        cat = parse_cat(then.get("target"))
        node = ctx.get("kp", {}).get(cat)
        if not node or len(node.get("items") or []) < 2:
            return []
        field = then.get("unique_field") or "pn"
        vals = [read_item_field(it, field) for it in (node.get("items") or [])]
        vals = [v for v in vals if v not in (None, "")]
        uniq = list(dict.fromkeys(str(v) for v in vals))  # 保序去重
        if len(uniq) > 1:
            return [{**base, "action": "exclude", "severity": "conflict", "target": cat,
                     "offenders": uniq, "desc": then.get("desc") or desc}]
        return []

    if action == "require":
        cat = parse_cat(then.get("target"))
        node = ctx.get("kp", {}).get(cat)
        min_qty = 1
        if then.get("min_qty") is not None:
            n = _num(resolve_value(ctx, then.get("min_qty")))
            min_qty = int(n) if (not math.isnan(n) and n) else 1
        have_qty = (node or {}).get("qty") or 0
        spec_ok = True
        sc = then.get("spec_constraint")
        if sc and node:
            spec_ok = any(
                all(str((it.get("spec") or {}).get(k, "")) == str(v) for k, v in sc.items())
                for it in (node.get("items") or [])
            )
        if have_qty < min_qty or not spec_ok:
            lack = (f"缺少 {cat}（需 {min_qty}，现有 {have_qty}）"
                    if have_qty < min_qty else f"{cat} 规格不符")
            return [{**base, "action": "require", "severity": "require", "target": cat,
                     "desc": then.get("desc") or lack}]
        return []

    if action == "derive":
        # 赋值型：then 带 field + value（条件→固定值，如 背板类型=tri）
        if then.get("field") and "value" in then:
            return [{**base, "action": "derive", "severity": "info",
                     "assignField": then.get("field"), "assignValue": then.get("value"),
                     "desc": then.get("desc") or desc}]
        # 算术型：basis ÷ per，ceil/floor
        basis_val = _num(resolve_value(ctx, then.get("basis")))
        per = _num(then.get("per")) or 1
        if math.isnan(basis_val) or basis_val <= 0:
            return []
        qty = math.ceil(basis_val / per) if then.get("round") == "ceil" else math.floor(basis_val / per)
        cat = parse_cat(then.get("target"))
        have_qty = (ctx.get("kp", {}).get(cat) or {}).get("qty") or 0
        if have_qty < qty:
            return [{**base, "action": "derive", "severity": "info",
                     "deriveTarget": cat, "deriveQty": qty, "derivePer": per,
                     "desc": then.get("desc") or f"{cat} 建议配 {qty}（现有 {have_qty}）"}]
        return []

    if action == "filter":
        return [{**base, "action": "filter", "severity": "info",
                 "filterScope": then.get("scope"), "filterField": then.get("field"),
                 "filterOp": then.get("op"), "filterValue": resolve_value(ctx, then.get("value")),
                 "desc": then.get("desc") or desc}]

    if action == "recommend":
        return [{**base, "action": "recommend", "severity": "info",
                 "target": then.get("target"), "desc": then.get("desc") or desc}]

    return []


def evaluate_rules(rules: Iterable[dict], ctx: dict) -> list[dict]:
    """对一组配置 context 跑全部 active 规则，返回命中动作清单。"""
    out: list[dict] = []
    for r in rules:
        if r.get("status") != "active":
            continue
        if not eval_when(ctx, _body(r).get("when")):
            continue
        out.extend(eval_then(ctx, r))
    return out


def eval_assign_value(rules: Iterable[dict], ctx: dict, field: str) -> Any:
    """求某赋值型字段的目标值（如背板类型 config.bp_type）。
    按 rules 原顺序，首条 when 命中且 then 为赋值型 derive + field 匹配的规则生效（short-circuit）。
    「更具体的规则放前、宽泛规则放后」。无命中返回 None（交消费端兜底）。"""
    for r in rules:
        if r.get("status") != "active":
            continue
        then = _body(r).get("then")
        if not then or then.get("action") != "derive":
            continue
        if not (then.get("field") and "value" in then):
            continue
        if then.get("field") != field:
            continue
        if eval_when(ctx, _body(r).get("when")):
            return then.get("value")
    return None
