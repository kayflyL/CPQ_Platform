# -*- coding: utf-8 -*-
"""配件规格事实层（part_selector 拆分，2026-09-11）：单位换算 / 规格比对 / 系列适用性。

只认库返回的规格字符串，不做业务决策；谁用谁 import，不反向依赖上层。
"""
from __future__ import annotations

from typing import Optional
import re


def _capacity_mismatch(grounded_cap: Optional[float], need_cap: Optional[float],
                       cmp: str, tolerance_ratio: float) -> bool:
    """容量是否符合请求；None 表示不校验。"""
    if grounded_cap is None or need_cap is None:
        return False
    if cmp == "gte":
        return grounded_cap < need_cap
    if cmp == "lte":
        return grounded_cap > need_cap
    return abs(grounded_cap - need_cap) > max(1.0, need_cap * tolerance_ratio)

def _norm_model(value) -> str:
    """料号/型号文本归一：忽略大小写、空格、连字符，便于 LLM 输出与库内料号对齐。"""
    return re.sub(r"[\s\-_]+", "", str(value or "")).lower()

def _num_of(value) -> Optional[float]:

    if value is None:
        return None
    m = re.search(r"[\d.]+", str(value))
    return float(m.group()) if m else None

def _gb_of(value) -> Optional[float]:
    """容量词 → GB：'960G'/'32 GB'→960/32；'1.92T'/'1.92 TB'→1966.08。"""
    s = str(value or "").strip().upper()
    m = re.search(r"([\d.]+)\s*(T|G)\s*B?", s)
    if not m:
        return None
    n = float(m.group(1))
    unit = (m.group(2) or "")
    if unit == "T":
        n *= 1024
    elif unit == "M":
        n /= 1024
    return n


def _series_ok(applicable, series: str) -> bool:
    """机型适配判定（与 kp_config API 同一语义）：applicable 缺省/无 series 键=通用件；
    series 列表含目标系列=适配；空列表=对全部系列隐藏。"""
    if not series or not isinstance(applicable, dict):
        return True
    lst = applicable.get("series")
    if lst is None:
        return True
    if isinstance(lst, list):
        return any(str(x).strip() == series for x in lst)
    return True

class _SeriesScopedRepo:
    """系列作用域包装：机型锁定后，配件候选池只剩适配件（含通用件）。
    过滤发生在取数边界，_ground_* 各 grounding 无需各自感知兼容性。"""

    def __init__(self, repo, series: str):
        self._repo = repo
        self._series = (series or "").strip()

    def __getattr__(self, name):
        return getattr(self._repo, name)

    def _f(self, rows):
        if not self._series:
            return rows
        return [r for r in rows if _series_ok(r.get("applicable"), self._series)]

    def get_by_category(self, category, search=""):
        return self._f(self._repo.get_by_category(category, search))

    def get_by_category_with_specs(self, category):
        return self._f(self._repo.get_by_category_with_specs(category))

    def get_by_category_with_spec_filter(self, category, spec_filters):
        return self._f(self._repo.get_by_category_with_spec_filter(category, spec_filters))

    def get_latest_prices(self, **kw):
        return self._f(self._repo.get_latest_prices(**kw))

def _cap_disp(gb: float) -> str:
    g = int(round(gb))
    if g % 1024 == 0:
        return f"{g // 1024}T"
    if g >= 1024:
        t = g / 1024
        s = f"{t:.2f}".rstrip("0").rstrip(".")
        return f"{s}T"
    return f"{g}G"

def _drive_media_label(row: dict) -> str:
    """盘介质标签：优先取目录规格 Type+Media（如 'SATA SSD'/'NVMe HDD'），
    无规格时按型号关键词兜底 SSD/HDD，保证展示与目录事实一致、不丢子类型。"""
    specs = row.get("specs") or {}
    bits = [str(specs.get("Type") or "").strip(), str(specs.get("Media") or "").strip()]
    label = " ".join(b for b in bits if b).upper()
    if label:
        return label
    hay = str(row.get("model") or "").upper()
    if "SSD" in hay:
        return "SSD"
    return "HDD"

def _drive_display(row: dict) -> str:
    """硬盘展示名：目录真实型号 + 介质子类型（如 '8T SATA SSD'），绝不改成 '2x 8T SSD'。"""
    model = str(row.get("model") or "").strip()
    media = _drive_media_label(row)
    if model and media.lower() not in model.lower():
        return f"{model} {media}"
    return model or media

def _spec_hit(specs: dict, filters: list) -> str:
    """规格 AND 过滤；全中返回标签串，否则 ''。"""
    hits = []
    for f in filters or []:
        sk = (f.get("spec_key") or "").strip()
        op = (f.get("op") or "=").strip()
        val = f.get("value")
        if not sk:
            continue
        sv = specs.get(sk)
        if sv is None:
            return ""
        svn = _num_of(sv)
        vn = _num_of(val) if not isinstance(val, list) else None
        if op in (">=", "<=", ">", "<") and svn is not None and vn is not None:
            ok = (svn >= vn if op == ">=" else svn <= vn if op == "<="
                  else svn > vn if op == ">" else svn < vn)
            if not ok:
                return ""
            hits.append(f"{sk}{op}{vn:g}")
        elif isinstance(val, list) or op == "in":
            vals = val if isinstance(val, list) else [val]
            if not any(str(sv).strip() == str(v).strip() for v in vals):
                return ""
            hits.append(f"{sk}∈{{{','.join(str(v) for v in vals)}}}")
        else:
            if str(sv).strip() != str(val).strip() and (svn is None or vn is None or abs(svn - vn) > 1e-9):
                return ""
            hits.append(f"{sk}={sv}")
    return " · ".join(hits)

def kp_repository():
    """KP 库句柄的唯一解析口：仍取总出口 part_selector.KPRepository。

    拆分子模块后，这条「替换 part_selector.KPRepository 即换库」的缝隙必须保持可用
    （现存桩测试与调用方都从总出口替换句柄），所以句柄一律在这里按运行期解析。
    """
    from app.services import part_selector as _ps
    return _ps.KPRepository()
