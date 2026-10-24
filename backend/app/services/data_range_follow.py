# -*- coding: utf-8 -*-
"""报告数据范围跟随用户输入（2026-10-22）。

语义定调：文档卡 data_range.mode = auto 的报告流，「自动（按数据实际边界）」升级为
「跟随本次用户输入」——用户消息里说了统计窗口（今年/近3个月/X月至Y月/…）就解析成
具体起止；没说就维持 auto 本义（按数据实际边界）。显式配置（近30天/今年/自定义…）
= 钉死硬边界，不做跟随（终检 _data_answer_gate 会物理核对报告首行）。

解析走一次轻量 LLM 结构化抽取（llm_client.chat_json），代码不做日期正则；LLM 输出
只做确定性收口（ISO 日期、start≤end、end 不晚于明天），非法视为「未指定」。

调用点：skill_turn_engine 回合开始 → engine["data_range_override"]；
消费点：steps_payload 契约改写 + document_target 合并 + _data_answer_gate 核对 +
_render_by_template（封面 period_label / 图表 days）——后三者本就从 data_range
确定性计算，回填后零改动自动生效。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


def document_report_art(flow: dict) -> dict:
    """流配置 → 第一个带章节的报告文档卡（与 skill_turn_engine 组装 document_target 同口径）。"""
    configs = flow.get("node_configs") if isinstance(flow.get("node_configs"), dict) else {}
    for cfg in configs.values():
        if not isinstance(cfg, dict):
            continue
        target = cfg.get("target")
        arts = target.get("artifacts") if isinstance(target, dict) else None
        for art in (arts or []):
            if isinstance(art, dict) and str(art.get("kind") or "") == "document" and art.get("sections"):
                return art
    return {}


def follow_wants(flow: dict, text: str) -> bool:
    """该回合是否需要跟随解析：有报告文档卡、其 data_range.mode=auto、用户说了话。"""
    art = document_report_art(flow)
    if not art:
        return False
    dr = art.get("data_range") if isinstance(art.get("data_range"), dict) else {}
    return str(dr.get("mode") or "auto").strip() == "auto" and bool(str(text or "").strip())


def _norm_date(v: Any) -> Optional[str]:
    s = str(v or "").strip()
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except (ValueError, TypeError):
        return None


def parse_range_reply(reply: Any, today: Optional[date] = None) -> Optional[dict]:
    """LLM 抽取结果 → data_range 覆盖（custom 起止）；未指定/非法 → None。

    确定性收口：ISO 日期、start≤end（LLM 说反了就换回来）、end 不晚于明天
    （防幻觉未来窗口）；收口后仍倒挂视为未指定。
    """
    today = today or date.today()
    if not isinstance(reply, dict):
        return None
    start, end = _norm_date(reply.get("start")), _norm_date(reply.get("end"))
    if not start or not end:
        return None
    if start > end:
        start, end = end, start
    tomorrow = (today + timedelta(days=1)).isoformat()
    if end > tomorrow:
        end = tomorrow
    if start > end:
        return None
    from app.services.skill_target_contract import USER_RANGE_LABEL
    return {"mode": "custom", "start": start, "end": end, "label": USER_RANGE_LABEL}


_EXTRACT_PROMPT = (
    "从下面的用户消息里抽取这次报告要统计的时间窗口（数据范围）。只输出 JSON："
    '{{"start":"YYYY-MM-DD","end":"YYYY-MM-DD"}}；消息没有指定时间窗口就输出 '
    '{{"start":null,"end":null}}。今天是 {today}。换算规则：'
    "今年/年初到现在/年初至今 = 今年1月1日 ~ 今天；近N天=从今天往前数N天（含今天）；"
    "近N周=从今天往前数7N天；近N个月=往前N个整月；上个月/上月=上个自然月；"
    "X月份=当月1日 ~ 当月最后一天（未来月份则 end 取今天）；X月至Y月=X月1日 ~ Y月最后一天；"
    "去年=去年1月1日 ~ 去年12月31日；消息里给了明确起止日期就照抄。"
    "end 晚于今天时一律截断为今天。"
)


async def extract_report_data_range(flow: dict, text: str,
                                    today: Optional[date] = None) -> Optional[dict]:
    """回合入口：mode=auto 且用户提到窗口 → LLM 抽取成 custom 起止覆盖；其余返回 None。

    LLM 失败/超时/输出非法一律 None（回落「按数据实际边界」），绝不阻塞回合——
    跟随是增强不是闸门，与文件产物渲染同一脾气。
    """
    if not follow_wants(flow, text):
        return None
    from app.services import llm_client

    today = today or date.today()
    try:
        reply = await llm_client.chat_json(
            [{"role": "system", "content": _EXTRACT_PROMPT.format(today=today.isoformat())},
             {"role": "user", "content": str(text)[:1500]}],
            timeout=30, max_attempts=1, max_tokens=200, temperature=0)
    except Exception:
        logger.warning("数据范围跟随抽取失败（回落按数据实际边界）", exc_info=True)
        return None
    override = parse_range_reply(reply, today)
    if override:
        logger.info("数据范围跟随用户输入：%s ~ %s", override["start"], override["end"])
    else:
        logger.info("用户消息未表达出可用时间窗口，数据范围维持按数据实际边界")
    return override
