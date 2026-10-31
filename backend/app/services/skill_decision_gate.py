# -*- coding: utf-8 -*-
"""skill_decision_gate —— 决策闸（P1.5）：库内多候选、用户没拍板时，机械拦下 AI 的自填并发卡。

第四个闸（缺口闸/确认闸/问答协议之后）。设计：docs/决策闸设计-P1.5.md。
声明在流节点配置（配置者定语义，引擎保执行）：

    "decisions": [
      {"slot": "gpu", "match_category": "GPU",
       "question": "GPU 在库有多款满足规格的候选，选哪款？",
       "min_candidates": 2, "allow_other": true}
    ]

闸判定（part_lock_verdict）：行类目命中声明 + 库内候选 ≥ min_candidates + 该 slot 无
用户信号（user_signal_for：AI 自填不产生信号）→ card（不锁定，AI pick 记推荐默认项，
沿用 2026-09-09"不许静默锁 AI 拍的料"语义）；否则 allow。候选检索失败 fail-open 但带
decision_gate_degraded 标注（闸失效一次可见，不把流程卡死）。
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_STOP_TOKENS = {"g", "个", "只", "条", "颗", "台", "以上", "以下", "左右"}

# ── 候选/信号供给者注入口（第 5 步画边界解耦）：闸机制只认回调，不 import 配件域。
# 宿主接线（app 启动时 set_candidate_provider）供给两件事：
#   search_candidates(category, text, series, price_ok, limit) -> list[dict]  候选行
#   pick_fresh(picks, category, spec, row) -> bool  该行有无"新鲜的用户 pick"
# 未接线 = 闸降级（与既有"候选检索失败 fail-open+degraded"同一档，日志可见）——
# 接线在 startup 强制执行，脱接线属部署事故而非静默通道。
_SEARCH_CANDIDATES = None
_PICK_FRESH = None


def set_candidate_provider(search_candidates, pick_fresh) -> None:
    """宿主接线：配件库候选检索 + 用户 pick 新鲜度判定。传 (None, None) 撤销（单测用）。"""
    global _SEARCH_CANDIDATES, _PICK_FRESH
    _SEARCH_CANDIDATES = search_candidates
    _PICK_FRESH = pick_fresh


def declared_decisions(flow_configs: dict) -> list:
    """汇总流内各节点声明的决策点（决策是流级语义，声明在写节点就近生效）。"""
    out: list = []
    for _key, cfg in (flow_configs or {}).items():
        if not isinstance(cfg, dict):
            continue
        for d in (cfg.get("decisions") or []):
            if isinstance(d, dict) and str(d.get("match_category") or "").strip():
                out.append({**d, "match_category": str(d["match_category"]).strip()})
    return out


def _spec_tokens(spec: str) -> list:
    """规格文本 → 检索词（字母数字词为主，滤单位量词）。"""
    toks = re.findall(r"[A-Za-z0-9][A-Za-z0-9.\-]*", str(spec or ""))
    return [t for t in toks if t.lower() not in _STOP_TOKENS][:6]


def decision_demote_parts(parts: list, decisions: list, picks: dict) -> list:
    """kp 阶段闸（确定性落料路径）：声明类目的行——已落地（有 name）但无用户 pick →
    剥 name 降级为未匹配白盒（行卡会带候选反问，用户点选经 kp_manual_pick/
    批量晋升写入 KP_PICKS 后，apply_kp_picks 的落地即用户背书，闸放行）。

    信号判定 = KP_PICKS 里有无该行身份的 pick：需求流里 KP_PICKS 只可能来自用户动作
    （kp_manual_pick 点选 reason="客户自选"/批量晋升）——大脑填表从不写 picks，
    所以"有 pick"="用户拍板过"，无循环风险。"""
    if _PICK_FRESH is None:
        logger.warning("决策闸降级：候选供给者未接线（set_candidate_provider）——fail-open 放行")
        return parts
    for p in parts:
        if not isinstance(p, dict) or not p.get("name") or p.get("waived"):
            continue
        cat = str(p.get("category") or "").strip()
        d = next((x for x in (decisions or [])
                  if str(x.get("match_category") or "").strip().lower() == cat.lower()), None)
        if not d:
            continue
        spec = str(p.get("request_spec") or "")
        if _PICK_FRESH(picks or {}, cat, spec, p):
            continue  # 有用户 pick → 放行
        slot = str(d.get("slot") or cat)
        p["decision_pending"] = slot
        p["demoted_name"] = p["name"]
        p.pop("name", None)
        p["unmatched"] = True
        logger.info("决策闸降级：category=%s slot=%s（AI 自选 %s 未获用户拍板）", cat, slot,
                    p.get("demoted_name"))
    return parts


def part_lock_verdict(*, thread_id: str, decisions: list, category: str, spec: str,
                      pick_name: str, series: str = "", price_ok: bool = True,
                      limit: int = 6) -> dict:
    """锁定前的闸判定。返回：
    {"verdict": "allow"}
    {"verdict": "card", "slot", "question", "entry"(已 open_query), "options", "candidates"}
    无 thread_id（卡没有可挂的会话）或候选检索异常 → fail-open 放行但带 degraded 标注。"""
    if not str(thread_id or "").strip():
        return {"verdict": "allow", "degraded": True}
    d = next((x for x in (decisions or [])
              if str(x.get("match_category") or "").strip().lower() == str(category or "").strip().lower()),
             None)
    if not d:
        return {"verdict": "allow"}
    try:
        from app.services.human_query import user_signal_for, open_query_of
        slot = str(d.get("slot") or category).strip()
        min_c = int(d.get("min_candidates") or 2)
        if user_signal_for(thread_id, slot):
            return {"verdict": "allow", "slot": slot}
        # 已有开放问题（本 slot 的卡已发等拍板 / 其他问题占用单开槽）→ 拒绝自填：
        # 这是协议状态，不是异常——fail-open 在这里等于给"重试代答"开后门
        # （2026-10-31 E2E 实锤：首次发卡后大脑重试，open_query 撞 ContractError
        # 走 fail-open 放行了自填锁定）。
        open_q = open_query_of(thread_id)
        if open_q:
            same = str((open_q.get("meta") or {}).get("slot") or "") == slot
            return {"verdict": "refuse", "slot": slot, "entry": open_q,
                    "reason": "decision_pending" if same else "other_question_open"}
        tokens = _spec_tokens(spec) or ([re.sub(r"\s+", "", str(pick_name or ""))] if pick_name else [])
        if _SEARCH_CANDIDATES is None:
            logger.warning("决策闸降级：候选供给者未接线（set_candidate_provider）——fail-open 放行")
            return {"verdict": "allow", "degraded": True, "slot": slot}
        candidates: list = []
        seen: set = set()
        for tok in tokens:
            rows = _SEARCH_CANDIDATES(category, tok, series or "", bool(price_ok), int(limit))
            for r in (rows or []):
                if not isinstance(r, dict):
                    continue
                nm = str(r.get("model") or r.get("name") or "").strip()
                if nm and nm not in seen:
                    seen.add(nm)
                    candidates.append({"label": nm, "recommended": nm == str(pick_name or "").strip()})
        candidates.sort(key=lambda x: 0 if x.get("recommended") else 1)
        if len(candidates) < min_c:
            return {"verdict": "allow", "slot": slot}
        from app.services.human_query import open_query
        entry = open_query(thread_id, kind="choice",
                           title=str(d.get("question") or f"{category} 在库有多款候选，选哪款？"),
                           hint="点选一款即可继续；没有合适的可选其他并说明",
                           options=candidates[:limit],
                           meta={"slot": slot})
        return {"verdict": "card", "slot": slot, "entry": entry,
                "options": entry.get("options") or [],
                "candidates_count": len(candidates)}
    except Exception:
        logger.exception("决策闸候选检索失败 category=%s（fail-open 放行）", category)
        return {"verdict": "allow", "degraded": True, "slot": str((d or {}).get("slot") or category)}
