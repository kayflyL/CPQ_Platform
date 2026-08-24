# -*- coding: utf-8 -*-
"""一次性修复：回填缺参配件 + 保守合并真重复（保留历史价格）。

跑法（backend 目录）：
  ./.venv/Scripts/python.exe -X utf8 scripts/fix_kp_data.py              # dry-run 预览
  ./.venv/Scripts/python.exe -X utf8 scripts/fix_kp_data.py --llm        # dry-run + 外部件走 LLM
  ./.venv/Scripts/python.exe -X utf8 scripts/fix_kp_data.py --commit --llm  # 写库

说明：
- 合并以"同一性键"（分类+容量/形态/型号等）为主，且做保守判定：
  若某件名称含差异化信息（DWPD / 电池 / 支架 / 具体料号）则保留为独立件，不并入。
- 合并时历史价格、兼容机型、关联件全部迁移到保留件，绝不丢。
- 外部件（国产 GPU/加速卡、CPU、HBA/Bridge/NVSwitch 等）默认仅 dry-run 列待补，
  加 --llm 由 LLM 生成规格；LLM 不确认的字段置空、整件无结果则标记待人工。
"""
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.models.kp import KPPart, KPPartSpec, KPPriceHistory, KPPartCompat, KPPartRelated
from app.repository.kp_repo import KPRepository

# 保守合并计划：保留件 -> 需并入的重复件 id 列表（已人工研判，见 dry-run 说明）
# 联网/人工研读取值（稳定落库；来源与既有 backfill_missing_specs.py 的 GPU_SPECS 一致）
# 智凯100duo / 智铠100 等国产卡 LLM 输出为猜测，未列入，留待人工。
CURATED_SPECS = {
    291: {  # NVIDIA RTX 5090 32G 涡轮
        "Capacity": "32 GB", "tdp": "575 W", "Architecture": "Blackwell",
        "Interface": "PCIe Gen5", "Memory Bandwidth": "1792 GB/s",
        "Cooling": "Active", "Memory Interface": "512-bit", "CUDA Cores": "21760",
    },
    312: {  # NVIDIA L4 24G
        "Capacity": "24 GB", "tdp": "72 W", "Architecture": "Ada Lovelace",
        "Interface": "PCIe Gen4 x16", "Memory Bandwidth": "192 GB/s",
        "Form Factor": "Single-Slot", "Cooling": "Passive",
        "Memory Interface": "192-bit", "CUDA Cores": "7424",
    },
    320: {  # 天数智芯100DUO 单卡64G
        "Capacity": "64 GB",
    },
}

MERGE_PLAN = {
    63: [307],
    74: [271, 292],
    77: [287],
    1: [293],
    56: [301, 288],
    268: [62, 218],
    210: [272],
    304: [97],     # 保留具体料号 WUS721208BLE604，并入通用 8T SATA HDD
    93: [315],
    88: [319],
    87: [283],
    219: [284],
}

# 复用 kp_repo 的确定性解析器（容量/形态/转速/内存等），保证口径一致
from app.repository.kp_repo import (
    _icap, _itype, _imedia, _iform, _igen, _iworkload, _irpm,
    _imem_type, _imem_speed, _imem_dimm, _imem_rank, _imem_ecc,
)

NIC_KNOWN_IF = ("CX", "I350", "X710", "Mellanox", "Mallanox", "英伟达", "Intel")

def _norm_s(v):
    return (v or "").strip()

def _parse_ports(name):
    u = (name or "").upper().replace(" ", "")
    m = re.search(r"(\d+)(?:PORT|口)", u)
    if m:
        return m.group(1)
    if "双口" in name or "DUAL" in u:
        return "2"
    if "四口" in name or "4PORT" in u:
        return "4"
    return None

def _parse_link(name):
    u = (name or "").upper()
    for spd in ("200G", "100G", "40G", "25G", "10G", "1G", "2.5G"):
        if spd in u:
            return spd
    m = re.search(r"(\d+)G\b", u)
    if m:
        return m.group(1) + "G"
    if "千兆" in name:
        return "1G"
    return None

def _parse_iface(name):
    u = (name or "").upper()
    m = re.search(r"(CX\d+|I350|X710|X550|万兆|千兆)", u)
    if m:
        return m.group(1)
    return None

def _nics_desc(name):
    out = {}
    p = _parse_ports(name)
    if p: out["Ports"] = p
    ls = _parse_link(name)
    if ls: out["Link Speed"] = ls
    i = _parse_iface(name)
    if i: out["接口"] = i
    return out

def _raid_desc(name):
    out = {}
    u = (name or "").upper()
    m = re.search(r"(\d+)\s*G(?:\s*CACHE)?", u)
    if m: out["Cache"] = m.group(1) + " GB"
    m = re.search(r"-(\d+)I\b", u)
    if m: out["Ports"] = m.group(1)
    if "SUPERCAP" in u or "超级电容" in name or "电容" in name:
        out["电容"] = "有"
    return out

def _hba_desc(name):
    out = {"Ports": "8"} if re.search(r"-8i", (name or "")) else {}
    out.setdefault("接口", "SAS")
    return out

def _cpu_desc(name):
    out = {}
    m = re.search(r"(\d+)C\s*/\s*(\d+)T", (name or "").upper())
    if m: out["Cores"] = m.group(1)
    m = re.search(r"([\d.]+)\s*GHz", (name or ""))
    if m: out["Base Clock"] = m.group(1) + " GHz"
    return out

def parse_specs_deterministic(cat, name):
    """分类 -> 确定性 spec dict（空 {} 表示无法从名称可靠解析，需 LLM/人工）。"""
    cat = _norm_s(cat)
    low = cat.lower()
    if "hdd" in low or "ssd" in low or "storage" in low:
        out = {}
        cap = _icap(name)
        if cap: out["Capacity"] = cap
        typ = _itype(name)
        if typ: out["Type"] = typ
        med = _imedia(name)
        if med: out["Media"] = med
        ff = _iform(name)
        if not ff:
            if typ == "NVMe": ff = "U.2"
            elif med == "SSD": ff = '2.5"'
            elif med == "HDD": ff = '3.5"'
        if ff: out["Form Factor"] = ff
        rpm = _irpm(name)
        if rpm: out["RPM"] = rpm
        gen = _igen(name)
        if gen: out["gen"] = gen
        wl = _iworkload(name)
        if wl: out["workload"] = wl
        m = re.search(r"DWPD\s*\*?\s*(\d+)", (name or "").upper())
        if m: out["DWPD"] = m.group(1)
        return out
    if "memory" in low or "ram" in low:
        out = {}
        for k, f in [("Capacity", _icap), ("Type", _imem_type), ("Speed", _imem_speed),
                     ("DIMM Type", _imem_dimm), ("Rank", _imem_rank), ("ECC", _imem_ecc)]:
            v = f(name)
            if v: out[k] = v
        if "Speed" not in out:
            m = re.search(r"(\d{4})", name)
            if m and (m.group(1).startswith(("4", "5", "6"))):
                out["Speed"] = m.group(1) + " MT/s"
        if not out.get("Type") and out.get("Speed", "").startswith(("5", "6")):
            out["Type"] = "DDR5"
        return out
    if "nic" in low or "network" in low or "网卡" in name:
        return _nics_desc(name)
    if "raid" in low or "raid" in name.lower():
        return _raid_desc(name)
    if "hba" in low:
        return _hba_desc(name)
    if "cpu" in low or "processor" in low:
        return _cpu_desc(name)
    return {}

CAT_ALLOWED_KEYS = {
    "CPU": ["Cores", "Base Clock", "Boost Clock", "tdp", "Socket", "L3 Cache", "Architecture", "Memory Support"],
    "GPU": ["Capacity", "tdp", "Architecture", "Interface", "Memory Bandwidth", "Form Factor",
            "Cooling", "Memory Interface", "CUDA Cores", "Boost Clock", "MSRP", "Compute Units"],
    "GPU card": ["Capacity", "tdp", "Architecture", "Interface", "Memory Bandwidth", "Form Factor",
                 "Cooling", "Memory Interface", "CUDA Cores", "Boost Clock", "MSRP", "Compute Units"],
    "GPU Card": ["Capacity", "tdp", "Architecture", "Interface", "Memory Bandwidth", "Form Factor",
                 "Cooling", "Memory Interface", "CUDA Cores", "Boost Clock", "MSRP", "Compute Units"],
    "HDD/SSD": ["Capacity", "Type", "Media", "Form Factor", "RPM", "gen", "workload", "DWPD"],
    "Memory": ["Capacity", "Type", "Speed", "DIMM Type", "Rank", "ECC"],
    "Network(NIC) requirement": ["Ports", "Link Speed", "接口"],
    "NIC card": ["Ports", "Link Speed", "接口"],
    "Raid card": ["Ports", "Cache", "电容"],
    "Raid Card": ["Ports", "Cache", "电容"],
    "RAID": ["Ports", "Cache", "电容"],
    "RAID Card": ["Ports", "Cache", "电容"],
    "HBA": ["Ports", "接口", "Link Speed"],
}

def _llm_config():
    from app.services.llm_client import _get_llm_config
    cfg = _get_llm_config()
    return cfg

def llm_specs(cat, name, brand):
    cfg = _llm_config()
    if not (cfg.get("api_key") and cfg.get("model")):
        return {}
    allowed = CAT_ALLOWED_KEYS.get(cat, []) or []
    sys_prompt = (
        "你是服务器配件产品规格专家。根据给定的配件名称和品类，输出该配件的真实规格参数。"
        "只输出一个 JSON 对象，键取自允许列表。只填你确定的值，不确定的字段不要出现。"
        "不要编造型号、容量或接口。若整体无法确认，输出空对象 {}。"
        "允许的键（仅这些）：" + ", ".join(allowed) + "。"
        "规格值请带单位（如 32 GB、4800 MT/s、PCIe Gen5、2-Slot、Active）。"
    )
    user_prompt = f"品类: {cat}\n品牌: {brand or '未知'}\n配件名称: {name}\n请输出规格 JSON。"
    try:
        from openai import OpenAI
        client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"], timeout=40, max_retries=1)
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "system", "content": sys_prompt},
                      {"role": "user", "content": user_prompt}],
            temperature=0.1,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        content = (resp.choices[0].message.content or "").strip()
        data = json.loads(content) if content else {}
        if not isinstance(data, dict):
            return {}
        return {k: ("" if v is None else str(v)) for k, v in data.items() if v not in (None, "",)}
    except Exception as e:
        print("  [LLM error] %s -> %s" % (name, str(e)[:160]))
        return {}

def _safe_set(obj, key, val):
    if not getattr(obj, key, None) and val:
        setattr(obj, key, val)

def set_part_specs(part, specs):
    """全量替换某件 specs（specs: dict key->value）。"""
    if not specs:
        return
    part.specs.clear()
    for i, (k, v) in enumerate(specs.items()):
        part.specs.append(KPPartSpec(part_id=part.id, spec_key=k, spec_value=v, sort_order=i))
    part.updated_at = datetime.utcnow()

def merge_part(repo, keep_id, drop_id):
    """把 drop_id 并入 keep_id：迁移价格/兼容/关联/specs，删除 drop。返回统计。

    注意：KPPart.price_history 等关系带 cascade=all, delete-orphan，
    直接把子行 part_id 改到 keep 后 delete(drop) 仍会被级联删掉。
    因此先 flush 落库部分，再 expire 所有 ORM 对象，重新加载 drop 的后代集合，
    使其在 DB 中已不属于 drop，delete 才不会误删历史价。
    """
    s = repo.session
    stat = {"price": 0, "compat": 0, "related": 0, "spec_added": 0}
    keep = s.query(KPPart).get(keep_id)
    drop = s.query(KPPart).get(drop_id)
    if not keep or not drop:
        return stat

    # 1) 历史价格全部迁移（bulk update，随后 expire 重载，不被级联删）
    n_price = s.query(KPPriceHistory).filter(KPPriceHistory.part_id == drop_id)        .update({"part_id": keep_id}, synchronize_session=False)
    stat["price"] = n_price

    # 2) 兼容机型迁移（去重）
    existing_compat = {c.server_model for c in keep.compat_servers}
    for c in s.query(KPPartCompat).filter(KPPartCompat.part_id == drop_id).all():
        if c.server_model in existing_compat:
            continue
        c.part_id = keep_id
        existing_compat.add(c.server_model)
        stat["compat"] += 1

    # 3) 关联件迁移（source/target 双向，去重）
    rel = s.query(KPPartRelated).filter(
        (KPPartRelated.source_part_id == drop_id) | (KPPartRelated.target_part_id == drop_id)).all()
    keep_rel = {(r.source_part_id, r.target_part_id) for r in s.query(KPPartRelated)
                .filter(KPPartRelated.source_part_id == keep_id).all()}
    for r in rel:
        if r.source_part_id == drop_id:
            r.source_part_id = keep_id
        if r.target_part_id == drop_id:
            r.target_part_id = keep_id
        if (r.source_part_id, r.target_part_id) in keep_rel:
            continue
        keep_rel.add((r.source_part_id, r.target_part_id))
        stat["related"] += 1

    # 4) 规格合并：保留件已有键优先；drop 独有键补进保留件
    keep_spec_map = {sp.spec_key: sp for sp in keep.specs}
    for sp in list(drop.specs):
        key = sp.spec_key
        if key in keep_spec_map:
            continue  # 保留件 wins
        keep.specs.append(KPPartSpec(part_id=keep_id, spec_key=key, spec_value=sp.spec_value,
                                     sort_order=len(keep.specs)))
        keep_spec_map[key] = sp
        stat["spec_added"] += 1

    # 5) 元信息补全（保留件缺才补）
    _safe_set(keep, "oem_sku", drop.oem_sku)
    _safe_set(keep, "alt_sku", drop.alt_sku)
    _safe_set(keep, "brand", drop.brand)
    _safe_set(keep, "short_desc", drop.short_desc)
    _safe_set(keep, "full_desc", drop.full_desc)
    keep.updated_at = datetime.utcnow()

    # 6) flush + expire：让 drop 的关系集合按 DB 最新状态重载（后代已不在 drop 下）
    s.flush()
    s.expire_all()
    drop2 = s.query(KPPart).get(drop_id)
    if drop2:
        s.delete(drop2)
    return stat

LLM_SKIP_IDS = {183, 184}  # 智凯/智铠 等国产卡 LLM 结果为猜测，不落库，留人工

def _cat_needs_llm(cat):
    low = (cat or "").lower()
    if any(k in low for k in ("gpu", "cpu", "bridge", "nvswitch", "nvswitch board")):
        return True
    # 含"缓存/电池/支架/WD/料号"等需判别；保守：让 LLM/deterministic 都能尝试
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="实际写库（默认 dry-run）")
    ap.add_argument("--llm", action="store_true", help="对确定性解析不出规格的外部件调用 LLM")
    args = ap.parse_args()

    repo = KPRepository()
    s = repo.session
    mode = "COMMIT 写库" if args.commit else "DRY-RUN（不写库）"
    print("===", mode, "===")

    total_merge_stats = {"price": 0, "compat": 0, "related": 0, "spec_added": 0}
    merged = 0

    # ---------- 1) 合并去重 ----------
    for keep_id, drop_ids in MERGE_PLAN.items():
        keep = s.query(KPPart).get(keep_id)
        if not keep:
            print("[跳过] 保留件不存在 id=%s" % keep_id); continue
        drops = [s.query(KPPart).get(d) for d in drop_ids if s.query(KPPart).get(d)]
        ph_keep = s.query(KPPriceHistory).filter(KPPriceHistory.part_id == keep_id).count()
        print("合并: 保留 id=%s %r | 并入 %s" % (keep_id, keep.name, [d.id for d in drops]))
        for d in drops:
            ph_d = s.query(KPPriceHistory).filter(KPPriceHistory.part_id == d.id).count()
            print("   <- id=%s %r (price=%s) -> 历史价迁移到 id=%s" % (d.id, d.name, ph_d, keep_id))
        if args.commit:
            for d in drops:
                st = merge_part(repo, keep_id, d.id)
                for k, v in st.items():
                    total_merge_stats[k] += v
                merged += 1

    # ---------- 2) 缺参回填（合并后仍无 specs 的件） ----------
    # 未知品类给 LLM 一个通用允许键集
    LLM_GENERIC = ["Model", "接口", "Capacity", "tdp", "Architecture", "Form Factor"]
    no_spec_ids = {row[0] for row in s.query(KPPart.id)
                   .outerjoin(KPPartSpec, KPPartSpec.part_id == KPPart.id)
                   .filter(KPPartSpec.id.is_(None)).all()}
    drop_set = {d for ids in MERGE_PLAN.values() for d in ids}
    exclude_set = drop_set | set(MERGE_PLAN.keys())
    no_spec_ids = {i for i in no_spec_ids if i not in exclude_set}
    targets = [s.query(KPPart).get(i) for i in sorted(no_spec_ids) if s.query(KPPart).get(i)]
    print("\n需回填（合并后仍 0 规格）: %s 件" % len(targets))

    backfilled = 0
    pending = []
    for p in targets:
        cat = p.category.name if p.category else "?"
        det = parse_specs_deterministic(cat, p.name)
        src = None
        specs = det
        if det:
            src = "name-parse"
        elif p.id in CURATED_SPECS:
            specs = dict(CURATED_SPECS[p.id])
            src = "curated"
        elif args.llm:
            if cat not in CAT_ALLOWED_KEYS:
                CAT_ALLOWED_KEYS[cat] = LLM_GENERIC
            specs = llm_specs(cat, p.name, p.brand)
            if specs and p.id in LLM_SKIP_IDS:
                specs = {}
            if specs:
                src = "LLM"
        status = "OK(%s,%s条)" % (src, len(specs)) if specs else "待人工"
        print("   id=%s [%s] %s -> %s (%s)" % (p.id, cat, p.name, specs, status))
        if specs:
            if args.commit:
                part = s.query(KPPart).get(p.id)
                set_part_specs(part, specs)
            backfilled += 1
        else:
            pending.append((p.id, cat, p.name))

    # ---------- 3) 汇总 ----------
    if args.commit:
        s.commit()
        print("\n[已写库] 合并件数=%s" % merged)
        print("[已写库] 迁移价格=%s 兼容=%s 关联=%s 规格补充=%s" % (
            total_merge_stats["price"], total_merge_stats["compat"],
            total_merge_stats["related"], total_merge_stats["spec_added"]))
        print("[已写库] 回填规格=%s 件" % backfilled)
    else:
        print("\n[dry-run] 需回填=%s 件，其中待人工=%s 件" % (len(targets), len(pending)))
        if pending:
            print("[dry-run] 待人工清单（加 --llm 可联网查证）：")
            for pid, c, n in pending:
                print("   id=%s [%s] %s" % (pid, c, n))
    repo.close()

def _parse_ports(name):
    u = (name or "").upper()
    m = re.search(r"(\d+)\s*(?:PORT|口)", u)
    if m:
        return m.group(1)
    if "双口" in name or "DUAL" in u:
        return "2"
    if "四口" in name or "4PORT" in u:
        return "4"
    return None

def _parse_iface(name):
    u = (name or "").upper()
    m = re.search(r"(CX\d+|I350|X710|X550|X540|82599)", u)
    if m:
        return m.group(1)
    return None

def _raid_desc(name):
    out = {}
    u = (name or "").upper()
    for ch in ("\u2010","\u2011","\u2012","\u2013","\u2014","\u2212"):
        u = u.replace(ch, "-")
    m = re.search(r"(\d+)\s*G(?:\s*CACHE)?", u)
    if m:
        out["Cache"] = m.group(1) + " GB"
    m = re.search(r"-(\d+)I\b", u)
    if m:
        out["Ports"] = m.group(1)
    if "SUPERCAP" in u or "超级电容" in name or "电容" in name:
        out["电容"] = "有"
    return out

if __name__ == "__main__":
    main()




