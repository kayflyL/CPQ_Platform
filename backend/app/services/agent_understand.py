# -*- coding: utf-8 -*-
"""agent_understand —— AI 路「需求理解」主节点（P1，纯 LLM 填表 + 确定性 resolver）。

架构：需求原文 → LLM 把需求填进固定表（RequirementSlots / EXTRACT_ENHANCE_SCHEMA）→
确定性 resolver（merge_into_ext：归一 + catalog 白名单锚定）→ ctx["ext"] → 确定性后半段出 BOM。

为什么纯 LLM 而非 regex extract / 混合：regex 不泛化（打地鼠），LLM 天然泛化格式；可靠性测试
（每输入 10 次）证明纯 LLM 填表关键字段 ~100% 命中。LLM 不直接产 ext（regex 专属信号如 qty_per_token
不由 LLM 复现），而是产 canonical 表 → 由确定性 resolver 归一成 ext 信号。resolver 不碰自由文本、
不打地鼠（结构化→结构化）。

抽不全（缺 server_type 等关键字段）→ 返回 sufficient=False + missing_critical，由 dispatch 触发反问
（SAGE uncertainty 门控：够就推进、不够才问最关键的一件）。

可靠性闸：① catalog 白名单锚定（server_type/series/form 只从在售清单选）② resolver 归一 + 禁编料号
③ LLM 关/失败 → 诚实降级（目录手动选型/反问），不再用正则假装理解（Phase3 清理）。
"""
import logging
from typing import Optional

from app.services import llm_client
from app.services.llm_extract_enhance import EXTRACT_ENHANCE_SCHEMA, merge_into_ext

logger = logging.getLogger(__name__)


AGENT_UNDERSTAND_SYSTEM_PROMPT = (
    "你是 CPQ 服务器需求结构化抽取器。输入：客户需求原文（格式随意/口语/表格化都行）。\n"
    "任务：把需求填进固定表（JSON 对象），只输出 JSON，不要任何多余文字。\n"
    "表字段：\n"
    "  cpu{model,cores,tdp_w,qty}  memory{per_stick_gb,qty,type(DDR4/DDR5),speed_mt,comparison(gte/lte)}  "
    "drives[{capacity,capacity_gb,interface(SATA/SAS/NVMe/U.2/U.3),qty,comparison(gte/lte)}]  "
    "gpu[{model,capacity_gb,comparison(gte/lte),qty}]  nic[{model,speed_g,ports,qty,with_optical_module}]  "
    "psu{wattage,qty}  raid{model,qty}  form  series  server_type  notes[]\n"
    "硬约束：\n"
    "1) 能力声明 ≠ 实际配置：「支持/最多/最大/可扩展 N 个 X」是机箱能力，不是要配 N 个 X。\n"
    "2) 数量约定：「X*N」「N*X」「X×N」都表示 N 个 X（* 和 × 是乘号），拆出 model 与 qty：\n"
    "   '32G*16'→memory per_stick_gb=32,qty=16；'RTX 5090 32G*8'→gpu[{model:'RTX 5090',qty:8}]；"
    "'2*480GB'→drives[{capacity:'480G',capacity_gb:480,qty:2}]；'双口25G'→nic[{speed_g:25,ports:2}]。\n"
    "3) 内存 qty 是【条数】不是插槽数；不知单条容量写 null。\n"
    "4) 没把握的字段写 null，绝不猜（尤其型号、单条容量、核数）。\n"
    "5) drives/memory 必须填 capacity_gb / per_stick_gb（数值 GB，AI 把自然语言归一成机器可用值）：\n"
    "   \"1T以上硬盘\"→{capacity:\"1T以上\",capacity_gb:1024,comparison:\"gte\",qty:1}；\"一tb/一t/1tb\"→capacity_gb:1024；\"960G\"→960。\n"
    "   comparison 语义：\"以上/至少/不小于\"→gte、\"以下/不超过/最多\"→lte、无比较→省略；\n"
    "   gpu.capacity_gb 为显存（GB）：\"48G以上显存的显卡\"→{capacity_gb:48,comparison:\"gte\",qty:1}，无型号也填；\n"
    "   capacity 保留原文，interface 只取 SATA/SAS/NVMe/U.2/U.3，qty 缺省 1。\n"
    "6) 电源 wattage 只取明确瓦数（1300W/2700W）；「根据功耗选择」写 null。\n"
    "7) form 只取 1U/2U/4U/5U/6U/8U 或 null。\n"
    "8) series 只从给定的「在售平台系列」里选，不确定写 null。\n"
    "9) server_type 从需求能推断就填（8 张 GPU 推理卡→AI/加速计算；大量硬盘→存储；"
    "虚拟化/数据库/Web→通用计算），只从「在售服务器类型」清单选，不确定写 null。\n"
    "10) raid 只在需求明确给出阵列卡型号时填（如 LSI 9560-16i）；只有 RAID 级别（RAID 0/1/10）写 null。"
)


def _catalog_whitelist_text(catalog: dict) -> str:
    st = catalog.get("server_types") or []
    sr = catalog.get("series") or []
    fm = catalog.get("forms") or []
    return "\n".join([
        "在售服务器类型（server_type 只允许从这里选）：" + ("、".join(st) if st else "（无）"),
        "在售平台系列（series 只允许从这里选）：" + ("、".join(sr) if sr else "（无）"),
        "机箱形态（form 只允许从这里选）：" + ("、".join(fm) if fm else "（无）"),
    ])


def build_agent_messages(requirement_text: str, catalog: dict,
                         system_prompt: Optional[str] = None,
                         few_shot: str = "", domain_knowledge: str = "") -> list:
    """构造 chat_json 的 messages：主抽取 system prompt + 领域知识(按需已过滤) + 目录白名单 + 需求原文（+ CBR few-shot 限量）。

    domain_knowledge：领域知识文本（词表触发词→品类/系列/类型/形态 映射），AI 理解时接地用——
    这些映射是产品领域知识（如"兆芯→Polaris"），LLM 不知道，必须查词表（2026-08 重构）。
    agent 化（2026-08）：领域知识由调用方按 match_text 过滤（只注入命中项）；需求原文限长
    3000 字防超长输入拖慢 reasoning 模型（空回/超时主因）；few-shot 限量在 _retrieve_few_shot。
    """
    text = (requirement_text or "").strip()
    if len(text) > 3000:
        text = text[:3000] + "…（原文过长已截断）"
    user = (
        f"{_catalog_whitelist_text(catalog)}\n\n"
        + (f"{domain_knowledge}\n\n" if domain_knowledge else "")
        + f"需求原文：\n{text}\n\n"
        + (f"{few_shot}\n\n" if few_shot else "")
        + "请填表（严格按字段名，没把握写 null）。"
    )
    return [
        {"role": "system", "content": system_prompt or AGENT_UNDERSTAND_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _is_sufficient(ext: dict) -> bool:
    """抽出来的够不够支撑后续选配？不够 → 该反问。
    判据：有 server_type（选型必需）且至少一个配置信号（cpu/memory/gpu/drive 品类）。"""
    has_type = bool(ext.get("server_type_name"))
    has_signal = bool(ext.get("categories"))
    return has_type and has_signal


def _missing_critical(ext: dict) -> list:
    """缺哪些关键字段（供反问文案用）。"""
    miss = []
    if not ext.get("server_type_name"):
        miss.append("服务器类型/用途")
    if not ext.get("categories"):
        miss.append("配置规格（CPU/内存/硬盘/GPU 等）")
    return miss


# CPU 型号 → 平台系列（硬事实，确定性优于 LLM 猜；LLM 常漏推 KH-50000=Polaris 导致选错机型）
_CPU_SERIES_RULES = [
    (r"KH-?50000|KH-?5000|KX-?4|兆芯|开胜", "Polaris"),
    (r"EPYC|AMD\s*7|AMD\s*9|猎户", "Orion"),
    (r"XEON|INTEL|至强", "Intel"),
]


def _infer_series_from_cpu(model: str) -> Optional[str]:
    """CPU 型号 → 平台系列（KH50000→Polaris / EPYC→Orion / Xeon→Intel）；无命中→None。"""
    import re
    for pat, series in _CPU_SERIES_RULES:
        if re.search(pat, str(model or ""), re.I):
            return series
    return None


async def _safe_broadcast(broadcast, step_id: Optional[str], kind: str, text: str) -> None:
    """发 step_progress 子事件（白盒化：让前端实时看 agent 理解进度，不再干等）。失败静默。"""
    if broadcast and step_id:
        try:
            await broadcast({"type": "step_progress", "step": step_id, "sub": {"kind": kind, "text": text}})
        except Exception:
            pass


def _understood_summary(ext: dict) -> str:
    """合并后的 ext → 一行理解摘要（子事件展示用）。"""
    parts = []
    if ext.get("server_type_name"):
        parts.append(ext["server_type_name"])
    for g in (ext.get("gpu_groups") or [])[:2]:
        parts.append(f"GPU×{g.get('qty', '?')}")
    mg = ext.get("mem_groups") or []
    if mg:
        parts.append(f"内存×{mg[0].get('qty', '?')}")
    dgs = ext.get("drive_groups") or []
    if dgs:
        parts.append(f"盘{sum(g.get('qty', 0) for g in dgs)}")
    return "·".join(parts) if parts else "已理解"


def _retrieve_few_shot(config: dict, query: str) -> str:
    """检索相似案例 → few-shot 文本（供 LLM 理解时接地真实配置，防幻觉）。

    config 门控：case_source=off 或 case_top_k<=0 → 空（退零样本）。无案例/检索失败 → 空（不阻塞）。
    """
    cfg = config or {}
    if cfg.get("case_source", "internal") == "off":
        return ""
    top_k = min(int(cfg.get("case_top_k") or 0), 2)  # 限量≤2：few-shot 只是接地，多了是噪音
    if top_k <= 0:
        return ""
    try:
        from app.services.case_provider import get_case_provider
        provider = get_case_provider(cfg)
        cases = (provider.retrieve(query, top_k=top_k) or [])[:top_k]
    except Exception as e:
        logger.warning("CBR few-shot 检索失败（退零样本）: %s", e)
        return ""
    if not cases:
        return ""
    lines = ["参考相似案例（真实配置过，学配置模式、勿照抄型号）："]
    for i, c in enumerate(cases, 1):
        req = ((c.get("requirement") or "").replace("\n", " "))[:80]
        kps = c.get("kp_parts") or []
        kp_text = "、".join(f"{k.get('category') or k.get('name') or '?'}×{k.get('qty', 1)}"
                           for k in kps[:6]) or "—"
        lines.append(f"  案例{i} 需求：{req}\n       实配：{kp_text}")
    return "\n".join(lines)


# ── 专家分析（Phase2）：像方案助手一样先给"问题清单"，再进入选配 ──────────
UNDERSTAND_ANALYSIS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "issues": {"type": "array", "items": {"type": "object", "properties": {
            "issue": {"type": "string"},
            "evidence": {"type": "string"},
            "suggestion": {"type": "string"},
        }}},
    },
}


# ── agent 化·分步子任务（2026-08 定稿：拆细，每个子任务 3-5 字段，prompt 聚焦）──────
# 背景：reasoning 模型（deepseek-v4-flash）对"10+ 字段一次性大填表"会过度思考——
# 把 max_tokens 烧在思考阶段（finish_reason=length）→ 正文空回（40-60% 失败，慢 42-64s）。
# 拆成聚焦小子任务：reasoning 骤降（实测 228~1414 字）→ ~100% 成功、单次 2-8s；
# 4 个任务互相独立 → 并行执行总墙钟 ~7-10s；失败单独便宜重试，仍失败只丢该子字段。
# 全部可配：split_steps 总开关、steps.{key}.enabled/system_prompt、parallel_sub_steps、sub_step_retries。
UNDERSTAND_STEPS_DEFAULT: list = [
    {
        "key": "type_form",
        "label": "类型/系列/形态",
        "fields": ["server_type", "series", "form"],
        "kinds": ["server_type", "series", "form"],
        "enabled": True,
        "system_prompt": (
            "你是 CPQ 选型助手。从需求推断服务器类型/平台系列/机箱形态，输出 JSON：\n"
            '{"server_type": "只从在售类型选，不确定null", "series": "只从在售系列选，不确定null", "form": "只取1U/2U/4U/5U/6U/8U，不确定null"}。\n'
            "规则：\n"
            "1) 「支持/最多 N 卡/N 盘位」是机箱能力，不是类型/形态依据；\n"
            "2) 客户点名品牌机型（如 WA5480 G3）无法映射到在售平台时，按 GPU/盘位等信号推断类型；\n"
            "3) 没把握写 null，绝不猜。只输出 JSON。"
        ),
    },
    {
        "key": "cpu_mem",
        "label": "CPU/内存",
        "fields": ["cpu", "memory"],
        "kinds": ["kp"],
        "enabled": True,
        "system_prompt": (
            "你是 CPQ 选型助手。从需求提取 CPU 和内存，输出 JSON：\n"
            '{"cpu": {"model": "型号，没把握null", "cores": 0, "tdp_w": 0, "qty": 1}, '
            '"memory": {"per_stick_gb": 0, "qty": 0, "type": "DDR4或DDR5", "speed_mt": 0, "comparison": "gte/lte/省略", "total_gb": 0}}。\n'
            "规则：\n"
            "1) memory qty 是【条数】；'32G*16'→per_stick_gb:32,qty:16,total_gb:512；\n"
            "2) 只给总量没给单条（'256GB DDR5-4800'）→total_gb:256,per_stick_gb:null,qty:null（单条/条数交给配件规划按通道拆）；\n"
            "3) '以上/至少/不小于'→comparison:gte、'以下/不超过/最多'→lte、无比较省略；\n"
            "4) 没把握写 null，绝不猜型号/单条容量。只输出 JSON。"
        ),
    },
    {
        "key": "drive_gpu",
        "label": "硬盘/GPU",
        "fields": ["drives", "gpu"],
        "kinds": ["kp"],
        "enabled": True,
        "system_prompt": (
            "你是 CPQ 选型助手。从需求提取硬盘和 GPU，输出 JSON：\n"
            '{"drives": [{"capacity": "原文容量", "capacity_gb": 0, "interface": "SATA/SAS/NVMe/U.2/U.3", "qty": 1, "comparison": "gte/lte/省略"}], '
            '"gpu": [{"model": "型号，没把握null", "qty": 1, "capacity_gb": 0, "comparison": "gte/lte/省略"}]}。\n'
            "规则：\n"
            "1) 容量归一：'1T以上'→capacity_gb:1024,comparison:gte；'一tb/1tb/一t'→1024；'960G'→960；'3.84T'→3840；\n"
            "2) gpu.capacity_gb 是显存 GB（'48G以上显存'→capacity_gb:48,comparison:gte），无型号也填；\n"
            "3) 「支持/最多 N 盘位」是机箱能力，不是实际盘配置，不产条目；\n"
            "4) 没把握写 null，绝不猜。只输出 JSON。"
        ),
    },
    {
        "key": "net_psu_raid",
        "label": "网卡/电源/RAID",
        "fields": ["nic", "psu", "raid"],
        "kinds": ["kp", "chassis"],
        "enabled": True,
        "system_prompt": (
            "你是 CPQ 选型助手。从需求提取网卡/电源/RAID，输出 JSON：\n"
            '{"nic": [{"model": "型号，没把握null", "speed_g": 0, "ports": 1, "qty": 1, "with_optical_module": false}], '
            '"psu": {"wattage": 0, "qty": 0}, "raid": {"model": "型号，没把握null", "qty": 1}}。\n'
            "规则：\n"
            "1) 电源只取明确瓦数（如 2700W），'根据功耗选择'写 null；\n"
            "2) raid 有明确型号就填；没给型号但给了规格（如 '2GB缓存,接口数8个'）→ 按规格推断常见型号"
            "（2GB缓存+8口→LSI 9361-8i；4GB缓存+16口→LSI 9560-16i），推断不出写 null；只有 RAID 0/1/10 写 null；\n"
            "3) 'N×speed'（如 2x 1GE / 2x 10GE）指 N 个网口（常为一张双口卡）→ports:N, qty:1，"
            "'2x 1GE'→nic[{speed_g:1,ports:2,qty:1}]、'2x10GE(含光模块)'→nic[{speed_g:10,ports:2,qty:1,with_optical_module:true}]；\n"
            "4) 没把握写 null，绝不猜。只输出 JSON。"
        ),
    },
    {
        "key": "analysis",
        "label": "专家分析",
        "fields": [],
        "kinds": [],
        "enabled": True,
        "schema": UNDERSTAND_ANALYSIS_SCHEMA,
        "system_prompt": (
            "你是 CPQ 服务器配置专家顾问。输入：客户需求原文。\n"
            "任务：像资深售前一样指出这份配置里的**硬问题**（会导致无法交付/性能严重受损/明显不合理），每条给依据与修正建议。\n"
            "检查维度（只报有依据的硬问题，最多 5 条）：\n"
            "1) 电源：GPU/CPU 满载功耗估算（8×300W GPU + 双路 ≈ 3200-4500W → 需 ≥4×2700W 冗余）；\n"
            "2) 内存：EPYC/Xeon 多通道平台，总量与条数是否匹配通道（如 256GB 建议 8×32G 填通道，别用 16 条 16G）；\n"
            "3) RAID/存储：NVMe 直连 vs RAID 卡取舍、容量是否够用；\n"
            "4) 网卡：分布式训练/高吞吐场景 10GE 是否瓶颈；\n"
            "5) 散热/机箱：多卡 GPU 是否需专用机箱/液冷。\n"
            "只输出 JSON：{issues:[{issue, evidence, suggestion}]}；没有硬问题输出空数组。"
        ),
    },
]


def _load_understand_steps(config: dict) -> list:
    """加载分步子任务。config.split_steps=false → []（legacy 单次大填表）。
    config.steps 按 key 覆盖 enabled/system_prompt；未配置用默认 4 步（全开）。
    """
    if not bool((config or {}).get("split_steps", True)):
        return []
    overrides = (config or {}).get("steps")
    out: list = []
    for s in UNDERSTAND_STEPS_DEFAULT:
        step = dict(s)
        o = (overrides or {}).get(step["key"]) or {}
        if isinstance(o, dict):
            if "enabled" in o:
                step["enabled"] = bool(o["enabled"])
            if o.get("system_prompt"):
                step["system_prompt"] = str(o["system_prompt"])
        if step.get("enabled", True):
            out.append(step)
    return out


def _step_whitelist_text(step: dict, catalog: dict) -> str:
    """子任务白名单：类型/系列/形态步骤喂目录白名单，其余步骤不需要（避免噪音）。"""
    if step.get("key") == "type_form":
        return _catalog_whitelist_text(catalog)
    return ""


def build_sub_step_messages(step: dict, requirement_text: str, catalog: dict,
                            domain_text: str = "", few_shot: str = "") -> list:
    """构造单个子任务的 messages：聚焦 system prompt + 白名单(按步) + 领域知识(按 kind) + 需求原文。"""
    parts: list = []
    wl = _step_whitelist_text(step, catalog)
    if wl:
        parts.append(wl)
    if domain_text:
        parts.append(domain_text)
    if few_shot:
        parts.append(few_shot)
    parts.append(f"需求原文：\n{(requirement_text or '').strip()}\n\n请输出 JSON（严格字段名，没把握写 null）。")
    return [
        {"role": "system", "content": step["system_prompt"]},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def _step_domain(step: dict, text: str, domain_map: Optional[dict], domain_knowledge: str) -> str:
    """子任务领域知识：从 map 按 step.kinds 取（type_form 已含工作负载映射段）。
    无 map（兼容旧调用）→ 整段领域知识只给 type_form，其余为空（保底关键类型知识不缺）。"""
    if not domain_map:
        return domain_knowledge if step.get("key") == "type_form" else ""
    parts = [domain_map[k] for k in (step.get("kinds") or []) if domain_map.get(k)]
    return "\n\n".join(parts)


async def _run_sub_step(step: dict, text: str, catalog: dict, domain_text: str,
                        few_shot: str, timeout: float = 50, retries: int = 1) -> tuple:
    """跑单个子任务：短超时 + 单次不重试（chat_json max_attempts=1）；失败按 sub_step_retries
    便宜重试（每子任务 2-8s，重试成本低）。返回 (data, ok, error)。"""
    msgs = build_sub_step_messages(step, text, catalog, domain_text, few_shot)
    last_err = ""
    for _attempt in range(max(1, int(retries) + 1)):
        try:
            data = await llm_client.chat_json(msgs, schema=step.get("schema"), temperature=0,
                                              timeout=timeout, max_attempts=1)
            if isinstance(data, dict) and data:
                return data, True, ""
            last_err = "empty_slots"
        except llm_client.LLMError as e:
            last_err = f"llm_error:{e}"[:200]
        except Exception as e:
            last_err = f"exception:{e}"[:200]
    return {}, False, last_err


async def _run_understand_legacy(text: str, config: dict, catalog: dict,
                                 domain_knowledge: str, broadcast, step_id, base) -> dict:
    """legacy 单次大填表（split_steps=false 时）：保持旧行为——首调失败用最小 prompt 重试一次。"""
    few_shot = _retrieve_few_shot(config, text)
    if few_shot:
        await _safe_broadcast(broadcast, step_id, "cbr", "📚 检索到相似案例作参照")
    await _safe_broadcast(broadcast, step_id, "llm_understand", "🤖 AI 理解需求中（单次填表）...")
    try:
        messages = build_agent_messages(text, catalog, system_prompt=config.get("system_prompt"),
                                        few_shot=few_shot, domain_knowledge=domain_knowledge)
        slots = await llm_client.chat_json(messages, schema=EXTRACT_ENHANCE_SCHEMA, temperature=0,
                                           timeout=75, max_attempts=1)
    except llm_client.LLMError as e:
        logger.warning("agent_understand 首调失败(%s)，用最小 prompt 重试一次", e)
        try:
            mini = build_agent_messages(text, catalog, system_prompt=config.get("system_prompt"),
                                        few_shot="", domain_knowledge="")
            slots = await llm_client.chat_json(mini, schema=EXTRACT_ENHANCE_SCHEMA, temperature=0,
                                               timeout=75, max_attempts=1)
        except llm_client.LLMError as e2:
            logger.warning("agent_understand 最小 prompt 重试仍失败（交规则理解兜底节点）: %s", e2)
            return {**base, "ok": False, "error": f"llm_error:{e2}"[:300]}
        except Exception as e2:
            logger.exception("agent_understand 最小 prompt 重试未预期异常（交规则理解兜底节点）: %s", e2)
            return {**base, "ok": False, "error": f"exception:{e2}"[:300]}
    except Exception as e:
        logger.exception("agent_understand 未预期异常（交规则理解兜底节点）: %s", e)
        return {**base, "ok": False, "error": f"exception:{e}"[:300]}

    if not isinstance(slots, dict) or not slots:
        return {**base, "ok": False, "error": "empty_slots"}
    ext: dict = {}
    try:
        changes = merge_into_ext(ext, slots, requirement_text=text, catalog=catalog)
    except Exception as e:
        logger.exception("agent_understand resolver 失败（交规则理解兜底节点）: %s", e)
        return {**base, "ok": False, "error": f"merge:{e}"[:300]}
    _infer_series_fallback(ext, catalog, changes)
    await _safe_broadcast(broadcast, step_id, "understood", f"✓ 理解到：{_understood_summary(ext)}")
    return {**base, "ok": True, "ext": ext, "source": "llm", "changes": changes, "slots": slots,
            "sufficient": _is_sufficient(ext), "missing_critical": _missing_critical(ext)}


def _infer_series_fallback(ext: dict, catalog: dict, changes: list) -> None:
    """系列兜底推断：LLM 没给 series 时按 CPU 型号确定性推断（KH50000→Polaris 等），
    仍受 catalog 白名单约束。"""
    if not ext.get("series") and (ext.get("cpu_signal") or {}).get("model"):
        inferred_series = _infer_series_from_cpu(ext["cpu_signal"]["model"])
        if inferred_series and inferred_series in {str(s) for s in (catalog.get("series") or [])}:
            ext["series"] = inferred_series
            changes.append(f"series(从CPU推断)={inferred_series}")


async def _run_understand_split(text: str, config: dict, catalog: dict, steps: list,
                                domain_map: Optional[dict], domain_knowledge: str,
                                broadcast, step_id, base) -> dict:
    """分步子任务：并行执行 → 确定性合并（merge_into_ext 单点收口，可靠性闸不变）。
    部分子任务失败 → 只丢该子字段，其余照常；全部失败 → ok=False 交规则理解兜底节点。"""
    parallel = bool(config.get("parallel_sub_steps", True))
    retries = max(0, int(config.get("sub_step_retries") or 1))
    few_shot = _retrieve_few_shot(config, text) if bool(config.get("use_few_shot")) else ""
    await _safe_broadcast(broadcast, step_id, "llm_understand", "🤖 AI 理解需求中（分步子任务）...")

    async def _run_one(step: dict) -> tuple:
        dom = _step_domain(step, text, domain_map, domain_knowledge)
        await _safe_broadcast(broadcast, step_id, "llm_understand", f"🔍 理解 {step['label']}...")
        data, ok, err = await _run_sub_step(step, text, catalog, dom, few_shot,
                                            timeout=50, retries=retries)
        if ok:
            await _safe_broadcast(broadcast, step_id, "llm_understand", f"✓ {step['label']} 完成")
        else:
            await _safe_broadcast(broadcast, step_id, "llm_understand",
                                  f"⚠️ {step['label']} 失败（{err[:80]}），跳过")
        return step, data, ok

    if parallel and len(steps) > 1:
        import asyncio
        results = await asyncio.gather(*[_run_one(s) for s in steps])
    else:
        results = []
        for s in steps:
            results.append(await _run_one(s))

    slots: dict = {}
    failures: list = []
    analysis_issues: list = []
    for step, data, ok in results:
        if not ok:
            failures.append(step["label"])
            continue
        if step.get("key") == "analysis":
            for it in (data.get("issues") or []):
                if isinstance(it, dict) and str(it.get("issue") or "").strip():
                    analysis_issues.append({k: it.get(k) for k in ("issue", "evidence", "suggestion") if it.get(k)})
            continue
        for f in step["fields"]:
            if data.get(f) is not None:
                slots[f] = data[f]
    if not slots:
        return {**base, "ok": False,
                "error": f"llm_error:all_substeps_failed:{';'.join(failures)}"[:300]}

    ext: dict = {}
    try:
        changes = merge_into_ext(ext, slots, requirement_text=text, catalog=catalog)
    except Exception as e:
        logger.exception("agent_understand 分步 resolver 失败（交规则理解兜底节点）: %s", e)
        return {**base, "ok": False, "error": f"merge:{e}"[:300]}
    _infer_series_fallback(ext, catalog, changes)
    await _safe_broadcast(broadcast, step_id, "understood", f"✓ 理解到：{_understood_summary(ext)}")
    return {**base, "ok": True, "ext": ext, "source": "llm", "changes": changes, "slots": slots,
            "sufficient": _is_sufficient(ext), "missing_critical": _missing_critical(ext),
            "analysis_issues": analysis_issues[:10],
            "sub_steps": {"total": len(steps), "failed": failures}}


async def run_agent_understand(requirement_text: str, config: dict,
                               extract_config: Optional[dict] = None,
                               catalog: Optional[dict] = None,
                               broadcast=None, step_id: Optional[str] = None,
                               domain_knowledge: str = "", domain_map: Optional[dict] = None) -> dict:
    """AI 路主理解（agent 化·分步）：聚焦子任务并行 → 确定性合并 → ext。

    config         —— understand 节点 config（split_steps/parallel_sub_steps/steps.* 可配）。
    extract_config —— extract 节点 config（词表），离线兜底用。
    catalog        —— 目录白名单；None 则现读。
    domain_map     —— {kind: 领域知识文本}（capabilities.run_understand 构建，按需检索+工作负载映射）；
                     未传则用 domain_knowledge 整段（legacy 兼容）。
    broadcast/step_id —— 透传图执行器的广播函数，发 step_progress 子事件（白盒化）。

    返回 {ok, ext, source, sufficient, missing_critical, changes, slots, error, sub_steps?}。
    source='llm'；ok=False = AI 失效（LLM 关/全子任务失败/合并失败）——由编排器路由到
    extract 规则理解兜底节点。sufficient=False 时 dispatch 应触发反问（force_complete 除外）。
    """
    base = {"ok": False, "ext": None, "source": None, "sufficient": False,
            "missing_critical": [], "changes": [], "slots": None, "error": None}
    text = (requirement_text or "").strip()
    if not text:
        base["error"] = "empty_text"
        return base
    if catalog is None:
        from app.services.requirement_slots import build_catalog_context
        catalog = build_catalog_context()
    try:
        enabled = llm_client.is_llm_enabled()
    except Exception:
        enabled = False
    if not enabled:
        return {**base, "ok": False, "error": "llm_disabled"}

    steps = _load_understand_steps(config)
    if steps:
        return await _run_understand_split(text, config, catalog, steps, domain_map,
                                           domain_knowledge, broadcast, step_id, base)
    return await _run_understand_legacy(text, config, catalog, domain_knowledge,
                                        broadcast, step_id, base)
