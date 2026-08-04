# -*- coding: utf-8 -*-
"""LLM 抽取增强 —— extract 节点 enable_llm 的增强实现（schema 收口 + 规则兜底）。

设计铁律（reasoning_executor._dispatch 的 llm 节点注释）：
  • LLM 输出绝不裸进 match_kp/compose（碰料号/价格/兼容必须 100% 确定性）；
  • 只以 schema 校验过的结果喂回 ext，规则始终兜底；
  • 任何失败（网络/超时/解析/schema）→ 静默降级，ctx 不变，不阻塞主流程。

本模块职责：
  1) 把「需求原文 + 规则抽取摘要」拼成 prompt（build_messages）；
  2) 调 llm_client.chat_json()（JSON mode + schema 收口）；
  3) merge_into_ext() 确定性合并：只补缺、规则赢、能力声明不当作实际配置。

典型收益（对齐训练轮次）：
  • R6 型号歧义：`2* AMD EPYC™ 9254 24 2.9 GHz 128 MB 200W` → 结构化
    cpu{model/cores/tdp_w/qty}，规则只抽到 9254 关键词 + duality；
  • R7 典型报价单（能力规格）：补 memory{type/speed}、form、确认 9004/9005 系列
    —— 但「支持12个盘/8个GPU」这类能力声明绝不产盘/GPU 条目（R7 教训）；
  • 规则词表够不到的措辞（如"傲腾缓存盘"）补出盘组，HDD/SSD 品类自动补位。
"""
import json
import logging
import re
from typing import Optional

from app.services import llm_client

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
        }},
        "drives": {"type": "array", "items": {"type": "object", "properties": {
            "capacity": {"type": "string"},
            "capacity_gb": {"type": "integer"},
            "interface": {"type": "string", "enum": ["SATA", "SAS", "NVMe", "U.2", "U.3"]},
            "qty": {"type": "integer"},
        }}},
        "gpu": {"type": "array", "items": {"type": "object", "properties": {
            "model": {"type": "string"},
            "qty": {"type": "integer"},
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
        "raid": {"type": "object", "properties": {
            "model": {"type": "string"},
            "qty": {"type": "integer"},
        }},
        "form": {"type": "string"},
        "series": {"type": "string"},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
}

EXTRACT_ENHANCE_SYSTEM_PROMPT = (
    "你是 CPQ 服务器需求的结构化抽取器。输入：需求原文 + 规则引擎已抽取摘要（可能不完整/有误）。\n"
    "任务：把需求里「规则没抽到或抽不准」的槽位补全成 JSON。只输出 JSON 对象，不要任何多余文字。\n"
    "硬性约束：\n"
    "1) 能力声明 ≠ 实际配置：「支持/最多/最大/可扩展 N 个 X」是机箱能力，不是要配 N 个 X。\n"
    "   例如「支持12个3.5英寸硬盘」不产硬盘条目；「支持8个GPU」不产 8 张 GPU（除非给出具体型号）。\n"
    "2) 内存 qty 是【内存条数】，不是插槽数；「24个DDR5插槽」不写 qty=24，且不知道单条容量就写 null。\n"
    "3) 没有把握的字段一律 null，绝不猜（尤其具体型号、单条容量、核数）。\n"
    "4) drives.capacity 按原文写（如 \"960G\" / \"7.68T\"），interface 只取 SATA/SAS/NVMe/U.2/U.3；\n"
    "   容量归属（启动盘/数据盘/缓存盘）不写进槽位。\n"
    "5) 电源 wattage 只取明确写出的瓦数（如 1300W/2700W）；「根据功耗选择」写 null。\n"
    "6) form 只取 1U/2U/4U/5U/6U/8U 或 null；series 只取平台系列（Orion/Polaris/Intel/工作站 等）或 null。\n"
    "7) 只补缺失/模糊项；规则已抽到且你同意的项也要在 JSON 里带出（确认即价值），但不要编新项。"
)


def build_messages(requirement_text: str, ext: dict) -> list:
    """构造 chat_json 的 messages：系统 prompt + 需求原文 + 规则摘要。"""
    digest = {
        "categories": ext.get("categories") or [],
        "keywords": ext.get("keywords") or [],
        "series": ext.get("series"),
        "form": ext.get("form"),
        "cpu_signal": ext.get("cpu_signal"),
        "mem_signal": ext.get("mem_signal"),
        "psu_signal": ext.get("psu_signal"),
        "drive_groups": ext.get("drive_groups") or [],
        "gpu_groups": ext.get("gpu_groups") or [],
        "mem_groups": ext.get("mem_groups") or [],
    }
    user = (
        f"需求原文：\n{(requirement_text or '').strip()}\n\n"
        f"规则引擎已抽取（可能不完整/有误）：\n{json.dumps(digest, ensure_ascii=False, default=str)}\n\n"
        "请输出补全后的 JSON 槽位（严格按上述 schema 的键名）。"
    )
    return [
        {"role": "system", "content": EXTRACT_ENHANCE_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


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
    """容量 → 盘组 term："960G"/"7.68T" 原样归一；只有数字 GB → "NG"。"""
    if capacity:
        m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([GT])(?:B)?\s*$", str(capacity), re.I)
        if m:
            return f"{m.group(1)}{m.group(2).upper()}"
    if capacity_gb:
        return f"{int(capacity_gb)}G"
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


def _has_drive_config_signal(text: str) -> bool:
    """需求文本是否在描述「实际盘配置」（而非机箱盘位能力）。"""
    low = (text or "")
    if _DRIVE_STRONG_RE.search(low):
        return True
    if _DRIVE_CAPABILITY_RE.search(low):
        return False
    return bool(_DRIVE_CONFIG_RE.search(low) or _DRIVE_FIELD_RE.search(low))


# ── 确定性合并：只补缺、规则赢 ─────────────────────────────────────────

def merge_into_ext(ext: dict, cleaned: dict, requirement_text: str = "") -> list:
    """把 schema 收口后的 LLM 槽位确定性合并进 ext（就地修改）。

    规则赢：已存在的字段/组绝不覆盖，只补缺；能力声明不当配置。
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

    # ── CPU：合并进 cpu_signal（duality/qty/cores/tdp_w/model），规则已抽到的键不覆盖 ──
    cpu = cleaned.get("cpu") or {}
    if cpu:
        _add_cat("CPU")
        sig = dict(ext.get("cpu_signal") or {})
        qty = cpu.get("qty")
        if qty and 1 <= int(qty) <= 64:
            if int(qty) >= 2:
                sig.setdefault("duality", True)
                sig["qty"] = int(qty)
            qty_map = ext.get("qty_map")
            if qty_map is None:
                qty_map = {}
                ext["qty_map"] = qty_map
            if "CPU" not in qty_map and int(qty) >= 1:
                qty_map["CPU"] = int(qty)
                changes.append(f"qty_map.CPU={qty}")
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

    # ── 内存：合并 mem_signal（type/speed/total_gb/per_stick_gb）；mem_groups 仅当
    #    规则没抽到任何内存组且 LLM 明确给了单条容量（R7：插槽数/未知容量绝不臆造）──
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
        if per and 4 <= int(per) <= 1024:
            if not sig.get("per_stick_gb"):
                sig["per_stick_gb"] = int(per)
            if mqty and 1 <= int(mqty) <= 64 and not sig.get("total_gb"):
                sig["total_gb"] = int(per) * int(mqty)
                changes.append(f"mem.total_gb={sig['total_gb']}")
        if sig:
            ext["mem_signal"] = sig
        if per and 4 <= int(per) <= 1024 and not (ext.get("mem_groups") or []):
            n = int(mqty) if mqty and 1 <= int(mqty) <= 64 else 1
            ext["mem_groups"] = [{"term": f"{int(per)}G", "qty": n}]
            changes.append(f"mem_groups+{per}G×{n}")

    # ── 盘：能力声明不当配置；有配置信号才补（去重：同 term+kind 已有则跳过）──
    if not _has_drive_config_signal(requirement_text):
        if cleaned.get("drives"):
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
            ext.setdefault("drive_groups", []).append(
                {"term": term, "qty": int(qty or 1), "kind": kind})
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
        if not model:
            continue
        if qty is not None and not (1 <= int(qty) <= 64):
            continue
        toks = _model_tokens_of(model)
        if not toks:
            continue
        hit = next((gg for gg in ggroups if any(t in (gg.get("tokens") or []) for t in toks)), None)
        if hit:
            if model not in (hit.get("tokens") or []):
                hit["tokens"] = [model] + list(hit.get("tokens") or [])
                changes.append(f"gpu_groups[{model}] 前置精确型号")
            continue
        ggroups.append({"tokens": [model] + toks, "qty": int(qty or 1)})
        changes.append(f"gpu_groups+{model}×{qty or 1}")
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
    raid = cleaned.get("raid") or {}
    raid_model = (raid.get("model") or "").strip()
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
        ext["raid_signal"] = {"model": raid_model, "qty": int(raid.get("qty") or 1)}
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


async def run_extract_enhance(requirement_text: str, ext: dict, config: dict) -> dict:
    """extract 节点 LLM 抽取增强（就地增强 ext；由 extract 节点 enable_llm 调用）。

    任何失败 → 返回 {llm_called, merged:False, error}，绝不抛到主流程。
    config 可配：sparse_max_categories —— 品类数 > 阈值则跳过（只对"稀疏"需求调 LLM）。
    """
    text = (requirement_text or "").strip()
    if not text:
        return {"llm_called": False, "merged": False, "reason": "empty_text"}
    sparse_max = config.get("sparse_max_categories")
    n_cat = len(ext.get("categories") or [])
    if sparse_max is not None and n_cat > int(sparse_max):
        return {"llm_called": False, "merged": False,
                "reason": f"categories={n_cat} > sparse_max_categories={sparse_max}"}
    try:
        data = await llm_client.chat_json(
            build_messages(text, ext),
            schema=EXTRACT_ENHANCE_SCHEMA,
        )
    except llm_client.LLMError as e:
        logger.warning("extract_enhance LLM 调用失败，降级规则结果: %s", e)
        return {"llm_called": True, "merged": False, "error": str(e)[:300]}
    if not data:
        return {"llm_called": True, "merged": False, "reason": "empty_slots"}
    try:
        changes = merge_into_ext(ext, data, requirement_text=text)
    except Exception as e:  # merge 异常也降级，不让 LLM 结果破坏主流程
        logger.exception("extract_enhance merge 失败，丢弃 LLM 结果: %s", e)
        return {"llm_called": True, "merged": False, "error": f"merge:{e}"[:300]}
    return {
        "llm_called": True,
        "merged": bool(changes),
        "changes": changes,
        "llm_slots": {
            k: data.get(k) for k in ("cpu", "memory", "drives", "gpu", "nic", "psu", "raid",
                                     "form", "series")
            if data.get(k) is not None
        },
    }


# ============================================================
# scene_analysis / review 的 LLM 增强（2026-08-04 流程重构阶段 2）
# 铁律同 extract：LLM 输出绝不裸进选件/改方案，只做"理解/判断"增强，
# 规则始终兜底；任何失败静默降级，不阻塞主流程。
# ============================================================

SCENE_INFER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scene_name": {"type": "string"},   # 服务器类型名（AI/通用/存储）
        "series": {"type": "string"},       # 系列（Orion/Polaris/Intel）
        "reason": {"type": "string"},
    },
}

SCENE_INFER_SYSTEM_PROMPT = (
    "你是服务器选型助手。根据客户需求判断「所属系列」与「应用场景」（AI/通用/存储）。"
    "规则：1) 只输出确定/强推断的信息，无法判断的字段给空字符串；"
    "2) 系列只从 Orion/AMD平台、Polaris/信创平台、Intel 平台 中选；"
    "3) 不确定就留空，不要猜。输出严格 JSON。"
)


def build_scene_messages(requirement_text: str, scene: dict) -> list:
    digest = {k: scene.get(k) for k in ("scene_name", "series", "form", "confidence", "evidence")}
    user = (
        f"需求原文：\n{(requirement_text or '').strip()}\n\n"
        f"规则引擎已判断（可能不完整）：\n{json.dumps(digest, ensure_ascii=False, default=str)}\n\n"
        "请补全 scene_name 与 series（严格按 schema 键名）。"
    )
    return [
        {"role": "system", "content": SCENE_INFER_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


async def run_scene_infer(requirement_text: str, scene: dict, config: dict) -> dict:
    """scene_analysis 节点 LLM 增强：规则推不出系列/场景时，LLM 从语义补推断。
    返回 {llm_called, series, scene_name, confidence, reason}；任何失败返回空（规则兜底）。"""
    try:
        data = await llm_client.chat_json(build_scene_messages(requirement_text or "", scene or {}),
                                          schema=SCENE_INFER_SCHEMA)
    except llm_client.LLMError as e:
        logger.warning("scene_infer LLM 调用失败（降级规则）: %s", e)
        return {"llm_called": True, "series": None, "scene_name": None}
    return {
        "llm_called": True,
        "series": str(data.get("series") or "").strip() or None,
        "scene_name": str(data.get("scene_name") or "").strip() or None,
        "reason": str(data.get("reason") or "").strip() or "",
    }


AUDIT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
}

AUDIT_SYSTEM_PROMPT = (
    "你是服务器方案校对员。客户给出需求，系统生成整机方案。请判断方案是否满足客户需求意图"
    "（如：客户要训练大模型但方案 GPU 不足、要存储但盘位/容量明显不够、要信创但配了非信创平台）。"
    "只列【硬性问题】（最多 3 条），不确定的不报；不要重复方案已有的措辞差异。输出严格 JSON。"
)


def build_audit_messages(requirement_text: str, plan: dict) -> list:
    summary = {
        "name": plan.get("name"),
        "series": plan.get("series"),
        "form": plan.get("form"),
        "bays": plan.get("bays"),
        "bom": [
            {"cat": r.get("part_category") or r.get("category"), "desc": r.get("description"), "qty": r.get("qty")}
            for r in (plan.get("cfg") or {}).get("bom_excel_rows") or []
        ],
    }
    user = (
        f"客户需求：\n{(requirement_text or '').strip()}\n\n"
        f"系统方案：\n{json.dumps(summary, ensure_ascii=False, default=str)}\n\n"
        "输出 passed 与 issues（严格按 schema）。"
    )
    return [
        {"role": "system", "content": AUDIT_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


async def run_llm_audit(requirement_text: str, plan: dict, config: dict) -> dict:
    """review 节点 LLM 语义校对：返回 {llm_called, passed, issues}；失败返回空（规则硬校验兜底）。"""
    try:
        data = await llm_client.chat_json(build_audit_messages(requirement_text or "", plan or {}),
                                          schema=AUDIT_SCHEMA)
    except llm_client.LLMError as e:
        logger.warning("llm_audit 调用失败（降级规则校对）: %s", e)
        return {"llm_called": True, "passed": None, "issues": []}
    issues = [str(i) for i in (data.get("issues") or []) if str(i).strip()]
    return {
        "llm_called": True,
        "passed": bool(data.get("passed")),
        "issues": issues[:3],
    }
