"""Requirement intelligence pipeline — 客户需求 → 关键词提取 → 聚合检索 → 候选清单。

一期纯本地：jieba 分词 + DB ILIKE 检索，不调 LLM。每步通过 reasoning_hub 实时广播到
商机详情页的推理面板。失败兜底广播 error，不阻塞。
"""
import logging
import re
import json
import uuid
from typing import Optional

from app.services.reasoning_hub import reasoning_hub
from app.api.candidate_search import select_models, pick_kp_parts, build_plan, kp_categories_for_type, build_variant_signals

logger = logging.getLogger(__name__)

# ── 关键词词表：品类 → 触发词（中英）──
CATEGORY_LEXICON: dict[str, list[str]] = {
    "CPU": ["cpu", "processor", "处理器", "epyc", "xeon", "至强", "intel", "amd"],
    "Memory": ["memory", "ram", "内存", "ddr", "rdimm"],
    "HDD/SSD": ["hdd", "ssd", "nvme", "硬盘", "磁盘", "sata", "u.2", "u.3", "u2", "u3", "启动盘", "系统盘", "数据盘", "存储盘"],
    "GPU": ["gpu", "显卡", "图形卡", "rtx", "l40", "w7900", "a100", "h100"],
    "NIC": ["nic", "网络", "网卡", "网口", "ethernet", "e810", "mlx", "connectx"],
    "HBA": ["hba", "hba卡"],
    "Raid card": ["raid", "阵列", "阵列卡", "mega", "brocade"],
    "Power": ["psu", "电源", "power", "风扇模块"],
    "Fan": ["fan", "风扇"],
    "Heatsink": ["heatsink", "散热器", "散热"],
    "Cable": ["cable", "线缆", "电源线", "数据线"],
    "Rail": ["rail", "导轨"],
    "Backplane": ["backplane", "背板"],
}
SERIES_KEYWORDS = ["Orion", "Polaris", "Intel", "工作站"]  # 兜底常量（权威源 = system_config.server_series）


def _load_series_values() -> list:
    """全平台系列权威源（system_config.server_series，[{value,label},...]）→ 值列表；读失败回退常量。"""
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            raw = repo.get_value("server_series", [])
        finally:
            repo.close()
        if isinstance(raw, list):
            vals = [str(it["value"]) for it in raw
                    if isinstance(it, dict) and it.get("value")]
            if vals:
                return vals
    except Exception:
        pass
    return list(SERIES_KEYWORDS)
FORM_PATTERN = re.compile(r"(?<![0-9])([12468]U)(?![A-Za-z])", re.IGNORECASE)
# 型号 token（必含数字，避免 nvme/sata 纯字母品类词误命中）：字母开头混合/纯数字≥4/数字开头混合(960G/7.68T/9560-8i)
MODEL_TOKEN_PATTERN = re.compile(r"^(?=.*[0-9])([A-Za-z]{2,}[0-9A-Za-z\-]{2,}|[A-Za-z][0-9]{3,}|[0-9]{4,}|[0-9][0-9A-Za-z.\-]{2,})$")

# 预算抽取：预算/budget 前缀 或 带万/w/k 单位的裸数字
_BUDGET_PREFIX = re.compile(r"(?:预算|budget|价位|价格|大概)[^\d]{0,8}(\d+(?:\.\d+)?)\s*(万|w|k|元|块)?", re.IGNORECASE)
_BUDGET_UNIT = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*(万|k)\b")   # 万/k；大写 W 是瓦（360W CPU TDP），不算预算
_BUDGET_UNIT_W = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*(w)\b")  # 小写 w=万（口语"20w"）；大写 W=瓦不认（2026-08-03 R2）

# 数量抽取："N卡"→GPU, "N条"→Memory, "N颗/N块"→CPU（给 pick_kp_parts 按数量配）
QTY_UNIT_PATTERN = re.compile(r"(\d+)\s*(卡|条|颗|块)")
QTY_UNIT_TO_CAT: dict[str, str] = {"卡": "GPU", "条": "Memory", "颗": "CPU", "块": "CPU"}

# 中文停用词（粗表）
_CN_STOPWORDS = set("的了和与及或是在为对我你他这那有无疑也都很还再又个把被让使给向从到上下进出过")


def _is_stopword(tok: str) -> bool:
    if not tok:
        return True
    if len(tok) == 1:
        return True
    if all(ch in _CN_STOPWORDS for ch in tok):
        return True
    return False


def _extract_budget(text: str) -> Optional[float]:
    """从需求文本抽预算（元）。支持「预算20万 / 20w / 200k / 预算200000 / 20万」。"""
    low = (text or "").lower()
    m = _BUDGET_PREFIX.search(low)
    if not m:
        m = _BUDGET_UNIT.search(low)          # 万/k（大小写不敏感）
    if not m:
        m = _BUDGET_UNIT_W.search(text or "")  # 小写 w=万：在原文上匹配（大写 W=瓦，360W CPU TDP 不算预算）
    if not m:
        return None
    try:
        num = float(m.group(1))
    except (TypeError, ValueError):
        return None
    unit = (m.group(2) or "").lower()
    if unit in ("万", "w"):
        num *= 10000
    elif unit == "k":
        num *= 1000
    return num


# 内存代际/速率/容量正则（_extract_mem_signal 用）
_MEM_GEN_RE = re.compile(r"DDR?([345])", re.IGNORECASE)
_MEM_SPEED_RE = re.compile(r"(?<![\d])(3200|4400|4800|5200|5600|6400)(?:\s*MT/s?\b|MHz)?", re.IGNORECASE)
_MEM_SIGNAL_RE = re.compile(r"DDR?([345])|\bD[345]\b|内存|memory|\bram\b|rdimm", re.IGNORECASE)
_NUM_GB_RE = re.compile(r"(\d+)\s*GB?\b", re.IGNORECASE)
# 裸容量含 TB："2TB Memory" → 2048GB（R4 修）
_MEM_BARE_TB_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([GT])B?\b", re.IGNORECASE)
# 代际数字紧贴容量（DDR564G = DDR5-64G，DDR[345] 后的数字不算容量）——修"内存 DDR564G*8"误读成 564G
_MEM_BUGGY_STICK_RE = re.compile(r"DDR[345](\d{1,3})\s*GB?\b", re.IGNORECASE)
# 单条容量 × 条数：64G*8 / DDR5 64G*8 / 512G*2 → cap×qty（总量 = 单条 × 条数）
_MEM_STICK_QTY_RE = re.compile(r"(\d{1,3})\s*GB?\b\s*[*×]\s*(\d+)", re.IGNORECASE)
# 反序 条数×单条容量：16×64G = 16 条 × 64G（客户口语/格式变体）
_MEM_STICK_QTY_REV = re.compile(r"(\d+)\s*[*×]\s*(\d{1,3})\s*GB?\b", re.IGNORECASE)
# 远距数量："64GB DDR5-5600B RDIMM服务器内存*24"（*N 在内存字样后，容量被文字隔开）——R3 修
_MEM_FAR_QTY_RE = re.compile(r"(\d{1,3})\s*GB?\b[^\n]{0,24}(?:内存|memory|ram|ddr)[^\n]{0,8}[*×]\s*(\d+)", re.IGNORECASE)
# 无单位「容量×条数 / 条数×容量」："内存：DDR5 32 * 16"（无 GB）→ 大数=容量(32G)、小数=条数(16)
# 2026-08-03 第一轮训练发现：客户常写"32 * 16"不带 GB 后缀，旧正则不识别还引发空指针崩溃。
_MEM_UNITLESS_PAIR_RE = re.compile(r"(\d{1,3})\s*[*×]\s*(\d{1,3})")

# 「字段标签：值」边界（内存：/ 硬盘：/ RAID卡：/ IO1：…），把单行"字段：值"格式切成独立段，
# 避免"内存：DDR5 32*16 硬盘：SATA SSD 960G*2"整段粘连 → 硬盘容量污染内存解析（2026-08-03 训练发现）。
_FIELD_BOUND_RE = re.compile(
    r"(?<![\u4e00-\u9fa5A-Za-z0-9])"                        # 标签前必须是字段边界（防"机|箱："二次切）
    r"(?=[\u4e00-\u9fa5]{1,6}[：:]"                         # 中文标签：内存：/ 电源：/ 机箱：
    r"|[A-Za-z][A-Za-z0-9]{1,7}(?:[\u4e00-\u9fa5])?[：:]"   # 英文/混合标签：CPU：/ RAID卡：/ IO1：
    r")"
)


def _split_requirement_fields(text: str) -> list[str]:
    """把需求文本切成逻辑字段段：换行/逗号/顿号/分号 + 「字段标签：值」冒号边界。

    场景：聊天/表格粘贴把多行折成单行——"机箱：2U CPU：AMD 9654 * 2 内存：DDR5 32 * 16
    硬盘：SATA SSD 960G * 2" 应切成 ["机箱：2U", "CPU：AMD 9654 * 2", "内存：DDR5 32 * 16",
    "硬盘：SATA SSD 960G * 2"]，让内存/硬盘/GPU 组解析互不污染。
    """
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"[\n\r，,、;；]+", text) if p.strip()]
    out: list[str] = []
    for part in parts:
        for sub in re.split(_FIELD_BOUND_RE, part):
            sub = sub.strip()
            if sub:
                out.append(sub)
    return out


def _extract_mem_signal(text: str) -> Optional[dict]:
    """从需求文本提取内存语义 {total_gb, type(DDR4/DDR5), speed}。
    total_gb 取「含内存信号(DDR/D5/内存)的段」里的 G 值，避免误抓 SSD/硬盘容量（如 480G启动盘）。
    无任何内存信号 → None（交回主流程按 spec_rules/代表件处理）。"""
    if not text:
        return None
    gen = _MEM_GEN_RE.search(text)
    mem_type = f"DDR{gen.group(1)}" if gen else (
        "DDR5" if re.search(r"\bD5\b", text, re.IGNORECASE) else
        "DDR4" if re.search(r"\bD4\b", text, re.IGNORECASE) else None
    )
    has_mem_word = bool(_MEM_SIGNAL_RE.search(text))
    # 无"内存/DDR"字样但存在 条数×单条容量（cap≤128G 且条数≥2）→ 服务器内存（R18："24*32G"）
    _bare_stick = False
    if not mem_type and not has_mem_word:
        for _p in (_MEM_STICK_QTY_REV, _MEM_STICK_QTY_RE):
            for _pm2 in _p.finditer(text):
                if _p is _MEM_STICK_QTY_REV:
                    _c, _q = int(_pm2.group(2)), int(_pm2.group(1))
                else:
                    _c, _q = int(_pm2.group(1)), int(_pm2.group(2))
                if _c <= 128 and _q >= 2:
                    _bare_stick = True
                    break
            if _bare_stick:
                break
    if not mem_type and not has_mem_word and not _bare_stick:
        return None
    # 容量：按字段段切（换行/逗号/「字段：值」冒号边界），只取含内存信号的段；无内存段则全文兜底
    segs = _split_requirement_fields(text)
    mem_segs = [s for s in segs if _MEM_SIGNAL_RE.search(s)]
    scope = " ".join(mem_segs) if mem_segs else text
    # 速率：优先取「实际内存行」段（含 条数×N 或 单条容量）——能力声明行
    # （"支持24通道DDR5内存，速率达4800MT/s"）不得抢先实际配置速率（I40）；
    # 无实际行段再回退内存段/全文首个命中。
    def _seg_speed(seg: str) -> Optional[int]:
        m = _MEM_SPEED_RE.search(seg)
        return int(m.group(1)) if m else None

    speed = None
    _actual_mem_segs = [s for s in mem_segs if (
        _MEM_STICK_QTY_RE.search(s) or _MEM_STICK_QTY_REV.search(s)
        or _MEM_FAR_QTY_RE.search(s) or _MEM_UNITLESS_PAIR_RE.search(s)
        or _MEM_BARE_TB_RE.search(s))]
    for _s in (_actual_mem_segs if _actual_mem_segs else mem_segs):
        speed = _seg_speed(_s)
        if speed:
            break
    if speed is None:
        speed = _seg_speed(text)
    # 代际剥离：DDR564G → DDR64G（DDR5 的"5"是代际不是容量），再算容量
    norm = _MEM_BUGGY_STICK_RE.sub(lambda m: f"DDR{m.group(1)}G", scope)
    # 单条容量 × 条数（64G*8 / DDR5 64G*8 / 512G*2 → 总量=单条×条数）
    stick_totals = []
    for m in _MEM_STICK_QTY_RE.finditer(norm):
        cap, qty = int(m.group(1)), int(m.group(2))
        if cap <= 1024 and 1 <= qty <= 64:  # 单条不 >1024G、条数不超 64（双路 32 槽上限）
            stick_totals.append(cap * qty)
    # 反序「条数×单条容量」：16×64G / 2×32G → 总量 = 条数 × 单条
    for m in _MEM_STICK_QTY_REV.finditer(norm):
        qty, cap = int(m.group(1)), int(m.group(2))
        if cap <= 1024 and 1 <= qty <= 64:
            stick_totals.append(qty * cap)
    # 无单位成对（"内存：DDR5 32 * 16" / "DDR5 16*32"）：大数=容量、小数=条数（2026-08-03 修）
    for m in _MEM_UNITLESS_PAIR_RE.finditer(norm):
        a, b = int(m.group(1)), int(m.group(2))
        cap, qty = max(a, b), min(a, b)
        if cap <= 1024 and 1 <= qty <= 64:
            stick_totals.append(cap * qty)
    # 远距数量："64GB …内存*24"（*N 在内存字样后）→ 64×24=1536（R3 修）
    for m in _MEM_FAR_QTY_RE.finditer(norm):
        cap, qty = int(m.group(1)), int(m.group(2))
        if cap <= 1024 and 1 <= qty <= 64:
            stick_totals.append(cap * qty)
    # 无条数的裸容量（"内存 512G"总量写法）兜底
    bare = []
    for m in _MEM_BARE_TB_RE.finditer(norm):  # 2TB → 2048（R4 修：英文总内存写法）
        v = float(m.group(1))
        bare.append(int(v * 1024) if m.group(2).upper() == "T" else int(v))
    # 内存段内无单位纯数字总量（R13/I64）："内存：256" → 256G（客户简写）。
    # 仅当该段无 G/T 单位容量、无 "N×M" 条数时兜底，防误伤 "64G×8" 的 64 / "5600" 速率 / "512GB"。
    if not re.search(r"\d+(?:\.\d+)?\s*[GT](?:B)?\b", scope, re.I) and not re.search(r"\d+\s*[*×]\s*\d+", scope):
        for m in re.finditer(r"(?<![\d.])(\d{2,4})(?![\d.])", scope):
            v = int(m.group(1))
            if 16 <= v <= 1024 * 8 and v not in bare:
                bare.append(v)
    bare = [c for c in bare if c <= 1024 * 8]  # 内存总量上限 8TB
    total = max(stick_totals + bare) if (stick_totals or bare) else None
    if not mem_type and not speed and not total:
        return None
    return {"type": mem_type, "speed": speed, "total_gb": total}


# CPU 双路信号（全套/满配/双路/2颗 → 双 CPU）
_DUAL_CPU_RE = re.compile(r"全套|满配|双路|双\s*CPU|2\s*颗|两颗|2\s*cpu", re.IGNORECASE)


def _extract_cpu_signal(text: str) -> Optional[dict]:
    """从需求文本提取 CPU 信号 {duality}。全套配置/双路/满配/2颗 → duality=True。"""
    if not text:
        return None
    return {"duality": True} if _DUAL_CPU_RE.search(text) else None


# 电源功率（W）：'电源配1300' / '1300W电源' / '1300W' → 1300
# PSU 上下文显式优先（电源/PSU/power/80 Plus/Platinum/Gold/冗余…）——"2* 2000W 80 Plus Platinum" 应取 2000
# 显式上下文窗口不跨句、允许中间出现数字（"2700W 2+2/3+1冗余高效铂金电源"），
# PRE 侧数字后允许可选 W——"电源\n宽448" 不得跨行取到机箱宽度 448（R7 修）
_PSU_EXPLICIT_PRE = re.compile(r"(?:电源|psu|power|80\s*plus|platinum|gold|titanium|redundant)[^\n，。]{0,12}?(\d{3,4})\s*[Ww]?(?:att)?", re.IGNORECASE)
_PSU_EXPLICIT_POST = re.compile(r"(\d{3,4})\s*[Ww](?:att)?[^\n，。]{0,20}?(?:电源|psu|power|80\s*plus|platinum|gold|titanium|redundant)", re.IGNORECASE)
# 裸 W 数字（"1300W"）——仅当全文唯一才认，避免 CPU TDP（"360W"）被误当电源（2026-08-03 R2）
_PSU_BARE_RE = re.compile(r"(\d{3,4})\s*[Ww](?:att)?\b")

# CPU 规格上下文标记：裸 W 数字旁出现这些词 → 判定为 CPU TDP 而非电源瓦数（R3 修）
_CPU_SPEC_CTX_RE = re.compile(r"cpu|ghz|mhz|缓存|物理核|cores?|processor|epyc|xeon|genoa|最大功率|处理器", re.IGNORECASE)


def _extract_psu_signal(text: str) -> Optional[dict]:
    """从需求文本提电源功率 {wattage}。合理服务器 PSU 范围 200-3000W，超范围忽略。

    2026-08-03 R2：优先「电源/PSU/power/80 Plus/Platinum 等上下文」附近的瓦数；
    无上下文时仅当全文只有一个 W 数字才认（"360W" 是 CPU TDP，不能当电源功率）。"""
    if not text:
        return None
    # 双电源/冗余电源 → qty=2（R16）："双电源" 无瓦数也要捕获数量；有瓦数时作为 qty 兜底
    _dual_qty = 2 if re.search(r"双\s*电源|双\s*冗余|冗余|双\s*psu|双\s*power|2\s*个\s*电源|redundant", text, re.I) else None

    def _qty_of(wattage: int) -> Optional[int]:
        # 数量在瓦数前："2* 1300W" / "2×2000W"；或瓦数后："1300W*2" / "2700瓦 白金 热插拔 * 4"（R10/I54）
        m = re.search(r"(\d+)\s*[*×]\s*" + str(wattage) + r"\s*[Ww]", text)
        if m:
            return int(m.group(1))
        m = re.search(
            r"\b" + str(wattage) + r"\s*(?:[Ww](?:att)?|瓦)"
            r"(?:\s*(?:白金|铂金|热插拔|冗余|redundant|platinum|80\s*plus))*\s*[*×]\s*(\d+)", text, re.I)
        if m:
            return int(m.group(1))
        # 冗余 N+M（R28 2026-08-04 ESA24V3-P）："2700W 2+2/3+1冗余" → 2+2=4、"3+1"=4。
        # 4U 8卡机 2+2/3+1 冗余 = 4 个电源（不是双电源 2 个），N+M 直接求和。
        m = re.search(
            r"\b" + str(wattage) + r"\s*(?:[Ww](?:att)?|瓦)?\s*(\d+)\s*\+\s*(\d+)"
            r"\s*(?:/|或)?[^，。\n]{0,8}(?:冗余|redundant|电源|psu|platinum|铂金)", text, re.I)
        if m:
            q = int(m.group(1)) + int(m.group(2))
            if 2 <= q <= 8:
                return q
        return None

    for pat in (_PSU_EXPLICIT_PRE, _PSU_EXPLICIT_POST):
        for m in pat.finditer(text):
            try:
                wattage = int(m.group(1))
            except (TypeError, ValueError):
                continue
            # 240Vdc/220V 是输入电压不是瓦数（R19）：数字后紧跟 V（电压）→ 跳过
            if text[m.end():m.end() + 1].lower() == "v":
                continue
            if 200 <= wattage <= 3000:
                _q = _qty_of(wattage) or _dual_qty
                return {"wattage": wattage, "qty": _q} if _q else {"wattage": wattage}
    # 裸 W 数字：先剔除 CPU-TDP 上下文（GHz/缓存/物理核/cpu/processor…，R3 修）——
    # "2.0GHz_450W" 的 450W 是 CPU TDP 不算电源（R14）；剩下的若唯一才认（"1300W*2"：450W 剔除后 1300W 唯一）
    matches = []
    for _m in _PSU_BARE_RE.finditer(text):
        # 上下文限本行（上一换行到匹配后 20 字符）——60 字符窗口会跨行扫到其他行的 GHz 误判 CPU TDP（R14）
        ctx = text[max(_m.start() - 40, text.rfind("\n", 0, _m.start()) + 1):_m.end() + 20]
        if _CPU_SPEC_CTX_RE.search(ctx):
            continue
        matches.append(_m)
    if len(matches) == 1:
        m = matches[0]
        try:
            wattage = int(m.group(1))
        except (TypeError, ValueError):
            return None
        if 200 <= wattage <= 3000:
            _q = _qty_of(wattage) or _dual_qty
            return {"wattage": wattage, "qty": _q} if _q else {"wattage": wattage}
    # 无瓦数但显式双电源 → 数量 2（瓦数交功耗估算）
    if _dual_qty:
        return {"qty": _dual_qty}
    return None


def _fold_lexicons(lexicons: Optional[list]) -> tuple:
    """把多张词表折叠成 5 个 dict，喂给 extract_keywords。
    - kind=kp          → category_lexicon {品类: [triggers]}（喂 pick_kp_parts）
    - kind=chassis     → chassis_lexicon {底盘件品类: [triggers]}（单独，不喂 pick）
    - kind=server_type → usage_keyword_map {trigger: 类型名}
    - kind=series      → series_keyword_map {trigger: 系列}
    - kind=form        → form_keyword_map {trigger: 形态}
    返回 (cat_lex, chassis_lex, usage_map, series_map, form_map)，均可能为空 dict。"""
    cat_lex, chassis_lex, usage_map, series_map, form_map = {}, {}, {}, {}, {}
    for lex in (lexicons or []):
        kind = lex.get("kind")
        for e in lex.get("entries") or []:
            key = e.get("key")
            triggers = e.get("triggers") or []
            if not key:
                continue
            if kind == "kp":
                cat_lex.setdefault(key, []).extend(triggers)
            elif kind == "chassis":
                chassis_lex.setdefault(key, []).extend(triggers)
            elif kind == "server_type":
                for t in triggers:
                    usage_map[t] = key
            elif kind == "series":
                for t in triggers:
                    series_map[t] = key
            elif kind == "form":
                for t in triggers:
                    form_map[t] = key
    return cat_lex, chassis_lex, usage_map, series_map, form_map


# ── 盘组解析（多盘场景）：每段「容量 + 接口 + 数量」→ 一组 {term, qty, kind} ──
# 解决"一品类只出一个代表件"导致 2×7.68T NVMe + 2×960G SATA 只出 1 件的问题：
# 每盘组独立匹配库件，数量从 qty_per_token（同段关联）取。
_DRIVE_CAPACITY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([GT])(?:B)?", re.IGNORECASE)
_DRIVE_INDICATORS = ("ssd", "hdd", "硬盘", "磁盘", "nvme", "sata", "sas", "存储", "盘", "storage", "drive")


def _normalize_table_rows(text: str) -> str:
    """Markdown/管道表格行归一（R21）—— 单一来源在 requirement_normalizer.normalize_table_rows。
    此薄包装保持既有调用方（extract_keywords / 测试）兼容，不重复实现。"""
    from app.services.requirement_normalizer import normalize_table_rows
    return normalize_table_rows(text)


def _normalize_capacity(term: str) -> str:
    """容量归一："7.68 TB"/"480 GB" → "7.68T"/"480G"（去数字与单位间空格，便于 qty_per_token/库检索）。"""
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([GT])(?:B)?$", term, re.I)
    return f"{m.group(1)}{m.group(2).upper()}" if m else term


def _drive_qty(term: str, qty_per_token: Optional[dict]) -> Optional[int]:
    """盘组数量：归一容量（7.68t/480g）+ 带 B 变体（480gb）+ 纯数字（7.68/480）依次查，
    兼容 "4* 7.68 TB"（数量挂 7.68）与 "2* 480GB"（数量挂 480gb）；无命中 → None（交调用方前缀量词/默认 1）。"""
    qpt = qty_per_token or {}
    low = term.lower()
    for key in (low, low + "b", low.rstrip("gt"), low.rstrip("gtb")):
        v = qpt.get(key)
        if v:
            return int(v)
    return None


# 无单位小数容量兜底（R9/I46 修）："Intel P5510 U.2NVME 3.84*2" 的 3.84 无 T/G 单位 →
# 默认按 TB 处理（硬盘容量为小数必是 TB 级：3.84/1.92/7.68）。只认小数避免把 "*2" 数量当容量。
_DRIVE_CAP_UNITLESS_RE = re.compile(r"(?<![\d*×A-Za-z])(\d+\.\d+)(?![\d.])(?![GT]B?\b)(?!\s*(?:英?寸|inch|in\b))", re.IGNORECASE)
# 无单位整数 + 介质连写（R13/I62）："480SSD*2" → 480G（数字紧跟 SSD/HDD/固态/机械）；"8T HDD" 的 8 不匹配（后跟 T）
_DRIVE_CAP_UNITLESS_INT_RE = re.compile(r"(?<![\d*×A-Za-z])(\d{2,4})(?=\s*(?:GB?)?(?:SSD|HDD|固态|机械))", re.IGNORECASE)


# 盘段合并的组件边界词（R17）：续段含这些词 → 不属于当前盘描述，停止合并（防吞网卡/RAID/GPU 行）
_COMPONENT_BOUNDARY = re.compile(
    r"网卡|nic|网络|以太网|显卡|gpu|rtx|raid|阵列|controller|hba|缓存|电源|psu|内存|memory|风扇|fan|导轨|rail|机箱|chassis|认证|维保|服务|小时|处理器|cpu|光模块|server", re.I)


def _drive_term_gb(term: str) -> int:
    """盘容量串 → GB 整数（'960G'→960；'1.92T'→1966）。解析失败返回 0（不触发默认规则）。"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*([GT])?(?:B)?", str(term), re.I)
    if not m:
        return 0
    v = float(m.group(1))
    return int(v * 1024) if (m.group(2) or "").upper() == "T" else int(v)


def _extract_drive_groups(text: str, qty_per_token: Optional[dict]) -> list[dict]:
    """盘组解析：按字段段切（硬盘：/nvme/sata…），每段可含多个容量，逐容量独立成组。

    2026-08-03 训练修复：
    1) 单行粘连逐段取首个容量漏掉后面的盘 → finditer 取全部容量；
    2) 接口按「容量就近的接口词」判定（不再被整段其他接口词污染）；
    3) R2：容量归一（"7.68 TB"→"7.68T"）使数量/库检索正确；"A or B"（"1.6T or 1.92T"）
       只取首个容量为一组（备选容量不重复出件）。"""
    groups: list[dict] = []
    segs = _split_requirement_fields(text or "")
    # 招标/表格格式：容量常被逗号拆到无盘标识的续段（"配置 2块SATA SSD, 单块容量480GB"）——
    # 把「盘标识段 + 后续无标识续段」合并成一条逻辑盘行（R17）；"2GB 缓存"（RAID 缓存）不并入
    _merged: list[str] = []
    for _seg in segs:
        _low = _seg.lower()
        if (_merged and not any(w in _low for w in _DRIVE_INDICATORS)
                and not _COMPONENT_BOUNDARY.search(_low)):
            _merged[-1] = _merged[-1] + " " + _seg
        else:
            _merged.append(_seg)
    segs = _merged
    for idx, seg in enumerate(segs):
        # U.2/U.3 接口与容量连写归一（R15/复现BUG）："U.21.92T" = U.2 接口 + 1.92T 容量，
        # 容量正则会把 "U.2" 的点和 1.92 合并成 "21.92T"（接口也丢失）→ 拆开再解析。
        # 仅当 u.2/u.3 后紧跟数字才拆（"U.2 NVME 7.68T" 有空格不受影响）。
        seg = re.sub(r"u\.(2|3)(?=\d)", r"u\1 ", seg, flags=re.I)
        low = seg.lower()
        if not low or not any(w in low for w in _DRIVE_INDICATORS):
            continue
        # RAID/HBA 卡段跳过（"LSI 9560-8i 12Gb SAS RAID 卡" / "8口12G SAS RAID控制器" 的
        # 12G 是 SAS 速率不是硬盘容量——R3/R19 修；"RAID1" 级别不带词边界不误伤盘行）
        if re.search(r"raid\s*卡|控制器|阵列|controller|hba|\braid\b", low):
            continue
        or_variant = bool(re.search(r"\bor\b|或", low))
        # 带单位容量 + 无单位兜底（R9/I46 小数；R13/I62 整数+介质连写"480SSD"），位置去重后全量成组
        _cap_pos: set = set()
        cap_items: list = []
        for _src_items in (
                [(m, _normalize_capacity(m.group(0)), True) for m in _DRIVE_CAPACITY_RE.finditer(seg)],
                [(m, f"{m.group(1)}T", False) for m in _DRIVE_CAP_UNITLESS_RE.finditer(seg)],
                [(m, f"{m.group(1)}G", False) for m in _DRIVE_CAP_UNITLESS_INT_RE.finditer(seg)]):
            for _m, _term, _hu in _src_items:
                if _m.start() in _cap_pos:
                    continue
                _cap_pos.add(_m.start())
                cap_items.append((_m, _term, _hu))
        # 接口速率容量过滤（R20）："6GSATA2.5in" 的 6G / "12G SAS" 的 12G 是 6Gb/s/12Gb/s 接口速率
        # 不是盘容量（容量 ≤16G 且后紧跟 SATA/SAS 接口词）
        cap_items = [ci for ci in cap_items
                     if not (float(ci[1].rstrip("GTgt")) <= 16
                             and re.search(r"sata|sas", seg[ci[0].end():ci[0].end() + 8], re.I))]
        caps = [ci[0] for ci in cap_items]
        if or_variant and caps:
            caps = caps[:1]
            cap_items = cap_items[:1]  # "1.6T or 1.92T"：备选容量不重复成组
        # 拼接下一段前 40 字符作数量窗口：容量在段1、*N 在段2（"960GB企业级SSD，2.5寸热插拔*2"——R3 修）
        nxt = segs[idx + 1] if idx + 1 < len(segs) else ""
        window = seg + "\u0001" + nxt[:40]
        caps_all = list(_DRIVE_CAPACITY_RE.finditer(window)) + list(_DRIVE_CAP_UNITLESS_RE.finditer(window))
        for m, term, _has_unit in cap_items:
            qty = _near_qty(window, m.end(), caps_all) or _drive_qty(term, qty_per_token)
            if not qty:
                # 前缀量词 N块/N个/N片/N张（R17 招标："2块SATA SSD" / "2个480G SSD"）；
                # "N个千兆" 是网卡端口不是盘数量（本函数只处理盘段，仍排除千/万/百兆）
                _pre = re.search(r"(?<![0-9])(\d+)\s*(?:块|个|片|张)(?!\s*(?:千兆|万兆|百兆))",
                                 seg[max(0, m.start() - 24):m.end()])
                if _pre:
                    qty = int(_pre.group(1))
            qty = qty or 1
            kind = _drive_kind_near(seg, m.start(), m.end())
            media = _drive_media_near(seg, m.start(), m.end())
            # 无接口 SSD 默认 SATA（I56/R16 复现）：≤960G 的系统盘/启动盘档 SSD 技术员均按 SATA 出；
            # 大容量数据盘（≥1.6T，如 7.68T Enterprise-class SSD）不强制，交规格替代/原逻辑（R2）
            if not kind and media == "SSD" and _drive_term_gb(term) <= 960:
                kind = "SATA"
            _g = {"term": term, "qty": qty, "kind": kind}
            if media:
                _g["media"] = media  # HDD/SSD 介质（R12/I58），仅明确时携带
            groups.append(_g)
    return groups


def _near_qty(seg: str, end: int, caps: list) -> Optional[int]:
    """容量后 30 字符内、且中间没有其他容量的 *N → 该容量数量（跨逗号，R3 修）：
    "960GB企业级SSD，2.5寸热插拔*2" 的 *2 挂在 960G 上；"960G，7.68T * 2" 的 *2 不串给 960G。"""
    tail = seg[end:end + 30]
    tm = re.search(r"[*×]\s*(\d+)(?!\.\d)", tail)  # 排除"4* 7.68"前缀乘号（* 后小数=容量）
    if not tm:
        return None
    pos = end + tm.start()
    for other in caps or []:
        if other.start() > end and other.start() < pos:
            return None
    try:
        q = int(tm.group(1))
    except (TypeError, ValueError):
        return None
    return q if 1 <= q <= 64 else None


def _drive_kind_near(seg: str, start: int, end: int) -> Optional[str]:
    """容量前后的接口词（先前 20 字符，再无则后 20 字符）→ NVMe/SAS/SATA/None。
    只认显式接口词（nvme/u.2/u.3/sata/sas）——"480G SSD" 接口不明 → None（不臆断 SATA）。"""
    head = seg[max(0, start - 24):start].lower()
    tail = seg[end:end + 24].lower()
    for src in (head, tail):
        if re.search(r"nvme|u\.?2|u\.?3", src):
            return "NVMe"
        if "sas" in src:
            return "SAS"
        if "sata" in src:
            return "SATA"
    return None


def _drive_media_near(seg: str, start: int, end: int) -> Optional[str]:
    """容量紧邻窗口的介质词 → HDD/SSD/None（R12/I58、R13/I62）。
    "SATAHDD 8T" → HDD；"SATA SSD 480G" → SSD；"480SSD*2+8T HDD*4" → 480=SSD、8T=HDD
    （紧邻 8 字符窗口，避免段内其他盘的介质词污染）。"""
    head = seg[max(0, start - 24):start].lower()
    tail = seg[end:end + 24].lower()
    for src in (tail, head):  # 容量后优先（"8T HDD" → tail 含 hdd）；前窗口可能被同段其他盘污染
        if "ssd" in src or "固态" in src:
            return "SSD"
        if "hdd" in src or "机械" in src or "氦气" in src:
            return "HDD"
    return None


def _extract_gpu_groups(text: str, qty_per_token: Optional[dict],
                        gpu_triggers: Optional[list], mt_pattern) -> list[dict]:
    """GPU 多规格分组：每段含 GPU 触发词 + 型号 token → 一组 {tokens, qty}。
    "2×NVIDIA RTX 5090 32G 涡轮卡，4×AMD R9700" → 两组，各带数量（与盘组同思路）。
    token 识别用模块 MODEL_TOKEN_PATTERN（含 H100/A100/R9700 单字母+3位数字），
    不依赖可能被改坏的配置正则（配置正则曾丢 H100 分支导致 GPU 型号全丢）。"""
    groups: list[dict] = []
    _tok_re = mt_pattern if mt_pattern is not None else MODEL_TOKEN_PATTERN
    _GPU_OTHER = ("内存", "memory", "ram", "ddr", "硬盘", "ssd", "hdd", "nvme", "sata", "sas",
                  "raid", "阵列", "网卡", "nic", "cpu", "cable", "线缆", "供电", "power")
    _in_gpu = False
    for seg in _split_requirement_fields((text or "").replace("+", "，").replace("＋", "，")):
        seg = seg.strip()
        low = seg.lower()
        if not low:
            _in_gpu = False
            continue
        toks: list[str] = []
        # 复合 GPU 型号优先（R10/I50）："RTX PRO 5000"/"RTX 5090"/"RX 7900" 整段保留在 toks 最前，
        # 避免拆出裸数字 "5000" 被泛匹配到错误件（"RTX 5000 Ada 32G"）；pick 按 toks[0] 精确搜库。
        for _cm in re.finditer(r"(?:RTX|RX|AI)\s+(?:PRO\s+)?\d{3,5}", seg, re.I):
            _ct = _cm.group().strip()
            if _ct.lower() not in [x.lower() for x in toks]:
                toks.append(_ct)
        for _m in re.finditer(r"[0-9A-Za-z][0-9A-Za-z.\-]{1,}", seg):
            _t = _m.group()
            if not (_tok_re.match(_t) or MODEL_TOKEN_PATTERN.match(_t)):
                continue
            if re.match(r"^\d+(?:\.\d+)?[GT]B?$", _t, re.I):  # 纯容量 32G/80G/24GB 不是型号
                continue
            if re.match(r"^\d+[A-Za-z]{2,}$", _t, re.I):  # 数字+单词连写（8GPU/6400MT）不是型号（R7）
                continue
            # 已被复合型号覆盖的裸数字（RTX PRO 5000 里的 5000）不再单独入组，避免泛匹配
            if re.match(r"^\d{3,5}$", _t) and any(re.search(r"\b" + _t + r"\b", t, re.I) for t in toks):
                continue
            if _t.lower() not in [x.lower() for x in toks]:
                toks.append(_t)
        has_gpu_label = any(t and t.lower() in low for t in (gpu_triggers or []))
        if has_gpu_label:
            _in_gpu = True
        elif not (_in_gpu and toks):
            _in_gpu = False
            continue
        # 其他品类标签中断 GPU 延续（"GPU：H100 ×2，AMD R9700 ×4" 第二段无标签仍算 GPU）
        if any(w in low for w in _GPU_OTHER):
            _in_gpu = False
            continue
        if not toks:
            _in_gpu = False
            continue
        # 数量：复合型号 token 无 qty_per_token 键（"RTX PRO 5000"）→ 回退其内裸数字（5000）（R10/I50）
        qty = 1
        _qpt = qty_per_token or {}
        for _t in toks:
            _v = int(_qpt.get(_t.lower()) or 0)
            if _v >= 1:
                qty = _v
                break
            _dm = re.search(r"\d{3,5}", _t)
            if _dm:
                _v = int(_qpt.get(_dm.group(0).lower()) or 0)
                if _v >= 1:
                    qty = _v
                    break
        # 显存容量（GB）：GPU 型号后的 "72G/32G/80GB" 规格（R10/I50，避免 5000 泛命中 48G 件）
        cap = None
        for _cm in re.finditer(r"(\d{1,3})\s*GB?\b", seg, re.I):
            _cap_v = int(_cm.group(1))
            if 8 <= _cap_v <= 256:
                cap = _cap_v
                break
        _g = {"tokens": toks, "qty": qty}
        if cap is not None:
            _g["cap"] = cap
        groups.append(_g)
    return groups


def _cap_gb(raw: str) -> float:
    """容量串 → GB 数值（"960G"→960，"7.68T"→7680；用于延续段大容量判定）。"""
    m = re.match(r"(\d+(?:\.\d+)?)\s*([GT])", raw or "", re.I)
    if not m:
        return 0.0
    n = float(m.group(1))
    return n * 1000 if m.group(2).upper() == "T" else n


def _extract_mem_groups(text: str, qty_per_token: Optional[dict],
                        interrupt_words: Optional[list] = None) -> list[dict]:
    """内存多规格分组：每段含内存信号 + 容量 → 一组 {term, qty}。
    "内存：64G ×8，32G ×8" → 两组；"16×64G DDR5" → {64G, 16}。
    延续规则："内存：64G ×8，32G ×8" 第二段无内存字样但紧接上段 → 仍算内存组；
    出现其他品类标签（CPU/GPU/硬盘/RAID…）则中断延续。
    2026-08-03 第一轮训练修复：
    1) 内存段无 G/T 容量（"内存：DDR5 32 * 16"）不再空指针崩溃；
    2) 无单位成对按「大数=容量、小数=条数」归一（→ {32G, 16}）。"""
    _OTHER_CAT = ("cpu", "gpu", "硬盘", "ssd", "hdd", "nvme", "sata", "sas", "raid", "网卡", "显卡", "盘",
                  "cable", "线缆", "sfp", "aoc", "hba")
    if interrupt_words:
        _extra = [str(w).lower() for w in interrupt_words if str(w).strip()]
        _OTHER_CAT = tuple(dict.fromkeys(_OTHER_CAT + tuple(_extra)))
    groups: list[dict] = []
    _in_mem = False
    for seg in _split_requirement_fields((text or "").replace("+", "，").replace("＋", "，")):
        seg = seg.strip()
        low = seg.lower()
        if not low:
            _in_mem = False
            continue
        # "ram" 用词边界——"Frame" 含 "ram" 子串会误触发内存信号（R2 修）
        has_mem = any(w in low for w in ("内存", "memory", "ddr")) or bool(re.search(r"\bram\b", low))
        # 无"内存/DDR"字样但存在 条数×单条容量（cap≤128G 且条数≥2）→ 服务器内存（R18："24*32G"）
        _bare_stick = False
        if not has_mem:
            for _p in (_MEM_STICK_QTY_REV, _MEM_STICK_QTY_RE):
                for _pm2 in _p.finditer(seg):
                    if _p is _MEM_STICK_QTY_REV:
                        _c, _q = int(_pm2.group(2)), int(_pm2.group(1))
                    else:
                        _c, _q = int(_pm2.group(1)), int(_pm2.group(2))
                    if _c <= 128 and _q >= 2:
                        _bare_stick = True
                        break
                if _bare_stick:
                    break
        # 代际剥离（R9/I46 修）："DDR564G" → "DDR64G"（DDR5 的 5 是代际不是容量），
        # 与 _extract_mem_signal 一致，避免容量被读成 564G 导致 unmatched
        seg = _MEM_BUGGY_STICK_RE.sub(lambda m2: f"DDR{m2.group(1)}G", seg)
        low = seg.lower()
        m = _DRIVE_CAPACITY_RE.search(seg)  # 容量正则通用（G/T/GB/TB）
        pm = _MEM_UNITLESS_PAIR_RE.search(seg) if not m else None  # 无单位成对（32 * 16）
        if has_mem or _bare_stick:
            _in_mem = True
        elif (not m and not pm) or (not _in_mem):
            _in_mem = bool(has_mem)
            continue
        # 延续段容量 ≥480G 是硬盘不是内存条（"1* 960G NMVE"）；服务器内存条 ≤256G（2026-08-03 训练）
        if not has_mem and m and _cap_gb(m.group(0)) >= 480:
            _in_mem = False
            continue
        if any(w in low for w in _OTHER_CAT):
            _in_mem = False
            continue
        # 无显式内存信号的延续段含型号样 token（H100/ConnectX-6/9500-8i/SFP28）→ 中断延续
        # （"1* NVIDIA H100 PCIe 80GB" 的 80GB 不得续成内存组——R2 修）
        if not has_mem and _seg_has_model_token(seg):
            _in_mem = False
            continue
        if m:
            # "2TB Memory RDIMM@128 GB each"：每根 128G、总量 2TB → {128G, 16}（R4 修）
            each_row = _mem_group_from_each(seg)
            if each_row:
                groups.append(each_row)
                continue
            term = _normalize_capacity(m.group(0))  # "64GB"→"64G"：KP 库件名多为 64G（R3 修）
            _qpt = qty_per_token or {}
            qty = (_near_qty(seg, m.end(), [m])
                   or _qpt.get(term.lower())
                   or _qpt.get(term.lower() + "b")
                   or 1)
            # 裸容量 ≥128G 且无条数（qty=1）→ 视为总量写法（"内存：128G DDR5" → 技术员 32G×4），
            # 不产"1 条 128G"单条组（库无 128G 单条会 unmatched），交给 mem_signal 总量反推（R10/I51）
            if qty == 1 and _cap_gb(m.group(0)) >= 128:
                continue
            groups.append({"term": term, "qty": qty})
        elif pm:
            a, b = int(pm.group(1)), int(pm.group(2))
            cap, qty = max(a, b), min(a, b)
            if cap <= 1024 and 1 <= qty <= 64:
                groups.append({"term": f"{cap}G", "qty": qty})
    return groups


def _mem_group_from_each(seg: str) -> Optional[dict]:
    """英文内存写法 "2TB Memory RDIMM@128 GB each" → {term:"128G", qty:16}（总量÷每根，R4 修）。
    含 "each" 时：取离 each 最近的容量为每根容量，另一容量为总量；无总量/数量不合理返回 None。"""
    low = seg.lower()
    each_idx = low.find("each")
    if each_idx < 0:
        return None
    caps = list(_DRIVE_CAPACITY_RE.finditer(seg))
    if len(caps) < 2:
        return None
    per = min(caps, key=lambda cm: abs(cm.start() - each_idx))
    total = caps[1] if per is caps[0] else caps[0]  # per 之外的另一个容量=总量

    def _gb(cm) -> Optional[float]:
        m = re.match(r"^(\d+(?:\.\d+)?)\s*([GT])(?:B)?$", cm.group(0), re.I)
        if not m:
            return None
        n = float(m.group(1))
        return n * 1024 if m.group(2).upper() == "T" else n

    total_gb, per_gb = _gb(total), _gb(per)
    if not total_gb or not per_gb or per_gb <= 0:
        return None
    qty = int(round(total_gb / per_gb))
    if not (1 <= qty <= 64):
        return None
    return {"term": _normalize_capacity(per.group(0)), "qty": qty}


def _seg_has_model_token(seg: str) -> bool:
    """段内是否含「型号样 token」（H100/9500-8i/SFP28/ConnectX-6/P5620…）。
    纯容量（32G/7.68T/25G）与纯数字不算——用于中断内存延续（2026-08-03 R2）。"""
    for _m in re.finditer(r"[0-9A-Za-z][0-9A-Za-z.\-]{1,}", seg):
        _t = _m.group()
        if re.match(r"^\d+(?:\.\d+)?[GT]B?$", _t, re.I):  # 纯容量
            continue
        if re.match(r"^\d+$", _t):  # 纯数字：<4 位不算型号（16/32 是数量/容量），≥4 位是型号（4500/9254/9654）
            if len(_t) < 4:
                continue
        if MODEL_TOKEN_PATTERN.match(_t):
            return True
    return False


# "接口+容量"连写碎片（SATASSD480G / U.2NVME7.68T）不是型号——容量归盘组解析，
# 避免当型号搜库报 unmatched 噪音（2026-08-03 第五轮训练发现）
_DRIVE_CAP_TOKEN_RE = re.compile(r"^(?:SATA|SAS|NVME?|U\.?2|SSD|HDD)[A-Za-z]*\d+(?:\.\d+)?[GT]B?$", re.IGNORECASE)

_NIC_SPEED_WORDS = (("万兆", "10G"), ("千兆", "1G"), ("百兆", "100M"))


# RAID 卡显式型号分组（2026-08-04 ESA24V3-P R28）：需求逐行给阵列卡型号（"RAID卡：LSI 9560 16i 8G缓存 *1"）
# → 每组 {model, qty, cache}，让 pick 按具体型号精确匹配，不再落到品类代表件（9540-8i 泛配）。
_RAID_MODEL_INLINE_RE = re.compile(r"(?:LSI|Broadcom|MegaRAID|Adaptec)?\s*(\d{4})\s*-?\s*(\d{1,2})\s*[iI]\b", re.I)


def _extract_raid_groups(text: str) -> list[dict]:
    """RAID 卡显式型号分组：'RAID卡：LSI 9560 16i 8G缓存 *1' → [{model:'9560-16i', qty:1, cache:'8'}]。
    型号归一：'9560 16i'/'9560-16i'/'9560 16I' → '9560-16i'（对齐配件库件名 LSI 9560-16i）。
    无显式型号（'RAID 0,1,10'）→ 空列表，交回 I22 applicable 兼容机型选件。"""
    if not text:
        return []
    groups: list[dict] = []
    for m in re.finditer(r"(?:raid\s*卡|阵列卡|raid\s*controller|raid\s*控制器|阵列控制器|控制器)(?:[：:\s]*)([^\n，,;；]+)", text, re.I):
        seg = m.group(1)
        mm = _RAID_MODEL_INLINE_RE.search(seg)
        if not mm:
            continue
        model = f"{mm.group(1)}-{mm.group(2)}i"
        qty = 1
        mq = re.search(r"[*×]\s*(\d+)(?!\s*(?:[GTgt][Bb]?|[Ww](?:att)?|mhz|ghz))", seg)
        if mq and int(mq.group(1)) >= 1:
            qty = int(mq.group(1))
        cache = None
        mc = re.search(r"(\d+)\s*[GT]?B?\s*缓存", seg, re.I)
        if mc:
            cache = mc.group(1)
        existing = next((g for g in groups if g["model"] == model), None)
        if existing:
            existing["qty"] += qty
        else:
            groups.append({"model": model, "qty": qty, "cache": cache})
    return groups


def _nic_line_filters(seg: str, opt_tail: str = "") -> Optional[dict]:
    """单行网卡描述 → 过滤组 {filters, qty?, name_contains?}。

    "网卡：25G双口含光模块*1" → filters=[{Link Speed=25G},{Ports=2}], qty=1,
                                  name_contains=["光模块"]。
    "网卡：CX5 25G双口含光模块*2" → name_contains=["cx5","光模块"]（用户写了具体型号优先精确匹配）。
    速率：万兆/千兆/百兆中文别名，或字面 25G/100G/10G 等；
    端口：4口/四口/4port → 4，双口/2口 → 2，单口/1口 → 1；
    数量：行内 *N/×N 后缀（未写默认 1）；
    含光模块：行内出现 光模块/模块 → 优先选带光模块的库件。
    """
    if not seg or not seg.strip():
        return None
    filters: list[dict] = []
    line: dict = {"filters": filters}
    # 速率
    speed = None
    for w, v in _NIC_SPEED_WORDS:
        if w in seg:
            speed = v
            break
    if speed is None:
        # 行内多速率（"10/25GE"、"10G/25G"）→ 取最大（技术员按 25G 卡出，R17）；
        # 支持 10GE/25GE/100GE（E 后缀）
        _speeds = [int(x.group(1)) for x in re.finditer(r"(?<!\d)(\d{1,3})\s*[Gg][Bb]?[Ee]?(?:ps)?(?![0-9A-Za-z.])", seg)
                   if 1 <= int(x.group(1)) <= 400]
        if _speeds:
            speed = f"{max(_speeds)}G"
    if speed:
        filters.append({"spec_key": "Link Speed", "op": "=", "value": speed})
    # 端口：兼容 "4口/四口/N port" 与 "4个千兆/4个万兆/4个百兆"（R10/I52）
    ports = None
    m = re.search(r"(?:四|4)\s*口|(\d+)\s*ports?\b|(?:四|4)\s*个?\s*(?:千兆|万兆|百兆)", seg)
    if m:
        ports = m.group(1) if m.lastindex and m.group(1) else "4"
    elif re.search(r"双|dual|2\s*口", seg):
        ports = "2"
    elif re.search(r"单|1\s*口", seg):
        ports = "1"
    else:
        # 字母 x 前缀「N x 速率」= N 端口（"2 x 25 GB SFP28" 双口 idiom，R4/I20）——
        # 与符号乘号（* / × = 卡数量）区分：2 x 25G = 1 张双口卡，不是 2 张卡。
        _m = re.search(r"(?<![0-9A-Za-z*×])(\d{1,2})\s*[xX]\s*\d{1,3}\s*[Gg][Bb]?(?:ps)?(?![0-9A-Za-z.])", seg)
        if _m:
            ports = _m.group(1)
    if ports:
        filters.append({"spec_key": "Ports", "op": "=", "value": ports})
    # 具体网卡型号（ConnectX-6/CX5/i350/X710/E810/SFP28…）：用户写了型号/端口类型时精确优先，
    # 不落到通用速率过滤。判据放宽到「字母+数字混合」并排除规格碎片（25G/1000M/960/2port），
    # 因为 cx5/cy5 这类短型号不满足通用 MODEL_TOKEN_PATTERN（R5 保 R1/R4 行为）。
    models: list[str] = []
    for _m in re.finditer(r"[0-9A-Za-z][0-9A-Za-z.\-]{1,}", seg):
        _t = _m.group().lower().replace("\u2011", "-")
        _t = re.sub(r"^mcx(\d+)$", r"cx\1", _t)  # MCX5→CX5（Mellanox ConnectX 别名，R9/I46）
        # Intel NIC SKU 后缀归一（R28 2026-08-04 ESA24V3-P）："X710DA2BLK" → "x710da2"
        # （BLK 是包装形态后缀，配件库件名是 "X710-DA2"）；连字符保留（ConnectX-6 形态），
        # 匹配侧（pick_kp_parts _has_all）再统一去连字符比较，两边归一一致。
        _t = re.sub(r"(?i)(?:-?blk|-?box|-?bulk)$", "", _t)
        if not (re.search(r"[a-z]", _t) and re.search(r"\d", _t)):
            continue
        if re.match(r"^\d+(?:\.\d+)?[GT]B?$|^\d+[Mm]$|^\d+$|^\d+\s*port", _t, re.I):  # 25G/1000M/960/2port 碎片
            continue
        models.append(_t)
    name_terms: list[str] = list(dict.fromkeys(models))
    if "光模块" in seg or "光模" in seg or "光口含模块" in seg or "含模块" in seg \
       or "带模块" in seg or "optical" in seg or "module" in seg or \
       (opt_tail and re.search(r"光模块|光模|光口含模块|含模块|带模块|optical|module", opt_tail, re.I)):
        name_terms.append("光模块")
    # OCP 形态（R8/I45 修）："OCP双口25G" → 优先选 OCP 版网卡（25G 2port+光模块 OCP3.0），
    # 不落通用 PCIe 网卡。KP 库 OCP 特征在件名（"…OCP3.0"），用 name_contains 过滤。
    if re.search(r"ocp", seg):
        name_terms.append("OCP")
    if name_terms:
        line["name_contains"] = name_terms
    if not filters and not name_terms:
        return None
    # 数量（I37）：后缀 型号*N（"25G双口含光模块*2"）或 前缀 N* 型号（"2* ConnectX-6"）。
    # 前缀式含 x 乘号（"2x 25G NIC"）；数量 0 无意义（"PCIe4.0 x16" 的 0x16 不当数量）。
    mq = re.search(r"[*×]\s*(\d+)(?!\s*(?:[GTgt][Bb]?|[Ww](?:att)?|mhz|ghz|小时|h\s*rs?|维保|服务)(?![0-9A-Za-z]))", seg)
    if not mq:
        mq = re.search(r"(?<![0-9A-Za-z*×])(\d+)\s*[*×]", seg)  # 符号乘号=卡数量；字母 x 是端口语义（I20），见上方端口解析
    if not mq:
        # 量词 N块/N张/N片；"N个千兆/万兆/百兆" 是端口数不是卡数量（R10/I52）
        mq = re.search(r"(?<![0-9A-Za-z])(\d+)\s*(?:块|张|片)", seg)
    if not mq:
        mq = re.search(r"(?<![0-9A-Za-z])(\d+)\s*个(?!\s*(?:千兆|万兆|百兆))", seg)
    if mq and int(mq.group(1)) >= 1:
        line["qty"] = int(mq.group(1))
    return line


def _extract_nic_line_filters(low: str, triggers: list) -> list[dict]:
    """按网卡行提取多张网卡各自的「速率+端口」过滤组（2026-08-03 R5）。

    需求里可同时要多张不同速率/端口的网卡（千兆4口 + 25G双口 + 100G双口…），
    每出现一个网卡触发词（网卡/nic/网络/connectx…）就是一行，独立产出一张卡。
    行边界：该触发词所在的连续片段（前后到分隔符/上一个触发词），兼容
    "网卡：25G双口…" 与 "25G双口网卡" 两种写法。
    """
    hits: list[tuple[int, int]] = []
    for t in triggers or []:
        t = str(t).lower()
        if not t:
            continue
        for m in re.finditer(re.escape(t), low):
            hits.append((m.start(), m.end()))
    hits.sort()
    if not hits:
        return []
    # 行分隔符只认 逗号/顿号/换行——":" "；" ";" 是「字段」分隔符（"网卡;100G双口" 的 ; 后面是速率），
    # 紧跟在触发词后会被误切段（R5：网卡;100G 段被截成 "网卡" 导致 100G 网卡丢失）
    _DELIM = "，,、\n\r"
    lines: list[dict] = []
    line_keys: list[tuple] = []  # (触发词位置, 子段序号)：➕ 拆出的多卡同物理行但不同子段 → 都保留
    for i, (st, en) in enumerate(hits):
        # 右边界：下一个触发词，或行内第一个分隔符
        r_end = hits[i + 1][0] if i + 1 < len(hits) else len(low)
        dm = re.search(rf"[{_DELIM}]", low[en:r_end])
        if dm:
            r_end = en + dm.start()
        # 左边界：上一个分隔符之后；无分隔符时从上一个触发词之后开始（防跨行串扰）
        l_start = 0
        if i > 0:
            l_start = hits[i - 1][1]
        _dl_last = None
        for _m in re.finditer(rf"[{_DELIM}]", low[:st]):
            _dl_last = _m
        if _dl_last and _dl_last.end() >= l_start:
            l_start = _dl_last.end()
        seg = low[l_start:r_end]
        # 逗号续段含 光模块/数量（R23）："网卡：10G 万兆网卡, PCIe4.0 适配 (含光模块) *3"
        # 逗号是行分隔符会切段 → 光模块信号丢失 → 把续段文本传给 _nic_line_filters 补回 name_contains。
        # 续段边界 = 触发词后的首个换行（只吞同行逗号续段，不跨到下一行，避免误给上一行网卡补光模块）。
        _nl_m = re.search(r"[\n\r]", low[st:])
        _nl_end = st + _nl_m.start() if _nl_m else len(low)
        _opt_tail = low[r_end:_nl_end] if _nl_end > r_end else ""
        # 段内多卡（R13/I63）："网络：四口千兆➕双口万兆含光模块" 一个字段含两张卡（➕/＋ 分隔）
        _sub_segs = re.split(r"[➕＋]", seg)
        for _si, _ss in enumerate(_sub_segs):
            line = _nic_line_filters(_ss.strip(), opt_tail=_opt_tail)
            if line:
                lines.append(line)
                line_keys.append((st, _si))
    # 去重一：同一物理行多个触发词（"2* ConnectX-6 Dx dual 25G SFP28" 的 connectx+sfp28）
    # 会产出多个 seg——后一个 seg 从上一触发词后开始，前缀数量（"2* "）被切掉 → qty 丢失、
    # 回退 qty_map 出 ×1 多余行（I37）。按「触发词所在物理行文本 + 子段序号」去重：
    # 同触发词的 ➕ 多卡（子段 0/1）保留，I37 的双触发词（子段都 0）只留最先一行（带数量）。
    _seen_lines: set = set()
    _span_uniq: list[dict] = []
    for _line, (_st, _si) in zip(lines, line_keys):
        # 物理行文本：触发词向两侧扩展到最近的分隔符（行首/行尾）
        _ls_m = [m for m in re.finditer(rf"[{_DELIM}]", low[:_st])]
        _ls = _ls_m[-1].end() if _ls_m else 0
        _le_m = re.search(rf"[{_DELIM}]", low[_st:])
        _le = _st + _le_m.start() if _le_m else len(low)
        # 子段号 = 物理行内 ➕/＋ 累计数 + 段内子段序号（2026-08-04 R22 修复）：
        # 触发词含速率词（千兆/万兆）后，同物理行「千兆➕万兆」两卡被切到不同段，
        # 若只按「物理行+段内序号」去重会误判重复只留一张 → 用物理行内 ➕ 位置区分。
        _sub_no = sum(1 for _m in re.finditer(r"[➕＋]", low[_ls:_st])) + _si
        _fl = f"{low[_ls:_le]}|{_sub_no}"
        if _fl in _seen_lines:
            continue
        _seen_lines.add(_fl)
        _span_uniq.append(_line)
    # 去重二：同一触发词复合词内多次出现（"网卡模块:10G万兆以太网卡" 的 网卡 出现 2 次）
    # 会产生同速率同数量的重复行 → 只保留一份（R3 回归：10G 网卡被拆成两行）
    _seen: set = set()
    _uniq: list[dict] = []
    for _line in _span_uniq:
        _sig = (tuple((f.get("spec_key"), f.get("value")) for f in _line.get("filters") or []),
                _line.get("qty"),
                tuple(_line.get("name_contains") or []))
        if _sig in _seen:
            continue
        _seen.add(_sig)
        _uniq.append(_line)
    return _uniq


def extract_keywords(text: str, lexicon: Optional[dict] = None, keyword_limit: int = 12,
                     series_keyword_map: Optional[dict] = None,
                     usage_keyword_map: Optional[dict] = None,
                     form_keyword_map: Optional[dict] = None,
                     chassis_lexicon: Optional[dict] = None,
                     spec_aliases: Optional[list] = None,
                     qty_units: Optional[list] = None,
                     qty_multipliers: Optional[list] = None,
                     model_token_regex: Optional[str] = None) -> dict:
    """从需求文本提取关键词、品类、系列、形态。

    Returns: {keywords:[...], categories:[...], series, form}
    """
    text = (text or "").strip()
    # 盘接口常见拼写颠倒归一（"960G NMVE"→NVMe），否则盘组/接口识别全部落空（2026-08-03 训练）
    text = text.replace("NMVE", "NVMe")  # 常见拼写颠倒（"960G NMVE"），R6 修
    # 英文端口词（SFP28/QSFP28）是网卡信号——配置词表缺时兜底（R4 修："2 x 25 GB SFP28"）
    if lexicon is not None:
        lexicon = {k: list(v) for k, v in lexicon.items()}
        _nic_toks = lexicon.setdefault("Network(NIC) requirement", [])
        for _tok in ("sfp28", "qsfp28", "qsfp"):
            if not any(str(t).lower() == _tok for t in _nic_toks):
                _nic_toks.append(_tok)
    series: Optional[str] = None
    form: Optional[str] = None
    categories: list[str] = []
    keywords: list[str] = []

    if not text:
        return {"keywords": [], "categories": [], "series": None, "form": None,
                "usage": None, "server_type_name": None, "chassis_categories": [],
                "qty_map": {}, "qty_per_token": {}, "spec_search_terms": set(), "budget": None,
                "mem_signal": None, "cpu_signal": None, "multi_spec_filters": {}, "psu_signal": None,
                "usage_inferred": False}

    text = _normalize_table_rows(text)
    low = text.lower()

    # 型号 token 正则（model_token_regex 可配，None→模块常量 MODEL_TOKEN_PATTERN 兜底；和 pick_kp_parts 同源）
    _mt_pattern = MODEL_TOKEN_PATTERN
    if model_token_regex:
        try:
            _mt_pattern = re.compile(model_token_regex)
        except Exception as e:
            logger.warning("model_token_regex 编译失败，用默认: %s", e)

    # 品类命中（lexicon 可来自 reasoning_flow 配置；None=用模块 CATEGORY_LEXICON）
    for cat, toks in (lexicon if lexicon is not None else CATEGORY_LEXICON).items():
        if any(t in low for t in toks):
            categories.append(cat)
            keywords.extend(t for t in toks if t in low)

    # RAID 级别（RAID1/5/10…）不是阵列卡需求——"2*480GB SATA SSD（RAID1）"不得触发 Raid card 品类（2026-08-03 R2）
    if "Raid card" in categories:
        _has_raid_word = any(t in low for t in ("阵列", "阵列卡", "raid卡", "raid controller", "raid控制", "控制器", "mega", "brocade"))
        if not _has_raid_word and re.search(r"raid\s*\d", low):
            categories.remove("Raid card")

    # 机箱底盘件命中（单独存 chassis_categories，不进 pick_kp_parts 的 categories——KP 库无底盘件，进了只制造 unmatched）
    chassis_categories: list[str] = []
    if chassis_lexicon:
        for cat, toks in chassis_lexicon.items():
            if any(t in low for t in toks):
                chassis_categories.append(cat)

    # 规格别名（千兆/万兆等规格描述 → 品类 + 搜索词；救 ILIKE 命不中的规格词，库 model 是英文不含"千兆"）
    spec_search_terms: set[str] = set()
    multi_spec_filters: dict[str, list[dict]] = {}
    if spec_aliases:
        for _alias in spec_aliases:
            _trig = (_alias.get("trigger") or "").lower()
            if _trig and _trig in low:
                _cat = _alias.get("category") or ""
                if _cat and _cat not in categories:
                    categories.append(_cat)
                for _term in (_alias.get("search_terms") or []):
                    if _term and _term.lower() not in {k.lower() for k in keywords}:
                        keywords.append(_term)
                        spec_search_terms.add(_term.lower())
                # 同品类多规格（如千兆+万兆网卡）：收集 spec_filter，pick stage2 按速率各产出一件
                _sf = _alias.get("spec_filter")
                if _cat and isinstance(_sf, dict) and _sf.get("spec_key"):
                    multi_spec_filters.setdefault(_cat, []).append(_sf)

    # 网卡多卡行（R5）：需求可同时要多张不同速率/端口的网卡（千兆4口 + 25G双口 + 100G双口…）。
    # 按每个网卡触发词一行提取「速率+端口」过滤组并替换 alias 的单一速率过滤——alias 只认
    # 千兆/万兆/百兆中文词，25G/100G 字面速率和端口数（4口/双口）需要按行解析；行内"含光模块"
    # 通过 name_contains 让 pick 优先选带光模块的库件。
    if "Network(NIC) requirement" in categories:
        _nic_triggers = (lexicon if lexicon is not None else CATEGORY_LEXICON).get("Network(NIC) requirement") or []
        _nic_lines = _extract_nic_line_filters(low, _nic_triggers)
        _alias_nic = multi_spec_filters.get("Network(NIC) requirement") or []
        if _nic_lines:
            # alias 速率 filter 未被行解析覆盖时补位（R22："双口万兆" 无网卡/网络触发词时靠 alias 兜底出 10G）
            _covered = set()
            for _ln in _nic_lines:
                for _f in (_ln.get("filters") or []):
                    if _f.get("spec_key") == "Link Speed":
                        _covered.add(str(_f.get("value")))
            _merged = list(_nic_lines)
            for _af in _alias_nic:
                _v = (_af or {}).get("value")
                if _v and str(_v) not in _covered:
                    _merged.append(_af)
            multi_spec_filters["Network(NIC) requirement"] = _merged
        else:
            multi_spec_filters["Network(NIC) requirement"] = _alias_nic

    # 数量解析（位置绑定）：每个数量(*N/×N/N+量词) 绑到【最近的品类触发词】。
    # 比旧"分段法"稳健——兼容前缀式「2块480G SSD」「8块GPU」(数量在品类词前) 和后缀式「64G*8」，
    # 不再把「块」固定映射 CPU（那是串台根因：8块GPU 漏成×1、2块SSD 反盗内存的 16）。
    _multipliers = list(qty_multipliers or ["*", "×"])
    if not any(str(m).lower() == "x" for m in _multipliers):
        _multipliers.append("x")  # 英文 "2x 32 core"（小写 x 乘号，R4 修；大写 X 排除防 RTX/CX5 误判）
    _multis = "".join(re.escape(_m) for _m in _multipliers)
    qty_map: dict[str, int] = {}
    qty_per_token: dict[str, int] = {}  # 型号 token → 附近 qty（精确到件）
    if lexicon:
        _trigger_to_cat = {t.lower(): c for c, toks in lexicon.items() for t in toks}
        _trig_hits: list[tuple[int, str]] = []
        for _trig, _cat in _trigger_to_cat.items():
            for _m in re.finditer(re.escape(_trig), low):
                _trig_hits.append((_m.start(), _cat))
        _trig_hits.sort()
        # 量词字符（从 qty_units 取，兜底默认）；只用来识别"数量"，不再映射到固定品类
        _unit_chars = "|".join(re.escape(u.get("unit", ""))
                               for u in (qty_units or [{"unit": k} for k in QTY_UNIT_TO_CAT])
                               if u.get("unit")) or "块|条|颗|个|张|台"
        # 收集数量出现位置 + 方向：后缀 *N/×N(型号在后→绑前面品类) 或 前缀 N量词(型号在后→绑后面品类)
        _mult_cls = "".join(set(_multipliers))  # 原始乘号字符(给字符类用，含 x)
        _qty_hits: list[tuple[int, int, str]] = []
        # 后缀 *N/×N：排除「×N 后紧跟容量/型号」的假阳性——"16×64G"、"2×7.68T"、"2×960G" 的 ×N
        # 是「数量×容量/型号」里的容量/型号部分（真实数量在 × 前面），不是后缀数量。
        # R4：乘号前是数字（"2x 32 core" 的 x 前是 2）不算后缀；N 后跟容量/速率（"2 x 25 GB"）不算数量。
        # R5：符号乘号（* ×）与字母乘号（x）分开处理——* 没有单词边界问题，紧跟单位字母/数字的
        #   "3.0GHz* 2"（R5）、"32G* 4"、"RAID 0,1,10* 1" 也必须是后缀数量（旧 (?<![0-9a-z]) 全挡了）；
        #   x 仍需排除单词内字母（"rtx 5090"）与 "2x 32 core"（x 前是数字 = 前缀式）。
        # 后缀 N 后跟容量/速率（16×64G / 2×7.68T / 2 x 25 GB）与瓦数（2* 2000W）都不是数量。
        _sym_multis = "".join(re.escape(_m) for _m in _multipliers if not _m.isalpha())
        _x_multis = "".join(re.escape(_m) for _m in _multipliers if _m.isalpha())
        _suf_excl = r"(?!\s*(?:[GTgt][Bb]?|[Ww](?:att)?|mhz|ghz|小时|h\s*rs?|维保|服务)(?![0-9A-Za-z]))"
        # 电源数量由 psu_signal 管（R10/I54）：*N 前 24 字符含 电源/瓦/白金/热插拔 → 不进 qty_map，
        # 否则 "2700瓦 白金 热插拔 * 4" 的 4 会串绑到最近的 kp 触发词（网口→NIC=4）
        _PSU_CTX = re.compile(r"电源|psu|瓦|白金|热插拔|redundant|platinum|80\s*plus", re.I)
        if _sym_multis:
            for _m in re.finditer(rf"[{_sym_multis}]\s*(\d+)(?![0-9A-Za-z.]){_suf_excl}", low):
                if _PSU_CTX.search(low[max(0, _m.start() - 24):_m.start()]):
                    continue
                _qty_hits.append((_m.start(), int(_m.group(1)), 'suf'))
        if _x_multis:
            for _m in re.finditer(rf"(?<![0-9a-z])[{_x_multis}]\s*(\d+)(?![0-9A-Za-z.]){_suf_excl}", low):
                # PCIe 槽位规格（"pcie x16"/"PCIe x8"/"PCle5.0 x16"）的 xN 是通道数，不是数量（I37）：
                # x 前 14 字符内出现 pcie/pci-e/pcle/pci[空格-] → 跳过。英文 "cards x 2" 不受影响。
                if re.search(r"pcie|pci-e|pcle|pci[ -]", low[max(0, _m.start() - 14):_m.start()], re.I):
                    continue
                if _PSU_CTX.search(low[max(0, _m.start() - 24):_m.start()]):
                    continue
                _qty_hits.append((_m.start(), int(_m.group(1)), 'suf'))
        if _x_multis:
            for _m in re.finditer(rf"(?<![0-9a-z])[{_x_multis}]\s*(\d+)(?![0-9A-Za-z.]){_suf_excl}", low):
                # PCIe 槽位规格（"pcie x16"/"PCIe x8"/"PCle5.0 x16"）的 xN 是通道数，不是数量（I37）：
                # x 前 14 字符内出现 pcie/pci-e/pcle/pci[空格-] → 跳过。英文 "cards x 2" 不受影响。
                if re.search(r"pcie|pci-e|pcle|pci[ -]", low[max(0, _m.start() - 14):_m.start()], re.I):
                    continue
                _qty_hits.append((_m.start(), int(_m.group(1)), 'suf'))
        # 前缀式 N量词：负向回望排除「×8条」这种后缀式(乘号+数+量词)，否则 8条 会重复匹配串到后面品类；
        # 再排除 "N个千兆/万兆/百兆"（端口数，不是卡数量，R10/I52）
        for _m in re.finditer(rf"(?<![{_mult_cls}])(\d+)\s*(?:{_unit_chars})(?!\s*(?:千兆|万兆|百兆))", low):
            _qty_hits.append((_m.start(), int(_m.group(1)), 'pre'))
        # 前缀式 N×M（N 是数量，M 是容量/型号）："16×64G DDR5" / "2×7.68T NVMe" / "2×960G SATA" /
        # "8×NVIDIA RTX" / "2×AMD EPYC"。绑 × 之后最近的品类（pre 方向）。
        _cap_mult = rf"(?<![0-9{_mult_cls}])(\d+)\s*[{_multis}]\s*\d+(?:\.\d+)?\s*[GTgt](?:[Bb])?\b"
        # I20：字母 x「N x 速率」是端口 idiom（"2 x 25 GB SFP28" = 双口 25G，1 张卡）不是卡数量。
        # 判别：x 后是 G/T 速率且附近有网卡上下文（sfp28/网卡/双口…）→ 跳过全局数量绑定，
        # 交由 _nic_line_filters 行级端口解析；"2×480GB SSD"（盘）不受影响。
        _NIC_CTX_AFTER = re.compile(r"sfp28|qsfp|网卡|nic|光模块|双口|单口|ethernet|ports?", re.I)
        for _m in re.finditer(_cap_mult, low):
            if _NIC_CTX_AFTER.search(low[_m.end():_m.end() + 24]):
                continue
            _qty_hits.append((_m.start(), int(_m.group(1)), 'pre'))
        # R10/I54：符号乘号 *× 后只认「字母开头」的型号/词（"8×NVIDIA RTX"/"2×AMD EPYC"）；
        # "9354 * 2"（* 后是纯数字）→ 9354 是型号不是数量，否则 qty_map[Memory]=9354 污染。
        if _sym_multis:
            for _m in re.finditer(rf"(?<![0-9{_mult_cls}])(\d+)\s*[{_sym_multis}]\s*(?=[A-Za-z])", low):
                _qty_hits.append((_m.start(), int(_m.group(1)), 'pre'))
        # 字母乘号 x 后保留数字（R4："2x 32 core 9005series" 的 2 是数量、32 是核数）；
        # I20：x 后是速率且带网卡上下文（"2 x 25 GB SFP28"）→ 端口 idiom 不是卡数量，跳过
        if _x_multis:
            for _m in re.finditer(rf"(?<![0-9a-z])(\d+)\s*[{_x_multis}]\s*(?=[0-9A-Za-z])", low):
                if _NIC_CTX_AFTER.search(low[_m.end():_m.end() + 24]):
                    continue
                _qty_hits.append((_m.start(), int(_m.group(1)), 'pre'))

        def _bind_cat(pos: int, direction: str) -> Optional[str]:
            # 方向感知：suf(型号*N)→取数量【之前】最近的品类词；pre(N量词 型号)→取【之后】最近。
            # 不区分方向会把「8块GPU」的 8 串到紧邻的「网卡」(NIC=8 那个 bug)。
            if not _trig_hits:
                return None
            if direction == 'suf':
                before = [c for p, c in _trig_hits if p < pos]
                return before[-1] if before else _trig_hits[0][1]
            after = [c for p, c in _trig_hits if p > pos]
            return after[0] if after else None  # 无后续触发词不硬绑（R10/I54：防 "4个千兆" 串到 raid）

        _DELIM = "，,、;；\n\r"
        for _qpos, _qval, _qdir in _qty_hits:
            if _qval < 1:
                continue  # 数量 0 无意义；"PCle5.0x16" 的 0x16 不得当数量（R7）
            _cat = _bind_cat(_qpos, _qdir)
            if _cat and _cat not in qty_map:
                qty_map[_cat] = _qval
            # 型号 token 关联此 qty（pick stage-1 精确到件）——只取【同段】token，避免跨条目串扰：
            # pre（N×M / N量词）：数量在前 → 取 [数量, 下一分隔符)；suf（容量×N）：数量在后 → 取 [上一分隔符, 乘号)
            if _qdir == 'pre':
                _rest = low[_qpos + 1:]
                _end = re.search(rf"[{_DELIM}]", _rest)
                _seg = low[_qpos: _qpos + 1 + (_end.start() if _end else 24)]
            else:
                _head = low[max(0, _qpos - 24): _qpos]
                _st = re.search(rf"[{_DELIM}]", _head)
                _seg = _head[_st.end() if _st else 0:]
            for _tm in re.finditer(r"[0-9A-Za-z][0-9A-Za-z.\-]{1,}", _seg):
                _t = _tm.group().lower()
                if _mt_pattern.match(_t) and _t not in qty_per_token:
                    qty_per_token[_t] = _qval

    # 系列：先查关键词→系列映射表（reasoning_flow 可配，如 amd→Orion），未命中再字面命中 SERIES_KEYWORDS
    if series_keyword_map:
        for kw, mapped in series_keyword_map.items():
            if kw and kw.lower() in low and mapped:
                series = mapped
                break
    if not series:
        for s in _load_series_values():
            if s.lower() in low:
                series = s
                break

    # 形态：优先走配置的 form_keyword_map（trigger→form，带数字边界避免"44u"误命中"4u"），未命中走 FORM_PATTERN 兜底
    if form_keyword_map:
        for trig, f_val in form_keyword_map.items():
            if trig and f_val and re.search(rf"(?<![0-9]){re.escape(trig.lower())}(?![A-Za-z])", low):
                form = f_val
                break
    if not form:
        m = FORM_PATTERN.search(text)
        if m:
            form = m.group(1).upper()
    if not form:
        # 机箱尺寸推断（R7）："宽448x高175x深822mm" → 175/44.45 ≈ 4U（I12 部分解决）
        # 高度数字须后跟 x 或 mm（"宽448x高175x深822mm"）；防"支持最高6400MT/s"的 高640 误判（R7）
        m = re.search(r"(?:高|height)\s*(\d{2,3})(?=\s*(?:mm|[xX×*]))", text, re.IGNORECASE)
        if m:
            _u = int(round(int(m.group(1)) / 44.45))
            if 1 <= _u <= 4:
                form = f"{_u}U"

    # 服务器类型：只走配置的 usage_keyword_map（trigger→server_type_name 精确，来自 extract
    # 节点的「服务器类型词表」，key 对齐 l6.server_types.name）。
    # 旧版 USAGE_LEXICON 臆造词表已删除——「类型」是客户在反问环节从真实目录里选的，
    # 不靠关键词猜测（猜不准是旧思路的病根）。
    usage: Optional[str] = None
    server_type_name: Optional[str] = None
    if usage_keyword_map:
        for trig, type_name in usage_keyword_map.items():
            if trig and trig.lower() in low and type_name:
                server_type_name = type_name
                usage = type_name
                break

    # 预算（元）
    budget = _extract_budget(text)
    mem_signal = _extract_mem_signal(text)
    cpu_signal = _extract_cpu_signal(text)
    psu_signal = _extract_psu_signal(text)
    # 内存延续段的中断词：全量非内存品类触发词（含 rtx/l40/w7900 等 GPU 型号词），
    # 防 "1 *RTX PRO 4500 Server 32G" 的 32G 续进内存组（2026-08-03 训练）
    _nonmem_interrupt: list[str] = []
    for _c, _toks in (lexicon if lexicon is not None else CATEGORY_LEXICON).items():
        if str(_c).lower() in ("memory", "内存"):
            continue
        _nonmem_interrupt.extend(t for t in _toks if isinstance(t, str))

    # jieba 分词补充关键词（型号 token + 有意义词）
    tokens: list[str] = []
    try:
        import jieba
        tokens = list(jieba.cut(text, cut_all=False))
    except Exception as e:
        logger.warning("jieba 不可用，退化到空格切分: %s", e)
        tokens = re.split(r"[\s,，、;；]+", text)

    for tok in tokens:
        tok = tok.strip()
        if not tok or _is_stopword(tok):
            continue
        # 型号样 token 直接收
        if _mt_pattern.match(tok) and tok not in keywords:
            keywords.append(tok)
        # 数字+单位（如 32G / 1.92T / 2U）作检索补充
        elif re.match(r"^[0-9]+\.?[0-9]*[GT]\b", tok, re.IGNORECASE) and tok not in keywords:
            keywords.append(tok)

    # 从原文直接补抓型号 token（jieba 会切碎数字+字母组合如 960G/7.68T/9560-8i）
    _model_tokens: list[str] = []
    _existing = {k.lower() for k in keywords}
    for _m in re.finditer(r"[0-9A-Za-z][0-9A-Za-z.\-]{1,}", text):
        _tok = _m.group()
        if _mt_pattern.match(_tok) and _tok.lower() not in _existing:
            _model_tokens.append(_tok)
            _existing.add(_tok.lower())
    keywords[0:0] = _model_tokens  # 型号 token 插入开头（优先，不被 keyword_limit 截断）

    # 去重保序、限长（型号 token 优先保留——精确匹配价值最高，不被品类词挤掉）
    seen = set()
    deduped = []
    _model_first = [k for k in keywords
                    if _mt_pattern.match(k)
                    and not _DRIVE_CAP_TOKEN_RE.match(k)
                    and not re.match(r"^\d+\.\d+$", k)          # 7.68/1.92/3.0 纯小数碎片（R5）
                    and not re.match(r"^\d+[A-Za-z]{2,}$", k)          # 8GPU/6400MT/822mm 数字+单词连写（R7）
                    and not re.match(r"^PCIe\d*(?:\.\d+)?$", k, re.I)  # PCIe4/PCIe4.0 槽位规格（R7）
                    and not re.match(r"^RAID\d+$", k, re.I)     # RAID1/5/10 是级别注释不是型号（I38，R2）
                    and not re.match(r"^[A-Za-z]{2,}\d+[Ww]$", k)]  # TDP360W 是 CPU TDP 规格不是型号（R28）
    _others = [k for k in keywords if not _mt_pattern.match(k)]
    for k in _model_first + _others:
        kl = k.lower()
        if kl not in seen:
            seen.add(kl)
            deduped.append(k)
        if len(deduped) >= keyword_limit:
            break

    # "12/24 bays HDDSupport of NVMe" 是机箱能力描述，不是硬盘配置（R4 修）：
    # 无盘组（容量+盘指示词同段）、无"2块SSD"式盘量词 → 不触发 HDD/SSD 品类。
    # 注：qty_map 的 HDD/SSD 可能是 "2 x 25 GB SFP28" 误绑到 HDDSupport 的假信号，不作为依据。
    if "HDD/SSD" in categories:
        _drive_groups = _extract_drive_groups(text, qty_per_token)
        _disk_unit_qty = bool(re.search(r"(\d+)\s*(?:块|个|片)\s*(?:ssd|hdd|硬盘|盘)", low))
        if not _drive_groups and not _disk_unit_qty:
            categories.remove("HDD/SSD")

    return {"keywords": deduped, "categories": categories, "series": series, "form": form,
            "usage": usage, "server_type_name": server_type_name,
            "chassis_categories": chassis_categories,
            "qty_map": qty_map, "qty_per_token": qty_per_token,
            "spec_search_terms": spec_search_terms, "budget": budget,
            "mem_signal": mem_signal, "cpu_signal": cpu_signal,
            "multi_spec_filters": multi_spec_filters, "psu_signal": psu_signal,
            "drive_groups": _extract_drive_groups(text, qty_per_token),
            "raid_groups": _extract_raid_groups(text),
            "gpu_groups": _extract_gpu_groups(text, qty_per_token, (lexicon or {}).get("GPU", []), _mt_pattern),
            "mem_groups": _extract_mem_groups(text, qty_per_token, interrupt_words=_nonmem_interrupt),
            "usage_inferred": False}


PIPELINE_STEPS = [
    {"key": "normalize_input", "label": "需求输入规范化"},
    {"key": "extract", "label": "需求理解与关键词提取"},
    {"key": "select_baseline", "label": "机型选型（基准配置）"},
    {"key": "match_kp", "label": "配件匹配"},
    {"key": "compose", "label": "组合整机方案"},
    {"key": "review", "label": "方案就绪"},
]


# 反问最多 N 轮（与 reasoning_executor.MAX_CLARIFY_ROUNDS 同步）。
# 目录驱动引导正常 3 步（类型→机型→KP 格式）即可走完，6 是兜底保险。
MAX_CLARIFY_ROUNDS = 6


def apply_budget_check(plans: list, budget: Optional[float], underspend_threshold: float = 0.5) -> int:
    """给 plans 注 over_budget / underspend 字段（在 summary.total_cost 上算）。
    - over_budget: 方案价 > 预算（超了多少）
    - underspend: 方案价/预算 < underspend_threshold（默认 0.5，预算没用足一半 → 可升级配置）
    返回超预算方案数。budget=None 时跳过。图 executor + 线性 fallback 共用。"""
    if budget is None or not plans:
        return 0
    over = 0
    for p in plans:
        total = (p.get("summary") or {}).get("total_cost") or 0
        if total and total > budget:
            p["over_budget"] = {
                "amount": round(total - budget, 2),
                "ratio": round((total - budget) / budget, 2),
            }
            p["underspend"] = None
            over += 1
        else:
            p["over_budget"] = None
            ratio = round(total / budget, 2) if budget else 0
            if ratio < underspend_threshold:
                p["underspend"] = {"ratio": ratio, "amount": round(budget - total, 2)}
            else:
                p["underspend"] = None
    return over


def _read_opportunity_extra(opportunity_id: str) -> dict:
    """读商机 extra_fields（JSON）。失败返回 {}。直查模式，不依赖 repo.get。"""
    try:
        from app.models.opportunity import Opportunity
        from app.models.base import Opportunity_SessionLocal
        with Opportunity_SessionLocal() as session:
            opp = session.query(Opportunity).filter(
                Opportunity.opportunity_id == opportunity_id
            ).first()
            if not opp or not opp.extra_fields:
                return {}
            return json.loads(opp.extra_fields) if isinstance(opp.extra_fields, str) else (opp.extra_fields or {})
    except Exception as e:
        logger.warning("读商机 extra_fields 失败 opp=%s err=%s", opportunity_id, e)
        return {}


def _read_opportunity_ctx(opportunity_id: str) -> dict:
    """读商机完整上下文（含 industry 等列 + extra_fields），给场景分析用。失败返回 {}。"""
    try:
        from app.models.opportunity import Opportunity
        from app.models.base import Opportunity_SessionLocal
        with Opportunity_SessionLocal() as session:
            opp = session.query(Opportunity).filter(
                Opportunity.opportunity_id == opportunity_id
            ).first()
            return opp.to_dict() if opp else {}
    except Exception as e:
        logger.warning("读商机上下文失败 opp=%s err=%s", opportunity_id, e)
        return {}


def _read_opportunity_budget(opportunity_id: str) -> Optional[float]:
    extra = _read_opportunity_extra(opportunity_id)
    b = extra.get("budget")
    try:
        return float(b) if b is not None else None
    except (TypeError, ValueError):
        return None


def _read_clarify_round(opportunity_id: str) -> int:
    extra = _read_opportunity_extra(opportunity_id)
    try:
        return int(extra.get("requirement_clarity_round", 0))
    except (TypeError, ValueError):
        return 0


def _write_clarify_round(opportunity_id: str, round_num: int) -> None:
    try:
        from app.repository.opportunity_repo import OpportunityRepository
        repo = OpportunityRepository()
        try:
            repo.update_meta(opportunity_id, {"requirement_clarity_round": round_num})
        finally:
            repo.close()
    except Exception as e:
        logger.warning("写 clarify_round 失败 opp=%s err=%s", opportunity_id, e)


def _read_clarify_supplements(opportunity_id: str) -> tuple:
    """返回 (base原文, 累积补充串)。跨轮持久化历次反答回填，避免每轮只拼最新一句丢失已答字段。"""
    extra = _read_opportunity_extra(opportunity_id)
    return extra.get("requirement_clarity_base") or "", extra.get("requirement_clarity_supplements") or ""

def _read_clarify_defaults(opportunity_id: str) -> list:
    """读"已答默认"字段集合（答"还没定/你推荐"跳过的字段，跨轮不再追问）。"""
    extra = _read_opportunity_extra(opportunity_id)
    v = extra.get("requirement_clarity_defaults")
    return list(v) if isinstance(v, list) else []


def _write_clarify_defaults(opportunity_id: str, defaults: list) -> None:
    try:
        from app.repository.opportunity_repo import OpportunityRepository
        repo = OpportunityRepository()
        try:
            repo.update_meta(opportunity_id, {"requirement_clarity_defaults": list(defaults)})
        finally:
            repo.close()
    except Exception as e:
        logger.warning("写 clarify_defaults 失败 opp=%s err=%s", opportunity_id, e)


def _read_last_asked(opportunity_id: str) -> list:
    """读"最近一轮反问问过的字段"（配合"还没定"→ 把该字段标为默认）。"""
    extra = _read_opportunity_extra(opportunity_id)
    v = extra.get("requirement_clarity_last_asked")
    return list(v) if isinstance(v, list) else []


def _write_last_asked(opportunity_id: str, fields: list) -> None:
    try:
        from app.repository.opportunity_repo import OpportunityRepository
        repo = OpportunityRepository()
        try:
            repo.update_meta(opportunity_id, {"requirement_clarity_last_asked": list(fields)})
        finally:
            repo.close()
    except Exception as e:
        logger.warning("写 last_asked 失败 opp=%s err=%s", opportunity_id, e)


def _write_clarify_supplements(opportunity_id: str, base: str, supplements: str) -> None:
    try:
        from app.repository.opportunity_repo import OpportunityRepository
        repo = OpportunityRepository()
        try:
            repo.update_meta(opportunity_id, {
                "requirement_clarity_base": base,
                "requirement_clarity_supplements": supplements,
            })
        finally:
            repo.close()
    except Exception as e:
        logger.warning("写 clarify_supplements 失败 opp=%s err=%s", opportunity_id, e)


def _merge_clarify_defaults(defaults: list, last_asked: list, supplement: dict,
                             is_new_conversation: bool) -> list:
    """更新"已答默认"字段集合（M1 1.3b，纯函数供单测）。

    语义：答"还没定/你推荐"（_is_default_reply 命中）→ 把上一轮问过的字段
    （last_asked）标为默认，后续轮次不再追问；全新对话清零。
    """
    from app.services.reasoning_executor import _is_default_reply  # 延迟 import 规避循环
    defaults = list(defaults or [])
    if is_new_conversation:
        return []
    if supplement and last_asked and _is_default_reply((supplement.get("text") or "")):
        return list(dict.fromkeys(defaults + [f for f in last_asked if f]))
    return defaults


def _merge_clarify_text(original: str, stored_base: str, acc_supplements: str,
                        supplement: dict = None, force_complete: bool = False) -> tuple:
    """合并「原文 + 历次反问补充」为完整需求文本（纯函数，供单测）。

    会话语义（M1 1.1，修"再次生成报价重复上一轮"）：
      - 无 supplement 且非 force_complete = 全新对话（用户重新点「生成报价」）
        → 无条件清空旧补充历史。此前仅原文变化才清，同文本重跑永远复读旧对话；
      - force_complete（点跳过）= 用当前已答信息出方案 → 保留已累积补充；
      - supplement（反答回填）= 续接对话 → 追加本轮补充（原文若变则先清旧历史）。
    返回 (full_text, 新 acc_supplements)。
    """
    original = (original or "").strip()
    acc = acc_supplements or ""
    if not supplement and not force_complete:
        acc = ""  # 全新对话：清空旧补充历史（不再依赖原文是否变化）
    elif stored_base and original and stored_base != original:
        acc = ""  # 原文变了 = 新一轮提问，丢弃旧补充历史
    if supplement and supplement.get("text"):
        piece = (supplement.get("text") or "").strip()
        if piece:
            acc = f"{acc}\n补充：{piece}" if acc else f"补充：{piece}"
    if original and acc:
        return f"{original}\n{acc}", acc
    return original or acc, acc


def _write_llm_feedback_sample(opportunity_id: str, requirement_text: str, applied: list) -> None:
    """LLM 确认反馈 → rules.requirement_samples（source=llm_feedback）。

    每次 confirm 节点应用决策（采纳/忽略）后落一条：需求原文 + 决策明细，
    供未来 LLM 语料/评测/反馈闭环。rule_id=0（不挂具体规则）。
    test-run 等占位商机不写，避免污染样本库。
    """
    if not applied or (opportunity_id or "").startswith("test"):
        return
    from app.repository.requirement_rule_repo import RequirementRuleRepository
    repo = RequirementRuleRepository()
    try:
        repo.add_sample({
            "rule_id": 0,
            "sample_text": (requirement_text or "")[:2000],
            "expected_result": {"confirm": applied, "source": "llm_feedback"},
            "source": "llm_feedback",
            "tags": ["llm_feedback", "confirm"],
        }, operator="system")
    finally:
        repo.close()


# ── 目录驱动引导会话状态（需求不明确时的反问状态机，见 catalog_guide）────────
def _read_catalog_state(opportunity_id: str) -> dict:
    """读目录引导会话状态（stage/type_name/model_id/offered）。无则返回空 state。"""
    extra = _read_opportunity_extra(opportunity_id)
    offered = extra.get("requirement_catalog_offered")
    try:
        offered = json.loads(offered) if isinstance(offered, str) else (offered or {})
    except Exception:
        offered = {}
    return {
        "stage": extra.get("requirement_catalog_stage") or "",
        "type_name": extra.get("requirement_catalog_type_name"),
        "model_id": extra.get("requirement_catalog_model_id"),
        "offered": offered if isinstance(offered, dict) else {},
    }


def _write_catalog_state(opportunity_id: str, state: dict) -> None:
    try:
        from app.repository.opportunity_repo import OpportunityRepository
        repo = OpportunityRepository()
        try:
            repo.update_meta(opportunity_id, {
                "requirement_catalog_stage": state.get("stage") or "",
                "requirement_catalog_type_name": state.get("type_name"),
                "requirement_catalog_model_id": state.get("model_id"),
                "requirement_catalog_offered": json.dumps(state.get("offered") or {}, ensure_ascii=False),
            })
        finally:
            repo.close()
    except Exception as e:
        logger.warning("写 catalog_state 失败 opp=%s err=%s", opportunity_id, e)


def _reset_catalog_state(opportunity_id: str) -> dict:
    state = {"stage": "", "type_name": None, "model_id": None, "offered": {}}
    _write_catalog_state(opportunity_id, state)
    return state


def _advance_catalog_state(opportunity_id: str, state: dict, reply: str, ask_cfg: dict,
                           flow_configs: dict) -> dict:
    """消费客户回复推进目录引导阶段（DB 目录数据版）。返回新 state；无变化时原样返回。"""
    from app.services.catalog_guide import advance_with_catalog
    new_state = advance_with_catalog(state, reply, ask_cfg)
    if new_state != state:
        _write_catalog_state(opportunity_id, new_state)
        return new_state
    return state


def _persist_catalog_offer(opportunity_id: str, stage: str, offered: dict) -> None:
    """ask_user 发问后记录本轮推给客户的选项 + 当前 stage（供下轮选项匹配）。"""
    try:
        from app.repository.opportunity_repo import OpportunityRepository
        repo = OpportunityRepository()
        try:
            repo.update_meta(opportunity_id, {
                "requirement_catalog_stage": stage,
                "requirement_catalog_offered": json.dumps(offered or {}, ensure_ascii=False),
            })
        finally:
            repo.close()
    except Exception as e:
        logger.warning("写 catalog_offer 失败 opp=%s err=%s", opportunity_id, e)


# ── 系列确认（confirm_series 节点，2026-08-04 流程重构 R29）────────────────
# 场景分析推断出系列后，问用户"是否 XX 系列？"；答复（是/不是/系列名）解析后
# 存 extra_fields.requirement_confirmed_series（跨轮），下轮注入 ctx.confirmed_series。
# 特殊值 "__ask__" = 用户否认推断系列 → confirm_series 改列在售系列让用户选。


def _persist_series_offer(opportunity_id: str, offered: dict) -> None:
    """confirm_series 发问后记录本轮推的系列（下轮答"是"时取用）。"""
    try:
        from app.repository.opportunity_repo import OpportunityRepository
        repo = OpportunityRepository()
        try:
            repo.update_meta(opportunity_id, {
                "requirement_series_offer": json.dumps(offered or {}, ensure_ascii=False),
            })
        finally:
            repo.close()
    except Exception as e:
        logger.warning("写 series_offer 失败 opp=%s err=%s", opportunity_id, e)


def _read_series_offer(opportunity_id: str) -> dict:
    extra = _read_opportunity_extra(opportunity_id)
    if isinstance(extra, dict):
        raw = extra.get("requirement_series_offer")
        try:
            return json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            return {}
    return {}


def _write_confirmed_series(opportunity_id: str, value: str) -> None:
    try:
        from app.repository.opportunity_repo import OpportunityRepository
        repo = OpportunityRepository()
        try:
            repo.update_meta(opportunity_id, {"requirement_confirmed_series": value})
        finally:
            repo.close()
    except Exception as e:
        logger.warning("写 confirmed_series 失败 opp=%s err=%s", opportunity_id, e)


def _read_confirmed_series(opportunity_id: str) -> str:
    extra = _read_opportunity_extra(opportunity_id)
    return str(extra.get("requirement_confirmed_series") or "") if isinstance(extra, dict) else ""


def _parse_series_confirm(reply: str, offer: dict) -> Optional[str]:
    """系列确认答复解析：是→offer.series；不是/换→'__ask__'；具体系列名→该名；无关→None。
    返回 None 表示"不是系列确认的回复"（目录引导等其他解析继续处理）。"""
    r = (reply or "").strip().lower()
    if not r:
        return None
    # 先查否认（"不是"里含"是"字，必须优先，否则"不是"被"是"误判为确认）
    if any(w in r for w in ("不是", "不对", "不要", "换系列", "换一个", "换", "其他", "别的", "算了")):
        return "__ask__"
    if any(w in r for w in ("是", "确认", "可以", "对的", "就它", "就要这个", "这个系列", "ok", "好")):
        if offer and offer.get("series"):
            return str(offer["series"])
        return None
    # 具体系列名（Orion / Polaris / Intel …）
    for s in _load_series_values():
        if s and (s.lower() in r or r in s.lower()):
            return s
    # 平台别名 → 系列（"兆芯/开胜"→Polaris、"AMD/EPYC"→Orion、"Xeon"→Intel；海光/飞腾/鲲鹏非 Polaris）
    _aliases = {
        "Orion": ["amd", "epyc", "霄龙", "猎户"],
        "Polaris": ["兆芯", "zhaoxin", "开胜", "开先", "信创", "国产"],
        "Intel": ["intel", "xeon", "至强"],
    }
    for series_name, words in _aliases.items():
        if any(w in r for w in words):
            return series_name
    return None


async def run_pipeline(opportunity_id: str, requirement_text: str,
                       supplement: dict = None, force_complete: bool = False) -> None:
    """跑推理 pipeline。有 active flow → 图驱动 executor；异常或无 flow → 线性 5 步 fallback。

    supplement: 反答回填 {"text":..., "budget":...}；force_complete: 用户点跳过，强制走选型。
    三层兜底：DB 异常 → linear fallback；graph executor 异常 → linear fallback。"""
    # 累积拼接完整需求文本（原文 + 历次反问补充）——跨轮持久化，避免每轮只拼最新一句、丢失已答字段。
    # 旧实现 full_text=原文+最新补充 → 第三轮答"Orion"时丢了第二轮"AI训练/推理" → 用途又变缺失 → 重复问用途。
    original = (requirement_text or "").strip()
    stored_base, acc_supplements = _read_clarify_supplements(opportunity_id)
    # M1 1.1：会话语义抽成纯函数 —— 无 supplement 且非 force_complete = 全新对话，无条件清空旧补充。
    full_text, acc_supplements = _merge_clarify_text(
        original, stored_base, acc_supplements, supplement, force_complete,
    )
    if original:
        _write_clarify_supplements(opportunity_id, original, acc_supplements)  # 持久化供下轮累积

    # M1 1.3b：已答默认字段（答"还没定/你推荐"跳过的）跨轮记忆，避免重复追问。
    is_new_conversation = not supplement and not force_complete
    defaults = _read_clarify_defaults(opportunity_id)
    last_asked = _read_last_asked(opportunity_id)
    new_defaults = _merge_clarify_defaults(defaults, last_asked, supplement, is_new_conversation)
    if new_defaults != defaults:
        _write_clarify_defaults(opportunity_id, new_defaults)
        defaults = new_defaults
    if is_new_conversation or (supplement and last_asked):
        # 全新对话清空 last_asked；补充后本轮 asked 已被消费（下轮 _broadcast 会重写）
        _write_last_asked(opportunity_id, [])

    # 预算优先级：反问明确给 > 商机 extra_fields > 无
    if supplement and supplement.get("budget") is not None:
        budget = supplement["budget"]
    else:
        budget = _read_opportunity_budget(opportunity_id)

    # 反问轮次（死循环防护，存 extra_fields 跨重启/多用户）。
    # ⚠️ 语义：每次点「生成报价」（无 supplement）= 全新对话，必须重置 round=0；
    # 只有反答回填（supplement）才 +1。否则 round 跨会话单调累积，用户多测几次就
    # 永久卡在 MAX 阈值 → clarity_check 强制出方案 → 反问机制整体失效（[0.1.43] 修）。
    round_num = _read_clarify_round(opportunity_id)
    # P2：纯 confirm 决策（无文本/预算）不算反问轮次，避免占用死循环防护预算
    _has_clarify = bool(supplement and (supplement.get("text") or supplement.get("budget") is not None))
    if _has_clarify:
        round_num = min(round_num + 1, MAX_CLARIFY_ROUNDS + 1)
        _write_clarify_round(opportunity_id, round_num)
    else:
        # 重新生成 = 新对话，重置死循环计数器（否则跨会话累积卡死反问）
        round_num = 0
        _write_clarify_round(opportunity_id, 0)

    pipeline_id = f"pl_{uuid.uuid4().hex[:12]}"
    initial_ctx = {
        "budget": budget,
        "clarify_round": round_num,
        "pipeline_id": pipeline_id,
        "force_complete": force_complete,
        "clarify_defaults": defaults,  # M1 1.3b：已答默认字段，clarity_check 剔除不再追问
        "confirmed_series": _read_confirmed_series(opportunity_id),  # R29：系列确认（confirm_series）
    }
    # P2：LLM 确认面板决策（confirm 节点消费）：{item_id: "accept"|"ignore"}
    if supplement and supplement.get("confirm"):
        initial_ctx["confirm_decisions"] = supplement["confirm"]
        initial_ctx["confirm_answered"] = True

    async def _broadcast(payload: dict):
        payload.setdefault("opportunity_id", opportunity_id)
        payload.setdefault("pipeline_id", pipeline_id)
        payload.setdefault("round", round_num)
        # M1 1.3b：need_input 广播时记录本轮问的字段，供下轮"还没定"标默认跳过
        if payload.get("type") == "need_input":
            _write_last_asked(opportunity_id, list(payload.get("asked_fields") or []))
        await reasoning_hub.broadcast(opportunity_id, payload)

    flow = None
    try:
        from app.repository.reasoning_flow_repo import ReasoningFlowRepository
        _rf = ReasoningFlowRepository()
        try:
            flow = _rf.get_active_flow()
        finally:
            _rf.close()
    except Exception as e:
        logger.warning("读 reasoning flow 失败: %s", e)

    # ── 目录驱动引导：消费客户回复推进 stage / 新对话重置（旧思路的 workload/rebuttal 已删）──
    # 阶段推进放在图执行前：stage 变 done → clarity_check 直接视为 explicit → 本轮就出方案，
    # 而不是像旧版那样「反问永远停在 ask_user，下轮才能继续」。
    flow_configs = (flow or {}).get("node_configs") or {}
    catalog = _read_catalog_state(opportunity_id)
    # 只有客户实际回复了文本才推进目录引导（纯 budget 补充不算回答，避免误跳到下一问）
    if supplement and (supplement.get("text") or "").strip():
        # 系列确认答复（confirm_series 节点）：是→确认推断系列 / 不是→标记补全 / 系列名→直选。
        _series_reply = (supplement.get("text") or "").strip()
        _series_offer = _read_series_offer(opportunity_id)
        _series_confirmed = _parse_series_confirm(_series_reply, _series_offer)
        if _series_confirmed is not None:
            _write_confirmed_series(opportunity_id, _series_confirmed)
        from app.services.catalog_guide import load_ask_config
        ask_cfg = load_ask_config(flow_configs)
        catalog = _advance_catalog_state(
            opportunity_id, catalog, supplement.get("text") or "", ask_cfg, flow_configs,
        )
    elif is_new_conversation and catalog.get("stage"):
        catalog = _reset_catalog_state(opportunity_id)
    from app.services.catalog_guide import load_ask_config as _ask_cfg
    initial_ctx.update({
        "catalog_stage": catalog.get("stage") or "",
        "catalog_type_name": catalog.get("type_name"),
        "catalog_model_id": catalog.get("model_id"),
        "catalog_state": catalog,
        "flow_configs": flow_configs,
        "max_clarify_rounds": int(_ask_cfg(flow_configs).get("max_rounds") or MAX_CLARIFY_ROUNDS),
    })

    graph_nodes = (flow or {}).get("graph", {}).get("nodes") or []
    if flow and graph_nodes:
        try:
            from app.services.reasoning_executor import run_graph_executor
            steps = [{"key": n.get("id"), "label": n.get("label") or n.get("id")} for n in graph_nodes]
            await _broadcast({"type": "pipeline_start", "steps": steps, "is_rerun": round_num > 0})
            ctx = await run_graph_executor(opportunity_id, full_text, flow, _broadcast, initial_ctx=initial_ctx)
            # P2：LLM 确认待决 → 先发 need_confirm（面板展示，默认采纳可改）再 paused
            if ctx.get("confirm_pending") and not force_complete:
                await _broadcast({
                    "type": "need_confirm",
                    "reply_id": ctx.get("confirm_reply_id"),
                    "items": ctx.get("confirm_items") or [],
                    "default": "accept",
                    "question": "大模型补充了以下信息，默认已采纳，可改为「忽略」后重新生成方案：",
                })
                await _broadcast({"type": "pipeline_paused"})
            elif ctx.get("awaiting_input") and not force_complete:
                # ask_user 叶子节点置 awaiting_input → 发 paused（等用户补）；否则 done
                await _broadcast({"type": "pipeline_paused", "reply_id": ctx.get("last_reply_id")})
            else:
                await _broadcast({"type": "pipeline_done"})
            return
        except Exception as e:
            logger.exception("graph executor 失败，回退 linear fallback: %s", e)

    await _run_linear_fallback(opportunity_id, full_text, _broadcast, flow, budget=budget, force_complete=force_complete)


async def _run_linear_fallback(opportunity_id: str, requirement_text: str, _broadcast, flow,
                              budget: Optional[float] = None, force_complete: bool = False) -> None:
    """线性 5 步 fallback（原 run_pipeline 体）。flow.node_configs 透传参数；三层兜底。"""
    cfg: dict = {}
    if flow:
        cfg = flow.get("node_configs") or {}
    try:
        await _broadcast({"type": "pipeline_start", "steps": PIPELINE_STEPS})

        # 0. 输入规范化（与图 executor 的 normalize_input 节点同源，保证两条路径行为一致）
        await _broadcast({"type": "step_start", "step": "normalize_input"})
        from app.services.requirement_normalizer import normalize_text
        requirement_text, _norm_report = normalize_text(
            requirement_text, cfg.get("normalize_input") or {})
        await _broadcast({"type": "step_done", "step": "normalize_input",
                          "payload": {"normalized": requirement_text, "report": _norm_report}})

        # 1. 提取
        await _broadcast({"type": "step_start", "step": "extract"})
        _ext_cfg = cfg.get("extract") or {}
        if _ext_cfg.get("lexicons"):
            _cat_lex, _chassis_lex, _usage_map, _series_map, _form_map = _fold_lexicons(_ext_cfg["lexicons"])
        else:
            _cat_lex = _ext_cfg.get("category_lexicon")
            _chassis_lex, _usage_map, _series_map, _form_map = None, None, None, None
        ext = extract_keywords(
            requirement_text,
            lexicon=_cat_lex,
            keyword_limit=_ext_cfg.get("keyword_limit") or 12,
            series_keyword_map=_series_map,
            usage_keyword_map=_usage_map,
            form_keyword_map=_form_map,
            chassis_lexicon=_chassis_lex,
            spec_aliases=_ext_cfg.get("spec_aliases"),
            qty_units=_ext_cfg.get("qty_units"),
            qty_multipliers=_ext_cfg.get("qty_multipliers"),
            model_token_regex=_ext_cfg.get("model_token_regex"),
        )
        await _broadcast({
            "type": "step_done", "step": "extract",
            "payload": {
                "keywords": ext["keywords"],
                "categories": ext["categories"],
                "series": ext["series"],
                "form": ext["form"],
            },
        })

        # 2. 机型选型（目录引导选的类型优先 > 场景分析 > extract 信号；只推命中的不硬塞）
        await _broadcast({"type": "step_start", "step": "select_baseline"})
        _sb_cfg = cfg.get("select_baseline") or {}
        _catalog = _read_catalog_state(opportunity_id)
        # 场景分析（与图 executor 的 scene_analysis 节点同源，保证线性 fallback 行为一致）
        try:
            from app.services.scene_analyzer import analyze_scene
            _scene = analyze_scene(
                ext, requirement_text,
                config=cfg.get("scene_analysis") or {},
                opportunity=_read_opportunity_ctx(opportunity_id),
                catalog_type_name=_catalog.get("type_name"),
                force_complete=bool(force_complete),
            )
        except Exception as _e:
            logger.warning("线性 fallback 场景分析失败，退回 extract 信号: %s", _e)
            _scene = {}
        _type_name = (_catalog.get("type_name")
                      or (_scene.get("scene_name") if _scene.get("determined") else None)
                      or ext.get("server_type_name"))
        baselines = select_models(
            ext.get("usage"),
            _type_name,
            _scene.get("series") or ext.get("series") or None,
            _scene.get("form") or ext.get("form") or None,
            limit=_sb_cfg.get("max_plans") or 3,
            recommend_strategy_id=_sb_cfg.get("recommend_strategy_id"),
            no_signal_strategy=_sb_cfg.get("no_signal_strategy"),
            variant_signals=build_variant_signals(ext, requirement_text),
        )
        # 目录引导选了具体机型 → 优先保留该机型（防混推其他类型机型）
        _cat_model_id = _catalog.get("model_id")
        if _cat_model_id:
            _keep = [b for b in baselines
                     if b.get("server_model_id") == _cat_model_id or b.get("id") == _cat_model_id]
            if _keep:
                baselines = _keep
        await _broadcast({
            "type": "step_done", "step": "select_baseline",
            "payload": {
                "count": len(baselines),
                "matches": [{
                    "config_id": b.get("id"),
                    "name": b.get("name") or "",
                    "series": b.get("series") or "",
                    "form": b.get("form") or "",
                } for b in baselines],
            },
        })

        # 3. 配件匹配（per-机型：每个机型按自己的 server_type 套餐 ∪ 需求品类）
        await _broadcast({"type": "step_start", "step": "match_kp"})
        _mk_cfg = cfg.get("match_kp") or {}
        _cfg_pick = _mk_cfg.get("representative_pick")
        if _cfg_pick and _cfg_pick != "auto":
            _pick = _cfg_pick
        else:
            from app.services.reasoning_executor import _resolve_budget_strategy
            _pick = _resolve_budget_strategy(budget)
        _kp_by_model: dict = {}
        _all_kp: list = []
        for _bl in baselines:
            _type_cats = kp_categories_for_type(_bl.get("server_type_name") or "", _mk_cfg.get("type_packages"), ext["categories"])
            _eff_cats = list(dict.fromkeys(_type_cats + (ext["categories"] or [])))
            _bl_kp = pick_kp_parts(
                _eff_cats, ext["keywords"],
                category_aliases=_mk_cfg.get("category_aliases"),
                representative_pick=_pick,
                spec_rules=_mk_cfg.get("spec_rules"),
                fallback_strategy=_mk_cfg.get("fallback_strategy") or "fallback_representative",
                requirement_text=requirement_text,
                qty_map=ext.get("qty_map"),
                qty_per_token=ext.get("qty_per_token"),
                spec_search_terms=ext.get("spec_search_terms"),
                model_token_regex=_ext_cfg.get("model_token_regex"),
                mem_signal=ext.get("mem_signal"),
                cpu_signal=ext.get("cpu_signal"),
                multi_spec_filters=ext.get("multi_spec_filters"),
                drive_groups=ext.get("drive_groups"),
                gpu_groups=ext.get("gpu_groups"),
                mem_groups=ext.get("mem_groups"),
                drive_spec_substitute=(cfg.get("match_kp") or {}).get("drive_spec_substitute", True),
            )
            _kp_by_model[_bl.get("server_model_id") or _bl.get("id")] = _bl_kp
            _all_kp.extend(_bl_kp)
        by_category: dict[str, int] = {}
        for kp in _all_kp:
            c = kp.get("category") or "其他"
            by_category[c] = by_category.get(c, 0) + 1
        unmatched_count = sum(1 for kp in _all_kp if kp.get("unmatched"))
        await _broadcast({
            "type": "step_done", "step": "match_kp",
            "payload": {"kp_count": len(_all_kp), "by_category": by_category, "unmatched_count": unmatched_count},
        })

        # 4. 组合整机方案（每 baseline 取自己 per-机型配的 KP）
        await _broadcast({"type": "step_start", "step": "compose"})
        if not baselines:
            await _broadcast({
                "type": "step_done", "step": "compose",
                "payload": {"plans_count": 0, "warning": "未找到匹配的基准配置，请手填或调整需求"},
            })
            await _broadcast({"type": "pipeline_done"})
            return
        plans = []
        for _bl in baselines:
            _bl_kp = _kp_by_model.get(_bl.get("server_model_id") or _bl.get("id")) or []
            plans.append(build_plan(_bl, _bl_kp))
        # 电源瓦数：需求文本信号优先覆盖 build_plan 的 GPU 推断值（前端模板电源行读 psu_wattage）
        _sig_w = (ext.get("psu_signal") or {}).get("wattage")
        _sig_q = (ext.get("psu_signal") or {}).get("qty")
        if _sig_w or _sig_q:
            for p in plans:
                # 合并而非整体替换：保留 build_plan 已派生的 bp_type / cable_qty_by_kind（选型配置规则）
                _cs = p.get("chassis_signals") or {}
                if _sig_w:
                    _cs = {**_cs, "psu_wattage": _sig_w}
                if _sig_q:
                    _cs = {**_cs, "psu_qty": int(_sig_q)}
                p["chassis_signals"] = _cs
        apply_budget_check(plans, budget)  # 注 over_budget / underspend 字段
        await _broadcast({
            "type": "step_done", "step": "compose",
            "payload": {"plans_count": len(plans)},
        })

        # 5. 方案就绪 → 下发整机方案清单
        await _broadcast({"type": "step_start", "step": "review"})
        await _broadcast({
            "type": "candidates_ready",
            "plans": plans,
            "keywords": ext["keywords"],
            "series": ext["series"],
            "form": ext["form"],
        })
        await _broadcast({"type": "step_done", "step": "review"})

        await _broadcast({"type": "pipeline_done"})
    except Exception as e:
        logger.exception("requirement pipeline failed for %s", opportunity_id)
        await _broadcast({"type": "error", "message": f"推理流程异常: {e}"})
