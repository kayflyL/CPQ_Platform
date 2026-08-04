# -*- coding: utf-8 -*-
"""目录驱动引导（catalog-guided clarification）—— 需求不明确时的反问状态机。

旧思路（workload 负载词表 + rebuttal 话术模板）已废弃：选项是臆造的，和库里真实目录对不齐，
客户选了库里没有的「类型」永远猜不准。新思路的核心原则：**反问内容 100% 来自产品目录**，
不猜、不臆造——库里有什么才推什么：

    第 1 步 选「服务器类型」  →  l6.server_types（有在售机型的类型才推）
    第 2 步 选「机型」        →  l6.server_models（按类型过滤，在售才推）
    第 3 步 按该类型支持的 KP 品类套餐给「填写格式模板」→ 引导客户按格式回复规格/预算

回复解析不靠猜：
  - 选类型/机型 = 与上一轮推给用户的选项做匹配（匹配不上且无规格 → 走「推荐默认」）；
  - KP 格式 = 由 extract_keywords 的信号抽取（型号/数量/容量/预算）拾取，格式越规范识别率越高。

状态持久化在商机 extra_fields（requirement_catalog_stage/type_name/model_id/offered），
跨重启、跨多用户；每一轮推进一个 stage，直到 done → clarity_check 视为 explicit → 出方案。

配置（ask_user 节点 config，需求中心画布抽屉可视化编辑，拒绝把内容硬编码在代码里）：
    enabled_types      []           启用的类型（空 = 全部有货类型）
    recommended_type   ""           客户说「不确定/你推荐」时的默认类型（空 = 第一个）
    recommended_models {}           类型名 → 代表性机型名（客户不选机型时用）
    type_question / model_question / kp_intro / default_hint / reply_format / max_rounds
"""
from __future__ import annotations

import re
from typing import Optional

from app.repository.server_catalog_repo import ServerCatalogRepository

# 会话阶段（持久化在商机 extra_fields.requirement_catalog_stage）
STAGE_TYPE = "type"      # 等客户选类型
STAGE_MODEL = "model"    # 等客户选机型
STAGE_KP = "kp"          # 等客户按格式填 KP 规格/预算
STAGE_DONE = "done"      # 信息足够（clarity_check 视为 explicit）

# 反问最多 N 轮兜底（与 MAX_CLARIFY_ROUNDS 同语义；正常流程 3 步即可走完，这是死循环保险）
DEFAULT_MAX_ROUNDS = 6

# 默认引导配置 —— 仅作为「画布 seed / 配置缺失时的运行时兜底」；
# 权威来源是 ask_user 节点 config（DB），需求中心可编辑。内容可整体替换，不散落硬编码。
DEFAULT_ASK_CONFIG: dict = {
    "mode": "catalog",
    "enabled_types": [],
    "recommended_type": "",
    "recommended_models": {},
    "max_rounds": DEFAULT_MAX_ROUNDS,
    "type_question": "请选择服务器类型（以下均为有货在售类型）：",
    "model_question": "请选择该类型下的在售机型：",
    "kp_intro": "请按以下格式填写需要的配件，没有的项可省略：",
    "reply_format": (
        "CPU：型号 ×数量\n"
        "内存：容量 ×条数\n"
        "GPU：型号 ×数量\n"
        "硬盘：容量 ×数量\n"
        "预算：金额"
    ),
    "default_hint": "不确定可回复「你推荐」，或点「跳过」让我推荐",
}

# ── 引导话术识别词（数据驱动：system_config.requirement_guide_words；以下为读失败兜底）──
_GUIDE_WORDS_FALLBACK = {
    "default": ["不确定", "你推荐", "还没定", "越大越好", "都可以", "不限", "随便", "您推荐", "帮我选"],
    "delegate": ["你帮我推荐", "帮我推荐", "你来推荐", "你推荐", "你定", "你来定", "你看着办",
                 "听你的", "随便", "都行", "都可以", "怎么都行", "帮我选", "你帮选", "帮我来一台"],
    "spec_hint_re": ["cpu", "内存", "gpu", "硬盘", "ssd", "hdd", "nvme", "raid", "网卡",
                     "万兆", "千兆", "机架", "塔式", "[1-8]\\s*u\\b", "核", "颗", "条", "张"],
}


def load_guide_words() -> dict:
    """读引导话术配置（system_config.requirement_guide_words），缺失/异常回退常量。"""
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            cfg = repo.get_value("requirement_guide_words")
        finally:
            repo.close()
        if isinstance(cfg, dict) and cfg:
            return {**_GUIDE_WORDS_FALLBACK, **cfg}
    except Exception:
        pass
    return dict(_GUIDE_WORDS_FALLBACK)


def _guide_text_ok(words: list) -> str:
    return "|".join(re.escape(w) for w in (words or []) if w)


def load_ask_config(flow_configs: Optional[dict]) -> dict:
    """读 ask_user 节点 config（DB 权威），缺失字段用默认兜底。flow_configs 为 None → 默认。"""
    cfg = {}
    if flow_configs:
        cfg = dict(flow_configs.get("ask_user") or {})
    merged = dict(DEFAULT_ASK_CONFIG)
    merged.update({k: v for k, v in cfg.items() if v is not None})
    return merged


def is_default_reply(text: str) -> bool:
    """客户答「不确定/你推荐/随便…」= 放弃指定，走推荐默认（词表来自配置，可编辑）。"""
    low = (text or "").strip()
    if not low:
        return False
    g = load_guide_words()
    _re = re.compile(_guide_text_ok(g.get("default") or []) + "|" + _guide_text_ok(g.get("delegate") or []), re.IGNORECASE)
    return bool(_re.search(low))


def has_spec_hint(text: str) -> bool:
    """回复里有具体规格线索（贴了配置清单/参数）→ 视为直接给规格，跳层级（正则来自配置）。"""
    low = (text or "").strip()
    if not low:
        return False
    g = load_guide_words()
    for pat in (g.get("spec_hint_re") or []):
        if pat and re.search(pat, low, re.IGNORECASE):
            return True
    return False


def _normalize(s: str) -> str:
    return re.sub(r"[\s/、，,。;；:：]+", "", (s or "")).lower()


def match_option(reply: str, options: list) -> Optional[str]:
    """回复与上一轮推给客户的选项匹配（归一化子串双向匹配）。无命中返回 None。"""
    if not reply or not options:
        return None
    r = _normalize(reply)
    if not r:
        return None
    for o in options:
        no = _normalize(o)
        if no and (no in r or r in no):
            return o
    return None


# ── 目录读取（真实数据源：l6.server_types / l6.server_models）────────────────
def _in_sale(model: dict) -> bool:
    return (model.get("lifecycle_status") or "active") not in ("discontinued", "eol")


def load_catalog() -> tuple:
    """返回 (types, models_by_type_name)。
    types：启用且至少有一个在售机型的类型 [{id,name,...}]；
    models_by_type_name：类型名 → 在售机型列表（id/name/description/series/form）。"""
    repo = ServerCatalogRepository()
    try:
        all_types = repo.list_types()
        models_by_type: dict = {}
        for t in all_types:
            ms = [m for m in repo.list_models(type_id=t.get("id")) if _in_sale(m)]
            if ms:
                models_by_type[t.get("name") or ""] = ms
        types = [t for t in all_types if (t.get("name") or "") in models_by_type]
    finally:
        pass
    return types, models_by_type


def _enabled_types(ask_cfg: dict, types: list) -> list:
    enabled = ask_cfg.get("enabled_types") or []
    if not enabled:
        return types
    return [t for t in types if t.get("name") in enabled]


def recommended_type_name(ask_cfg: dict, types: list) -> Optional[str]:
    rec = ask_cfg.get("recommended_type") or ""
    if rec and any(t.get("name") == rec for t in types):
        return rec
    return types[0].get("name") if types else None


def recommended_model_id(ask_cfg: dict, type_name: Optional[str], models_by_type: dict) -> Optional[int]:
    if not type_name:
        return None
    models = models_by_type.get(type_name) or []
    if not models:
        return None
    rec = (ask_cfg.get("recommended_models") or {}).get(type_name) or ""
    for m in models:
        if m.get("name") == rec:
            return m.get("id")
    return models[0].get("id")


def kp_categories_for_type_name(type_name: Optional[str], flow_configs: Optional[dict]) -> list:
    """该类型支持的 KP 品类套餐。数据源：match_kp 节点 config.type_packages（DB）；
    配置缺失时兜底回模块常量（与 match_kp 执行器同一来源，避免两处漂移）。"""
    if not type_name:
        return []
    from app.api.candidate_search import kp_categories_for_type, TYPE_KP_CATEGORIES
    packages = (flow_configs or {}).get("match_kp", {}).get("type_packages")
    if not packages:
        packages = [{"type_keyword": k, "categories": v} for k, v in TYPE_KP_CATEGORIES.items()]
    return kp_categories_for_type(type_name, packages, requested_cats=None)


# ── 阶段推进（纯逻辑，测试友好）──────────────────────────────────────────
def advance_stage(state: dict, reply: str, ask_cfg: dict,
                  types: list, models_by_type: dict) -> dict:
    """消费客户上一轮回复，推进目录引导阶段。返回新 state（stage/type_name/model_id/offered）。

    规则（全部围绕「别猜」）：
      - 回复命中上一轮选项 → 按选项推进（type → model → kp）；
      - 回复为「不确定/你推荐」→ 用配置的推荐类型/代表性机型，直接 done（已委托，不再追问）；
      - 回复含具体规格 → 跳过层级直接 done（extract 会拾取规格）；
      - 其余无法识别 → 用推荐默认推进到下一问（不重复问同一句）。
    """
    state = dict(state or {})
    stage = state.get("stage") or ""
    reply = (reply or "").strip()
    types = _enabled_types(ask_cfg, types)

    if stage in ("", STAGE_TYPE):
        chosen = match_option(reply, [t.get("name") or "" for t in types])
        if chosen:
            return {"stage": STAGE_MODEL, "type_name": chosen, "model_id": None, "offered": {}}
        if is_default_reply(reply):
            tn = recommended_type_name(ask_cfg, types)
            return {
                "stage": STAGE_DONE, "type_name": tn,
                "model_id": recommended_model_id(ask_cfg, tn, models_by_type), "offered": {},
            }
        if has_spec_hint(reply):
            return {"stage": STAGE_DONE, "type_name": None, "model_id": None, "offered": {}}
        tn = recommended_type_name(ask_cfg, types)
        return {"stage": STAGE_MODEL, "type_name": tn, "model_id": None, "offered": {}}

    if stage == STAGE_MODEL:
        tn = state.get("type_name")
        models = models_by_type.get(tn or "") or []
        chosen = match_option(reply, [m.get("name") or "" for m in models])
        if chosen:
            mid = next((m.get("id") for m in models if m.get("name") == chosen), None)
            return {"stage": STAGE_KP, "type_name": tn, "model_id": mid, "offered": {}}
        if is_default_reply(reply):
            return {
                "stage": STAGE_DONE, "type_name": tn,
                "model_id": recommended_model_id(ask_cfg, tn, models_by_type), "offered": {},
            }
        if has_spec_hint(reply):
            return {"stage": STAGE_DONE, "type_name": tn, "model_id": None, "offered": {}}
        mid = recommended_model_id(ask_cfg, tn, models_by_type)
        return {"stage": STAGE_KP, "type_name": tn, "model_id": mid, "offered": {}}

    if stage == STAGE_KP:
        # 客户已选类型+机型，任何实质回复都视为「按格式填了」——规格由 extract 拾取，
        # 没填的字段由方案卡标注「需手填」，不再追问（旧版逐个问已被证明体验差）。
        return {"stage": STAGE_DONE, "type_name": state.get("type_name"),
                "model_id": state.get("model_id"), "offered": {}}

    return state


def advance_with_catalog(state: dict, reply: str, ask_cfg: dict) -> dict:
    types, models_by_type = load_catalog()
    return advance_stage(state, reply, ask_cfg, types, models_by_type)


# ── 问题生成（纯逻辑）─────────────────────────────────────────────────────
def _default_format(cats: list) -> str:
    lines = []
    mapping = {
        "CPU": "CPU：型号 ×数量",
        "Memory": "内存：容量 ×条数",
        "GPU": "GPU：型号 ×数量",
        "HDD/SSD": "硬盘：容量 ×数量",
        "Raid card": "RAID：型号",
        "NIC": "网卡：型号 ×数量",
    }
    for c in cats:
        lines.append(mapping.get(c, f"{c}：需求描述"))
    if not lines:
        lines.append("配件：型号 ×数量")
    lines.append("预算：金额")
    return "\n".join(lines)


def build_question(stage: str, state: dict, ask_cfg: dict,
                   types: list, models_by_type: dict, flow_configs: Optional[dict]) -> tuple:
    """按当前阶段生成 (question, options, offered, format)。offered 持久化供下轮选项匹配。"""
    cfg = ask_cfg or {}
    types = _enabled_types(cfg, types)
    hint = cfg.get("default_hint") or ""

    if stage in ("", STAGE_TYPE):
        opts = [t.get("name") or "" for t in types][:6]
        q = cfg.get("type_question") or DEFAULT_ASK_CONFIG["type_question"]
        if hint:
            q += f"\n（{hint}）"
        return q, opts + (["不确定/你推荐"] if opts else []), {"type": opts}, ""

    if stage == STAGE_MODEL:
        tn = state.get("type_name")
        models = models_by_type.get(tn or "") or []
        opts = [m.get("name") or "" for m in models][:6]
        base = cfg.get("model_question") or DEFAULT_ASK_CONFIG["model_question"]
        q = base + (f"（{tn}）" if tn else "")
        if hint:
            q += f"\n（{hint}）"
        return q, opts + (["不确定/你推荐"] if opts else []), {"model": opts}, ""

    if stage == STAGE_KP:
        cats = kp_categories_for_type_name(state.get("type_name"), flow_configs)
        fmt = cfg.get("reply_format") or _default_format(cats)
        intro = cfg.get("kp_intro") or DEFAULT_ASK_CONFIG["kp_intro"]
        q = f"{intro}\n{fmt}"
        if cats:
            q += f"\n可选项配件品类：{' / '.join(cats)}"
        return q, ["不确定/你推荐"], {"type": [], "model": []}, fmt

    # STAGE_DONE（防御：正常不会走到，clarity_check 已放行）
    return "信息已足够，正在生成方案…", [], {}, ""


def build_question_with_catalog(stage: str, state: dict, ask_cfg: dict,
                                flow_configs: Optional[dict]) -> tuple:
    types, models_by_type = load_catalog()
    return build_question(stage, state, ask_cfg, types, models_by_type, flow_configs)
