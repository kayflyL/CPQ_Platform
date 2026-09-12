# -*- coding: utf-8 -*-
"""part_lexicon 词法引擎 + data_tools 接线回归（2026-09-12 P0）。

锁住的病灶（改前实测）：万兆/千兆/智铠/核显等中文口语词零召回、智铠100→H100 数字串
误报、SATA 意图召回 NVMe（media 维度丢失）、纯字母词（i350/mellanox）与 brand 不参与检索。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.part_lexicon import (
    normalize_text, extract_query_tokens, build_row_blob, score_row,
    passes_discriminators, _gb_of,
)
from app.services.data_tools import part_query, part_recall

ALIASES = [{"alias": "万兆", "expansion": "10G"},
           {"alias": "千兆", "expansion": "1G"},
           {"alias": "智凯", "expansion": "智铠"},
           {"alias": "固态硬盘", "expansion": "SSD"},
           {"alias": "机械硬盘", "expansion": "HDD"}]


def _row(name, specs=None, brand="", cat="NIC"):
    return {"id": 1, "category": cat, "model": name, "brand": brand,
            "specs": specs or {}, "applicable": {"series": []}}


class _StubRepo:
    def __init__(self, rows, aliases=None):
        self._rows = list(rows)
        self._aliases = list(aliases or [])

    def get_categories(self):
        return [{"category": self._rows[0]["category"], "count": len(self._rows)}]

    def get_by_category_with_specs(self, category):
        return list(self._rows)

    def list_search_aliases(self):
        return self._aliases

    def close(self):
        pass


# ── 归一 ──────────────────────────────────────────────────────────────

def test_normalize_port_notation():
    assert "4port" in normalize_text("千兆 4口")
    assert "4port" in normalize_text("10G 四口，不含光模块")
    assert normalize_text("Intel Xeon 6530").startswith("intel xeon")


def test_gb_of_picks_largest_capacity():
    assert _gb_of("480G") == 480.0
    assert abs(_gb_of("1.92T") - 1.92 * 1024) < 0.01
    assert _gb_of("4个") is None  # 裸数量不是容量


# ── token 提取 ────────────────────────────────────────────────────────

def test_extract_tokens_covers_latin_alpha_cjk_and_alias():
    t = extract_query_tokens("2个万兆光口网卡 i350", ALIASES)
    assert "i350" in t["mixed_tokens"]
    assert {"光口", "网卡"} <= t["cjk_runs"]
    assert "10g" in t["alias_tokens"]  # 万兆→10G 别名扩展


def test_extract_tokens_ignores_single_cjk_chars():
    t = extract_query_tokens("4 块 千 兆")
    assert t["cjk_runs"] == set() or all(len(r) >= 2 for r in t["cjk_runs"])


# ── 打分与误报治理 ────────────────────────────────────────────────────

def test_zhikai_outranks_h100_on_zhikai_query():
    """「智铠100」必须把 智铠 行排到 H100 之上（中文段命中 > 裸数字串）。"""
    zhikai = _row("天数智芯 智铠100", cat="GPU")
    h100 = _row("NVIDIA H100 80G", cat="GPU")
    t = extract_query_tokens("智铠100", ALIASES)
    sz, _ = score_row(t, zhikai)
    sh, _ = score_row(t, h100)
    assert sz > sh


def test_brand_participates_in_blob():
    t = extract_query_tokens("兆芯", [{"alias": "兆芯", "expansion": "KH"}])
    name, blob = build_row_blob({"model": "KH50000 96C", "brand": "兆芯", "specs": {}})
    assert "兆芯" in blob and "兆芯" not in name
    sc, kinds = score_row(t, {"model": "KH50000 96C", "brand": "兆芯", "specs": {}},
                          row_name=name, row_blob=blob)
    assert sc > 0


def test_spec_values_participate_in_blob():
    row = _row("10G 2port", specs={"Link Speed": "10G", "接口": "光口"})
    t = extract_query_tokens("万兆 光口", ALIASES)  # 10G 来自别名、光口来自 spec 值
    name, blob = build_row_blob(row)
    sc, _ = score_row(t, row, row_name=name, row_blob=blob)
    assert sc > 0


# ── 判别轴 ────────────────────────────────────────────────────────────

def test_sata_intent_filters_out_nvme():
    sata = _row("1.92T SATA SSD", specs={"Type": "SATA"}, cat="HDD/SSD")
    nvme = _row("1.92T NVMe SSD", specs={"Type": "NVMe"}, cat="HDD/SSD")
    t = extract_query_tokens("1.92T SATA", ALIASES)
    _, sata_blob = build_row_blob(sata)
    _, nvme_blob = build_row_blob(nvme)
    assert passes_discriminators(t, sata_blob) is True
    assert passes_discriminators(t, nvme_blob) is False


def test_no_media_word_means_no_filter():
    """查询没点名介质轴 → 不过滤（NVMe/SATA 都可召回，交给容量/词法排序）。"""
    nvme = _row("1.92T NVMe SSD", specs={"Type": "NVMe"}, cat="HDD/SSD")
    t = extract_query_tokens("1.92T", ALIASES)
    _, blob = build_row_blob(nvme)
    assert passes_discriminators(t, blob) is True


def test_ddr_generation_is_discriminator():
    ddr5 = _row("64G 4800 DDR5 RDIMM", specs={"Type": "DDR5"}, cat="Memory")
    t = extract_query_tokens("64G DDR4", ALIASES)
    _, blob = build_row_blob(ddr5)
    assert passes_discriminators(t, blob) is False


def test_row_silent_on_axis_is_not_filtered():
    """料未声明接口轴（无 SATA/NVMe/SAS 字样）→ 不臆造过滤。
    （声明了 SAS 的料被 SATA 查询排除是正确行为——同轴互斥。）"""
    row = _row("12T HDD", specs={}, cat="HDD/SSD")
    t = extract_query_tokens("SATA 12T", ALIASES)
    _, blob = build_row_blob(row)
    assert passes_discriminators(t, blob) is True


# ── data_tools 接线（stub 库 + 别名注入） ─────────────────────────────

_NIC_ROWS = [
    _row("1G Intel I350 4port OCP3.0", specs={"Link Speed": "1G"}, brand="Intel"),
    _row("10G 2port OCP3.0光口网卡", specs={"Link Speed": "10G", "接口": "光口"}),
    _row("25G 2port+光模块", specs={"Link Speed": "25G"}),
]


def test_part_query_recalls_colloquial_wanshao():
    res = part_query("NIC", keywords="万兆", limit=5, _repo=_StubRepo(_NIC_ROWS, ALIASES))
    names = [r["name"] for r in res["rows"]]
    assert any("10G" in n for n in names)
    assert not any("I350" in n for n in names)  # 千兆卡不该被「万兆」召回


def test_part_recall_uses_alias_expansion():
    res = part_recall("NIC", desc="2个万兆光口网卡", limit=5,
                      _repo=_StubRepo(_NIC_ROWS, ALIASES))
    names = [r["name"] for r in res["rows"]]
    assert names and "10G" in names[0]


def test_part_query_ranks_by_relevance():
    res = part_query("NIC", keywords="千兆 4口", limit=5, _repo=_StubRepo(_NIC_ROWS, ALIASES))
    names = [r["name"] for r in res["rows"]]
    assert names and ("I350" in names[0] or "4port" in names[0])


def test_stub_repo_without_alias_method_degrades():
    repo = _StubRepo(_NIC_ROWS)  # 不带别名
    repo.list_search_aliases = None  # 模拟旧 stub：方法不存在
    res = part_query("NIC", keywords="10G 光口", limit=5, _repo=repo)
    assert res["ok"] is True and res["rows"]
