# -*- coding: utf-8 -*-
"""纯 LLM 填表可靠性测试 —— 决定 AI 路能否去 extract 基底（纯 LLM + resolver）。

每条输入跑 N 次 chat_json（主抽取 prompt，不喂 extract 摘要），统计：
  - 关键字段命中率（填了且值对 / 期望次数）
  - 抽不全的频率（不足以支撑选配 → 需触发反问的占比）

跑法（backend 目录）：./.venv/Scripts/python.exe -X utf8 scripts/test_llm_extraction_reliability.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import llm_client
from app.services.llm_extract_enhance import EXTRACT_ENHANCE_SCHEMA
from app.services.requirement_slots import build_catalog_context

PRIMARY_PROMPT = (
    "你是 CPQ 服务器需求结构化抽取器。输入：客户需求原文（格式随意/口语/表格化都行）。\n"
    "任务：把需求填进下面的固定表（JSON 对象），只输出 JSON，不要任何多余文字。\n"
    "表字段：\n"
    "  cpu{model,cores,tdp_w,qty}  memory{per_stick_gb,qty,type(DDR4/DDR5),speed_mt}  "
    "drives[{capacity,capacity_gb,interface(SATA/SAS/NVMe/U.2/U.3),qty}]  "
    "gpu[{model,qty}]  nic[{model,speed_g,ports,qty,with_optical_module}]  "
    "psu{wattage,qty}  raid{model,qty}  form  series  server_type  notes[]\n"
    "硬约束：\n"
    "1) 能力声明≠配置（支持N个=能力，不是配N个）；2) X*N/N*X/X×N = N 个 X，拆 model 与 qty；\n"
    "3) 内存 qty 是条数不是插槽数；4) 没把握写 null，绝不猜；5) server_type 从清单选并按需推断；\n"
    "6) series/form 只从清单选。"
)


def build_msgs(req: str, catalog: dict):
    st = "、".join(catalog.get("server_types") or []) or "（无）"
    sr = "、".join(catalog.get("series") or []) or "（无）"
    fm = "、".join(catalog.get("forms") or []) or "（无）"
    user = (f"在售服务器类型（server_type 只从这里选）：{st}\n"
            f"在售平台系列（series 只从这里选）：{sr}\n"
            f"机箱形态（form 只从这里选）：{fm}\n\n"
            f"需求原文：\n{req.strip()}\n\n"
            "请填表（严格按字段名，没把握写 null）。")
    return [{"role": "system", "content": PRIMARY_PROMPT}, {"role": "user", "content": user}]


def _g(d, *path):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


# 每条输入：要求 + 期望关键字段（field_path → 判定函数）
INPUTS = [
    ("5090AI结构化",
     "内存:32G*16 DDR5 / 系统盘:2*480GB SATA SSD / 数据盘:2*3.84TB PCIe Gen4 NVMe / GPU: RTX 5090 32G*8 / 网卡:双口25G SFP+",
     {"server_type": lambda v: v and "AI" in str(v),
      "gpu[0].qty": lambda v: v == 8, "gpu[0].model": lambda v: v and "5090" in str(v),
      "memory.qty": lambda v: v == 16, "memory.per_stick_gb": lambda v: v == 32,
      "drives_len": lambda v: v >= 2, "nic[0].speed_g": lambda v: v == 25}),
    ("9654通用结构化",
     "机箱：2U机架式 CPU：AMD 9654 * 2 内存：DDR5  32 * 16 硬盘：SATA 960G*2+NVMe 3.84T*2 网卡：双口25G+光模块 RAID：LSI 9560-8i",
     {"server_type": lambda v: v and ("通用" in str(v) or "计算" in str(v)),
      "cpu.qty": lambda v: v == 2, "memory.qty": lambda v: v == 16, "memory.per_stick_gb": lambda v: v == 32,
      "drives_len": lambda v: v >= 2, "nic[0].speed_g": lambda v: v == 25}),
    ("9254+GPU结构化",
     "机箱：2U CPU：AMD EPYC 9254 *2 内存：32G*2 DDR5 硬盘：960G NVMe GPU：RTX 4500 *1",
     {"cpu.qty": lambda v: v == 2, "memory.per_stick_gb": lambda v: v == 32,
      "gpu[0].model": lambda v: v and "4500" in str(v), "gpu[0].qty": lambda v: v == 1}),
    ("口语化messy",
     "客户要搭个大模型推理集群，单节点8张5090涡轮卡，2U机架，内存够大512G，双口25G光口，预算40万以内",
     {"server_type": lambda v: v and "AI" in str(v), "form": lambda v: v == "2U",
      "gpu[0].qty": lambda v: v == 8, "nic[0].speed_g": lambda v: v == 25}),
]


def extract_val(slots, field):
    """从 slots 按 'memory.qty' / 'gpu[0].qty' / 'drives_len' 取值。"""
    if field == "drives_len":
        return len(slots.get("drives") or []) if isinstance(slots.get("drives"), list) else 0
    if "[" in field:
        # gpu[0].qty
        import re
        m = re.match(r"(\w+)\[(\d+)\]\.(\w+)", field)
        arr = slots.get(m.group(1)) or []
        idx = int(m.group(2))
        return _g(arr[idx] if idx < len(arr) else {}, m.group(3)) if arr else None
    return _g(slots, *field.split("."))


def is_sufficient(slots):
    """抽出来的够不够支撑后续选配？不够 → 该反问。
    判据：有 server_type 且至少一个配置信号（cpu/memory/gpu/drive 之一非空）。"""
    st = slots.get("server_type")
    has_signal = any(slots.get(k) for k in ("cpu", "memory", "gpu", "drives"))
    return bool(st) and has_signal


async def extract_once(req, catalog):
    try:
        return await llm_client.chat_json(build_msgs(req, catalog), schema=EXTRACT_ENHANCE_SCHEMA)
    except Exception as e:
        return {"_error": str(e)[:120]}


async def main():
    catalog = build_catalog_context()
    N = 10
    print(f"纯 LLM 填表可靠性测试（每条 {N} 次）  catalog: {len(catalog.get('server_types') or [])} 类型\n")
    print("=" * 80)
    for name, req, expect in INPUTS:
        runs = await asyncio.gather(*[extract_once(req, catalog) for _ in range(N)])
        runs = [r for r in runs if isinstance(r, dict) and not r.get("_error")]
        n_ok = len(runs)
        print(f"\n【{name}】  成功 {n_ok}/{N} 次   需求: {req[:60]}...")
        # 关键字段命中率
        for field, ok_fn in expect.items():
            hits = sum(1 for r in runs if (lambda v: v is not None and ok_fn(v))(extract_val(r, field)))
            print(f"   {field:24s} 命中 {hits}/{n_ok}")
        # 完整度（够不够支撑选配 → 不够则需反问）
        suff = sum(1 for r in runs if is_sufficient(r))
        print(f"   {'>>> 够支撑选配':24s} {suff}/{n_ok}   （不够的 {n_ok - suff} 次需触发反问）")
        # 示例输出（第一次成功的）
        if runs:
            ex = {k: runs[0].get(k) for k in ("server_type", "cpu", "memory", "gpu", "drives", "nic", "form")}
            print(f"   示例: {json.dumps(ex, ensure_ascii=False)[:220]}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
