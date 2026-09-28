"""Repository for KP (Key Parts) — 配件管理

指向新拆分的 6 张表：kp_categories, kp_parts, kp_part_specs, kp_price_history, kp_part_compat, kp_part_related
保持旧接口签名兼容（pricing_engine / quote_service 无感迁移）。
新增完整 CRUD 方法支持配件管理页面。
"""
from datetime import datetime, date, timedelta
import difflib
import json
import re
import statistics
from typing import List, Optional, Dict, Any
from sqlalchemy import text, select, func, exists, and_, Date
from sqlalchemy.orm import Session, joinedload
from app.models.base import KP_SessionLocal
from app.models.kp import (
    KPCategory, KPPart, KPPartSpec, KPPriceHistory, KPPartCompat, KPPartRelated,
    KPSearchAlias
)

_NUM_SPEC_OPS = {">=", "<=", ">", "<"}

def _spec_num(val) -> Optional[float]:
    """从 spec 值提首个数字：'32 GB'→32.0 / '5600 MT/s'→5600.0 / 'DDR5'→None。"""
    if val is None:
        return None
    m = re.search(r"[\d.]+", str(val))
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _spec_match_all(spec_map: dict, parsed: list) -> str:
    """所有 (spec_key, op, value) AND 满足 → 返回命中标签串（如 'Type=DDR5 · Speed>=5600'）；任一不满足 → ''。
    数值型 op 且双方都能提数 → 数值比较；op='in' → 等值/数值等值集合；其余 → 字符串等值。"""
    hits = []
    for sk, op, val in parsed:
        sv = spec_map.get(sk)
        if sv is None:
            return ""  # 该 spec 不存在 → AND 不满足
        sv_num = _spec_num(sv)
        val_num = _spec_num(val) if not isinstance(val, list) else None
        if op in _NUM_SPEC_OPS and sv_num is not None and val_num is not None:
            ok = (sv_num >= val_num if op == ">="
                  else sv_num <= val_num if op == "<="
                  else sv_num > val_num if op == ">"
                  else sv_num < val_num if op == "<"
                  else abs(sv_num - val_num) < 1e-9)  # = / ==
            if not ok:
                return ""
            hits.append(f"{sk}{op}{val_num:g}")
        elif op == "in":
            vals = val if isinstance(val, list) else [val]
            if not any(str(sv).strip() == str(v).strip() or _spec_num(sv) == _spec_num(v) for v in vals):
                return ""
            hits.append(f"{sk}∈{{{','.join(str(v) for v in vals)}}}")
        else:
            sv_s = str(sv).strip()
            v_s = str(val).strip()
            sv_n = _spec_num(sv)
            v_n = _spec_num(val) if not isinstance(val, list) else None
            if not (sv_s == v_s or (sv_n is not None and v_n is not None and abs(sv_n - v_n) < 1e-9)):
                return ""
            hits.append(f"{sk}={sv_s}")  # 显示真实 spec_value（DDR5 / 1G / 32 GB）
    return " · ".join(hits)


# 连字符归一（U+2010 单连字符 / U+2011 不换行连字符 … → ASCII '-'）：
# 客户需求写 "ConnectX-6"（ASCII -），库件名可能是 "ConnectX‑6"（U+2011），ILIKE 不命中（2026-08-03 R2）。
_UNICODE_HYPHENS = ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212")


def _norm_hyphen(s: str) -> str:
    for ch in _UNICODE_HYPHENS:
        s = s.replace(ch, "-")
    return s


def _name_norm(expr):
    """列表达式上的 Unicode 连字符 → ASCII '-'（供 ILIKE 归一匹配）。"""
    out = expr
    for ch in _UNICODE_HYPHENS:
        out = func.replace(out, ch, "-")
    return out


# ============================================================
# 同一性判据（导入去重 / 疑似重复检测共用）
# 决定两条记录是否「同一个件」——spec 主导、name 差异词兜底：让大小写/空格/冗余词
# （SSD/HDD/U.2/形态，因已结构化成 spec）不再制造一物多码；同时保留 gen4/工作负载/转速
# 等真差异词，避免 M.2/U.2、HDD/SSD、gen3/gen4 被误合。详见 memory kp-dedup-tier-a。
# ============================================================
def _icap(name):
    m = re.search(r'([\d.]+)\s*([TG])', (name or '').upper())
    if not m: return None
    n = float(m.group(1)); gb = n * 1024 if m.group(2) == 'T' else n
    if gb >= 1024 and abs(gb / 1024 - round(gb / 1024)) < 1e-6: return f"{int(gb // 1024)} TB"
    if gb >= 1024: return f"{gb / 1024:g} TB"
    return f"{int(gb)} GB"

def _itype(name):
    u = (name or '').upper()
    if 'NVME' in u: return 'NVMe'
    if 'SAS' in u: return 'SAS'
    if 'SATA' in u: return 'SATA'
    return None

def _imedia(name):
    u = (name or '').upper()
    if 'HDD' in u: return 'HDD'
    if 'SSD' in u: return 'SSD'
    return 'SSD' if _itype(name) == 'NVMe' else None   # NVMe 协议物理上必为 SSD

def _iform(name):
    u = (name or '').upper()
    if 'M.2' in u or 'M2 ' in u: return 'M.2'
    if 'U.2' in u or 'U2 ' in u or 'U.2' in (name or ''): return 'U.2'
    if '2.5' in u: return '2.5"'
    if "3.5" in u or "3'5" in u or "3’5" in u: return '3.5"'
    return None

def _igen(name):
    m = re.search(r'gen\s?(\d)', (name or '').lower())
    return f"gen{m.group(1)}" if m else ""

def _iworkload(name):
    s = (name or '').lower()
    for pat, k in [(r'读取?密集型|读密集型', '读密集'), (r'写密集型', '写密集'),
                   (r'混合型', '混合'), (r'企业级', '企业级')]:
        if re.search(pat, s): return k
    return ""

def _irpm(name):
    s = (name or '').upper(); m = re.search(r'([\d.]+)\s*K\b', s)
    if m:
        k = float(m.group(1))
        if abs(k - 7.2) < .05: return "7200"
        if abs(k - 10) < .05: return "10000"
        if abs(k - 15) < .05: return "15000"
    for t, v in [('7200', '7200'), ('10K', '10000'), ('15K', '15000')]:
        if t in s: return v
    return ""

def _inorm_general(name):
    s = re.sub(r'[ \t]+', ' ', (name or '').lower().replace('（', '(').replace('）', ')').replace('，', ',')).strip()
    s = re.sub(r'(\d+\.?\d*)\s*t\b', r'\1t', s)
    s = re.sub(r'(\d+\.?\d*)\s*gb\b', r'\1g', s)
    return re.sub(r'\s*([+,/])\s*', r'\1', s)   # 标点周围空格归一（2port +光 → 2port+光）

def _imem_type(name):
    u = (name or '').upper()
    m = re.search(r'\b(LPDDR[0-9X]+|DDR[0-9L]+)\b', u)
    return m.group(1) if m else None

def _imem_speed(name):
    u = (name or '').upper()
    m = re.search(r'\b(\d{4})\s*(?:MT/S|MHZ)?', u)
    if not m:
        return None
    return f"{int(m.group(1))} MT/s"

def _imem_dimm(name):
    u = (name or '').upper()
    for k in ('LRDIMM', 'RDIMM', 'UDIMM', 'SODIMM', 'DIMM'):
        if k in u:
            return k
    return None

def _imem_rank(name):
    u = (name or '').upper()
    m = re.search(r'(SINGLE|DUAL|QUAD)\s*RANK', u)
    return f"{m.group(1).title()} Rank" if m else None

def _imem_ecc(name):
    u = (name or '').upper()
    return 'ECC' if 'ECC' in u else None

# 分类族：报价侧零散分类名归一到 canonical，再映射到库里真实 kp_categories 变体。
# 先归一分类，再做匹配——否则 GPU card / Raid Card 这种变体连候选桶都进不去。
CATEGORY_FAMILIES = {
    'CPU': ['CPU'],
    'Memory': ['Memory'],
    'HDD/SSD': ['HDD/SSD'],
    'GPU': ['GPU'],
    'Raid card': ['Raid card'],
    'NIC': ['NIC'],
    'HBA': ['HBA'],
    'Bridge': ['Bridge'],
    'NVSwitch': ['NVSwitch'],
    'Power': ['Power'],
    'Fan': ['Fan'],
    'Heatsink': ['Heatsink'],
    'Cable': ['Cable'],
    'Rail': ['Rail'],
}

_CATEGORY_KEYWORDS = (
    ('raid', 'Raid card'),
    ('network', 'NIC'),
    ('nic', 'NIC'),
    ('gpu', 'GPU'),
    ('memory', 'Memory'),
    ('ram', 'Memory'),
    ('hdd', 'HDD/SSD'),
    ('ssd', 'HDD/SSD'),
    ('m.2', 'HDD/SSD'),
    ('storage', 'HDD/SSD'),
    ('cpu', 'CPU'),
    ('processor', 'CPU'),
    ('hba', 'HBA'),
    ('bridge', 'Bridge'),
    ('nvswitch', 'NVSwitch'),
    ('power', 'Power'),
    ('psu', 'Power'),
    ('fan', 'Fan'),
    ('heatsink', 'Heatsink'),
    ('cooler', 'Heatsink'),
    ('cable', 'Cable'),
    ('wire', 'Cable'),
    ('rail', 'Rail'),
)

def category_family(raw: str) -> str:
    """报价/库里零散分类名 → 分类族 canonical。未知分类原样返回，避免静默吞掉。"""
    s = (raw or '').strip().lower()
    if not s:
        return ''
    for kw, family in _CATEGORY_KEYWORDS:
        if kw in s:
            return family
    return s

def category_family_members(family: str) -> List[str]:
    """分类族对应的库里真实 kp_categories 名称（含变体）。"""
    if not family:
        return []
    return CATEGORY_FAMILIES.get(family, [family])

def canonical_category_name(raw: str) -> str:
    """把零散分类写法归一到分类族里的正式名称；未知分类保留原样，避免误降级/误新建。"""
    name = (raw or "").strip()
    if not name:
        return "Key Parts"
    family = category_family(name)
    members = category_family_members(family)
    if family in CATEGORY_FAMILIES and members:
        return members[0]
    return name

def part_identity_key(name: str, category: str, specs: Optional[dict] = None) -> tuple:
    """同一性键。HDD/SSD 用结构化 spec（缺则从 name 解析，含形态默认推断）+ name 差异词；
    Memory 用容量/代数/速率/DIMM 形态/rank/ECC（缺则从 name 解析）；
    其它品类用归一名。新件（specs=None）全从 name 解析；库内件传 specs 更准。导入与去重共用此键。"""
    sp = specs or {}
    if (category or '') == 'HDD/SSD':
        typ = sp.get('Type') or _itype(name)
        media = sp.get('Media') or _imedia(name)
        ff = sp.get('Form Factor') or _iform(name)
        if not ff:  # name/spec 都无形态 → 按企业盘主流规律推断默认（用户拍板，见 kp-dedup-tier-a）
            if typ == 'NVMe': ff = 'U.2'
            elif media == 'HDD': ff = '3.5"'
            elif media == 'SSD': ff = '2.5"'
        return ('HDD/SSD',
                sp.get('Capacity') or _icap(name), typ, ff, media,
                _igen(name), _iworkload(name), sp.get('RPM') or _irpm(name))
    if (category or '') == 'Memory':
        return ('Memory',
                sp.get('Capacity') or _icap(name),
                sp.get('Type') or _imem_type(name),
                sp.get('Speed') or _imem_speed(name),
                sp.get('DIMM Type') or _imem_dimm(name),
                sp.get('Rank') or _imem_rank(name),
                sp.get('ECC') or _imem_ecc(name))
    return (category or '', _inorm_general(name))


# ============================================================
# 语义 token 匹配（L1.5）：报价上传行 vs 库内件的宽松同件判定。
# 思路同 HDD/SSD 结构化 identity——对语序/冗余词/写法差免疫；
# 接受从严：输入 token ⊆ 库件 token 且族内唯一，防误合。
# ============================================================
_SEM_BRAND_RE = re.compile(
    r'nvidia|geforce|amd|intel|mellanox|broadcom|lsi|samsung|zhaoxin|huawei|hygon|phytium'
    r'|兆芯|华为|海光|飞腾|国产')
_SEM_NOISE_RE = re.compile(
    r'network\s*card|adapter|含模块|含光模块|多模光模块|单模光模块|光模块|光卡'
    r'|涡轮卡|涡轮|server\s+edition|显卡|处理器|内存条'
    r'|supercap|super-capacitor|超级电容|含电容|含电池|cachevault|掉电保护|支架'
    r'|网卡|涡轮|光口|电口|企业级|读取密集型|读密集型|写密集型|混合型|\becc\b|\bcache\b|\bib\b|roce|rdma')
_SEM_PORT_RE = re.compile(r'双口|二口|双电口|四口|单口|(\d+)\s*口')
_SEM_FUSE_RE = re.compile(r'([a-z])[\-_.·]+([0-9])')
_SEM_TOKEN_RE = re.compile(r'[a-z0-9]+(?:\.[0-9]+)?')


def semantic_tokens(text: str) -> set:
    """配件名 → 规范 token 集：端口/单位/型号连写归一，品牌与模块类噪声剔除；
    字母数字连写 token 统一拆分（rtx5090/kh50000 → {rtx,5090}/{kh,50000}），连写分写对称。
    上传行与库名走同一函数，任一侧写法差不敏感；对语序天然免疫（集合语义）。"""
    s = (text or '').lower().replace('（', ' ').replace('）', ' ')
    s = _SEM_PORT_RE.sub(lambda m: f" {m.group(1) or {'双口': '2', '二口': '2', '双电口': '2', '四口': '4', '单口': '1'}[m.group(0)]}port ", s)  # 两侧补空格防 2port25g 粘连
    s = _SEM_FUSE_RE.sub(r'\1\2', s)                      # kh-50000→kh50000
    s = re.sub(r'(\d)\s*gb\b', r'\1g', s)
    s = re.sub(r'(\d)\s*tb\b', r'\1t', s)
    s = re.sub(r'([gt])b/s', r'\1', s)                    # 1792 GB/s → 1792g
    s = re.sub(r'(\d{4,5})\s*(?:mts|mt/s|mhz)\b', r'\1', s)  # 4800MHz → 4800（对齐库名裸数字）
    s = re.sub(r'(\d(?:\.\d+)?)\s*ghz\b', r'\1', s)          # 2.6GHz → 2.6（对齐 spec 裸频率）
    s = _SEM_BRAND_RE.sub(' ', s)
    s = _SEM_NOISE_RE.sub(' ', s)
    out = set()
    for t in _SEM_TOKEN_RE.findall(s):
        m = re.match(r'^([a-z]+)(\d.+)$', t)
        out.update(m.groups() if m else {t})              # rtx5090/kh50000 → {rtx,5090}/{kh,50000}，连写分写对称
    return out


def semantic_match(text: str, family_parts: List[dict]) -> List[dict]:
    """族内语义 token 匹配。候选：输入 tokens ⊆ 库件全 tokens（名字+specs 值，
    specs 兜底 canonical 名比 alias 短的场景，如 Cache=4 GB 补 4g）；
    平局裁决：输入与「名字 tokens」完全相等者优先（specs 只扩超集不做相等面，防稀释）。
    接受：相等候选唯一，或候选本身唯一。歧义返回空（宁可新部件不误合）。"""
    in_toks = semantic_tokens(text)
    if not (len(in_toks) >= 2 or any(ch.isdigit() for t in in_toks for ch in t)):
        return []
    cands = []
    for p in family_parts or []:
        name_toks = semantic_tokens(p.get('name') or '')
        full_toks = set(name_toks)
        for v in (p.get('specs') or {}).values():
            full_toks |= semantic_tokens(str(v))
        if in_toks and in_toks <= full_toks:
            cands.append((in_toks == name_toks or in_toks == full_toks, p))
    exact = [p for eq, p in cands if eq]
    if len(exact) == 1:
        return [exact[0]]
    if len(cands) == 1:
        return [cands[0][1]]
    return []


# ============================================================
# 疑似重复检测（display-only 不自动合并）：信号分层 + Union-Find 聚组。
# 信号强度递减：SKU 精确(1.0) > 结构化 identity 键(0.95) > 语义 token
# 相等(0.9) / 子集+价格簇<1.3(0.8) > 子集(0.7) > 名称相似兜底(≤0.69)。
# 判据来自四轮合并战役（287→173）实证；brand 不参与分桶（同件 brand
# 标注不一致是常见录入噪声，按 category 分桶两两比，百件量级毫秒级）。
# 聚组只用强信号（≥0.8）：弱信号（子集无价/名称相似）只独立出对，
# 防同类名（"2T SATA HDD"↔"2T SATA SSD"↔…）经并查集级联成巨组。
# ============================================================
_DUP_STRONG_SIM = 0.8


def _duplicate_groups(records: List[dict], threshold: float = 0.6) -> dict:
    """纯函数（无 DB）：records → {total_groups, total_duplicate_parts, groups}。
    每条 record: {id, name, brand, category_id, category_name, oem_sku, alt_sku,
    specs: dict, latest_price, latest_currency}。groups[].reasons 为多信号列表。"""
    if len(records) < 2:
        return {"total_groups": 0, "total_duplicate_parts": 0, "groups": []}
    threshold_clamped = max(0.0, min(1.0, float(threshold)))

    def norm(s):
        return (s or "").strip()

    pre = {}
    for r in records:
        name_toks = semantic_tokens(r.get("name") or "")
        full_toks = set(name_toks)
        for v in (r.get("specs") or {}).values():
            full_toks |= semantic_tokens(str(v))
        pre[r["id"]] = {
            "identity": part_identity_key(r.get("name") or "", r.get("category_name") or "", r.get("specs") or None),
            "toks": full_toks,
        }

    pair_reasons: Dict[tuple, List[str]] = {}
    pair_sims: Dict[tuple, float] = {}

    def hit(a_id, b_id, reason, sim):
        key = tuple(sorted((a_id, b_id)))
        if reason not in pair_reasons.setdefault(key, []):
            pair_reasons[key].append(reason)
        pair_sims[key] = max(pair_sims.get(key, 0.0), sim)

    # L1 SKU 精确（全局跨分类）：同值 SKU 聚簇两两出对，天然覆盖 oem/alt 四组合
    sku_ids: Dict[str, List[Any]] = {}
    for r in records:
        for field in ("oem_sku", "alt_sku"):
            v = norm(r.get(field))
            if v:
                sku_ids.setdefault(v, []).append(r["id"])
    for v, ids in sku_ids.items():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                hit(ids[i], ids[j], f"SKU 相同 ({v})", 1.0)

    # 分类桶内：L2 identity / L3 语义 token / L4 名称相似
    cat_buckets: Dict[Any, List[dict]] = {}
    for r in records:
        cat_buckets.setdefault(r.get("category_id"), []).append(r)
    for bucket in cat_buckets.values():
        m = len(bucket)
        for i in range(m):
            a = bucket[i]
            pa = pre[a["id"]]
            for j in range(i + 1, m):
                b = bucket[j]
                pb = pre[b["id"]]
                if norm(a.get("name")) and norm(b.get("name")) and pa["identity"] == pb["identity"]:
                    hit(a["id"], b["id"], "结构化键一致", 0.95)
                ta, tb = pa["toks"], pb["toks"]
                if ta and tb:
                    if ta == tb:
                        hit(a["id"], b["id"], "语义 token 相等", 0.9)
                    elif len(ta) >= 2 and len(tb) >= 2 and (ta < tb or tb < ta):
                        # 单 token 名（"400G多模模块"→{400g}）信息不足，子集只会匹配一切 → 不比
                        pa_price, pb_price = a.get("latest_price"), b.get("latest_price")
                        if pa_price and pb_price:
                            ratio = max(pa_price, pb_price) / min(pa_price, pb_price)
                            if ratio < 1.3:
                                hit(a["id"], b["id"], f"语义 token 子集 + 最新价比 {ratio:.2f}", 0.8)
                            else:
                                hit(a["id"], b["id"], f"语义 token 子集（价比 {ratio:.2f}，可能真不同件）", 0.7)
                        else:
                            hit(a["id"], b["id"], "语义 token 子集", 0.7)
                # 数字 token 是判件决定性差异（嵌入校准同结论）：一侧独有的含数 token
                # 直接否决弱信号，防同前缀家族（EPYC 9xxx / PN 码尾字母）刷屏出对
                da = {x for x in ta if any(c.isdigit() for c in x)}
                db = {x for x in tb if any(c.isdigit() for c in x)}
                if not ((da - tb) or (db - ta)):
                    ratio4 = difflib.SequenceMatcher(None, a.get("name") or "", b.get("name") or "").ratio()
                    if ratio4 >= threshold_clamped:
                        # 兜底信号封顶 0.69：近同名对的 difflib 比值常高于语义分层，不封顶会淹没排序
                        hit(a["id"], b["id"], f"名称相似 ({ratio4:.2f})", min(ratio4, 0.69))

    # Union-Find 聚组
    parent = {r["id"]: r["id"] for r in records}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a_id, b_id in pair_reasons:
        if pair_sims[(a_id, b_id)] >= _DUP_STRONG_SIM:
            ra, rb = find(a_id), find(b_id)
            if ra != rb:
                parent[ra] = rb

    by_id = {r["id"]: r for r in records}
    comps: Dict[Any, List[Any]] = {}
    for r in records:
        comps.setdefault(find(r["id"]), []).append(r["id"])

    # 组 = 强分量 ∪ 未被强分量覆盖的弱对（弱对之间不级联、不并入强分量）
    group_ids: List[List[Any]] = [ids for ids in comps.values() if len(ids) >= 2]
    for key in pair_sims:
        if pair_sims[key] < _DUP_STRONG_SIM and find(key[0]) != find(key[1]):
            group_ids.append(list(key))

    def part_summary(r):
        specs = r.get("specs") or {}
        brief = " · ".join(f"{k}: {v}" for k, v in sorted(specs.items())[:2]) or None
        return {
            "id": r["id"],
            "name": r["name"],
            "brand": r.get("brand"),
            "oem_sku": r.get("oem_sku"),
            "alt_sku": r.get("alt_sku"),
            "category_name": r.get("category_name"),
            "specs_brief": brief,
            "latest_price": r.get("latest_price"),
            "latest_currency": r.get("latest_currency"),
        }

    groups = []
    for ids in group_ids:
        best_key, best_sim = None, None
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                key = tuple(sorted((ids[i], ids[j])))
                if key in pair_sims and (best_sim is None or pair_sims[key] > best_sim):
                    best_key, best_sim = key, pair_sims[key]
        prices = [by_id[pid].get("latest_price") for pid in ids]
        prices = [p for p in prices if p]
        price_ratio = round(max(prices) / min(prices), 2) if len(prices) >= 2 and min(prices) > 0 else None
        groups.append({
            "reasons": pair_reasons.get(best_key, ["疑似重复"]) if best_key else ["疑似重复"],
            "similarity": round(best_sim, 2) if best_sim is not None else 0.0,
            "price_ratio": price_ratio,
            "price_warning": price_ratio is not None and price_ratio >= 1.3,
            "parts": [part_summary(by_id[pid]) for pid in sorted(ids)],
        })

    groups.sort(key=lambda g: (g["similarity"], len(g["parts"])), reverse=True)
    return {
        "total_groups": len(groups),
        "total_duplicate_parts": sum(len(g["parts"]) for g in groups),
        "groups": groups,
    }


class KPRepository:
    """配件管理 Repository — 新表 + 旧接口兼容"""

    def __init__(self):
        self.session: Session = KP_SessionLocal()

    def close(self):
        if self.session:
            self.session.close()

    # ============================================================
    # 旧接口兼容层（pricing_engine / quote_service 使用）
    # ============================================================

    def get_latest_prices(self, search: str = "", category: str = "", sort_by: str = "date", sort_order: str = "desc", include_record_count: bool = True) -> List[dict]:
        """获取每个配件的最新价格（兼容旧接口）

        include_record_count=False 时跳过逐件 COUNT(*) 统计（导入/匹配热路径使用，
        避免 N+1 往返）；管理页等需要展示历史记录数的调用保持默认 True。
        """
        # 白名单排序字段
        allowed_sort = {"name": "name", "price": "latest_price", "date": "latest_date", "category": "category_name"}
        sort_field = allowed_sort.get(sort_by, "latest_date")
        if sort_order.lower() not in ("asc", "desc"):
            sort_order = "desc"

        q = self.session.query(
            KPPart.id,
            KPPart.name,
            KPPart.applicable,
            KPCategory.name.label("category_name"),
            KPPriceHistory.price,
            KPPriceHistory.currency,
            KPPriceHistory.price_date,
            KPPriceHistory.note,
        ).join(KPCategory, KPPart.category_id == KPCategory.id, isouter=True)\
         .join(KPPriceHistory, KPPart.id == KPPriceHistory.part_id, isouter=True)\
         .filter(KPPriceHistory.id == self._latest_price_subquery())

        if search:
            _s = _norm_hyphen(search)
            q = q.filter(_name_norm(KPPart.name).ilike(f"%{_s}%") | KPPriceHistory.note.ilike(f"%{_s}%"))
        if category:
            q = q.filter(KPCategory.name == category)

        # 动态排序
        if sort_field == "name":
            q = q.order_by(KPPart.name.asc() if sort_order == "asc" else KPPart.name.desc())
        elif sort_field == "latest_price":
            q = q.order_by(KPPriceHistory.price.asc() if sort_order == "asc" else KPPriceHistory.price.desc())
        elif sort_field == "latest_date":
            q = q.order_by(KPPriceHistory.price_date.asc() if sort_order == "asc" else KPPriceHistory.price_date.desc())
        elif sort_field == "category_name":
            q = q.order_by(KPCategory.name.asc() if sort_order == "asc" else KPCategory.name.desc())

        rows = q.all()
        result = []
        for r in rows:
            # 统计该配件的历史记录数（热路径可跳过，避免逐件 COUNT 的 N+1 往返）
            if include_record_count:
                record_count = self.session.query(KPPriceHistory).filter(KPPriceHistory.part_id == r.id).count()
            else:
                record_count = None
            result.append({
                "id": r.id,
                "category": r.category_name or "",
                "model": r.name,
                "price": r.price or 0.0,
                "currency": r.currency or "RMB",
                "date": r.price_date.isoformat() if r.price_date else "",
                "note": r.note or "",
                "record_count": record_count,
                "applicable": r.applicable,
            })
        return result

    def _latest_price_subquery(self):
        """子查询：每个 part_id 的最新 price_history id"""
        return text("""
            (SELECT MAX(id) FROM kp.kp_price_history ph2 WHERE ph2.part_id = kp.kp_parts.id)
        """)

    def get_latest_price_for_model(self, model: str) -> Optional[dict]:
        """根据配件名称获取最新价格（兼容旧接口）"""
        part = self.session.query(KPPart).filter(KPPart.name == model).first()
        if not part:
            return None
        latest = self.session.query(KPPriceHistory)\
            .filter(KPPriceHistory.part_id == part.id)\
            .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc())\
            .first()
        if not latest:
            return None
        return {
            "category": part.category.name if part.category else "",
            "model": part.name,
            "price": latest.price,
            "currency": latest.currency,
            "date": latest.price_date.isoformat() if latest.price_date else "",
            "note": latest.note,
        }

    def fuzzy_match_price(self, model_fragment: str) -> Optional[dict]:
        """模糊匹配配件名称获取最新价格（pricing_engine 使用）"""
        part = self.session.query(KPPart).filter(KPPart.name.ilike(f"%{model_fragment}%")).first()
        if not part:
            return None
        latest = self.session.query(KPPriceHistory)\
            .filter(KPPriceHistory.part_id == part.id)\
            .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc())\
            .first()
        if not latest:
            return None
        return {
            "category": part.category.name if part.category else "",
            "model": part.name,
            "price": latest.price,
            "currency": latest.currency,
            "date": latest.price_date.isoformat() if latest.price_date else "",
            "note": latest.note,
        }

    def get_parts_for_matching(self, families: List[str], latest_map: Optional[dict] = None) -> List[dict]:
        """按分类族取料号（含 specs + 最新价），供报价匹配候选。

        latest_map：外部预取的最新价 {model: row}，传入时不再内部重复拉全量价
        （导入流程跨 CFG 共享同一份快照，避免每分类族一次全量拉价）。
        """
        cats = []
        for f in families or []:
            cats.extend(category_family_members(f))
        cats = sorted(set(cats))
        if not cats:
            return []

        parts = self.session.query(KPPart)\
            .options(joinedload(KPPart.specs))\
            .join(KPCategory, KPPart.category_id == KPCategory.id)\
            .filter(KPCategory.name.in_(cats))\
            .all()
        if latest_map is not None:
            latest = {k: v for k, v in latest_map.items() if v.get('category') in cats}
        else:
            latest = {r['model']: r for r in self.get_latest_prices() if r.get('category') in cats}
        out = []
        for p in parts:
            lr = latest.get(p.name) or {}
            out.append({
                'id': p.id,
                'name': p.name,
                'category': p.category.name if p.category else '',
                'oem_sku': p.oem_sku or '',
                'alt_sku': p.alt_sku or '',
                'specs': {s.spec_key: s.spec_value for s in (p.specs or [])},
                'price': lr.get('price'),
                'currency': lr.get('currency', 'RMB'),
                'date': lr.get('date', ''),
            })
        return out

    def resolve_part(self, model: str, category: Optional[str] = None) -> Optional[KPPart]:
        """按上传型号解析库内件（工作台历史查询 / 价格入库共用一条阶梯）：
        精确名 → 归一名唯一 → 分类族 identity 唯一 → 语义 token 唯一；歧义返回 None 不猜。"""
        name = str(model or '').strip()
        if not name:
            return None
        parts = self.session.query(KPPart)\
            .options(joinedload(KPPart.specs), joinedload(KPPart.category)).all()
        for p in parts:
            if (p.name or '').strip() == name:
                return p
        norm = _inorm_general(name)
        norm_hits = [p for p in parts if _inorm_general(p.name or '') == norm]
        if len(norm_hits) == 1:
            return norm_hits[0]

        def as_dict(p: KPPart) -> dict:
            return {'id': p.id, 'name': p.name,
                    'specs': {s.spec_key: s.spec_value for s in (p.specs or [])}}

        scoped = parts
        family = category_family((category or '').lower()) or None
        if family:
            fam_names = set(category_family_members(family))
            scoped = [p for p in parts if (p.category.name if p.category else '') in fam_names]
            q_key = part_identity_key(name, family)
            key_hits = [p for p in scoped
                        if part_identity_key(p.name or '', family, as_dict(p)['specs']) == q_key]
            if len(key_hits) == 1:
                return key_hits[0]
        sem = semantic_match(name, [as_dict(p) for p in scoped])
        if len(sem) == 1:
            return next(p for p in parts if p.id == sem[0]['id'])
        return None

    def get_price_history(self, model: str, limit: int = 20, category: Optional[str] = None) -> List[dict]:
        """获取配件价格历史（兼容旧接口）。型号解析走 resolve_part 阶梯，不再要求名字精确相等。"""
        part = self.resolve_part(model, category)
        if not part:
            return []
        rows = self.session.query(KPPriceHistory)\
            .filter(KPPriceHistory.part_id == part.id)\
            .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc())\
            .limit(limit)\
            .all()
        return [{
            "id": r.id,
            "category": part.category.name if part.category else "",
            "model": part.name,
            "price": r.price,
            "currency": r.currency,
            "date": r.price_date.isoformat() if r.price_date else "",
            "note": r.note,
        } for r in rows]

    def insert_price(self, category: str, model: str, price: float,
                     currency: str = "RMB", date: str = None, note: str = "") -> bool:
        """插入价格记录（兼容旧接口）"""
        # 归一化到分类族，避免 "GPU card"/"Raid Card" 这类零散写法新建出同义分类
        category = canonical_category_name(category)
        # 先走 resolve_part 阶梯找已有件（写法差/别名不再出生重复件），找不到才新建
        part = self.resolve_part(model, category)
        if not part:
            # 查找或创建分类
            cat = self.session.query(KPCategory).filter(KPCategory.name == category).first()
            if not cat:
                cat = KPCategory(name=category)
                self.session.add(cat)
                self.session.flush()
            part = KPPart(category_id=cat.id, name=model)
            self.session.add(part)
            self.session.flush()

        # 解析日期
        price_date = None
        if date:
            try:
                price_date = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                price_date = datetime.now().date()
        else:
            price_date = datetime.now().date()

        history = KPPriceHistory(
            part_id=part.id,
            price=price,
            currency=currency,
            price_date=price_date,
            note=note
        )
        self.session.add(history)
        self.session.commit()
        return True

    def get_price_history_by_id(self, history_id: int) -> dict | None:
        """按 id 取单条价格历史（含所属型号名，供「改最新一条」的乐观锁校验用）"""
        r = self.session.query(KPPriceHistory).filter(KPPriceHistory.id == history_id).first()
        if not r:
            return None
        part = self.session.query(KPPart).filter(KPPart.id == r.part_id).first()
        return {
            "id": r.id,
            "model": part.name if part else "",
            "price": r.price,
            "currency": r.currency,
            "date": r.price_date.isoformat() if r.price_date else "",
            "note": r.note,
        }

    def update_price_history(self, history_id: int, price: float,
                             currency: str = "RMB", note: str = "") -> bool:
        """原地修改一条价格记录（金额/币种/备注；日期不动，历史仍只增不删）"""
        r = self.session.query(KPPriceHistory).filter(KPPriceHistory.id == history_id).first()
        if not r:
            return False
        r.price = price
        r.currency = currency
        r.note = note
        self.session.commit()
        return True

    def get_categories(self) -> List[dict]:
        """获取所有分类及其配件数量（兼容旧接口）"""
        rows = self.session.query(
            KPCategory.name,
            KPCategory.id,
            KPCategory.sort_order,
        ).outerjoin(KPPart, KPCategory.id == KPPart.category_id)\
         .group_by(KPCategory.id, KPCategory.name, KPCategory.sort_order)\
         .order_by(KPCategory.sort_order)\
         .all()

        result = []
        for r in rows:
            count = self.session.query(KPPart).filter(KPPart.category_id == r.id).count()
            result.append({
                "id": r.id,
                "category": r.name,
                "count": count,
                "sort_order": r.sort_order,
            })
        return result

    def get_by_category(self, category: str, search: str = "") -> List[dict]:
        """获取指定分类下的配件列表（兼容旧接口）"""
        q = self.session.query(KPPart, KPCategory.name.label("category_name"))\
            .join(KPCategory, KPPart.category_id == KPCategory.id, isouter=True)\
            .filter(KPCategory.name == category)

        if search:
            _s = _norm_hyphen(search)
            q = q.filter(_name_norm(KPPart.name).ilike(f"%{_s}%"))

        q = q.order_by(KPPart.name)
        rows = q.all()

        result = []
        for part, cat_name in rows:
            latest = self.session.query(KPPriceHistory)\
                .filter(KPPriceHistory.part_id == part.id)\
                .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc())\
                .first()
            record_count = self.session.query(KPPriceHistory).filter(KPPriceHistory.part_id == part.id).count()
            result.append({
                "id": part.id,
                "category": cat_name or "",
                "model": part.name,
                "price": latest.price if latest else 0.0,
                "currency": latest.currency if latest else "RMB",
                "date": latest.price_date.isoformat() if latest and latest.price_date else "",
                "note": latest.note if latest else "",
                "record_count": record_count,
                "applicable": part.applicable,  # 兼容机型/系列（I22：RAID 默认按机型选件用）
            })
        return result

    def get_by_category_with_spec_filter(self, category: str, spec_filters: list[dict]) -> List[dict]:
        """品类下按 spec 过滤配件（多条件 AND，支持数值范围 + 等值/IN）。

        spec_filters: [{spec_key, op, value, unit?}, ...]，AND 组合。
        - 数值型 op（>= <= > < =）：spec_value 提数字比较（'32 GB'→32、'5600 MT/s'→5600）。
        - 等值/IN（op='=' 且 value 非数值，或 op='in'）：字符串等值匹配（Type=DDR5、Link Speed=1G）。
        KP 件少（品类级几十件），全取 + Python 过滤，避免拼动态 raw SQL（且能组合多条件）。
        无 spec_filters / 全无 spec_key → 退化 get_by_category（向后兼容）。
        """
        if not spec_filters:
            return self.get_by_category(category)
        parsed = []
        for f in spec_filters:
            sk = (f.get("spec_key") or "").strip()
            if sk:
                parsed.append((sk, (f.get("op") or "=").strip(), f.get("value")))
        if not parsed:
            return self.get_by_category(category)

        parts = self.session.query(KPPart).options(joinedload(KPPart.specs)) \
            .join(KPCategory, KPPart.category_id == KPCategory.id, isouter=True) \
            .filter(KPCategory.name == category) \
            .order_by(KPPart.name).all()

        out: list = []
        for part in parts:
            spec_map = {s.spec_key: s.spec_value for s in (part.specs or [])}
            hit = _spec_match_all(spec_map, parsed)
            if not hit:
                continue
            latest = self.session.query(KPPriceHistory) \
                .filter(KPPriceHistory.part_id == part.id) \
                .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc()) \
                .first()
            record_count = self.session.query(KPPriceHistory).filter(KPPriceHistory.part_id == part.id).count()
            out.append({
                "id": part.id,
                "category": category,
                "model": part.name,
                "price": latest.price if latest else 0.0,
                "currency": latest.currency if latest else "RMB",
                "date": latest.price_date.isoformat() if latest and latest.price_date else "",
                "note": latest.note if latest else "",
                "record_count": record_count,
                "matched_spec": hit,
                "applicable": part.applicable,  # 系列适配过滤（引擎锁定机型后按 applicable 过滤候选）
            })
        return out

    def get_by_category_with_specs(self, category: str) -> list:
        """品类下全部件 + 规格字典（Capacity/Type…），供规格属性替代匹配。

        返回 [{id, category, model, price, currency, specs:{spec_key: spec_value}}]。
        与 get_by_category 不同：带上完整 specs，让调用方做「数值容量/接口」判断
        （2026-08-03：盘件按 Capacity/Type 属性替代，不再只靠名字字符串）。
        """
        parts = self.session.query(KPPart).options(joinedload(KPPart.specs)) \
            .join(KPCategory, KPPart.category_id == KPCategory.id, isouter=True) \
            .filter(KPCategory.name == category) \
            .order_by(KPPart.name).all()
        out = []
        for part in parts:
            latest = self.session.query(KPPriceHistory) \
                .filter(KPPriceHistory.part_id == part.id) \
                .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc()) \
                .first()
            out.append({
                "id": part.id,
                "category": category,
                "model": part.name,
                "brand": part.brand,
                "short_desc": part.short_desc,
                "applicable": part.applicable,
                "price": latest.price if latest else 0.0,
                "currency": latest.currency if latest else "RMB",
                "specs": {sp.spec_key: sp.spec_value for sp in (part.specs or [])},
            })
        return out

    # ── 检索别名（kp.kp_search_aliases；part_lexicon 词法引擎的唯一别名来源） ──

    def list_search_aliases(self, *, enabled_only: bool = True) -> List[Dict[str, Any]]:
        q = self.session.query(KPSearchAlias)
        if enabled_only:
            q = q.filter(KPSearchAlias.enabled == 1)  # type: ignore[arg-type]
        rows = q.order_by(KPSearchAlias.alias).all()
        return [r.to_dict() for r in rows]

    def upsert_search_alias(self, alias: str, expansion: str, note: Optional[str] = None) -> Dict[str, Any]:
        a = str(alias or "").strip()
        e = str(expansion or "").strip()
        if not a or not e:
            raise ValueError("alias/expansion 必填")
        row = self.session.query(KPSearchAlias).filter(KPSearchAlias.alias == a).first()
        if row:
            row.expansion = e
            if note is not None:
                row.note = note
        else:
            row = KPSearchAlias(alias=a, expansion=e, note=note, enabled=1)
            self.session.add(row)
        self.session.commit()
        return row.to_dict()

    def delete_search_alias(self, alias: str) -> bool:
        a = str(alias or "").strip()
        row = self.session.query(KPSearchAlias).filter(KPSearchAlias.alias == a).first()
        if not row:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def rename_model(self, old_model: str, new_model: str) -> bool:
        """重命名配件（兼容旧接口）"""
        part = self.session.query(KPPart).filter(KPPart.name == old_model).first()
        if part:
            part.name = new_model
            part.updated_at = datetime.utcnow()
            self.session.commit()
        return True

    def update_note(self, model: str, note: str) -> bool:
        """更新配件最新价格记录的备注（兼容旧接口）"""
        part = self.session.query(KPPart).filter(KPPart.name == model).first()
        if not part:
            return False
        latest = self.session.query(KPPriceHistory)\
            .filter(KPPriceHistory.part_id == part.id)\
            .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc())\
            .first()
        if latest:
            latest.note = note
            self.session.commit()
        return True

    def get_distinct_cpu_models(self) -> List[str]:
        """获取所有 CPU 型号（pricing_engine 使用）"""
        cpu_cat = self.session.query(KPCategory).filter(KPCategory.name == "CPU").first()
        if not cpu_cat:
            return []
        rows = self.session.query(KPPart.name)\
            .filter(KPPart.category_id == cpu_cat.id, KPPart.name.isnot(None), KPPart.name != "")\
            .order_by(KPPart.name)\
            .all()
        return [r[0] for r in rows]

    # ============================================================
    # 新增方法：配件完整 CRUD
    # ============================================================

    # ---- 分类管理 ----
    def list_categories(self) -> List[dict]:
        """列出所有分类（含层级）"""
        rows = self.session.query(KPCategory).order_by(KPCategory.sort_order).all()
        return [c.to_dict() for c in rows]

    def create_category(self, data: dict) -> dict:
        """创建分类"""
        cat = KPCategory(
            name=data["name"],
            parent_id=data.get("parent_id"),
            icon=data.get("icon"),
            sort_order=data.get("sort_order", 0),
            description=data.get("description"),
        )
        self.session.add(cat)
        self.session.commit()
        self.session.refresh(cat)
        return cat.to_dict()

    def update_category(self, cat_id: int, data: dict) -> Optional[dict]:
        """更新分类"""
        cat = self.session.query(KPCategory).get(cat_id)
        if not cat:
            return None
        for key in ["name", "parent_id", "icon", "sort_order", "description"]:
            if key in data:
                setattr(cat, key, data[key])
        self.session.commit()
        return cat.to_dict()

    def delete_category(self, cat_id: int) -> bool:
        """删除分类（需先确保无配件关联）"""
        cat = self.session.query(KPCategory).get(cat_id)
        if not cat:
            return False
        count = self.session.query(KPPart).filter(KPPart.category_id == cat_id).count()
        if count > 0:
            raise ValueError(f"分类下还有 {count} 个配件，无法删除")
        self.session.delete(cat)
        self.session.commit()
        return True

    # ---- 配件管理 ----
    def list_parts(self, category_id: int = None, search: str = "", page: int = 1, page_size: int = 20,
                   sort_by: str = "name", sort_order: str = "asc",
                   brands: str = None, price_filter: str = None, specs: str = None) -> Dict[str, Any]:
        """分页列出配件

        sort_by 支持: name / price / updated_at / first_price_date；
        price 按最新一次报价排序，first_price_date 按首次报价日期(入库时间)排序。
        brands: 逗号分隔的品牌名；price_filter: has_price/no_price/multi；specs: JSON 字符串 {key:[values]}。
        """
        q = self.session.query(KPPart).options(joinedload(KPPart.category))
        if category_id:
            q = q.filter(KPPart.category_id == category_id)
        if search:
            q = q.filter(KPPart.name.ilike(f"%{search}%") | KPPart.oem_sku.ilike(f"%{search}%") | KPPart.brand.ilike(f"%{search}%"))

        # 品牌 / 价格记录 / 规格筛选
        if brands:
            brand_list = [b.strip() for b in brands.split(',') if b.strip()]
            if brand_list:
                q = q.filter(KPPart.brand.in_(brand_list))
        if price_filter in ('has_price', 'no_price', 'multi'):
            price_count_sq = select(func.count(KPPriceHistory.id))\
                .where(KPPriceHistory.part_id == KPPart.id).scalar_subquery()
            if price_filter == 'has_price':
                q = q.filter(price_count_sq > 0)
            elif price_filter == 'no_price':
                q = q.filter(price_count_sq == 0)
            elif price_filter == 'multi':
                q = q.filter(price_count_sq >= 3)
        if specs:
            specs_dict = None
            try:
                specs_dict = json.loads(specs) if isinstance(specs, str) else specs
            except Exception:
                specs_dict = None
            if isinstance(specs_dict, dict):
                for sk, svs in specs_dict.items():
                    values = svs if isinstance(svs, list) else [svs]
                    values = [str(v) for v in values if v is not None and str(v).strip()]
                    if not values:
                        continue
                    q = q.filter(exists().where(and_(
                        KPPartSpec.part_id == KPPart.id,
                        KPPartSpec.spec_key == sk,
                        KPPartSpec.spec_value.in_(values),
                    )))

        # 排序键：price 用标量子查询取最新报价（与列表 latest_price 口径一致，按 price_date desc, id desc）
        if sort_by == "price":
            sort_expr = select(KPPriceHistory.price)\
                .where(KPPriceHistory.part_id == KPPart.id)\
                .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc())\
                .limit(1)\
                .scalar_subquery()
        elif sort_by == "updated_at":
            sort_expr = KPPart.updated_at
        elif sort_by == "first_price_date":
            # 入库时间：取该配件最早一次报价日期(MIN price_date)。
            # 实测 created_at 68% 挤在同一次批量导入、区分度极差，故用首次报价日期代替。
            sort_expr = select(func.min(KPPriceHistory.price_date))\
                .where(KPPriceHistory.part_id == KPPart.id)\
                .scalar_subquery()
        else:
            sort_expr = KPPart.name

        sort_expr = sort_expr.desc() if sort_order == "desc" else sort_expr.asc()
        sort_expr = sort_expr.nullslast()

        total = q.count()
        rows = q.order_by(sort_expr).offset((page - 1) * page_size).limit(page_size).all()

        items = []
        for part in rows:
            latest = self.session.query(KPPriceHistory)\
                .filter(KPPriceHistory.part_id == part.id)\
                .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc())\
                .first()
            d = part.to_dict()
            d["latest_price"] = latest.price if latest else None
            d["latest_date"] = latest.price_date.isoformat() if latest and latest.price_date else None
            d["latest_currency"] = latest.currency if latest else None
            items.append(d)

        return {"total": total, "page": page, "page_size": page_size, "items": items}

    def list_brands(self, category_id: int = None) -> list:
        """聚合品牌列表 + 计数（可选按分类过滤，用于筛选面板）"""
        q = self.session.query(KPPart.brand, func.count(KPPart.id))\
            .filter(KPPart.brand.isnot(None), KPPart.brand != '')
        if category_id:
            q = q.filter(KPPart.category_id == category_id)
        rows = q.group_by(KPPart.brand).order_by(func.count(KPPart.id).desc()).all()
        return [{"brand": b, "count": int(c)} for b, c in rows]

    def list_spec_facets(self, category_id: int = None) -> Dict[str, list]:
        """聚合规格维度：{spec_key: [{value, count}]}（可选按分类过滤，用于动态筛选面板）"""
        q = self.session.query(KPPartSpec.spec_key, KPPartSpec.spec_value, func.count(KPPart.id))\
            .join(KPPart, KPPartSpec.part_id == KPPart.id)\
            .filter(KPPartSpec.spec_value.isnot(None), KPPartSpec.spec_value != '')
        if category_id:
            q = q.filter(KPPart.category_id == category_id)
        rows = q.group_by(KPPartSpec.spec_key, KPPartSpec.spec_value).all()
        facets: Dict[str, list] = {}
        for k, v, c in rows:
            facets.setdefault(k, []).append({"value": v, "count": int(c)})
        for k in facets:
            facets[k].sort(key=lambda x: x["count"], reverse=True)
        return facets

    def get_part(self, part_id: int) -> Optional[dict]:
        """获取单个配件详情（含规格、价格历史、兼容机型）"""
        part = self.session.query(KPPart).options(
            joinedload(KPPart.category),
            joinedload(KPPart.specs),
            joinedload(KPPart.price_history),
            joinedload(KPPart.compat_servers),
        ).get(part_id)
        if not part:
            return None
        return part.to_dict(include_specs=True, include_history=True, include_compat=True)

    # ---- 总览统计（仪表盘） ----
    def _summarize_parts(self, parts) -> list:
        """把 KPPart 列表归一成仪表盘用的摘要（含最新报价）"""
        out = []
        for part in parts:
            latest = self.session.query(KPPriceHistory) \
                .filter(KPPriceHistory.part_id == part.id) \
                .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc()) \
                .first()
            out.append({
                "id": part.id,
                "name": part.name,
                "category_name": part.category.name if part.category else None,
                "brand": part.brand,
                "latest_price": latest.price if latest else None,
                "latest_currency": latest.currency if latest else None,
                "latest_date": latest.price_date.isoformat() if latest and latest.price_date else None,
                "created_at": part.created_at.isoformat() if part.created_at else None,
            })
        return out

    def get_stats(self, recent_limit: int = 6, series_days: int = 14) -> dict:
        """配件库总览：总数 / 本周新增 / 上周新增 / 有效价格数 / 每日新增序列 / 最近入库 / 最近调价"""
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        total = self.session.query(func.count(KPPart.id)).scalar() or 0
        this_week_new = self.session.query(func.count(KPPart.id)) \
            .filter(KPPart.created_at >= week_ago).scalar() or 0
        last_week_new = self.session.query(func.count(KPPart.id)) \
            .filter(KPPart.created_at >= two_weeks_ago, KPPart.created_at < week_ago).scalar() or 0

        # 有效价格：最新报价日在最近 2 天内的配件数
        cutoff = date.today() - timedelta(days=2)
        latest_price_date_sq = select(func.max(KPPriceHistory.price_date)) \
            .where(KPPriceHistory.part_id == KPPart.id).scalar_subquery()
        valid_price_count = self.session.query(func.count(KPPart.id)) \
            .filter(latest_price_date_sq >= cutoff).scalar() or 0

        # 最近 N 天每日新增序列（缺失日补 0）
        series_start_dt = now - timedelta(days=series_days - 1)
        series_start = series_start_dt.date()
        rows = self.session.query(
            func.cast(KPPart.created_at, Date).label("d"),
            func.count(KPPart.id),
        ).filter(KPPart.created_at >= series_start_dt) \
         .group_by(text("d")).order_by(text("d")).all()
        counts_by_day = {r[0]: int(r[1]) for r in rows}
        new_series = []
        for i in range(series_days):
            d = series_start + timedelta(days=i)
            new_series.append({"date": d.isoformat(), "count": counts_by_day.get(d, 0)})

        # 最近入库（按 created_at desc）
        recent_parts_q = self.session.query(KPPart) \
            .options(joinedload(KPPart.category)) \
            .order_by(KPPart.created_at.desc().nullslast(), KPPart.id.desc()) \
            .limit(recent_limit).all()
        recent_parts = self._summarize_parts(recent_parts_q)

        # 最近调价（按每个配件最新 price_date desc）
        latest_sub = select(
            KPPriceHistory.part_id.label("pid"),
            func.max(KPPriceHistory.price_date).label("lpd"),
        ).group_by(KPPriceHistory.part_id).subquery()
        price_rows = self.session.query(KPPart) \
            .join(latest_sub, latest_sub.c.pid == KPPart.id) \
            .options(joinedload(KPPart.category)) \
            .order_by(latest_sub.c.lpd.desc().nullslast(), KPPart.id.desc()) \
            .limit(recent_limit).all()
        recent_price_updates = self._summarize_parts(price_rows)

        return {
            "total": total,
            "this_week_new": this_week_new,
            "last_week_new": last_week_new,
            "valid_price_count": valid_price_count,
            "new_series": new_series,
            "recent_parts": recent_parts,
            "recent_price_updates": recent_price_updates,
        }

    # ---- 数据洞察：价格异动 / 比价矩阵 / 疑似重复 ----

    def _latest_price_map(self, part_ids: List[int]) -> Dict[int, KPPriceHistory]:
        """一次查全量价格历史，按 part_id 分组取最新一条（口径：price_date DESC NULLS LAST, id DESC）。"""
        if not part_ids:
            return {}
        rows = self.session.query(KPPriceHistory) \
            .filter(KPPriceHistory.part_id.in_(part_ids)) \
            .order_by(KPPriceHistory.part_id,
                      KPPriceHistory.price_date.desc().nullslast(),
                      KPPriceHistory.id.desc()).all()
        latest: Dict[int, KPPriceHistory] = {}
        for h in rows:
            if h.part_id not in latest:
                latest[h.part_id] = h
        return latest

    def get_price_movers(self, days: int = 7, limit: int = 10) -> dict:
        """价格异动看板：每个配件最新价 vs N 天前最近一条价的涨跌幅，返回涨幅/跌幅 TOP。"""
        cutoff_days = max(1, int(days))
        top_n = max(1, int(limit))

        # 一次拉全量价格历史，按 part_id 分组（已按最新价口径排序）
        all_hist = self.session.query(KPPriceHistory) \
            .order_by(KPPriceHistory.part_id,
                      KPPriceHistory.price_date.desc().nullslast(),
                      KPPriceHistory.id.desc()).all()
        by_part: Dict[int, List[KPPriceHistory]] = {}
        for h in all_hist:
            by_part.setdefault(h.part_id, []).append(h)

        candidates = []  # [(part_id, curr, prev, delta_pct)]
        for pid, hist in by_part.items():
            if len(hist) < 2:
                continue
            curr = hist[0]
            if not curr.price or curr.price_date is None:
                continue
            threshold_date = curr.price_date - timedelta(days=cutoff_days)
            prev = None
            for r in hist[1:]:
                if r.price_date is not None and r.price_date <= threshold_date:
                    prev = r
                    break
            if not prev or not prev.price:
                continue
            delta_pct = (curr.price - prev.price) / prev.price * 100
            candidates.append((pid, curr, prev, delta_pct))

        # 批量取 part 实体
        part_ids = [c[0] for c in candidates]
        parts_map = {}
        if part_ids:
            parts = self.session.query(KPPart).options(joinedload(KPPart.category)) \
                .filter(KPPart.id.in_(part_ids)).all()
            parts_map = {p.id: p for p in parts}

        def build(c):
            pid, curr, prev, delta_pct = c
            part = parts_map.get(pid)
            return {
                "id": pid,
                "name": part.name if part else None,
                "category_name": part.category.name if part and part.category else None,
                "brand": part.brand if part else None,
                "latest_price": curr.price,
                "latest_currency": curr.currency,
                "latest_date": curr.price_date.isoformat() if curr.price_date else None,
                "prev_price": prev.price,
                "prev_date": prev.price_date.isoformat() if prev.price_date else None,
                "delta_pct": round(delta_pct, 2),
            }

        gainers = sorted([build(c) for c in candidates if c[3] > 0],
                         key=lambda x: x["delta_pct"], reverse=True)[:top_n]
        losers = sorted([build(c) for c in candidates if c[3] < 0],
                        key=lambda x: x["delta_pct"])[:top_n]

        return {"days": cutoff_days, "gainers": gainers, "losers": losers}

    def detect_duplicates(self, threshold: float = 0.6) -> dict:
        """疑似重复检测（display-only，不做合并）。信号层见 _duplicate_groups：
        SKU 精确 / 结构化 identity 键 / 语义 token（含价格簇佐证）/ 名称相似兜底。"""
        parts = self.session.query(KPPart).options(
            joinedload(KPPart.category), joinedload(KPPart.specs)).all()
        if len(parts) < 2:
            return {"total_groups": 0, "total_duplicate_parts": 0, "groups": []}

        latest_map = self._latest_price_map([p.id for p in parts])
        records = []
        for p in parts:
            lp = latest_map.get(p.id)
            records.append({
                "id": p.id,
                "name": p.name,
                "brand": p.brand,
                "oem_sku": p.oem_sku,
                "alt_sku": p.alt_sku,
                "category_id": p.category_id,
                "category_name": p.category.name if p.category else None,
                "specs": {s.spec_key: s.spec_value for s in p.specs},
                "latest_price": lp.price if lp else None,
                "latest_currency": lp.currency if lp else None,
            })
        return _duplicate_groups(records, threshold)

    def create_part(self, data: dict) -> dict:
        """创建配件"""
        part = KPPart(
            category_id=data.get("category_id"),
            oem_sku=data.get("oem_sku"),
            alt_sku=data.get("alt_sku"),
            brand=data.get("brand"),
            name=data["name"],
            short_desc=data.get("short_desc"),
            full_desc=data.get("full_desc"),
            condition=data.get("condition", "全新"),
            lead_time=data.get("lead_time"),
            image_url=data.get("image_url"),
            datasheet_url=data.get("datasheet_url"),
            moq=data.get("moq", 1),
            applicable=data.get("applicable"),
        )
        self.session.add(part)
        self.session.flush()

        # 批量创建规格
        if "specs" in data and data["specs"]:
            for i, spec in enumerate(data["specs"]):
                s = KPPartSpec(part_id=part.id, spec_key=spec["key"], spec_value=spec.get("value"), sort_order=i)
                self.session.add(s)

        # 批量创建兼容机型
        if "compat_servers" in data and data["compat_servers"]:
            for model in data["compat_servers"]:
                c = KPPartCompat(part_id=part.id, server_model=model)
                self.session.add(c)

        self.session.commit()
        self.session.refresh(part)
        return part.to_dict()

    def update_part(self, part_id: int, data: dict) -> Optional[dict]:
        """更新配件"""
        part = self.session.query(KPPart).get(part_id)
        if not part:
            return None

        for key in ["category_id", "oem_sku", "alt_sku", "brand", "name", "short_desc",
                    "full_desc", "condition", "lead_time", "image_url", "datasheet_url", "moq", "applicable"]:
            if key in data:
                setattr(part, key, data[key])
        part.updated_at = datetime.utcnow()

        # 更新规格（全量替换）
        if "specs" in data:
            self.session.query(KPPartSpec).filter(KPPartSpec.part_id == part_id).delete()
            for i, spec in enumerate(data["specs"]):
                s = KPPartSpec(part_id=part_id, spec_key=spec["key"], spec_value=spec.get("value"), sort_order=i)
                self.session.add(s)

        # 更新兼容机型（全量替换）
        if "compat_servers" in data:
            self.session.query(KPPartCompat).filter(KPPartCompat.part_id == part_id).delete()
            for model in data["compat_servers"]:
                c = KPPartCompat(part_id=part_id, server_model=model)
                self.session.add(c)

        self.session.commit()
        return part.to_dict()

    def delete_part(self, part_id: int) -> bool:
        """删除配件（级联删除规格、价格历史、兼容机型）"""
        part = self.session.query(KPPart).get(part_id)
        if not part:
            return False
        self.session.delete(part)
        self.session.commit()
        return True

    # ---- 批量导入/导出辅助 ----
    def find_or_create_category_by_name(self, name: Optional[str]) -> int:
        """按名称查找分类,不存在则创建(空名兜底「未分类」)。返回 category_id。"""
        nm = (str(name).strip() if name else "") or "未分类"
        cat = self.session.query(KPCategory).filter(KPCategory.name == nm).first()
        if not cat:
            cat = KPCategory(name=nm)
            self.session.add(cat)
            self.session.flush()
        return cat.id

    def find_parts_by_dedupe_key(self, oem_sku: Optional[str] = None,
                                 name: Optional[str] = None,
                                 category: Optional[str] = None) -> List[KPPart]:
        """去重键查询:优先 oem_sku,空则 name 精确,再空则同 category 下 identity 匹配。
        返回列表(空/单/多 → new/update/conflict)。identity 层抓大小写/空格/冗余词变体
        (SSD/U.2/形态等已结构化的冗余标注),但 M.2/U.2、HDD/SSD、gen3/gen4 因 spec/差异词
        不同不会被误合。"""
        if oem_sku and str(oem_sku).strip():
            return self.session.query(KPPart)\
                .filter(KPPart.oem_sku == str(oem_sku).strip()).all()
        if name and str(name).strip():
            nm = str(name).strip()
            exact = self.session.query(KPPart).filter(KPPart.name == nm).all()
            if exact:
                return exact
            if category and str(category).strip():
                cat_name = str(category).strip()
                cat = self.session.query(KPCategory).filter(KPCategory.name == cat_name).first()
                if cat:
                    new_key = part_identity_key(nm, cat_name)
                    cands = self.session.query(KPPart).options(joinedload(KPPart.specs))\
                        .filter(KPPart.category_id == cat.id).all()
                    hits = [p for p in cands
                            if part_identity_key(p.name, cat_name,
                                                 {s.spec_key: s.spec_value for s in (p.specs or [])}) == new_key]
                    if hits:
                        return hits
        return []

    def list_all_for_export(self, category_id: Optional[int] = None) -> List[KPPart]:
        """导出用:不分页,eager load category/specs/price_history。"""
        q = self.session.query(KPPart).options(
            joinedload(KPPart.category),
            joinedload(KPPart.specs),
            joinedload(KPPart.price_history),
        )
        if category_id:
            q = q.filter(KPPart.category_id == category_id)
        return q.order_by(KPPart.id.asc()).all()

    def list_spec_keys(self, category_id: Optional[int] = None, top_n: int = 15) -> List[tuple]:
        """[(spec_key, freq)] 按 freq 降序,供导入模板预置高频规格列。"""
        q = self.session.query(KPPartSpec.spec_key, func.count(KPPartSpec.id))\
            .join(KPPart, KPPartSpec.part_id == KPPart.id)\
            .filter(KPPartSpec.spec_key.isnot(None), KPPartSpec.spec_key != '')
        if category_id:
            q = q.filter(KPPart.category_id == category_id)
        rows = q.group_by(KPPartSpec.spec_key)\
            .order_by(func.count(KPPartSpec.id).desc()).limit(top_n).all()
        return [(k, int(c)) for k, c in rows]

    # ---- 价格历史 ----
    def add_price_history(self, part_id: int, price: float, currency: str = "RMB",
                          price_date: str = None, note: str = "", source: str = "") -> dict:
        """添加价格记录"""
        pd = None
        if price_date:
            try:
                pd = datetime.strptime(price_date, "%Y-%m-%d").date()
            except ValueError:
                pd = datetime.now().date()
        else:
            pd = datetime.now().date()

        h = KPPriceHistory(part_id=part_id, price=price, currency=currency, price_date=pd, note=note, source=source)
        self.session.add(h)
        self.session.commit()
        self.session.refresh(h)
        return h.to_dict()

    def price_history_exists(self, part_id: int, price: float,
                             currency: Optional[str] = None,
                             price_date: Any = None) -> bool:
        """判断同 part 是否已存在相同(价格 + 币种 + 日期)的记录,用于导入去重防堆积。"""
        if price is None:
            return False
        pd_ = None
        if price_date:
            try:
                pd_ = datetime.strptime(str(price_date)[:10], "%Y-%m-%d").date()
            except ValueError:
                pd_ = None
        if pd_ is None:
            return False  # 没有日期不去重(避免误合并不同时点的报价)
        q = self.session.query(KPPriceHistory).filter(
            KPPriceHistory.part_id == part_id,
            KPPriceHistory.price == price,
            KPPriceHistory.currency == (currency or "RMB"),
            KPPriceHistory.price_date == pd_,
        )
        return self.session.query(q.exists()).scalar()

    def update_price_history(self, price_id: int, price: float = None,
                              currency: str = None,
                              price_date: str = None, note: str = None) -> bool:
        """更新价格记录"""
        h = self.session.query(KPPriceHistory).filter(KPPriceHistory.id == price_id).first()
        if not h:
            return False
        if price is not None:
            h.price = price
        if currency is not None:
            h.currency = currency
        if price_date is not None:
            try:
                h.price_date = datetime.strptime(price_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        if note is not None:
            h.note = note
        self.session.commit()
        return True

    def delete_price_history(self, price_id: int) -> bool:
        """删除价格记录"""
        h = self.session.query(KPPriceHistory).filter(KPPriceHistory.id == price_id).first()
        if not h:
            return False
        self.session.delete(h)
        self.session.commit()
        return True

    # ---- 关联配件 ----
    def list_related(self, part_id: int) -> List[dict]:
        """获取关联配件"""
        rows = self.session.query(KPPartRelated).filter(KPPartRelated.source_part_id == part_id)\
            .order_by(KPPartRelated.sort_order).all()
        result = []
        for r in rows:
            target = self.session.query(KPPart).get(r.target_part_id)
            result.append({
                "id": r.id,
                "source_part_id": r.source_part_id,
                "target_part_id": r.target_part_id,
                "target_name": target.name if target else None,
                "sort_order": r.sort_order,
            })
        return result

    def add_related(self, source_part_id: int, target_part_id: int, sort_order: int = 0) -> dict:
        """添加关联配件"""
        r = KPPartRelated(source_part_id=source_part_id, target_part_id=target_part_id, sort_order=sort_order)
        self.session.add(r)
        self.session.commit()
        self.session.refresh(r)
        return r.to_dict()

    def remove_related(self, relation_id: int) -> bool:
        """删除关联"""
        r = self.session.query(KPPartRelated).get(relation_id)
        if not r:
            return False
        self.session.delete(r)
        self.session.commit()
        return True
