# -*- coding: utf-8 -*-
"""机型候选能力：按类型/系列/形态从【机型层】选出整机骨架候选。

能力归属（树干-枝叶）：机型选型节点的数据接口。检索与排序是机制；
推荐标注（_annotate_recommend）只读策略中心 selection.model_recommend 规则——
"规则存策略中心、机制只读规则"的正样板。消费方：skill_phases.phase_model_reason
（引擎）、skill_chat.tool_catalog_search / agent tool select_models（AI 角色工具）。
2026-09-02 自 app/api/candidate_search.py 原样迁入（纯搬移零行为变化）。
"""
import logging
from typing import Optional

from app.repository.base_config_repo import BaseConfigRepository
from app.repository.server_catalog_repo import ServerCatalogRepository

logger = logging.getLogger(__name__)


def _rank_base_config_variant(bc: dict, main_config_id: Optional[int]) -> int:
    """机型多基准配置变体排序分：需求信号缺失时按主配置优先、其余按 id 稳定排序。

    旧的信号偏好（形态/RAID/直连/Switch/8卡直连）依赖 build_variant_signals 产出的
    variant_signals；该信号源已按「AI 唯一大脑 + 不臆断」删除。无信号时不替用户做模板偏好，
    只保留主配置 +5 作默认保底，其余按 id 稳定排序。
    """
    score = 0
    if bc.get("id") == main_config_id:
        score += 5
    return score


def _variant_short_name(cfg_name: str) -> str:
    """变体名 → 短标签："4U-Orion-Switch机型" → "Switch"；"Orion 2U12 直连版…" → "直连版"。”"""
    n = (cfg_name or "").replace("机型", "").strip()
    for pre in ("4.5U-", "4U-", "2U25-", "2U12-", "Orion ", "Polaris ", "ES220 V3", "ESA240 V3"):
        n = n.replace(pre, "").strip()
    return n or (cfg_name or "")


def select_models(usage: Optional[str], server_type_name: Optional[str] = None,
                  series: Optional[str] = None, form: Optional[str] = None,
                  limit: Optional[int] = None,
                  no_signal_strategy: Optional[str] = None) -> list[dict]:
    """按机型类型 + series/form 从【机型层】选 1-N 个机型作整机骨架。

    类型匹配：server_type_name 精确（词表/目录引导配的真实类型名）；无类型信号但有形态 → 取目录排序首个类型；
    无任何信号 → 返空（交给 clarity_check 反问）。
    （旧 usage→类型关键词路由 USAGE_TYPE_ROUTING 已删：usage 现只来自配置词表、与 server_type_name 同源，
    模糊路由是死代码。）
    选 server_models（机型，有 server_type/use）而非旧 base_configs 直选
    （基准配置，无 type）；**匹配多少给多少，不硬塞全量凑数**。

    返回每条 dict 兼容 build_plan 原 baseline 字段（id/series/form/bays/parts_count/total_price/
    bom_template_id）+ 机型顶层字段（server_model_id/name/use/product_content/server_type_*）。
    其中 id = base_config_id（下游 confirmPlan/buildPlanCfg 靠它，语义不变）。
    无任何信号（usage/type/series/form 都空）→ 返空，不硬推全量（交给 clarity_check 反问）。
    """
    if not any([usage, server_type_name, series, form]):
        if no_signal_strategy != "fallback_all":
            return []  # return_empty（默认）/ prompt 都返空让反问；fallback_all 才继续查全量
    cat_repo = ServerCatalogRepository()
    types = cat_repo.list_types()
    # 优先按 server_type_name 精确匹配（词表配的就是真实类型名），未给走 usage 关键词模糊
    type_id = None
    if server_type_name:
        for t in types:
            if t.get("name") == server_type_name:
                type_id = t["id"]
                break
    # 无类型信号但有形态（如"2U"）→ 取目录排序首个类型作默认（admin 配 sort_order），
    # 避免 AI/存储机型混入结果；不在代码里写死"通用计算服务器"。
    if type_id is None and form and types:
        type_id = types[0]["id"]
    # 严格匹配：只按信号条件精确查候选，命中多少给多少；不再由引擎逐级放宽。
    # 放宽决策（去系列/拓宽池）交由调用方（phase_model_reason 白盒路径）或 AI 角色显式做。
    models = cat_repo.list_models(type_id=type_id, series=series, form=form, published_only=True)
    match_stage = "exact"
    type_name_by_id = {t["id"]: t.get("name") or "" for t in types}
    # 批量取 base_configs 聚合（parts_count/total_price/bom_template_id）
    bc_repo = BaseConfigRepository()
    bc_map = {bc["id"]: bc for bc in bc_repo.list()}
    out: list[dict] = []
    for m in models:
        bc_id = m.get("base_config_id")
        if not bc_id:
            continue  # 无主配置机型（新建未关联/未设主）跳过：选型需要可配置 baseline
        sid = m.get("server_type_id")
        # 机型多基准配置变体（R7）：一个机型挂多个 base_config（model_id 反向关联，各绑不同
        # BOM 模板），按需求信号排序全部给出；单变体机型行为不变（只有主配置）。
        # 按机型分组而非全局排序：跨机型竞争会让 ZSA(4U AI) 混入存储需求并靠 storage+50 反超（R13 回归）
        mid = m.get("id")
        variants = [bc for bc in bc_map.values() if bc.get("model_id") == mid] or [bc_map.get(bc_id, {})]
        variants = [v for v in variants if v]
        variants.sort(key=lambda v: (-_rank_base_config_variant(v, bc_id), v.get("id") or 0))
        for bc in variants:
            if limit is not None and len(out) >= limit:
                break
            bc_embed = m.get("base_config") or {}
            _name = m.get("name") or ""
            if len(variants) > 1:
                _name = f"{_name}（{_variant_short_name(bc.get('name') or '')}）"
            out.append({
                # 机型顶层字段
                "server_model_id": m.get("id"),
                "name": _name,
                "use": m.get("use") or "",
                "product_content": m.get("product_content"),
                "server_type_id": sid,
                "server_type_name": type_name_by_id.get(sid, "") if sid is not None else "",
                # base_config 元信息（build_plan/下游按 baseline 字段消费，id = base_config_id）
                "id": bc.get("id"),
                "series": bc_embed.get("series") or bc.get("series"),
                "form": bc_embed.get("form") or bc.get("form"),
                "bays": bc_embed.get("bays") if bc_embed.get("bays") is not None else bc.get("bays"),
                "model": m.get("name") or bc.get("model") or "",
                "bom_template_id": bc.get("bom_template_id"),
                # 白盒标注：命中级（严格匹配，不再有放宽链）
                "match_stage": match_stage,
                "fallback_note": "精确匹配",
                # 机箱能力约束（基准配置页「机箱能力」可配）：PSU 档位 / CPU 上限 / 内存条数上限 / 每路通道数
                # 缺省 None → 消费端用全局兜底（不把物理边界硬编码在推理链路）
                "psu_wattages": bc.get("psu_wattages") or None,
                "max_cpu": bc.get("max_cpu") or None,
                "max_dimm": bc.get("max_dimm") or None,
                "mem_channels": bc.get("mem_channels") or None,
                "gpu_slots": bc.get("gpu_slots") or None,
                "max_tdp": bc.get("max_tdp") or None,
                "parts_count": int(bc.get("parts_count") or 0),
                "total_price": float(bc.get("total_price") or 0),
                # 机型卡片渲染所需顶层字段（候选卡/详情页自配入口用；下游仍按 id/series/form 消费，不破坏）
                "image_url": m.get("image_url"),
                "description": m.get("description"),
                "lifecycle_status": m.get("lifecycle_status"),
                "is_published": m.get("is_published"),
                "base_config": m.get("base_config"),
            })
    results = out if limit is None else out[:limit]
    _annotate_recommend(results)
    return results


def _annotate_recommend(baselines: list[dict]) -> None:
    """S1: 读 selection.model_recommend 策略，按 scope.series 给 baseline 附加
    recommend_level（recommend/avoid/neutral）+ selling_points（包装点）。仅标注，不改检索。
    series 维度与 KP 配件适用系列、base_config.series 同源（l6.server_types（设置-服务器管理-产品系列））。
    自动读取全部 active 规则，不做单策略筛选。"""
    try:
        from app.repository.strategy_repo import StrategyRepository
        repo = StrategyRepository()
        rules = [r for r in repo.list(domain='selection', status='active') if r.get('type') == 'model_recommend']
        repo.close()
    except Exception:
        return
    if not rules:
        return
    for b in baselines:
        for r in rules:
            sc = r.get('scope') or {}
            if sc.get('series') and b.get("series") != sc['series']:
                continue
            body = r.get('body') or {}
            b['recommend_level'] = body.get('level', 'neutral')
            b['selling_points'] = body.get('selling_points', '')
            break
