# -*- coding: utf-8 -*-
"""选项卡信号：从最近一张卡的结构化载荷里解释客户点选，落到归属节点的状态里。

2026-09-10 自 skill_chat.py 拆出（纯搬运，零行为变更）。
"""
from __future__ import annotations

import logging
from app.services.slot_contract import slot_spec
from typing import Optional


logger = logging.getLogger(__name__)


def _match_card_signal(mem: dict, slot: str, value: str) -> Optional[dict]:
    """从最近一张选项卡的结构化载荷里按 (slot, value) 匹配 signal（发卡时持久化的原始数据）。"""
    for o in ((mem.get("last_card") or {}).get("options") or []):
        if str(o.get("slot") or "") == slot and str(o.get("value") or "") == value \
                and isinstance(o.get("signal"), dict) and o.get("signal"):
            return o.get("signal")
    return None


def _signal_with_qty(signal: dict, qty: int, pick_meta: dict) -> dict:
    """数量覆盖（前端 stepper 参数）：克隆留底 signal 改数量，按机箱能力 clamp。
    数量是参数不是信号语义——服务端单点收口，客户端只传数字。"""
    import copy
    qty = max(1, int(qty or 1))
    meta = pick_meta if isinstance(pick_meta, dict) else {}
    gpu_cap = int(meta.get("gpu_slots") or 0) or 8
    dimm_cap = int(meta.get("max_dimm") or 0) or 8
    cpu_cap = int(meta.get("max_cpu") or 0) or 2
    sig = copy.deepcopy(signal)
    try:
        if isinstance(sig.get("kp_manual_pick"), dict):
            # 客户自选（kp 行卡）：数量直接覆盖申报，上限 clamp
            sig["kp_manual_pick"]["qty"] = min(qty, 999)
        elif isinstance(sig.get("gpu"), list) and sig["gpu"]:
            sig["gpu"][0]["qty"] = min(qty, gpu_cap)
        elif isinstance(sig.get("cpu"), dict):
            sig["cpu"]["qty"] = min(qty, cpu_cap)
        elif isinstance(sig.get("memory"), dict):
            sig["memory"]["qty"] = min(qty, dimm_cap)
        elif isinstance(sig.get("storage"), list) and sig["storage"]:
            sig["storage"][0]["qty"] = min(qty, 16)
        else:
            return signal
    except Exception:
        logger.exception("数量覆盖失败，回退原 signal")
        return signal
    return sig


def _apply_registration_signal(ext: dict, signal: dict, picks: Optional[dict] = None) -> bool:
    """把信号里的**线索登记表字段**按登记通道落值（apply_structured_slots 只管部件槽）。

    字段集来自登记表契约（slot_spec），不写第二套词表：选项声明 slot 时，
    客户点选就是把该字段登记成确认值——凡推断必求证，求证结果落同一张表。
    """
    if not isinstance(ext, dict) or not isinstance(signal, dict):
        return False
    try:
        from app.services.slot_contract import slot_spec
        keys = {str(s.get("key") or "") for s in slot_spec() if str(s.get("src_type") or "") != "kp"}
    except Exception:
        logger.exception("登记表字段契约读取失败")
        return False
    sub = {k: v for k, v in signal.items()
           if k in keys and v is not None and str(v).strip() != ""}
    if not sub:
        return False
    from app.services.capabilities import _apply_extracted_slots
    return _apply_extracted_slots(ext, sub, allow_overwrite=True, picks=picks)


def _brain_ask_manual_signal(mem: dict, text: str) -> Optional[dict]:
    """brain_ask 行卡的手动型号（2026-09-06 自选料接线）：pick_meta 留底池内匹配 →
    kp_manual_pick（价格用服务端留底值，客户端不可携带）；未命中 → kp_row_merge 文本
    并入行描述（白盒，下一轮大脑消化），绝不编造料号。"""
    meta = (mem.get("last_card") or {}).get("pick_meta") or {}
    row = str(meta.get("row") or "").strip()
    if not row:
        return None
    pool = [p for p in (meta.get("pool") or []) if isinstance(p, dict)]
    t = text.strip().lower()
    if not t:
        return None
    for c in pool:
        name = str(c.get("name") or "")
        if name.lower() == t or t in name.lower():
            return {"kp_manual_pick": {"row": row, "part_id": str(c.get("part_id") or ""),
                                        "name": name, "price": c.get("price"),
                                        "currency": str(c.get("currency") or "RMB")}}
    return {"kp_row_merge": {"row": row, "answer": text.strip()}}


def _manual_model_signal(mem: dict, slot: str, text: str) -> Optional[dict]:
    """自由输入型号 → 目录模糊匹配构造 signal（未命中返回 None，走登记表白盒路径）。"""
    meta = (mem.get("last_card") or {}).get("pick_meta") or {}
    if not isinstance(meta, dict) or not meta:
        return None
    from app.services.part_selector import manual_signal_for_text
    try:
        return manual_signal_for_text(slot, text, str(meta.get("server_type_name") or ""),
                                       baseline=meta)
    except Exception:
        logger.exception("手动型号目录匹配失败 slot=%s", slot)
        return None
