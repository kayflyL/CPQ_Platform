"""需求分析 pipeline —— 会话状态 + 图驱动/线性兜底执行入口。

2026-08 重构（AI-first）：自由文本需求理解由 LLM（understand 节点）承担，
本模块只保留：pipeline 入口、反问/补充/目录/系列 会话状态机、线性兜底。
"""

import logging
import re
import json
import uuid
from typing import Optional

from app.services.reasoning_hub import reasoning_hub
from app.api.candidate_search import select_models, pick_kp_parts, build_plan, kp_categories_for_type, build_variant_signals
# 平台系列权威源 + 中文停用词（本地定义；series 权威源 = system_config.server_series）。
# 正则解析路径（requirement_parser 包）已随 AI-first 改革删除，见 CHANGELOG [0.1.55-56]。
_SERIES_KEYWORDS = ["Orion", "Polaris", "Intel", "工作站"]  # 兜底常量（读配置失败时用）


def _load_series_values() -> list:
    """全平台系列权威源（system_config.server_series，[{value,label},...]）→ 值列表；读失败回退常量。"""
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            raw = repo.get_value("server_series", [])
        finally:
            repo.close()
        if isinstance(raw, list):
            vals = [str(it["value"]) for it in raw
                    if isinstance(it, dict) and it.get("value")]
            if vals:
                return vals
    except Exception:
        pass
    return list(_SERIES_KEYWORDS)


_CN_STOPWORDS = set("的了和与及或是在为对我你他这那有无疑也都很还再又个把被让使给向从到上下进出过")

logger = logging.getLogger(__name__)

# 反问最多 N 轮（与 reasoning_executor.MAX_CLARIFY_ROUNDS 同步）。
# 目录驱动引导正常 3 步（类型→机型→KP 格式）即可走完，6 是兜底保险。
MAX_CLARIFY_ROUNDS = 6


def apply_budget_check(plans: list, budget: Optional[float], underspend_threshold: float = 0.5) -> int:
    """给 plans 注 over_budget / underspend 字段（在 summary.total_cost 上算）。
    - over_budget: 方案价 > 预算（超了多少）
    - underspend: 方案价/预算 < underspend_threshold（默认 0.5，预算没用足一半 → 可升级配置）
    返回超预算方案数。budget=None 时跳过。图 executor + 线性 fallback 共用。"""
    if budget is None or not plans:
        return 0
    over = 0
    for p in plans:
        total = (p.get("summary") or {}).get("total_cost") or 0
        if total and total > budget:
            p["over_budget"] = {
                "amount": round(total - budget, 2),
                "ratio": round((total - budget) / budget, 2),
            }
            p["underspend"] = None
            over += 1
        else:
            p["over_budget"] = None
            ratio = round(total / budget, 2) if budget else 0
            if ratio < underspend_threshold:
                p["underspend"] = {"ratio": ratio, "amount": round(budget - total, 2)}
            else:
                p["underspend"] = None
    return over


def _read_opportunity_extra(opportunity_id: str) -> dict:
    """读商机 extra_fields（JSON）。失败返回 {}。直查模式，不依赖 repo.get。"""
    try:
        from app.models.opportunity import Opportunity
        from app.models.base import Opportunity_SessionLocal
        with Opportunity_SessionLocal() as session:
            opp = session.query(Opportunity).filter(
                Opportunity.opportunity_id == opportunity_id
            ).first()
            if not opp or not opp.extra_fields:
                return {}
            return json.loads(opp.extra_fields) if isinstance(opp.extra_fields, str) else (opp.extra_fields or {})
    except Exception as e:
        logger.warning("读商机 extra_fields 失败 opp=%s err=%s", opportunity_id, e)
        return {}


def _extra_for(session_id: str, store=None) -> dict:
    """会话状态读后端：给了 store 走 store（thread/商机），否则读商机 extra_fields。"""
    if store is not None:
        try:
            return store.get_extra()
        except Exception:
            return {}
    return _read_opportunity_extra(session_id)


def _update_meta(session_id: str, patch: dict, store=None) -> None:
    """会话状态写后端：给了 store 走 store，否则写商机 extra_fields。"""
    if store is not None:
        try:
            store.update_meta(patch)
            return
        except Exception as e:
            logger.warning("写会话状态失败 session=%s err=%s", session_id, e)
            return
    try:
        from app.repository.opportunity_repo import OpportunityRepository
        repo = OpportunityRepository()
        try:
            repo.update_meta(session_id, patch)
        finally:
            repo.close()
    except Exception as e:
        logger.warning("写商机 extra_fields 失败 opp=%s err=%s", session_id, e)

def _read_opportunity_ctx(opportunity_id: str) -> dict:
    """读商机完整上下文（含 industry 等列 + extra_fields），给场景分析用。失败返回 {}。"""
    try:
        from app.models.opportunity import Opportunity
        from app.models.base import Opportunity_SessionLocal
        with Opportunity_SessionLocal() as session:
            opp = session.query(Opportunity).filter(
                Opportunity.opportunity_id == opportunity_id
            ).first()
            return opp.to_dict() if opp else {}
    except Exception as e:
        logger.warning("读商机上下文失败 opp=%s err=%s", opportunity_id, e)
        return {}


def _read_opportunity_budget(session_id: str, store=None) -> Optional[float]:
    extra = _extra_for(session_id, store)
    b = extra.get("budget")
    try:
        return float(b) if b is not None else None
    except (TypeError, ValueError):
        return None

def _read_clarify_round(session_id: str, store=None) -> int:
    extra = _extra_for(session_id, store)
    try:
        return int(extra.get("requirement_clarity_round", 0))
    except (TypeError, ValueError):
        return 0

def _write_clarify_round(session_id: str, round_num: int, store=None) -> None:
    _update_meta(session_id, {"requirement_clarity_round": round_num}, store)

def _read_clarify_supplements(session_id: str, store=None) -> tuple:
    """返回 (base原文, 累积补充串)。跨轮持久化历次反答回填，避免每轮只拼最新一句丢失已答字段。"""
    extra = _extra_for(session_id, store)
    return extra.get("requirement_clarity_base") or "", extra.get("requirement_clarity_supplements") or ""

def _read_clarify_defaults(session_id: str, store=None) -> list:
    """读"已答默认"字段集合（答"还没定/你推荐"跳过的字段，跨轮不再追问）。"""
    extra = _extra_for(session_id, store)
    v = extra.get("requirement_clarity_defaults")
    return list(v) if isinstance(v, list) else []

def _write_clarify_defaults(session_id: str, defaults: list, store=None) -> None:
    _update_meta(session_id, {"requirement_clarity_defaults": list(defaults)}, store)

def _read_last_asked(session_id: str, store=None) -> list:
    """读"最近一轮反问问过的字段"（配合"还没定"→ 把该字段标为默认）。"""
    extra = _extra_for(session_id, store)
    v = extra.get("requirement_clarity_last_asked")
    return list(v) if isinstance(v, list) else []

def _write_last_asked(session_id: str, fields: list, store=None) -> None:
    _update_meta(session_id, {"requirement_clarity_last_asked": list(fields)}, store)

def _write_clarify_supplements(session_id: str, base: str, supplements: str, store=None) -> None:
    _update_meta(session_id, {
        "requirement_clarity_base": base,
        "requirement_clarity_supplements": supplements,
    }, store)

def _enrich_supplement_text(reply: str, flow_configs: Optional[dict]) -> str:
    """把反问选项的「语义标签」翻译成需求文本里能解析的规格/类型（配置驱动，禁硬编码）。

    - llm_ask.workload_categories：工作负载标签（如 "AI / 机器学习"）→ 追加映射类型（如 "AI / 加速计算服务器"）
    - llm_ask.scale_tiers：分档标签（如 "中型"）→ 追加推荐规格（如 "CPU按中型规模：32-48 核"）
    否则 understand 只看到选项标签，问完就丢，下轮又重复问同一题（实测复现）。
    只处理「精确命中标签」的答复，普通自由文本原样返回。
    """
    r = (reply or "").strip()
    if not r:
        return r
    la = (flow_configs or {}).get("llm_ask") or {}
    out = r
    for c in (la.get("workload_categories") or []):
        label = str(c.get("label") or "").strip()
        t = str(c.get("type") or "").strip()
        if label and t and r == label:
            out = f"{r}（属于 {t}）"
            break
    for key, tiers in (la.get("scale_tiers") or {}).items():
        for tier in (tiers or []):
            label = str(tier.get("label") or "").strip()
            rec = str(tier.get("recommend") or "").strip()
            if label and rec and r == label:
                # 推荐规格必须可解析（如 CPU：32核 / 内存：32G*8条 / 存储：2×960G SSD）
                suffix = f"{key}：{rec}"
                if suffix not in out:
                    out = f"{out}，{suffix}"
    return out


def _merge_clarify_defaults(defaults: list, last_asked: list, supplement: dict,
                             is_new_conversation: bool) -> list:
    """更新"已答默认"字段集合（M1 1.3b，纯函数供单测）。

    语义：答"还没定/你推荐"（_is_default_reply 命中）→ 把上一轮问过的字段
    （last_asked）标为默认，后续轮次不再追问；全新对话清零。
    """
    from app.services.reasoning_executor import _is_default_reply  # 延迟 import 规避循环
    defaults = list(defaults or [])
    if is_new_conversation:
        return []
    if supplement and last_asked and _is_default_reply((supplement.get("text") or "")):
        return list(dict.fromkeys(defaults + [f for f in last_asked if f]))
    return defaults


def _merge_clarify_text(original: str, stored_base: str, acc_supplements: str,
                        supplement: dict = None, force_complete: bool = False) -> tuple:
    """合并「原文 + 历次反问补充」为完整需求文本（纯函数，供单测）。

    会话语义（M1 1.1，修"再次生成报价重复上一轮"）：
      - 无 supplement 且非 force_complete = 全新对话（用户重新点「生成报价」）
        → 无条件清空旧补充历史。此前仅原文变化才清，同文本重跑永远复读旧对话；
      - force_complete（点跳过）= 用当前已答信息出方案 → 保留已累积补充；
      - supplement（反答回填）= 续接对话 → 追加本轮补充（原文若变则先清旧历史）。
    返回 (full_text, 新 acc_supplements)。
    """
    original = (original or "").strip()
    acc = acc_supplements or ""
    if not supplement and not force_complete:
        acc = ""  # 全新对话：清空旧补充历史（不再依赖原文是否变化）
    elif stored_base and original and stored_base != original:
        acc = ""  # 原文变了 = 新一轮提问，丢弃旧补充历史
    if supplement and supplement.get("text"):
        piece = (supplement.get("text") or "").strip()
        if piece:
            acc = f"{acc}\n补充：{piece}" if acc else f"补充：{piece}"
    if original and acc:
        return f"{original}\n{acc}", acc
    return original or acc, acc


def _write_llm_feedback_sample(opportunity_id: str, requirement_text: str, applied: list) -> None:
    """LLM 确认反馈 → rules.requirement_samples（source=llm_feedback）。

    每次 confirm 节点应用决策（采纳/忽略）后落一条：需求原文 + 决策明细，
    供未来 LLM 语料/评测/反馈闭环。rule_id=0（不挂具体规则）。
    test-run 等占位商机不写，避免污染样本库。
    """
    if not applied or (opportunity_id or "").startswith("test"):
        return
    from app.repository.requirement_rule_repo import RequirementRuleRepository
    repo = RequirementRuleRepository()
    try:
        repo.add_sample({
            "rule_id": 0,
            "sample_text": (requirement_text or "")[:2000],
            "expected_result": {"confirm": applied, "source": "llm_feedback"},
            "source": "llm_feedback",
            "tags": ["llm_feedback", "confirm"],
        }, operator="system")
    finally:
        repo.close()


# ── 目录驱动引导会话状态（需求不明确时的反问状态机，见 catalog_guide）────────

def _read_catalog_state(session_id: str, store=None) -> dict:
    """读目录引导会话状态（stage/type_name/model_id/offered）。无则返回空 state。"""
    extra = _extra_for(session_id, store)
    offered = extra.get("requirement_catalog_offered")
    try:
        offered = json.loads(offered) if isinstance(offered, str) else (offered or {})
    except Exception:
        offered = {}
    return {
        "stage": extra.get("requirement_catalog_stage") or "",
        "type_name": extra.get("requirement_catalog_type_name"),
        "model_id": extra.get("requirement_catalog_model_id"),
        "offered": offered if isinstance(offered, dict) else {},
    }

def _write_catalog_state(session_id: str, state: dict, store=None) -> None:
    _update_meta(session_id, {
        "requirement_catalog_stage": state.get("stage") or "",
        "requirement_catalog_type_name": state.get("type_name"),
        "requirement_catalog_model_id": state.get("model_id"),
        "requirement_catalog_offered": json.dumps(state.get("offered") or {}, ensure_ascii=False),
    }, store)

def _reset_catalog_state(session_id: str, store=None) -> dict:
    state = {"stage": "", "type_name": None, "model_id": None, "offered": {}}
    _write_catalog_state(session_id, state, store)
    return state


def _advance_catalog_state(session_id: str, state: dict, reply: str, ask_cfg: dict,
                           flow_configs: dict, store=None) -> dict:
    """消费客户回复推进目录引导阶段（DB 目录数据版）。返回新 state；无变化时原样返回。"""
    from app.services.catalog_guide import advance_with_catalog
    new_state = advance_with_catalog(state, reply, ask_cfg)
    if new_state != state:
        _write_catalog_state(session_id, new_state, store)
        return new_state
    return state

def _persist_catalog_offer(session_id: str, stage: str, offered: dict, store=None) -> None:
    """ask_user 发问后记录本轮推给客户的选项 + 当前 stage（供下轮选项匹配）。"""
    _update_meta(session_id, {
        "requirement_catalog_stage": stage,
        "requirement_catalog_offered": json.dumps(offered or {}, ensure_ascii=False),
    }, store)

def _persist_series_offer(session_id: str, offered: dict, store=None) -> None:
    """confirm_series 发问后记录本轮推的系列（下轮答"是"时取用）。"""
    _update_meta(session_id, {
        "requirement_series_offer": json.dumps(offered or {}, ensure_ascii=False),
    }, store)

def _read_series_offer(session_id: str, store=None) -> dict:
    extra = _extra_for(session_id, store)
    if isinstance(extra, dict):
        raw = extra.get("requirement_series_offer")
        try:
            return json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            return {}
    return {}

def _write_confirmed_series(session_id: str, value: str, store=None) -> None:
    _update_meta(session_id, {"requirement_confirmed_series": value}, store)

def _read_confirmed_series(session_id: str, store=None) -> str:
    extra = _extra_for(session_id, store)
    return str(extra.get("requirement_confirmed_series") or "") if isinstance(extra, dict) else ""

def _parse_series_confirm(reply: str, offer: dict) -> Optional[str]:
    """系列确认答复解析：是→offer.series；不是/换→'__ask__'；具体系列名→该名；无关→None。
    返回 None 表示"不是系列确认的回复"（目录引导等其他解析继续处理）。"""
    r = (reply or "").strip().lower()
    if not r:
        return None
    # 先查否认（"不是"里含"是"字，必须优先，否则"不是"被"是"误判为确认）
    if any(w in r for w in ("不是", "不对", "不要", "换系列", "换一个", "换", "其他", "别的", "算了")):
        return "__ask__"
    if any(w in r for w in ("是", "确认", "可以", "对的", "就它", "就要这个", "这个系列", "ok", "好")):
        if offer and offer.get("series"):
            return str(offer["series"])
        return None
    # 具体系列名（Orion / Polaris / Intel …）
    for s in _load_series_values():
        if s and (s.lower() in r or r in s.lower()):
            return s
    # 平台别名 → 系列（"兆芯/开胜"→Polaris、"AMD/EPYC"→Orion、"Xeon"→Intel；海光/飞腾/鲲鹏非 Polaris）
    _aliases = {
        "Orion": ["amd", "epyc", "霄龙", "猎户"],
        "Polaris": ["兆芯", "zhaoxin", "开胜", "开先", "信创", "国产"],
        "Intel": ["intel", "xeon", "至强"],
    }
    for series_name, words in _aliases.items():
        if any(w in r for w in words):
            return series_name
    return None


async def run_pipeline(opportunity_id: str, requirement_text: str,
                       supplement: dict = None, force_complete: bool = False,
                       session=None, hub=None, collector=None) -> None:
    """跑推理 pipeline。有 active flow → 图驱动 executor；异常或无 flow → 线性 5 步 fallback。

    supplement: 反答回填 {"text":..., "budget":...}；force_complete: 用户点跳过，强制走选型。
    三层兜底：DB 异常 → linear fallback；graph executor 异常 → linear fallback。

    session/hub（方案助手通道复用，2026-08-05）：默认 None → 绑商机(extra_fields) + reasoning_hub；
    方案助手/企微传 ReasoningSession(thread_id,'thread') + assistant_hub，会话状态与会话一起存，
    与商机通道物理隔离（互不串状态）。
    collector：可选事件收集器（每个广播 payload 回调一次），供调用方在 pipeline 结束后
    拿 candidates_ready 的方案清单落库（方案助手结果消息重放）。
    """
    from app.services.reasoning_session import ReasoningSession
    session = session or ReasoningSession(opportunity_id, "opportunity")
    hub = hub or reasoning_hub
    # 累积拼接完整需求文本（原文 + 历次反问补充）——跨轮持久化，避免每轮只拼最新一句、丢失已答字段。
    # 旧实现 full_text=原文+最新补充 → 第三轮答"Orion"时丢了第二轮"AI训练/推理" → 用途又变缺失 → 重复问用途。
    original = (requirement_text or "").strip()
    stored_base, acc_supplements = _read_clarify_supplements(opportunity_id, session)
    # P1-1 意图切换：用户"改主意/重新开始/换需求" → 清空历史累积（补充/默认/目录/系列），
    # 并把「本次改主意后的新需求」作为全新原文重跑 understand 首问（工作负载引导），
    # 而不是丢弃本次补充又拼回旧原文（实测复现：改主意后仍按旧 AI 需求继续问）。
    if supplement and (supplement.get("text") or "").strip():
        from app.services.catalog_guide import is_restart_reply
        if is_restart_reply(supplement["text"]):
            _new_text = (supplement.get("text") or "").strip()
            _write_clarify_supplements(opportunity_id, "", "", session)
            _write_clarify_defaults(opportunity_id, [], session)
            _reset_catalog_state(opportunity_id, session)
            _write_confirmed_series(opportunity_id, "", session)
            original = _new_text  # 新需求成为本轮原文（旧原文丢弃）
            supplement = {"budget": supplement.get("budget"),
                          "confirm": supplement.get("confirm") or None}
            stored_base, acc_supplements = "", ""
    # 读 active 推理流（提前到合并文本前：supplement 语义标签翻译需要 flow_configs）
    flow = None
    try:
        from app.repository.reasoning_flow_repo import ReasoningFlowRepository
        _rf = ReasoningFlowRepository()
        try:
            flow = _rf.get_active_flow()
        finally:
            _rf.close()
    except Exception as e:
        logger.warning("读 reasoning flow 失败: %s", e)
    flow_configs = (flow or {}).get("node_configs") or {}
    # 反问选项语义标签 → 可解析文本（工作负载标签→类型 / 分档标签→推荐规格）
    if supplement and (supplement.get("text") or "").strip():
        supplement = {**supplement, "text": _enrich_supplement_text(supplement["text"], flow_configs)}
    # M1 1.1：会话语义抽成纯函数 —— 无 supplement 且非 force_complete = 全新对话，无条件清空旧补充。
    full_text, acc_supplements = _merge_clarify_text(
        original, stored_base, acc_supplements, supplement, force_complete,
    )
    if original:
        _write_clarify_supplements(opportunity_id, original, acc_supplements, session)  # 持久化供下轮累积

    # M1 1.3b：已答默认字段（答"还没定/你推荐"跳过的）跨轮记忆，避免重复追问。
    is_new_conversation = not supplement and not force_complete
    defaults = _read_clarify_defaults(opportunity_id, session)
    last_asked = _read_last_asked(opportunity_id, session)
    new_defaults = _merge_clarify_defaults(defaults, last_asked, supplement, is_new_conversation)
    if new_defaults != defaults:
        _write_clarify_defaults(opportunity_id, new_defaults, session)
        defaults = new_defaults
    if is_new_conversation or (supplement and last_asked):
        # 全新对话清空 last_asked；补充后本轮 asked 已被消费（下轮 _broadcast 会重写）
        _write_last_asked(opportunity_id, [], session)

    # 预算优先级：反问明确给 > 商机/会话 extra > 无
    if supplement and supplement.get("budget") is not None:
        budget = supplement["budget"]
    else:
        budget = _read_opportunity_budget(opportunity_id, session)

    # 反问轮次（死循环防护，存会话状态跨重启/多用户）。
    # ⚠️ 语义：每次点「生成报价」（无 supplement）= 全新对话，必须重置 round=0；
    # 只有反答回填（supplement）才 +1。否则 round 跨会话单调累积，用户多测几次就
    # 永久卡在 MAX 阈值 → clarity_check 强制出方案 → 反问机制整体失效（[0.1.43] 修）。
    round_num = _read_clarify_round(opportunity_id, session)
    # P2：纯 confirm 决策（无文本/预算）不算反问轮次，避免占用死循环防护预算
    _has_clarify = bool(supplement and (supplement.get("text") or supplement.get("budget") is not None))
    if _has_clarify:
        round_num = min(round_num + 1, MAX_CLARIFY_ROUNDS + 1)
        _write_clarify_round(opportunity_id, round_num, session)
    else:
        # 重新生成 = 新对话，重置死循环计数器（否则跨会话累积卡死反问）
        round_num = 0
        _write_clarify_round(opportunity_id, 0, session)

    pipeline_id = f"pl_{uuid.uuid4().hex[:12]}"
    # 委托（"你推荐/不确定/随便"）：只认「最新输入」（原文或本轮补充）是委托话术才生效；
    # 用户后续补具体规格则自动解除，恢复可反问。AI 编排路径据此停止反问、按推荐默认出方案
    # （等价目录引导的 delegate 特判；实测复现：委托后下一轮仍反问同一题）。
    _delegated_input = ""
    if supplement and (supplement.get("text") or "").strip():
        _delegated_input = supplement["text"]
    elif original:
        _delegated_input = original
    try:
        from app.services.catalog_guide import is_default_reply as _is_default_reply
        delegated = bool(_delegated_input) and _is_default_reply(_delegated_input)
    except Exception:
        delegated = False
    initial_ctx = {
        "budget": budget,
        "clarify_round": round_num,
        "pipeline_id": pipeline_id,
        "force_complete": force_complete,
        "delegated": delegated,  # 2026-08：客户委托推荐 → gap_analyze 视为 explicit，不再反问
        "clarify_defaults": defaults,  # M1 1.3b：已答默认字段，clarity_check 剔除不再追问
        "confirmed_series": _read_confirmed_series(opportunity_id, session),  # R29：系列确认（confirm_series）
    }
    # P2：LLM 确认面板决策（confirm 节点消费）：{item_id: "accept"|"ignore"}
    if supplement and supplement.get("confirm"):
        initial_ctx["confirm_decisions"] = supplement["confirm"]
        initial_ctx["confirm_answered"] = True

    async def _broadcast(payload: dict):
        payload.setdefault("opportunity_id", opportunity_id)
        payload.setdefault("pipeline_id", pipeline_id)
        payload.setdefault("round", round_num)
        # M1 1.3b：need_input 广播时记录本轮问的字段，供下轮"还没定"标默认跳过
        if payload.get("type") == "need_input":
            _write_last_asked(opportunity_id, list(payload.get("asked_fields") or []), session)
        await hub.broadcast(opportunity_id, payload)
        if collector:
            try:
                collector(payload)
            except Exception:
                pass

    # ── 目录驱动引导：消费客户回复推进 stage / 新对话重置（旧思路的 workload/rebuttal 已删）──
    # 阶段推进放在图执行前：stage 变 done → clarity_check 直接视为 explicit → 本轮就出方案，
    # 而不是像旧版那样「反问永远停在 ask_user，下轮才能继续」。
    catalog = _read_catalog_state(opportunity_id, session)
    # 只有客户实际回复了文本才推进目录引导（纯 budget 补充不算回答，避免误跳到下一问）
    if supplement and (supplement.get("text") or "").strip():
        # 系列确认答复（confirm_series 节点）：是→确认推断系列 / 不是→标记补全 / 系列名→直选。
        _series_reply = (supplement.get("text") or "").strip()
        _series_offer = _read_series_offer(opportunity_id, session)
        _series_confirmed = _parse_series_confirm(_series_reply, _series_offer)
        if _series_confirmed is not None:
            _write_confirmed_series(opportunity_id, _series_confirmed, session)
        from app.services.catalog_guide import load_ask_config
        ask_cfg = load_ask_config(flow_configs)
        # 只在「目录引导会话」里推进（stage 已由 ask_user/兜底发问建立）：
        # AI 编排反问（workload/分档/形态）的答复不推进目录状态机，否则推荐类型会被错塞进
        # catalog_type_name，覆盖 understand/场景判定出的正确类型（实测复现）。
        if catalog.get("stage"):
            catalog = _advance_catalog_state(
                opportunity_id, catalog, supplement.get("text") or "", ask_cfg, flow_configs, session,
            )
    elif is_new_conversation and catalog.get("stage"):
        catalog = _reset_catalog_state(opportunity_id, session)
    from app.services.catalog_guide import load_ask_config as _ask_cfg
    initial_ctx.update({
        "catalog_stage": catalog.get("stage") or "",
        "catalog_type_name": catalog.get("type_name"),
        "catalog_model_id": catalog.get("model_id"),
        "catalog_state": catalog,
        "flow_configs": flow_configs,
        "max_clarify_rounds": int(_ask_cfg(flow_configs).get("max_rounds") or MAX_CLARIFY_ROUNDS),
    })

    graph_nodes = (flow or {}).get("graph", {}).get("nodes") or []
    # ── 执行：V11 单路能力链 → orchestrator（唯一执行引擎）──────────────────
    if flow and graph_nodes:
        try:
            from app.services.reasoning_orchestrator import run_orchestrator
            if supplement and supplement.get("text"):
                initial_ctx["supplement_text"] = supplement["text"]
            await run_orchestrator(opportunity_id, full_text, flow, _broadcast,
                                   initial_ctx=initial_ctx, session=session)
            return
        except Exception as e:
            logger.exception("orchestrator 执行失败，走诚实降级: %s", e)

    # 无 flow / orchestrator 异常 → 诚实降级（不假装跑规则链出方案）
    await _broadcast({"type": "pipeline_start", "steps": []})
    await _broadcast({"type": "step_progress", "step": "orchestrator",
                      "sub": {"kind": "degraded",
                              "text": "⚠️ 需求分析引擎暂时不可用，请稍后重试，或在配置页手动选型"}})
    await _broadcast({"type": "pipeline_done", "plans": [], "ext": {}, "kp_by_model": {}})
async def run_assistant_pipeline(thread_id: str, requirement_text: str,
                                 supplement: dict = None, force_complete: bool = False) -> list:
    """方案助手/未来企微通道的需求分析入口。

    与商机通道共用 run_pipeline 全部逻辑（图驱动 executor + clarify 反问 + 目录引导 +
    LLM 增强/确认 + 线性兜底），差异只在：
      - 会话状态存 opportunities.assistant_threads.reasoning_state（thread 会话，重启不丢）；
      - 步骤/方案事件广播到 assistant_hub 的 thread 房间（前端方案助手 WS 直接消费）。
    返回本次 pipeline 的全部广播事件（供调用方拿 candidates_ready 方案落库重放）。
    这样「方案助手」= 通道无关的 Agent API，企微接入时只需新增一个消息适配层调用同一入口。
    """
    from app.services.reasoning_session import ReasoningSession
    from app.services.assistant_hub import assistant_hub
    events: list = []
    await run_pipeline(
        thread_id, requirement_text,
        supplement=supplement, force_complete=force_complete,
        session=ReasoningSession(thread_id, "thread"),
        hub=assistant_hub,
        collector=events.append,
    )
    return events
