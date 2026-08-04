# -*- coding: utf-8 -*-
"""场景分析器（scene_analysis 节点）—— 纯函数、无副作用、可单测。

职责：机型选型前，把需求信号 + 商机上下文 → 场景（AI/存储/通用）× 系列 × 形态，
输出候选范围 + 置信度 + 证据（白盒，不黑盒）。

数据驱动铁律：
- 场景映射（scene_rules / series_hints / form_infer / opportunity_hints / fallback）
  100% 来自 system_config.scene_mapping（平台可编辑）；读失败回退本模块
  DEFAULT_SCENE_MAPPING（仅兜底，不散落硬编码）。
- 服务器类型来自 l6.server_types（真实产品目录），不是代码臆造；只对有货在售的类型打分。
- 系列/形态优先取 extract 词表结果（lex_series / lex_form，用户明说/词表命中），
  缺失才用 hints 推断，推断结果带证据。

返回 scene dict：
    scene_name     服务器类型名（l6.server_types.name），无法确定时 None
    series         Orion / Polaris / Intel / 工作站 或 None
    form           1U/2U/4U/… 或 None
    determined     True=可直接进入机型选型；False=需反问补全（missing 给出字段）
    confidence     0-100 置信度
    evidence       [命中证据…]（白盒：为什么选这个场景/系列/形态）
    candidates     [{scene_name, series, form, score, evidence}] 供前端展示
    missing        determined=False 时的待反问字段（场景/系列/形态）
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 服务器类型兜底（system_config / l6.server_types 读失败时才用；名字需与 l6.server_types 一致）
DEFAULT_SERVER_TYPE_NAMES = ["AI / 加速计算服务器", "通用计算服务器", "存储服务器"]

# 场景映射默认值 —— 仅作 system_config.scene_mapping 的种子/读失败兜底。
# 权威来源是 system_config.scene_mapping（策略中心可编辑），改这里需同步种子。
DEFAULT_SCENE_MAPPING: dict = {
    "version": 1,
    "scene_rules": [
        {
            "scene": "AI / 加速计算服务器",
            "weight": 80,
            "signals": {
                # 单张消费级/专业级显卡（RTX/5090/RTX PRO）多为通用机加加速卡（R6：1*RTX PRO 4500 → 通用 2U）；
                # AI 场景需 ≥2 卡，或数据中心 GPU 型号（H100/A100/L40S/国产算力卡），或明确 AI 场景词。
                "keywords": [
                    "ai训练", "ai 推理", "深度学习", "训练", "大模型", "llm", "推理", "infer",
                    "部署模型", "serving", "多卡", "8卡", "4卡", "双卡", "gpu整机", "gpu 服务器",
                    "gpu算力", "加速计算", "加速卡",
                ],
                "usage": ["AI", "加速", "训练", "推理"],
                "gpu_min": 2,
                "gpu_datacenter": [
                    "h100", "h200", "h800", "a100", "a800", "b100", "b200", "l40", "l40s", "l20",
                    "mi100", "mi250", "mi300", "910b", "智铠", "沐曦", "曦索", "摩尔线程", "mtt", "天数智芯",
                ],
            },
            "evidence": {
                "keywords": "训练/推理/AI 场景词",
                "usage": "AI 用途",
                "gpu_min": "GPU 数量≥2（多卡）",
                "gpu_datacenter": "数据中心 GPU（H100/A100/L40S 等）",
            },
        },
        {
            "scene": "存储服务器",
            "weight": 70,
            "signals": {
                # 强词：明确存储场景（OR 命中即算）；弱词（大容量/高盘位/氦气）需盘量≥8 佐证（drive_high）
                "keywords": ["存储服务器", "存储节点", "对象存储", "分布式存储", "nas", "冷存储", "备份", "归档"],
                "drive_high": {"min": 8, "keywords": ["大容量", "高盘位", "氦气"]},
                "usage": ["存储"],
            },
            "evidence": {
                "keywords": "存储场景词（存储服务器/NAS/分布式/冷存储）",
                "drive_high": "高盘位/大容量/氦气盘（≥8 盘）",
                "usage": "存储用途",
            },
        },
        {
            "scene": "通用计算服务器",
            "weight": 50,
            "signals": {
                "keywords": ["虚拟化", "云主机", "容器", "k8s", "虚拟机", "openstack", "数据库",
                             "mysql", "olap", "oltp", "oracle", "postgres", "渲染", "视觉",
                             "特效", "影视后期", "通用", "办公", "web 服务", "业务系统", "企业应用"],
                "usage": ["通用", "办公", "虚拟化", "数据库"],
            },
            "evidence": {
                "keywords": "通用计算场景词",
                "usage": "办公/虚拟化/数据库",
            },
        },
    ],
    "series_hints": [
        {"series": "Orion", "keywords": ["epyc", "amd", "orion", "猎户", "genoa", "9654", "9554", "9354", "9124", "9254", "9745"],
         "evidence": "AMD/EPYC 平台"},
        {"series": "Polaris", "keywords": ["kh50000", "kh-50000", "kh5000", "kh-5000", "kh50000-72", "兆芯", "zhaoxin",
                                           "开胜", "开先", "kx", "kx40000", "kx-40000", "信创"],
         "evidence": "兆芯/信创平台"},
        {"series": "Intel", "keywords": ["xeon", "intel", "至强"],
         "evidence": "Intel 平台"},
    ],
    "form_infer": {
        # 多卡 GPU：产品目录 8 卡机型均为 4U；需求写了 2U 且 GPU≥4 时按目录能力纠正（带证据）
        "gpu_override_min": 4,
        "gpu_form": "4U",
        "gpu_evidence": "多卡 GPU（≥4 卡）需 4U 高扩展机箱",
        "override_forms": ["2U"],
    },
    "opportunity_hints": {
        "industry": {
            "AI": {"scene": "AI / 加速计算服务器", "weight": 20, "evidence": "商机行业：AI/互联网"},
            "互联网": {"scene": "AI / 加速计算服务器", "weight": 20, "evidence": "商机行业：AI/互联网"},
            "存储": {"scene": "存储服务器", "weight": 20, "evidence": "商机行业：存储"},
            "云": {"scene": "通用计算服务器", "weight": 20, "evidence": "商机行业：云/虚拟化"},
        },
        "customer_type": {},
    },
    "thresholds": {"decide": 30},
    "fallback_scene": "通用计算服务器",
}


def load_scene_mapping(config: Optional[dict]) -> dict:
    """读场景映射：system_config.scene_mapping（权威）→ 节点配置 mapping → 模块默认。

    任何一层失败/缺失都向下回退，绝不抛异常阻塞推理流。
    """
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            cfg = repo.get_value("scene_mapping")
        finally:
            repo.close()
        if isinstance(cfg, dict) and cfg.get("scene_rules"):
            return cfg
    except Exception as e:
        logger.warning("读 system_config.scene_mapping 失败，回退节点配置/模块默认: %s", e)
    if config:
        m = config.get("mapping")
        if isinstance(m, dict) and m.get("scene_rules"):
            return m
    return DEFAULT_SCENE_MAPPING


def _load_server_types() -> list:
    """读 l6.server_types（真实目录）。失败回退默认类型名（无 id，仅名字）。"""
    try:
        from app.repository.server_catalog_repo import ServerCatalogRepository
        repo = ServerCatalogRepository()
        return repo.list_types()
    except Exception as e:
        logger.warning("读 l6.server_types 失败，用默认类型名: %s", e)
        return [{"id": i + 1, "name": n} for i, n in enumerate(DEFAULT_SERVER_TYPE_NAMES)]


# ── 信号构建 ──────────────────────────────────────────────────────────────
def _qty_of(ext: dict, category: str) -> int:
    try:
        return int((ext.get("qty_map") or {}).get(category) or 0)
    except (TypeError, ValueError):
        return 0


def _gpu_qty(ext: dict) -> int:
    qty = _qty_of(ext, "GPU")
    for g in ext.get("gpu_groups") or []:
        try:
            qty = max(qty, int(g.get("qty") or 0))
        except (TypeError, ValueError):
            pass
    return qty


def _drive_qty(ext: dict) -> int:
    qty = _qty_of(ext, "HDD/SSD")
    for g in ext.get("drive_groups") or []:
        try:
            qty += int(g.get("qty") or 0)
        except (TypeError, ValueError):
            pass
    return qty


def _build_signals(ext: dict, requirement_text: str) -> dict:
    ext = ext or {}
    return {
        "categories": [str(c) for c in (ext.get("categories") or [])],
        "keywords": [str(k) for k in (ext.get("keywords") or [])],
        "text_low": (requirement_text or "").lower(),
        "series": ext.get("series") or None,
        "form": ext.get("form") or None,
        "usage": str(ext.get("usage") or ""),
        "server_type_name": ext.get("server_type_name") or None,
        "gpu_qty": _gpu_qty(ext),
        "drive_qty": _drive_qty(ext),
    }


def _text_contains(text_low: str, word: str) -> bool:
    w = (word or "").strip().lower()
    return bool(w) and w in text_low


def _rule_hits(rule: dict, s: dict) -> list:
    """规则命中的证据标签列表（空 = 未命中）。信号组之间是 OR：任一组命中即算命中。"""
    sig = rule.get("signals") or {}
    ev = rule.get("evidence") or {}
    hits: list = []
    if sig.get("categories") and any(
            any(c and c.lower() == (x or "").lower() for x in s["categories"])
            for c in sig["categories"]):
        hits.append(ev.get("categories") or "品类命中")
    if sig.get("keywords") and any(
            _text_contains(s["text_low"], w) or any(w.lower() in k.lower() for k in s["keywords"])
            for w in sig["keywords"]):
        hits.append(ev.get("keywords") or "关键词命中")
    # 弱词 + 盘量佐证（存储等：如"大容量/高盘位/氦气"需 ≥min 盘才认）
    if sig.get("drive_high"):
        dh = sig["drive_high"]
        if s["drive_qty"] >= int(dh.get("min") or 8) and any(
                _text_contains(s["text_low"], w) for w in dh.get("keywords") or []):
            hits.append(ev.get("drive_high") or "高盘位/大容量")
    if sig.get("usage") and any(u and u.lower() in s["usage"].lower() for u in sig["usage"]):
        hits.append(ev.get("usage") or "用途命中")
    if sig.get("gpu_min") is not None and s["gpu_qty"] >= int(sig["gpu_min"]):
        hits.append(ev.get("gpu_min") or "GPU 数量命中")
    # 数据中心 GPU 型号（H100/A100/L40S…）：单卡也算 AI 场景
    if sig.get("gpu_datacenter") and any(
            _text_contains(s["text_low"], w) for w in sig["gpu_datacenter"]):
        hits.append(ev.get("gpu_datacenter") or "数据中心 GPU 型号")
    if sig.get("drive_min") is not None and s["drive_qty"] >= int(sig["drive_min"]):
        hits.append(ev.get("drive_min") or "盘数量命中")
    return hits


def _resolve_series(s: dict, mapping: dict) -> tuple:
    """系列：extract 词表（lex_series）优先；缺失用 series_hints 按文本推断。"""
    if s.get("series"):
        return s["series"], []
    for hint in mapping.get("series_hints") or []:
        if any(_text_contains(s["text_low"], w) for w in hint.get("keywords") or []):
            return hint["series"], [hint.get("evidence") or f"系列推断：{hint['series']}"]
    return None, []


def _resolve_form(s: dict, mapping: dict) -> tuple:
    """形态：extract 词表（lex_form）优先；多卡 GPU 按目录能力纠正；否则 hints。"""
    fi = mapping.get("form_infer") or {}
    gpu_min = int(fi.get("gpu_override_min") or 0)
    if gpu_min and s["gpu_qty"] >= gpu_min:
        cur = s.get("form")
        if not cur or cur in (fi.get("override_forms") or []):
            return fi.get("gpu_form") or "4U", [fi.get("gpu_evidence") or "多卡 GPU 需 4U 机箱"]
    return s.get("form"), []


def _opportunity_hits(opportunity: Optional[dict], mapping: dict) -> list:
    """商机上下文 → [(scene, weight, evidence)]。industry 命中优先，其次 customer_type。"""
    if not opportunity:
        return []
    hints = mapping.get("opportunity_hints") or {}
    out = []
    for field_key, group in (("industry", hints.get("industry") or {}), ("customer_type", hints.get("customer_type") or {})):
        val = str(opportunity.get(field_key) or "").strip()
        if not val:
            continue
        for key, spec in (group or {}).items():
            if key.lower() in val.lower():
                out.append((spec.get("scene"), int(spec.get("weight") or 0),
                            spec.get("evidence") or f"商机{field_key}：{key}"))
    return out


def analyze_scene(ext: dict, requirement_text: str = "", config: Optional[dict] = None,
                  opportunity: Optional[dict] = None, catalog_type_name: Optional[str] = None,
                  server_types: Optional[list] = None,
                  force_complete: bool = False) -> dict:
    """场景分析主入口（scene_analysis 节点 handler 调用，纯函数）。

    Returns: scene dict（结构见模块 docstring）。
    """
    mapping = load_scene_mapping(config)
    types = server_types if server_types is not None else _load_server_types()
    type_names = [t.get("name") or "" for t in types if t.get("name")]
    s = _build_signals(ext, requirement_text)
    thresholds = mapping.get("thresholds") or {}
    decide = float(thresholds.get("decide") or 30)
    fallback_scene = mapping.get("fallback_scene") or "通用计算服务器"

    # 场景打分
    scores: dict[str, dict] = {}
    for rule in mapping.get("scene_rules") or []:
        scene_name = rule.get("scene")
        if not scene_name or scene_name not in type_names:
            continue  # 只对有货在售的类型打分
        hits = _rule_hits(rule, s)
        if hits:
            entry = scores.setdefault(scene_name, {"score": 0, "evidence": []})
            entry["score"] += int(rule.get("weight") or 0)
            for h in hits:
                if h not in entry["evidence"]:
                    entry["evidence"].append(h)

    # extract 词表已命中类型（lex_server_type）→ 强信号
    if s.get("server_type_name") and s["server_type_name"] in type_names:
        entry = scores.setdefault(s["server_type_name"], {"score": 0, "evidence": []})
        entry["score"] += 100
        if "需求词表命中服务器类型" not in entry["evidence"]:
            entry["evidence"].insert(0, "需求词表命中服务器类型")

    # 商机上下文（行业/客户类型）只作「需求已定场景」的偏好微调，不单独决定场景：
    # 需求文本没有场景信号（无 GPU/存储词等）时，行业线索不越权，避免"通用需求+AI行业"推 AI 机型。
    if scores:
        for scene_name, w, ev in _opportunity_hits(opportunity, mapping):
            if scene_name and scene_name in type_names:
                entry = scores.setdefault(scene_name, {"score": 0, "evidence": []})
                entry["score"] += w
                if ev not in entry["evidence"]:
                    entry["evidence"].append(ev)

    # 系列 / 形态
    series, series_ev = _resolve_series(s, mapping)
    form, form_ev = _resolve_form(s, mapping)
    # 系列来源（2026-08-04 流程重构，R29）：extract 词表命中=explicit（需求明说/词表），
    # hints 推断=inferred（系统推的 → confirm_series 节点要问用户确认）；无= None。
    series_source = "explicit" if s.get("series") else ("inferred" if series else None)

    # 客户在目录引导中已选类型 → 权威，直接确定
    if catalog_type_name and catalog_type_name in type_names:
        return {
            "scene_name": catalog_type_name,
            "series": series,
            "series_source": series_source,
            "form": form,
            "determined": True,
            "confidence": 100,
            "evidence": ["客户在目录引导中选择了服务器类型"] + series_ev + form_ev,
            "candidates": [{"scene_name": catalog_type_name, "series": series,
            "series_source": series_source, "form": form,
                            "score": 100, "evidence": ["目录引导选择"]}],
            "missing": [],
        }

    # 判定
    if not scores:
        has_any = bool(s["categories"] or s["keywords"] or s["series"] or s["form"]
                       or s["usage"] or s["server_type_name"])
        if not has_any and not force_complete:
            # 真·无信号：完全无法判断 → 反问补全场景（force_complete/封顶时按默认场景硬出，避免死循环）
            return {
                "scene_name": None, "series": series,
            "series_source": series_source, "form": form,
                "determined": False, "confidence": 0,
                "evidence": series_ev + form_ev,
                "candidates": [],
                "missing": ["场景"],
            }
        # 有系列/形态/配件信号但未命中强场景词 → 按默认场景（避免过度反问，白盒说明）
        return {
            "scene_name": fallback_scene if fallback_scene in type_names else None,
            "series": series,
            "series_source": series_source, "form": form,
            "determined": True, "confidence": 0,
            "evidence": ["未命中强场景词，按默认场景"] + series_ev + form_ev,
            "candidates": [],
            "missing": [],
        }

    top_name = max(scores, key=lambda k: scores[k]["score"])
    top = scores[top_name]
    if top["score"] >= decide:
        return {
            "scene_name": top_name,
            "series": series,
            "series_source": series_source, "form": form,
            "determined": True,
            "confidence": min(100, int(top["score"])),
            "evidence": top["evidence"] + series_ev + form_ev,
            "candidates": [{"scene_name": top_name, "series": series,
            "series_source": series_source, "form": form,
                            "score": top["score"], "evidence": top["evidence"]}],
            "missing": [],
        }
    # 分数不足阈值 → 默认场景（避免过度反问）
    return {
        "scene_name": fallback_scene if fallback_scene in type_names else top_name,
        "series": series,
            "series_source": series_source, "form": form,
        "determined": True,
        "confidence": int(top["score"]),
        "evidence": top["evidence"] + ["未达判定阈值，按默认场景"] + series_ev + form_ev,
        "candidates": [{"scene_name": top_name, "series": series,
            "series_source": series_source, "form": form,
                        "score": top["score"], "evidence": top["evidence"]}],
        "missing": [],
    }
