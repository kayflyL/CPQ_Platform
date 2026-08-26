# -*- coding: utf-8 -*-
"""LLM 抽取增强 —— 需求理解/选型节点共用的 LLM 增强实现（schema 收口 + 规则兜底）。

设计铁律（reasoning_executor._dispatch 的 llm 节点注释）：
  • LLM 输出绝不裸进 match_kp/compose（碰料号/价格/兼容必须 100% 确定性）；
  • 只以 schema 校验过的结果喂回 ext，规则始终兜底；
  • 任何失败（网络/超时/解析/schema）→ 静默降级，ctx 不变，不阻塞主流程。

本模块职责：
  1) 把「需求原文 + 规则抽取摘要」拼成 prompt（build_messages）；
  2) 提供 EXTRACT_ENHANCE_SCHEMA 供理解节点填表；
  3) merge_into_ext() 确定性合并：只补缺、规则赢、能力声明不当作实际配置。

典型收益（对齐训练轮次）：
  • R6 型号歧义：`2* AMD EPYC™ 9254 24 2.9 GHz 128 MB 200W` → 结构化
    cpu{model/cores/tdp_w/qty}，规则只抽到 9254 关键词 + duality；
  • R7 典型报价单（能力规格）：补 memory{type/speed}、form、确认 9004/9005 系列
    —— 但「支持12个盘/8个GPU」这类能力声明绝不产盘/GPU 条目（R7 教训）；
  • 规则词表够不到的措辞（如"傲腾缓存盘"）补出盘组，HDD/SSD 品类自动补位。
"""
import logging
import re
from typing import Optional

from app.services.slot_contract import canonical_get, canonical_set

logger = logging.getLogger(__name__)

# ── 槽位 schema（canonical slots）──────────────────────────────────────
# 与规则 ext 结构不同：这是给 LLM 看的"人能读的槽位"，merge 时再确定性翻译成
# ext 的 drive_groups/gpu_groups/mem_signal… 结构。interface 里的 U.2/U.3 在
# merge 归一为 NVMe；drives.capacity 是原文容量写法（"960G"/"7.68T"），
# capacity_gb 是可选数字（GB），merge 优先取 capacity。
EXTRACT_ENHANCE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "cpu": {"type": "object", "properties": {
            "model": {"type": "string"},
            "cores": {"type": "integer"},
            "tdp_w": {"type": "integer"},
            "qty": {"type": "integer"},
        }},
        "memory": {"type": "object", "properties": {
            "per_stick_gb": {"type": "integer"},
            "qty": {"type": "integer"},
            "type": {"type": "string", "enum": ["DDR4", "DDR5"]},
            "speed_mt": {"type": "integer"},
            "comparison": {"type": "string", "enum": ["gte", "lte"]},
            "total_gb": {"type": "integer"},   # 需求只给总容量（如 256GB DDR5-4800）时填，单条/条数交给配件规划拆
        }},
        "drives": {"type": "array", "items": {"type": "object", "properties": {
            "capacity": {"type": "string"},
            "capacity_gb": {"type": "integer"},
            "interface": {"type": "string", "enum": ["SATA", "SAS", "NVMe", "U.2", "U.3"]},
            "qty": {"type": "integer"},
            "comparison": {"type": "string", "enum": ["gte", "lte"]},
        }}},
        "gpu": {"type": "array", "items": {"type": "object", "properties": {
            "model": {"type": "string"},
            "qty": {"type": "integer"},
            "capacity_gb": {"type": "integer"},
            "comparison": {"type": "string", "enum": ["gte", "lte"]},
        }}},
        "nic": {"type": "array", "items": {"type": "object", "properties": {
            "model": {"type": "string"},
            "speed_g": {"type": "integer"},
            "ports": {"type": "integer"},
            "qty": {"type": "integer"},
            "with_optical_module": {"type": "boolean"},
        }}},
        "psu": {"type": "object", "properties": {
            "wattage": {"type": "integer"},
            "qty": {"type": "integer"},
        }},
        "raid": {"type": "array", "items": {"type": "object", "properties": {
            "model": {"type": "string"},
            "qty": {"type": "integer"},
            "cache": {"type": ["string", "integer", "null"]},
            "raid_levels": {"type": "array", "items": {"type": "string"},
                            "description": "只写 RAID 级别、未写型号时填，如 [\"0\",\"1\",\"10\"]；写了型号则留空"},
        }}},
        "purchase_qty": {"type": "integer", "description": "整机采购台数（如 2 台、10 台；未明确写则缺省 1）"},
        "form": {"type": "string"},
        "series": {"type": "string"},
        "server_type": {"type": "string", "description": "服务器类型（从在售类型清单选一个规范类型名，未明确则留空）"},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
}

# ── 确定性翻译工具（merge 用，全部可单测）──────────────────────────────

_MODEL_TOKEN_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z.\-]{1,}")
_CAPACITY_TOK_RE = re.compile(r"^\d+(?:\.\d+)?[GT]B?$", re.I)


def _model_tokens_of(model: str) -> list:
    """从完整型号字符串里提取「像型号的 token」（含数字、非容量碎片）。

    "NVIDIA RTX PRO 4500 Server 32G" → ["4500"]；"LSI 9560-8i" → ["9560-8i"]。
    容量碎片（32G/960G/7.68T）不是型号 token，过滤掉（R6 教训：32G 不能当型号）。
    """
    out: list = []
    for m in _MODEL_TOKEN_RE.finditer(model or ""):
        t = m.group()
        if not re.search(r"\d", t) or len(t) < 3:
            continue
        if _CAPACITY_TOK_RE.match(t):
            continue
        if t.lower() not in (x.lower() for x in out):
            out.append(t)
    return out


def _term_from_capacity(capacity: Optional[str], capacity_gb: Optional[int]) -> Optional[str]:
    """容量 → 盘组 term（AI-first 契约，2026-08）：
    - 优先用 LLM 归一好的 capacity_gb（数值 GB，AI 理解自然语言：1T以上/一tb/1tb/960G → 数值），
      下游选件按「容量≥需求的最小件」匹配——AI 路不靠约束词正则；
    - capacity_gb 缺失/离谱才回退解析 capacity 原文（只认纯容量串，比较词不猜——那是 AI 的职责）；
    - 只有数字 GB → "NG"。"""
    if capacity_gb is not None and 1 <= int(capacity_gb) <= 65536:
        return f"{int(capacity_gb)}G"
    if capacity:
        m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([GT])(?:B)?\s*$", str(capacity), re.I)
        if m:
            return f"{m.group(1)}{m.group(2).upper()}"
    return None


def _interface_norm(kind: Optional[str]) -> Optional[str]:
    """接口归一：U.2/U.3 → NVMe；SATA/SAS 原样；未知 → None（不臆断接口）。"""
    k = (kind or "").strip().lower().replace(".", "")
    if k in ("u2", "u3", "nvme", "nvmessd", "nvmes"):
        return "NVMe"
    if k == "sata":
        return "SATA"
    if k == "sas":
        return "SAS"
    return None


# 盘「实际配置 vs 能力声明」判定（merge 的确定性闸门，R7 教训）：
#   • 强信号（N*容量 / 容量*N）→ 一定是实际配置（R6 "1* 960G NMVE"、R2 "2* 480GB"）；
#   • 文本含能力词（支持/最多/最大/可…盘位）→ 一律不当实际配置（R7 "支持12个3.5英寸硬盘"、
#     R4 "12/24 bays HDDSupport"）；
#   • 其余靠「配/装/需/含 N 块…盘」或「硬盘：…容量」字段行兜底。
_DRIVE_STRONG_RE = re.compile(
    r"\d+\s*[*×]\s*\d+(?:\.\d+)?\s*[GT]|\d+(?:\.\d+)?\s*[GT]\s*[*×]\s*\d+", re.I)
_DRIVE_CAPABILITY_RE = re.compile(
    r"支持\s*\d|最多\s*\d|最大\s*\d|可\s*(?:支持|扩展|扩)?\s*\d|\d+\s*(?:个|块)?\s*(?:盘位|插槽|bays?)",
    re.I)
_DRIVE_CONFIG_RE = re.compile(
    r"(?:配|装|用|需要|需|含)\s*\d+\s*(?:块|个|片|颗)?\s*(?:[^\n，。]{0,15}?)(?:ssd|hdd|盘|nvme|sata|sas)",
    re.I)
_DRIVE_FIELD_RE = re.compile(
    r"(?:硬盘|磁盘|存储|ssd|hdd)\s*[:：][^\n，。]{0,20}\d+(?:\.\d+)?\s*[GT]", re.I)
_GPU_CAPABILITY_RE = re.compile(
    r"(?:支持|最多|最大|可(?:支持|扩展|扩)?)\s*\d+\s*(?:个|张|块)?\s*(?:GPU|卡)", re.I)


def _has_drive_config_signal(text: str) -> bool:
    """需求文本是否在描述「实际盘配置」（而非机箱盘位能力）。"""
    low = (text or "")
    if _DRIVE_STRONG_RE.search(low):
        return True
    if _DRIVE_CAPABILITY_RE.search(low):
        return False
    return bool(_DRIVE_CONFIG_RE.search(low) or _DRIVE_FIELD_RE.search(low))


# ── 确定性合并：只补缺、规则赢 ─────────────────────────────────────────

def merge_into_ext(ext: dict, cleaned: dict, requirement_text: str = "",
                   catalog: Optional[dict] = None) -> list:
    """把 schema 收口后的 LLM 槽位确定性合并进 ext（就地修改）。

    规则赢：已存在的字段/组绝不覆盖，只补缺；能力声明不当配置。
    catalog：可选的目录白名单上下文（build_catalog_context 产出），提供时用于 server_type/系列
    锚定校验（agent 主理解路传入；增强路不传则 series 仍走 _load_series_values）。
    返回变更说明列表（step_done payload / 日志用）。
    """
    if not cleaned:
        return []
    changes: list = []
    categories = ext.get("categories")
    if categories is None:
        categories = []
        ext["categories"] = categories

    def _add_cat(cat: str) -> None:
        if cat not in categories:
            categories.append(cat)

    # ── 形态：仅当规则没抽到，且 LLM 值合规 ──
    form = (cleaned.get("form") or "").strip().upper()
    if form and not ext.get("form") and re.match(r"^[1-8]U$", form):
        ext["form"] = form
        changes.append(f"form={form}")

    # ── 系列：仅当命中平台系列白名单（避免 "9004/9005" 这种 CPU 系列号误当机型系列路由）──
    series = (cleaned.get("series") or "").strip()
    if series and not ext.get("series"):
        from app.services.requirement_intel_service import _load_series_values
        known = [str(s).lower() for s in _load_series_values()]
        if series.lower() in known:
            ext["series"] = series
            changes.append(f"series={series}")
        else:
            changes.append(f"series 跳过(非平台系列): {series}")

    # ── 服务器类型：catalog 锚定（命中在售类型白名单才写 server_type_name/usage，防 LLM 编造类型）──
    stype = (cleaned.get("server_type") or "").strip()
    if stype and not canonical_get(ext, "server_type"):
        known_types = [str(t).lower() for t in ((catalog or {}).get("server_types") or []) if t]
        hit = stype.lower() in known_types or \
            any(stype.lower() in t or t in stype.lower() for t in known_types)
        if hit:
            canonical_set(ext, "server_type", stype)
            changes.append(f"server_type={stype}")
        else:
            changes.append(f"server_type 跳过(不在在售白名单): {stype}")

    # ── 整机采购台数：只补缺，且不要和内存条数/盘数混淆（由 schema 单独字段收口）──
    purchase_qty = cleaned.get("purchase_qty")
    if purchase_qty and 1 <= int(purchase_qty) <= 10000:
        if not ext.get("purchase_qty"):
            ext["purchase_qty"] = int(purchase_qty)
            changes.append(f"purchase_qty={purchase_qty}")

    # ── CPU：单真值源 cpu_signal（duality/qty/cores/tdp_w/model）。
    #    不再双写 qty_map.CPU，也不再额外塞 CPU 型号 keywords；pick 阶段按 cpu_signal 推导。──
    cpu = cleaned.get("cpu") or {}
    if cpu:
        _add_cat("CPU")
        sig = dict(ext.get("cpu_signal") or {})
        qty = cpu.get("qty")
        if qty and 1 <= int(qty) <= 64:
            sig["qty"] = int(qty)
            if int(qty) >= 2:
                sig.setdefault("duality", True)
                changes.append(f"cpu.qty={qty}")
            elif not (sig.get("duality") is True):
                changes.append(f"cpu.qty={qty}")
        cores = cpu.get("cores")
        if cores and 1 <= int(cores) <= 512:
            sig.setdefault("cores", int(cores))
            changes.append(f"cpu.cores={cores}")
        tdp = cpu.get("tdp_w")
        if tdp and 50 <= int(tdp) <= 600:
            sig.setdefault("tdp_w", int(tdp))
            changes.append(f"cpu.tdp_w={tdp}")
        model = (cpu.get("model") or "").strip()
        if model:
            sig.setdefault("model", model)
            changes.append(f"cpu.model={model}")
        if sig:
            ext["cpu_signal"] = sig

    # ── 内存：单真值源 mem_signal（type/speed/total_gb/per_stick_gb/qty）。
    #    不再双写 mem_groups；下游需要分组时由 _mem_groups_from_signal 确定性派生。──
    mem = cleaned.get("memory") or {}
    if mem:
        _add_cat("Memory")
        sig = dict(ext.get("mem_signal") or {})
        mtype = mem.get("type")
        if mtype and not sig.get("type"):
            sig["type"] = mtype
            changes.append(f"mem.type={mtype}")
        speed = mem.get("speed_mt")
        if speed and 800 <= int(speed) <= 10000 and not sig.get("speed"):
            sig["speed"] = int(speed)
            changes.append(f"mem.speed={speed}")
        per = mem.get("per_stick_gb")
        mqty = mem.get("qty")
        total = mem.get("total_gb")
        if per and 4 <= int(per) <= 1024:
            if not sig.get("per_stick_gb"):
                sig["per_stick_gb"] = int(per)
            if mqty and 1 <= int(mqty) <= 64:
                sig["qty"] = int(mqty)
                if not sig.get("total_gb"):
                    sig["total_gb"] = int(per) * int(mqty)
                    changes.append(f"mem.total_gb={sig['total_gb']}")
            # 单条 + 总量都给了但没条数 → 反推条数（32G×? = 256G → 8）
            if total and 128 <= int(total) <= 32768 and mqty is None:
                _q = int(total) // int(per)
                if 1 <= _q <= 64 and _q * int(per) == int(total):
                    mqty = _q
                    sig["qty"] = int(mqty)
        elif total and 128 <= int(total) <= 32768:
            # 只给总量：保留 mem_signal.total_gb，条数由配件规划（kp LLM 提议）按通道拆
            sig["total_gb"] = int(total)
            changes.append(f"mem.total_gb={int(total)}")
        if mem.get("comparison") in ("gte", "lte"):
            sig["comparison"] = mem["comparison"]
        if sig:
            ext["mem_signal"] = sig

    # ── 盘：仅当文本含显式能力声明（支持/最多/最大 N 盘位）且无强配置信号时跳过（R7：能力≠配置）；
    # 否则信任 LLM 已按 prompt 过滤能力声明。"2块960G SSD 系统盘" 无能力词，是实际配置，应进 drive_groups
    # （旧 _has_drive_config_signal 对无"配/装/需"前缀的格式误判为非配置，丢盘——已弃用该文本 guard）。
    _text = requirement_text or ""
    _cap_only = bool(_DRIVE_CAPABILITY_RE.search(_text)) and not bool(_DRIVE_STRONG_RE.search(_text))
    if _cap_only and cleaned.get("drives"):
        changes.append("drives 跳过：需求为能力声明/盘位描述，非实际盘配置")
    else:
        existing = [(g.get("term"), g.get("kind")) for g in (ext.get("drive_groups") or [])]
        for d in (cleaned.get("drives") or [])[:16]:
            term = _term_from_capacity(d.get("capacity"), d.get("capacity_gb"))
            kind = _interface_norm(d.get("interface"))
            qty = d.get("qty")
            if not term:
                continue
            if qty is not None and not (1 <= int(qty) <= 64):
                continue
            if (term, kind) in existing:
                continue
            _dg = {"term": term, "qty": int(qty or 1), "kind": kind}
            if d.get("comparison") in ("gte", "lte"):
                _dg["comparison"] = d["comparison"]
            ext.setdefault("drive_groups", []).append(_dg)
            existing.append((term, kind))
            changes.append(f"drive_groups+{term}×{qty or 1} {kind or ''}".strip())
            _add_cat("HDD/SSD")

    # ── GPU：无具体型号（能力声明）不产组；已有组含同型号 token → 仅前置完整型号
    #    （更精确匹配，R6：token "4500" 曾命中备注含 4500 的智铠100）──
    ggroups = ext.get("gpu_groups")
    if ggroups is None:
        ggroups = []
        ext["gpu_groups"] = ggroups
    for g in (cleaned.get("gpu") or [])[:8]:
        model = (g.get("model") or "").strip()
        qty = g.get("qty")
        cap = g.get("capacity_gb")
        cmpv = g.get("comparison")
        brand_tokens = re.findall(r"[\u4e00-\u9fff]{2,}", model or "")
        if not model and cap is None and qty is None:
            continue
        if qty is not None and not (1 <= int(qty) <= 64):
            continue
        toks = _model_tokens_of(model) if model else []
        if model and not toks:
            continue
        if toks:
            hit = next((gg for gg in ggroups if any(t in (gg.get("tokens") or []) for t in toks)), None)
            if hit:
                hit_tokens = list(hit.get("tokens") or [])
                for _t in brand_tokens + [model] + toks:
                    if _t not in hit_tokens:
                        hit_tokens.insert(0, _t)
                hit["tokens"] = hit_tokens
                changes.append(f"gpu_groups[{model}] 前置精确型号")
                continue
            _gg = {"tokens": brand_tokens + [model] + toks, "qty": int(qty or 1)}
            if cap is not None and 1 <= int(cap) <= 512:
                _gg["cap"] = int(cap)
                if cmpv in ("gte", "lte"):
                    _gg["comparison"] = cmpv
            ggroups.append(_gg)
            changes.append(f"gpu_groups+{model}×{qty or 1}")
        elif cap is not None and 1 <= int(cap) <= 512:
            # 纯显存需求（无型号）："48G以上显存" → 只带 cap + comparison，无 tokens
            _gg = {"tokens": [], "qty": int(qty or 1), "cap": int(cap)}
            if cmpv in ("gte", "lte"):
                _gg["comparison"] = cmpv
            ggroups.append(_gg)
            changes.append(f"gpu_groups+显存{cap}G×{qty or 1}")
        else:
            # 仅给数量、无型号无显存（如“4张GPU卡，型号你推荐”）：
            # 卡数本身也是需求事实，必须落 gpu_groups 供下游唯一真值源读取。
            if _GPU_CAPABILITY_RE.search(requirement_text or ""):
                continue
            _gg = {"tokens": [], "qty": int(qty or 1)}
            ggroups.append(_gg)
            changes.append(f"gpu_groups+数量×{qty or 1}")
        _add_cat("GPU")

    # ── 网卡：仅当规则没抽到任何网卡行时按 LLM 槽位补行 ──
    nics = (cleaned.get("nic") or [])[:8]
    msf = ext.get("multi_spec_filters")
    if nics and not (msf or {}).get("Network(NIC) requirement"):
        lines: list = []
        for n in nics:
            line: dict = {}
            filters = []
            speed = n.get("speed_g")
            if speed and 1 <= int(speed) <= 400:
                filters.append({"spec_key": "Link Speed", "op": "=", "value": f"{int(speed)}G"})
            ports = n.get("ports")
            if ports and 1 <= int(ports) <= 64:
                filters.append({"spec_key": "Ports", "op": "=", "value": str(int(ports))})
            if filters:
                line["filters"] = filters
            name_terms = _model_tokens_of(n.get("model") or "")
            if n.get("with_optical_module"):
                name_terms.append("光模块")
            if name_terms:
                line["name_contains"] = name_terms
            q = n.get("qty")
            if q and 1 <= int(q) <= 64:
                line["qty"] = int(q)
            if line:
                lines.append(line)
        if lines:
            if msf is None:
                msf = {}
                ext["multi_spec_filters"] = msf
            msf["Network(NIC) requirement"] = lines
            changes.append(f"multi_spec_filters[NIC]+{len(lines)} 行")
            _add_cat("Network(NIC) requirement")

    # ── 电源：规则没抽到才整条补；已抽到只补缺 qty ──
    psu = cleaned.get("psu") or {}
    psu_sig = ext.get("psu_signal")
    w = psu.get("wattage")
    q = psu.get("qty")
    if not psu_sig and w and 200 <= int(w) <= 3000:
        sig = {"wattage": int(w)}
        if q and 1 <= int(q) <= 8:
            sig["qty"] = int(q)
        ext["psu_signal"] = sig
        changes.append(f"psu_signal+{w}W×{q or '?'}")
    elif psu_sig and q and not psu_sig.get("qty") and 1 <= int(q) <= 8:
        psu_sig["qty"] = int(q)
        changes.append(f"psu.qty={q}")

    # ── 阵列卡：补型号 token 进 keywords（无专属 group 机制，靠 stage-1 精确匹配）──
    # 兼容单对象与数组：多张 RAID 卡（如 9560 + 9364）分别进入 raid_groups，不覆盖第一张。
    raid_raw = cleaned.get("raid") or {}
    raid_items = raid_raw if isinstance(raid_raw, list) else ([raid_raw] if isinstance(raid_raw, dict) else [])
    for raid in raid_items:
        if not isinstance(raid, dict):
            continue
        raid_model = (raid.get("model") or "").strip()
        raid_levels = [str(x).strip() for x in (raid.get("raid_levels") or []) if str(x).strip()]
        raid_qty = int(raid.get("qty") or 1)
        _rg = ext.get("raid_groups")
        if _rg is None:
            _rg = []
            ext["raid_groups"] = _rg
        if not raid_model and not raid_levels:
            continue
        if raid_model:
            toks = _model_tokens_of(raid_model)
            keywords = ext.get("keywords")
            if keywords is None:
                keywords = []
                ext["keywords"] = keywords
            for t in toks:
                if t not in keywords:
                    keywords.append(t)
                    changes.append(f"keywords+{t}")
            if not any((g or {}).get("model") == raid_model for g in _rg):
                _rg.append({"model": raid_model, "qty": raid_qty, "cache": raid.get("cache")})
                changes.append(f"raid_groups+{raid_model}×{raid_qty}")
        else:
            # 只写 RAID 级别未写型号（如 RAID 0,1,10）：不臆造型号，保留级别信号，下游按兼容机型选件。
            if not any((g or {}).get("raid_levels") for g in _rg):
                _rg.append({"raid_levels": raid_levels, "qty": raid_qty})
                changes.append(f"raid_groups+RAID {'/'.join(raid_levels)}×{raid_qty}")
        _add_cat("Raid card")

    notes = cleaned.get("notes") or []
    if notes:
        ext["llm_notes"] = list(notes)[:10]

    # 透明记录：LLM 主张的槽位（含被 merge 拒绝的，如能力声明盘/非平台系列），便于排查
    ext["llm_enhanced"] = {
        k: cleaned.get(k) for k in ("cpu", "memory", "drives", "gpu", "nic", "psu", "raid",
                                    "form", "series")
        if cleaned.get(k) is not None
    }
    return changes
