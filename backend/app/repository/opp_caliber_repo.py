# -*- coding: utf-8 -*-
"""商机口径权威层：需求单 slots 读取 + 当前版本配置数子查询。

商机线索页（opportunity_repo）、驾驶舱（api/dashboard）、AI 商机统计工具
（services/opp_stats）共用本模块的同一份实现——口径漂移的历史教训：
平台/机箱维度、配置数都曾因各自实现而统计不一致（2026-09-16 趋势报告事故）。
改这里 = 三处同时变，别再复制。
"""
import json
from typing import Optional

from sqlalchemy import func

from app.models.flow import OpportunityRequirement
from app.models.opportunity import Opportunity
from app.models.quotation import Quotation


def slots_dict(raw) -> dict:
    """统一把需求单 slots 解析为 dict。"""
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    return raw if isinstance(raw, dict) else {}


def current_slot_map(session, opp_ids: Optional[list] = None) -> dict:
    """读取需求单 slots，口径与商机列表一致：current 优先，缺失时回退最新 draft。"""
    q = session.query(
        OpportunityRequirement.opportunity_id,
        OpportunityRequirement.status,
        OpportunityRequirement.version,
        OpportunityRequirement.slots,
    ).filter(OpportunityRequirement.status.in_(["current", "draft"]))
    if opp_ids:
        q = q.filter(OpportunityRequirement.opportunity_id.in_(opp_ids))
    q = q.order_by(
        OpportunityRequirement.opportunity_id,
        OpportunityRequirement.version.desc(),
    )

    current: dict = {}
    draft: dict = {}
    for oid, status, _version, raw in q.all():
        parsed = slots_dict(raw)
        if status == "current" and oid not in current:
            current[oid] = parsed
        elif status == "draft" and oid not in draft:
            draft[oid] = parsed

    out: dict = {}
    for oid in set(current) | set(draft):
        out[oid] = current.get(oid) or draft.get(oid) or {}
    return out


def current_config_subquery(session, conds: list):
    """每个商机取「当前版本」的 config_count（status=active 中 version 最大的一条）。

    与商机列表/工作台的"当前版本"口径一致：一条商机只对应一个配置数，
    避免把同一商机多个版本报价单的 config_count 重复相加（导致周新增/总配置虚高）。
    返回子查询列：oid(opportunity_id), cc(config_count), date(商机创建日期), rn(排名)。
    """
    rn = func.row_number().over(
        partition_by=Quotation.opportunity_id,
        order_by=(Quotation.version.desc(), Quotation.created_at.desc()),
    ).label("rn")
    de_q = func.substr(Opportunity.created_at, 1, 10)
    return session.query(
        Quotation.opportunity_id.label("oid"),
        Quotation.config_count.label("cc"),
        de_q.label("date"),
        rn,
    ).join(
        Opportunity, Quotation.opportunity_id == Opportunity.opportunity_id
    ).filter(
        *conds,
        Quotation.status == "active",
    ).subquery()
