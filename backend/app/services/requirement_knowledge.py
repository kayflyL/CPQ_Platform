# -*- coding: utf-8 -*-
"""需求规则知识化注入：requirement 域规则 → brain 系统提示知识块。

设计：docs/需求分析/01_架构与契约/需求规则知识化注入-设计方案.md

- 渲染是 (规则行)→(文本) 的纯函数：无时间戳/轮次号/动态序号，同一规则版本字节稳定
 （KV cache 前缀友好）；
- 绑定按组名（= category）：system_config key=requirement.knowledge_bindings，
  {node_key: [组名]}；规则页是绑定编辑唯一入口，节点抽屉只读；
- 词典卡（平台归置）另有影子校验（CRE 硬命中 vs AI 值：一致标「规则推荐」、
  不一致 contract_warning，永不代填）；原则卡（场景配置基线）纯知识不校验；
- 规则本体只住 rules.compatibility_rules（domain=requirement，铁律③），
  本模块只格式化、不内置规则内容（组级「用法」行是渲染格式的一部分）。
- 一切读失败降级：渲染返回空串/绑定回默认，绝不阻塞回合。
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

PLATFORM_GROUP = "平台归置"
SCENE_GROUP = "场景配置基线"
KNOWLEDGE_GROUPS = (PLATFORM_GROUP, SCENE_GROUP)

BINDINGS_KEY = "requirement.knowledge_bindings"

# 组级「用法」行：一句话启发式（事实型，不写操作规程——更强的模型要更少的脚手架）
_GROUP_USAGE = {
    PLATFORM_GROUP: "用法：按语义就近归置（信号词变体按系列就近处理，如 KH-40000 按 KH 系列处理），填表时注明依据规则",
    SCENE_GROUP: "用法：推荐依据，照此校准数量与必备件；客户明确给过数量时以客户为准",
}

# 默认绑定：平台归置进登记+kp（kp 也要知道 CPU 平台——P1 平台冲突的源头修复）；
# 场景基线只进 kp（要点全在选配件环节用）。形状 = {node_key: {groups, rule_ids}}
# （组绑定 = 整组选入、新规则自动跟进；rule_ids = 单条勾选）
DEFAULT_KNOWLEDGE_BINDINGS = {
    "agent_fill": {"groups": [PLATFORM_GROUP], "rule_ids": []},
    "kp_reason": {"groups": [PLATFORM_GROUP, SCENE_GROUP], "rule_ids": []},
}

_BINDINGS_DESC = "需求分析知识绑定：{node_key: {groups:[组名], rule_ids:[规则id]}}（编辑入口=推理流画布·节点抽屉·规则层；缺 key 启动补默认）"


# ── 绑定存取 ────────────────────────────────────────────────────────────────

def _default_bindings_copy() -> dict:
    from copy import deepcopy
    return deepcopy(DEFAULT_KNOWLEDGE_BINDINGS)


def _clean_node_binding(v) -> dict:
    """单节点绑定值归一：旧形状（[组名] 列表）与新形状（{groups, rule_ids}）统一成
    {groups:[有效组名], rule_ids:[int]}；两组皆空返回 {}（调用方据此删 key）。"""
    groups_raw: list = []
    ids_raw: list = []
    if isinstance(v, dict):
        groups_raw = v.get("groups") or []
        ids_raw = v.get("rule_ids") or []
    elif isinstance(v, list):
        groups_raw = v
    groups = []
    for g in groups_raw:
        g = str(g or "").strip()
        if g in KNOWLEDGE_GROUPS and g not in groups:
            groups.append(g)
    rule_ids: list = []
    for x in ids_raw:
        try:
            i = int(x)
        except (TypeError, ValueError):
            continue
        if i not in rule_ids:
            rule_ids.append(i)
    if not groups and not rule_ids:
        return {}
    return {"groups": groups, "rule_ids": rule_ids}


def _clean_bindings(bindings) -> dict:
    out: dict = {}
    for k, v in (bindings or {}).items():
        key = str(k or "").strip()
        if key:
            clean = _clean_node_binding(v)
            if clean:
                out[key] = clean
    return out


def knowledge_bindings() -> dict:
    """读知识绑定 {node_key: {groups, rule_ids}}（旧列表形状读时归一）。
    键缺失/不可读 → 默认绑定；键存在但为空 dict 是用户的显式「全部解绑」，
    照原样返回（空 dict 不回退默认）。"""
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            val = repo.get_value(BINDINGS_KEY)
        finally:
            repo.close()
        if val is None:
            return _default_bindings_copy()
        if isinstance(val, dict):
            return _clean_bindings(val)
        logger.warning("知识绑定类型异常 %r，回退默认", type(val).__name__)
    except Exception:
        logger.warning("读知识绑定失败（降级：用默认绑定）", exc_info=True)
    return _default_bindings_copy()


def merge_node_bindings(cur: dict, node_key: str, groups: list, rule_ids: list = None) -> dict:
    """纯函数：单节点绑定合并进全量绑定（全量值一并归一新形状——写一次自愈一次）。
    未知组名丢弃、rule_ids 转 int 去重；groups 与 rule_ids 皆空 = 该节点显式解绑
    （删 key）。其他节点不动。"""
    from copy import deepcopy
    out = {}
    for k, v in (cur or {}).items():
        clean = _clean_node_binding(v)
        if clean:
            out[str(k)] = clean
    node_clean = _clean_node_binding({"groups": groups or [], "rule_ids": rule_ids or []})
    if node_clean:
        out[str(node_key)] = node_clean
    else:
        out.pop(str(node_key), None)
    return out


def set_node_bindings(node_key: str, groups: list, rule_ids: list = None) -> dict:
    """写单节点绑定（节点抽屉·规则层入口）：读改写 system_config 全局单键。"""
    next_bindings = merge_node_bindings(knowledge_bindings(), str(node_key), groups, rule_ids)
    from app.repository.system_config_repo import SystemConfigRepository
    repo = SystemConfigRepository()
    try:
        repo.set(BINDINGS_KEY, next_bindings, "json", _BINDINGS_DESC, "system")
    finally:
        repo.close()
    return next_bindings


def ensure_knowledge_bindings_bootstrapped() -> bool:
    """启动期 bootstrap：键缺失时写默认绑定（幂等；只在缺失时写，永不覆盖用户改动）。"""
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            if repo.get(BINDINGS_KEY) is not None:
                return False
            repo.set(BINDINGS_KEY, _default_bindings_copy(), "json",
                     _BINDINGS_DESC, "system")
        finally:
            repo.close()
        return True
    except Exception:
        logger.warning("知识绑定 bootstrap 失败（运行期读缺失键会用默认绑定）", exc_info=True)
        return False


# ── 渲染（确定性纯函数） ────────────────────────────────────────────────────

def _contains_signals(rule: dict) -> list:
    """when 里 contains 条件的信号词（去重、保序）。"""
    from app.services.selection_engine import _body
    when = (_body(rule).get("when") or {})
    conds: list = []
    for key in ("any", "all"):
        v = when.get(key)
        if isinstance(v, list):
            conds.extend(v)
    if isinstance(when.get("field"), str):
        conds.append(when)
    out: list = []
    for c in conds:
        if isinstance(c, dict) and c.get("op") == "contains":
            v = str(c.get("value") or "").strip()
            if v and v not in out:
                out.append(v)
    return out


def render_platform_rule(rule: dict) -> str:
    """词典卡一行：客户提「信号/信号」→ 值（依据：…）。"""
    from app.services.selection_engine import _body
    body = _body(rule)
    then = body.get("then") or {}
    value = str(then.get("value") or "").strip()
    signals = _contains_signals(rule)
    if not value or not signals:
        return ""
    line = f"客户提「{'/'.join(signals)}」→ {value}"
    ev = str(body.get("evidence") or "").strip()
    if ev:
        line += f"（依据：{ev}）"
    return line


def render_scene_rule(rule: dict) -> str:
    """原则卡一行：标题（信号：…）：类目=要点；…（依据：…）。"""
    from app.services.selection_engine import _body
    body = _body(rule)
    then = body.get("then") or {}
    title = str(then.get("title") or rule.get("name") or "").strip()
    parts = [f"{str(i.get('category') or '').strip()}={str(i.get('text') or '').strip()}"
             for i in (then.get("items") or [])
             if isinstance(i, dict) and str(i.get("text") or "").strip()]
    if not parts:
        return ""
    line = title
    signals = _contains_signals(rule)
    if signals:
        line += f"（信号：{'/'.join(signals)}）"
    line += "：" + "；".join(parts)
    ev = str(body.get("evidence") or "").strip()
    if ev:
        line += f"（依据：{ev}）"
    return line


_RENDERERS = {PLATFORM_GROUP: render_platform_rule, SCENE_GROUP: render_scene_rule}


def render_group(group: str, rules: list) -> str:
    """一组 active 规则 → 一个知识块：【需求理解知识·{组}】+ 每规则一行 + 组级用法行。
    无可渲染规则 → 空串（绑定空组不注入空标题）。"""
    renderer = _RENDERERS.get(group)
    if renderer is None:
        return ""
    lines: list = []
    for r in rules or []:
        if str(r.get("status") or "") != "active":
            continue
        try:
            line = renderer(r)
        except Exception:
            logger.warning("规则渲染失败 name=%s（跳过该条）", r.get("name"), exc_info=True)
            continue
        if line:
            lines.append(line)
    if not lines:
        return ""
    out = [f"【需求理解知识·{group}】"] + lines
    usage = _GROUP_USAGE.get(group)
    if usage:
        out.append(usage)
    return "\n".join(out)


def knowledge_for_node(node_key: str, rules: list = None, bindings: dict = None) -> str:
    """节点注入的知识块拼装（brain 系统提示固定段；毫秒级、无 LLM）。
    注入集 = 绑定组的全部 active 规则 ∪ 单条勾选的 rule_ids（active）；
    分块按 KNOWLEDGE_GROUPS 顺序渲染（确定性）。读规则/渲染失败降级空串
    （不带知识继续，不阻塞回合）。"""
    try:
        if bindings is None:
            bindings = knowledge_bindings()
        node = _clean_node_binding(bindings.get(str(node_key or "")))
        groups = node.get("groups") or []
        id_set = set(node.get("rule_ids") or [])
        if not groups and not id_set:
            return ""
        if rules is None:
            from app.services.plan_rule_apply import load_active_rules
            rules = load_active_rules(domain="requirement")
        group_set = set(groups)
        by_group: dict = {}
        for r in rules or []:
            g = str(r.get("category") or "").strip()
            if not g:
                continue
            rid = r.get("id")
            if g in group_set or (id_set and rid is not None and rid in id_set):
                by_group.setdefault(g, []).append(r)
        blocks = [b for b in (render_group(g, by_group.get(g) or []) for g in KNOWLEDGE_GROUPS) if b]
        return "\n\n".join(blocks)
    except Exception:
        logger.warning("知识块渲染失败（降级：不带知识继续）", exc_info=True)
        return ""


# ── 影子校验（词典卡专属；确定性、零 LLM、永不代填） ──────────────────────────

def shadow_check_platform(ext: dict, rules: list = None) -> Optional[dict]:
    """平台归置硬命中：返回 {slot, rule_value}，无命中返回 None。

    求值直接复用 catalog_derivations_for_registration（旧摆桌路径降级为校验器，逻辑不动）；
    对 probe 副本清掉已登记 platform_type 再求——AI 是否已填不影响硬命中的计算
    （比对语义：规则说该是什么）。只报告事实，代填/拦截都不做。
    """
    try:
        from app.services.plan_rule_apply import catalog_derivations_for_registration
        probe = dict(ext or {})
        probe.pop("platform_type", None)
        for slot, value in catalog_derivations_for_registration(probe, rules):
            if slot == "platform_type":
                return {"slot": slot, "rule_value": str(value)}
        return None
    except Exception:
        logger.warning("平台归置影子校验失败（降级：不干预）", exc_info=True)
        return None
