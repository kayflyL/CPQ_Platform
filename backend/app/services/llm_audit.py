# -*- coding: utf-8 -*-
"""LLM 方案校对节点 llm_audit —— 意图级校对，bom_cases 同平台 few-shot（P3）。

对比旧 review 散装 LLM 校对：
  - 独立节点，一次调用校对全部方案（不逐方案多次调，省时）；
  - few-shot：取同系列/同形态的 bom_cases 当「参考样本」（这类需求长这样、该有什么），
    明确要求参考案例判断合理性、禁止逐行 diff（2026-08-04 案例库规格对照全误报教训）；
  - 规则硬校验（缺件/平台/超预算）仍在 review 节点 100% 兜底，LLM 只报意图级问题；
  - 任何失败静默降级（返回空，review 纯规则），绝不阻塞主流程；
  - 每次调用落 rules.llm_trace（状态/耗时/问题数），配合 llm_feedback 样本算指标。
"""
import json
import logging
import re
import time
from typing import Optional

from app.services import llm_client

logger = logging.getLogger(__name__)

LLM_AUDIT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "plans": {"type": "array", "items": {"type": "object", "properties": {
            "index": {"type": "integer"},          # 与输入方案列表序号对应
            "passed": {"type": "boolean"},
            "issues": {"type": "array", "items": {"type": "string"}},
        }}},
    },
}

LLM_AUDIT_SYSTEM_PROMPT = (
    "你是 CPQ 服务器方案的意图级校对员。输入：客户需求原文 + 同平台已成交参考案例 + 系统生成的方案清单。\n"
    "任务：判断每个方案是否满足客户需求的【意图】（如：要训练大模型但 GPU 明显不够、要存储但盘位/容量不够、"
    "要信创却配了非信创平台、要双路却只配单路、明确点名了型号/容量却没配）。\n"
    "硬性约束：\n"
    "1) 参考案例只是「这类需求该长什么样」的样本，禁止逐行 diff、禁止把案例当必须 100% 复制的模板；\n"
    "2) 只报【意图级硬问题】（最多 2 条），不确定/可接受的不报；替代件、库缺口、措辞差异不算；\n"
    "3) 需求没提的（如没提网卡）不算缺失；能力声明（支持 N 盘位）不等于已配置；\n"
    "4) 只输出 JSON（plans 数组），每条带 index（对应输入序号）、passed、issues。"
)


def _plan_digest(plan: dict) -> dict:
    """方案摘要（给 LLM 看，不暴露价格敏感字段）。"""
    bom = (plan.get("cfg") or {}).get("bom_excel_rows") or []
    return {
        "name": plan.get("name"),
        "series": plan.get("series"),
        "form": plan.get("form"),
        "bays": plan.get("bays"),
        "bom": [
            {"cat": r.get("part_category") or r.get("category"),
             "desc": (r.get("description") or "")[:80],
             "qty": r.get("qty")}
            for r in bom
        ],
    }


def find_reference_cases(plan: dict, requirement_text: str = "", limit: int = 2) -> list:
    """取同平台 few-shot 参考案例（bom_cases）。

    教训（2026-08-04）：案例库跨平台规格级对照全是误报噪音。这里只取同 series（平台）
    案例当「参考样本」，按需求关键词命中排序，绝不做规格 diff。
    """
    try:
        from app.repository.bom_case_repo import BomCaseRepository
        repo = BomCaseRepository()
        try:
            series = str((plan or {}).get("series") or "")
            cands = repo.list_cases(series=series, enabled=True, with_parts=False) if series else []
            if not cands:
                cands = repo.list_cases(enabled=True, with_parts=False)
        finally:
            repo.close()
    except Exception as e:
        logger.warning("读 bom_cases few-shot 失败: %s", e)
        return []

    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9\u4e00-\u9fa5]{2,}", requirement_text or "")]

    def _score(c: dict) -> int:
        text = " ".join([
            c.get("requirement") or "", c.get("name") or "",
            " ".join(c.get("scenario_tags") or []),
        ]).lower()
        return sum(1 for t in tokens if t in text)

    cands.sort(key=lambda c: (_score(c), str(c.get("created_at") or "")), reverse=True)
    out = []
    for c in cands:
        out.append({
            "case_key": c.get("case_key"),
            "name": c.get("name"),
            "series": c.get("series"),
            "form": c.get("form"),
            "scenario_tags": c.get("scenario_tags") or [],
            "requirement": (c.get("requirement") or "")[:400],
            "l6_rows": (c.get("l6_rows") or [])[:10],
            "kp_count": len(c.get("kp_lines") or []),
        })
        if len(out) >= limit:
            break
    return out


def build_audit_messages(requirement_text: str, plans: list, references: list) -> list:
    """构造 chat_json 的 messages：需求 + 参考案例（few-shot）+ 方案清单。"""
    refs_text = "（库内暂无同平台参考案例）" if not references else "\n".join(
        f"- [{r.get('name')}]（案例号 {r.get('case_key')}）系列={r.get('series')} 形态={r.get('form')} "
        f"标签={'/'.join(r.get('scenario_tags') or [])}\n"
        f"  需求：{r.get('requirement') or ''}\n"
        f"  KP 件数={r.get('kp_count')}，L6 行数={len(r.get('l6_rows') or [])}"
        for r in references
    )
    plans_text = "\n".join(
        f"[{i}] {json.dumps(_plan_digest(p), ensure_ascii=False, default=str)}"
        for i, p in enumerate(plans)
    )
    user = (
        f"客户需求原文：\n{(requirement_text or '').strip()}\n\n"
        f"同平台参考案例（已成交，仅作「这类需求该长什么样」的样本）：\n{refs_text}\n\n"
        f"系统方案清单：\n{plans_text}\n\n"
        "请输出 plans 数组（index 对应上面的 [i] 序号），每条 passed + issues（≤2 条意图级硬问题）。"
    )
    return [
        {"role": "system", "content": LLM_AUDIT_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _record_trace(status: str, duration_ms: int, plans_checked: int, issue_count: int,
                 opportunity_id: str, pipeline_id: str, prompt_chars: int = 0,
                 response_chars: int = 0, error: Optional[str] = None) -> None:
    if not (opportunity_id or "") or (opportunity_id or "").startswith("test"):
        return  # 无商机（单测/未挂载）或试运行：不写 trace，避免污染指标
    from app.services.llm_trace import record_llm_trace
    record_llm_trace(
        node_type="llm_audit", opportunity_id=opportunity_id, pipeline_id=pipeline_id,
        status=status, called=True, duration_ms=duration_ms,
        prompt_chars=prompt_chars, response_chars=response_chars,
        plans_checked=plans_checked, issue_count=issue_count,
        merged=issue_count > 0, error=error,
    )


async def run_llm_audit(requirement_text: str, plans: list, config: dict,
                        opportunity_id: str = "", pipeline_id: str = "") -> dict:
    """llm_audit 节点主入口：bom_cases few-shot + 一次调用校对全部方案。

    返回 {called, reason, error, audits:[{index,passed,issues}], plans_checked,
    issue_plans, duration_ms, references}。任何失败静默降级（audits=[]）。
    """
    base: dict = {
        "called": False, "reason": None, "error": None, "audits": [],
        "plans_checked": 0, "issue_plans": 0, "duration_ms": 0, "references": [],
    }
    plans = plans or []
    if not plans:
        base["reason"] = "no_plans"
        return base
    config = config or {}
    if not config.get("enable_llm"):
        base["reason"] = "disabled"
        return base
    try:
        if not llm_client.is_llm_enabled():
            base["reason"] = "global_ai_disabled"
            return base
    except Exception:
        pass

    references = find_reference_cases(plans[0], requirement_text or "")
    base["references"] = [r["case_key"] for r in references]
    messages = build_audit_messages(requirement_text or "", plans, references)
    prompt_chars = sum(len(m.get("content") or "") for m in messages)
    t0 = time.time()
    try:
        data = await llm_client.chat_json(messages, schema=LLM_AUDIT_SCHEMA)
    except llm_client.LLMError as e:
        duration = int((time.time() - t0) * 1000)
        base.update(called=True, reason="llm_error", error=str(e)[:300], duration_ms=duration)
        _record_trace("llm_error", duration, len(plans), 0, opportunity_id, pipeline_id,
                      prompt_chars=prompt_chars, error=str(e)[:300])
        return base
    duration = int((time.time() - t0) * 1000)
    response_chars = len(json.dumps(data, ensure_ascii=False, default=str))

    by_index: dict = {}
    for item in (data.get("plans") or []):
        if isinstance(item, dict) and isinstance(item.get("index"), int):
            by_index[item["index"]] = item
    audits: list = []
    issue_plans = 0
    for i in range(len(plans)):
        it = by_index.get(i) or {}
        issues = [str(x) for x in (it.get("issues") or []) if str(x).strip()]
        audits.append({"index": i, "passed": bool(it.get("passed")), "issues": issues[:2]})
        if issues:
            issue_plans += 1
    base.update(called=True, reason="ok", audits=audits, plans_checked=len(plans),
                issue_plans=issue_plans, duration_ms=duration)
    _record_trace("ok", duration, len(plans), issue_plans, opportunity_id, pipeline_id,
                  prompt_chars=prompt_chars, response_chars=response_chars)
    return base
