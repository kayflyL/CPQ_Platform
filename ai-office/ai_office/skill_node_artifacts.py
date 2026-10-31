# -*- coding: utf-8 -*-
"""节点产物打包（插头解释器·产物侧·纯机制）。

插座 = 节点机制（本模块 + 消费方）；插头 = 节点配置 target.artifacts[]（DB 唯一权威）。
机制只认产物槽注册表，不认具体节点：换/加目标表 = 注册一个 builder 并在抽屉
声明 slot，节点循环与主循环零改动（铁律⑤「换目标层不碰代码生效」的验收口径）。

2026-10-31 路线图 v4 第 1 步「装注册插座」：本模块只剩注册表机制，CPQ 域的
builder/实时发射器实现全部住宿主侧 `cpq_artifact_builders.py`（import 时自注册，
本模块首次使用时惰性触发——同 transaction_engine.resolve_app 组合根先例）。
新域接产物 = 宿主另写实现文件注册自己的 builder，引擎零改动。

插头两栏针脚（各司其职，不互相顶替）：
  slot  装什么 = 产物槽（注册表键，本模块分发认它，**只由抽屉声明**，代码无节点→产物表）
  kind  怎么显示 = 渲染类型（form/table/document/...，前端抽屉预览认它，不参与分发）

未注册 kind 的节点：产物为空（不装懂），只在 output 里给白盒事实。
"""
from __future__ import annotations

import logging

from ai_office.skill_target_contract import first_artifact

logger = logging.getLogger(__name__)

# kind 注册表：新增插头类型 = 宿主注册一个 builder，机制零改动
BUILDERS: dict = {}
# 「产物槽 → 回合内实时发射器」：实时可视化（边干边亮）是产物槽的属性，不是节点名的属性
LIVE_EMITTERS: dict = {}

_ENSURED = False


def register_builder(kind: str, fn) -> None:
    """宿主注册产物生成器（新增产物槽的唯一入口）。"""
    key = str(kind or "").strip()
    if key:
        BUILDERS[key] = fn


def register_live_emitter(kind: str, fn) -> None:
    """宿主注册产物槽的实时发射器（边干边亮）。"""
    key = str(kind or "").strip()
    if key:
        LIVE_EMITTERS[key] = fn


def ensure_registered() -> None:
    """宿主产物实现注册（组合根惰性触发一次，幂等）。

    引擎不得顶层 import 宿主；首次取注册表时代为 import 宿主实现模块，
    宿主被 import 时自注册（register_formatter 同款）。宿主缺位 = 注册表为空
    = 所有节点产物为空（白盒不装懂，不装懂也不崩）。
    """
    global _ENSURED
    if _ENSURED:
        return
    _ENSURED = True
    try:
        from app.services import cpq_artifact_builders  # noqa: F401  # noqa: E402
    except Exception:
        logger.exception("宿主产物实现注册失败（产物注册表为空，节点产物将为空）")


def builder_kinds() -> set:
    """已注册产物槽清单（flow_validation E3 条款的注册表查询口）。"""
    ensure_registered()
    return set(BUILDERS)


async def emit_live_artifact(node_key: str, engine: dict, event_sink, label: str,
                             started: float, text: str = "") -> bool:
    """节点回合内的实时产物广播（边干边亮）：该节点声明的产物槽注册了实时发射器才发。

    「这一步边想边亮」是产物槽的属性（见 LIVE_EMITTERS），不是节点名的属性：主循环只问
    有没有实时产物，不认节点名。换插头（把 slot 换成别的产物槽）→ 实时行为跟着换。
    """
    ensure_registered()
    emitter = LIVE_EMITTERS.get(resolve_kind(engine, node_key))
    if emitter is None:
        return False
    await emitter(engine, event_sink, label, started, text)
    return True


def declared_slot(engine: dict, key: str) -> str:
    """抽屉插头声明的产物槽：target.artifacts[0].slot（权威针脚）。

    过渡期兼容 output_artifact：仅当它的值恰好是已注册产物槽时才认（老库把产物槽写在
    这个字段里，如 requirement_text / plans）；值不是产物槽（如 'ext / requirement'）
    视为未声明，不猜。
    """
    ensure_registered()
    node_cfg = ((engine.get("flow_configs") or {}).get(key)
                if isinstance(engine.get("flow_configs"), dict) else None)
    cfg = node_cfg if isinstance(node_cfg, dict) else {}
    slot = str((first_artifact(cfg) or {}).get("slot") or "").strip()
    if not slot:
        leg = str(cfg.get("output_artifact") or "").strip()
        if leg in BUILDERS:
            slot = leg
    return slot


def resolve_kind(engine: dict, key: str) -> str:
    """产物槽分发：**完全由抽屉声明**（换插头生效），代码里没有「节点 → 产物」硬编码表。

    针脚分两栏：`slot` = 装什么（产物注册表键，本函数认它）；`kind` = 怎么显示
    （form/table/... 渲染类型，前端认它，不参与分发）。没声明 slot 的节点产物为空
    ——白盒不装懂，绝不按节点名兜底（否则换插头换不掉）。
    """
    slot = declared_slot(engine, key)
    return slot if slot in BUILDERS else ""


def done_summary(engine: dict, key: str, artifact: dict, vres: dict = None) -> str:
    """节点完成摘要：从该节点**真实产物**生成——产物是空的就如实说空，不报「已完成」。

    摘要不许再按节点 key 硬编码文案（历史事故：agent_fill 完成时显示「配件选型完成」）。
    """
    art = artifact if isinstance(artifact, dict) else {}
    data = art.get("data") if isinstance(art.get("data"), dict) else {}
    title = str(art.get("title") or "").strip() or str(key)
    if not art:
        return title + "：本节点未注册产物"
    vres = vres if isinstance(vres, dict) else {}
    kind = str(art.get("kind") or "")
    bits: list = []
    if str(vres.get("locked") or "").strip():
        bits.append("机型「" + str(vres["locked"]) + "」")
    rows = data.get("rows")
    if isinstance(rows, list) and rows:
        bits.append(str(len(rows)) + " 行")
        waived = [r for r in rows if isinstance(r, dict) and r.get("waived")]
        if waived:
            bits.append(f"其中 {len(waived)} 行库内无料·客户已知悉")
    plans = data.get("plans")
    n_plans = len(plans) if isinstance(plans, list) else data.get("plans_count")
    if isinstance(n_plans, int) and n_plans > 0:
        bits.append(str(n_plans) + " 个整机配置")
    if kind == "requirement_slots" and not bits:
        filled = len([k for k, v in data.items() if v not in (None, "", [], {})])
        if filled:
            bits.append(str(filled) + " 项已登记")
    if kind == "document":
        md = str(data.get("markdown") or "")
        if md:
            bits.append(str(len(md)) + " 字")
    if bits:
        return title + " · " + " / ".join(bits)
    return (title + " 已生成") if data else (title + "（产物为空）")


def node_payload(engine: dict, key: str, label: str, summary: str, vres: dict = None) -> dict:
    """节点完成广播载荷：summary + 该节点真实产物（output/artifact）。

    供画布节点卡在节点下方展示「产出 / 输出物」；kind 未知则产物为空（白盒不装懂）。
    summary 留空时由产物生成（见 done_summary）。
    """
    output = None
    artifact = None
    try:
        node_cfg = ((engine.get("flow_configs") or {}).get(key)
                    if isinstance(engine.get("flow_configs"), dict) else None)
        art = first_artifact(node_cfg) or {}
        builder = BUILDERS.get(resolve_kind(engine, key))
        if builder is not None:
            output, artifact = builder(engine, art)
    except Exception:
        logger.exception("节点产物打包失败 step=%s", key)
        output, artifact = None, None
    if not summary:
        summary = done_summary(engine, key, artifact, vres)
    return {"type": "node_trace", "step": key, "label": label, "status": "done",
            "input": None, "output": output, "summary": summary or "", "artifact": artifact}
