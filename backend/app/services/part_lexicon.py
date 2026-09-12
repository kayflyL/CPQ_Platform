# -*- coding: utf-8 -*-
"""配件检索词法引擎（2026-09-12 P0）：纯函数，无 DB 依赖。

背景：data_tools 旧词法只吃拉丁/数字 token 且只匹配料号名——中文口语词（万兆/千兆/智铠/核显）
整体丢失、brand/specs 值不参与、数字串子串误报（智铠100→H100）。本模块把「查询→token」与
「料→可检索 blob」标准化，统一供 part_query（收窄）与 part_recall（召回）打分：

- 查询侧：拉丁 token（≥3 位数字段 / 含数字混合词）+ 中文连续段（≥2 字）+ 别名扩展（万兆→10G）
- 料侧 blob：name + brand + spec 值 + short_desc（归一后小写）
- 加权：中文名命中 > 数字/混合词名命中 > 别名命中 > blob 外围命中；查询带中文段时数字串权重降档
  （治「智铠100」靠裸数字 100 误配 H100）
- 判别轴（discriminator families）：存储介质轴 {sata,nvme,sas}、盘种轴 {ssd,hdd}、内存代际轴
  {ddr3,ddr4,ddr5}——查询点名了某轴的值、料也声明了该轴的值但两者不相交 → 该料出局
  （治「1.92T SATA」意图召回 NVMe）

别名数据在 kp.kp_search_aliases 表（DB 唯一来源，startup 空表种子），由调用方注入。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

# ── 归一 ──────────────────────────────────────────────────────────────

_CJK_NUM = {"一": "1", "二": "2", "两": "2", "三": "3", "四": "4", "五": "5",
            "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}
_RE_PORT_CN = re.compile(r"([0-9]|[一二两三四五六七八九十])\s*口")
_RE_FULLWIDTH = re.compile(r"［］（）｛｝，。：；！？　")  # 全角标点归半角空格


def normalize_text(text: str) -> str:
    """检索前归一：小写、全角标点→空格、「4口/四口」→「4port」。双方（查询与 blob）同规则。"""
    s = str(text or "").lower()
    s = s.replace("（", " ").replace("）", " ").replace("，", " ").replace("。", " ") \
         .replace("：", " ").replace("；", " ").replace("！", " ").replace("？", " ").replace("　", " ")
    s = _RE_PORT_CN.sub(lambda m: f"{_CJK_NUM.get(m.group(1), m.group(1))}port", s)
    return s


# ── 判别轴 ────────────────────────────────────────────────────────────
# 同轴值互斥：查询点名 A、料声明 B（A≠B 同轴）→ 过滤。料未声明该轴 → 不过滤（不臆造）。

DISCRIMINATOR_FAMILIES: List[Set[str]] = [
    {"sata", "nvme", "sas", "u.2"},
    {"ssd", "hdd"},
    {"ddr3", "ddr4", "ddr5"},
]


# ── 查询 token ────────────────────────────────────────────────────────

class QueryTokens(dict):
    """dict 子类方便调试打印；字段见 extract_query_tokens。"""

    def __repr__(self) -> str:  # pragma: no cover
        return (f"QueryTokens(num={self['num_tokens']}, mixed={self['mixed_tokens']}, "
                f"alpha={self['alpha_tokens']}, cjk={self['cjk_runs']}, "
                f"alias={self['alias_tokens']}, qcap={self['capacity_gb']})")


def extract_query_tokens(text: str, aliases: Optional[List[dict]] = None) -> QueryTokens:
    """查询/行描述 → 可检索 token 集合。

    aliases 形如 [{"alias": "万兆", "expansion": "10G"}, ...]，alias 作为子串出现在
    原文里即把 expansion 拆成拉丁 token 并入（expansion 里的中文段同样参与，如 智凯→智铠）。
    """
    raw = str(text or "")
    s = normalize_text(raw)
    latin = re.findall(r"[a-z0-9.]+", s)
    num_tokens = {t for t in latin if t.replace(".", "").isdigit() and len(t) >= 3}
    # 「6t/8g/96c/1g」数字+单位短探针（行描述最硬的检索词）；ghz 是全员规格噪音
    mixed_tokens = {t for t in latin
                    if any(c.isalpha() for c in t) and any(c.isdigit() for c in t)
                    and len(t) >= 2 and not t.endswith("ghz")}
    # 纯字母词（≥2 位）：brand/规格值词形（mellanox/ssd/nvme/sata/rdimm…）；单位噪音排除
    alpha_tokens = {t for t in latin if t.isalpha() and len(t) >= 2
                    and t not in ("ghz", "mhz", "gb", "tb", "wb", "and", "for")}
    cjk_full = set(re.findall(r"[一-鿿]{2,}", s))
    cjk_runs = set(cjk_full)
    # 长连续段（「块千兆网卡」）整段匹配不到名字里的「网卡」——补 2/3 字滑窗子词，
    # 让段内的词形也能命中。窗口 gram 与原始 run 分级计权（score_row）：跨字边界的
    # 2-gram（如「口网」）是滑窗伪词，证据弱，只给低分——不引入误过滤，只压排序。
    for _run in list(cjk_full):
        if len(_run) <= 3:
            continue
        for _n in (2, 3):
            for _i in range(len(_run) - _n + 1):
                cjk_runs.add(_run[_i:_i + _n])
    alias_tokens: Set[str] = set()
    for a in aliases or []:
        al = str((a or {}).get("alias") or "").strip()
        exp = str((a or {}).get("expansion") or "").strip()
        if not al or not exp:
            continue
        if al in raw or al in s:
            es = normalize_text(exp)
            alias_tokens.update(re.findall(r"[a-z0-9.]+", es))
            alias_tokens.update(re.findall(r"[一-鿿]{2,}", es))
    # 容量等值（GB）只在原文真带容量写法时启用——裸数字（"4个"的 4）不算容量
    capacity_gb: Optional[float] = None
    if re.search(r"\d+(?:\.\d+)?\s*(?:g|gb|t|tb)(?![a-z0-9])", s):
        capacity_gb = _gb_of(s)
    return QueryTokens(num_tokens=num_tokens, mixed_tokens=mixed_tokens,
                       alpha_tokens=alpha_tokens, cjk_runs=cjk_runs,
                       cjk_full=cjk_full,
                       alias_tokens=alias_tokens,
                       capacity_gb=capacity_gb, _normalized=s)


_UNIT_GB = {"g": 1.0, "gb": 1.0, "t": 1024.0, "tb": 1024.0}


def _gb_of(text: str) -> Optional[float]:
    """容量写法 → GB 数值（480G/1.92T/768GB）；解析不出返回 None。"""
    s = normalize_text(text)
    best: Optional[float] = None
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(g|gb|t|tb)(?![a-z0-9])", s):
        v = float(m.group(1)) * _UNIT_GB[m.group(2)]
        best = v if best is None else max(best, v)
    return best


# ── 料侧 blob ─────────────────────────────────────────────────────────

def build_row_blob(row: dict) -> Tuple[str, str]:
    """库件行 → (归一名, 归一全 blob)。blob = name + brand + spec 值 + short_desc。

    spec 键本身不进 blob（键是维度名不是检索词），值进（10G/光口/DDR5/SATA…）。
    """
    name = normalize_text(row.get("model") or row.get("name") or "")
    parts = [name,
             normalize_text(row.get("brand") or ""),
             normalize_text(row.get("short_desc") or "")]
    specs = row.get("specs")
    if isinstance(specs, dict):
        for v in specs.values():
            if v is None or str(v).strip() == "":
                continue
            parts.append(normalize_text(str(v)))
    blob = " ".join(p for p in parts if p)
    return name, blob


# ── 打分 ──────────────────────────────────────────────────────────────

def _hit(token: str, target: str) -> bool:
    """拉丁 token 边界命中：前不得是数字/小数点（6t 不得命中 1.6t 内嵌），后不得是数字
    （100 不得命中 1000 内嵌）；前是字母允许（kh50000 ⊃ 50000 是合法桥接）。"""
    return re.search(rf"(?<![0-9.]){re.escape(token)}(?![0-9])", target) is not None


def score_row(tokens: QueryTokens, row: dict, *, row_name: str = None,
              row_blob: str = None) -> Tuple[int, List[str]]:
    """加权打分。返回 (score, hit_kinds)；0 分 = 不召回。排序稳定位：同分按名序（调用方 sort 负责）。"""
    if row_name is None or row_blob is None:
        row_name, row_blob = build_row_blob(row)
    score = 0
    kinds: List[str] = []
    # 中文段：原始 run > 3-gram 滑窗 > 2-gram 滑窗（跨字边界伪词证据弱）。
    # 已命中的长词吸收其子词（网络接口卡 命中后不再重复计 网络/接口）。
    _full = tokens.get("cjk_full") or set()
    _matched: List[str] = []
    for r in sorted(tokens["cjk_runs"], key=len, reverse=True):
        if any(r in m for m in _matched):
            continue
        if r in row_name:
            score += 6 if r in _full else (5 if len(r) >= 3 else 3)
            kinds.append(f"cjk:{r}")
            _matched.append(r)
        elif r in row_blob:
            score += 2 if (r in _full or len(r) >= 3) else 1
            kinds.append(f"cjk_blob:{r}")
            _matched.append(r)
    # 数字段/混合词：名内命中；查询带中文段时数字串裸命中降档（防 智铠100→H100 误报坐大）
    num_w = 3 if tokens["cjk_runs"] else 4
    for t in tokens["num_tokens"]:
        if _hit(t, row_name):
            score += num_w
            kinds.append(f"num:{t}")
        elif _hit(t, row_blob):
            score += 1
            kinds.append(f"num_blob:{t}")
    for t in tokens["mixed_tokens"]:
        if _hit(t, row_name):
            score += 4
            kinds.append(f"mix:{t}")
        elif _hit(t, row_blob):
            score += 1
            kinds.append(f"mix_blob:{t}")
    for t in tokens["alpha_tokens"]:
        if _hit(t, row_name):
            score += 3
            kinds.append(f"alpha:{t}")
        elif _hit(t, row_blob):
            score += 1
            kinds.append(f"alpha_blob:{t}")
    # 别名扩展 token（10G/1G/ssd…）：blob 命中即算（值多在 spec 里）
    for t in tokens["alias_tokens"]:
        if re.search(r"[一-鿿]", t):
            if t in row_name or t in row_blob:
                score += 5
                kinds.append(f"alias:{t}")
        elif _hit(t, row_name):
            score += 4
            kinds.append(f"alias:{t}")
        elif _hit(t, row_blob):
            score += 2
            kinds.append(f"alias_blob:{t}")
    # 容量等值（±1%）：行名容量 vs 查询容量
    qcap = tokens["capacity_gb"]
    if qcap is not None and qcap > 0:
        mcap = _gb_of(row_name)
        if mcap is not None and abs(mcap - qcap) <= max(1.0, qcap * 0.01):
            score += 3
            kinds.append(f"cap:{qcap:g}")
    return score, kinds


def passes_discriminators(tokens: QueryTokens, row_blob: str) -> bool:
    """判别轴过滤：同轴查询值与料值不相交 → False。料未声明该轴 → True（不臆造）。"""
    q = tokens["num_tokens"] | tokens["mixed_tokens"] | tokens["alpha_tokens"] | tokens["alias_tokens"]
    for fam in DISCRIMINATOR_FAMILIES:
        qf = {v for v in fam if v in q}
        if not qf:
            continue
        rf = {v for v in fam if v in row_blob}
        if rf and not (qf & rf):
            return False
    return True
