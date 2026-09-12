# -*- coding: utf-8 -*-
"""part_search 混合检索回归（2026-09-12 P1）：词法/语义双通道 → RRF 融合 + match 溯源。

语义通道全部 monkeypatch（不依赖 fastembed/模型下载）；fastembed 缺席时整体降级
纯词法（行为=P0）也在测试里锁死。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import part_search_index as psi
from app.services.part_search import hybrid_search

ALIASES = [{"alias": "万兆", "expansion": "10G"},
           {"alias": "千兆", "expansion": "1G"},
           {"alias": "固态硬盘", "expansion": "SSD"}]


def _row(pid, name, specs=None, brand="", cat="NIC", series=None):
    return {"id": pid, "category": cat, "model": name, "brand": brand,
            "specs": specs or {},
            "applicable": {"series": series or []}}


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


_ROWS = [
    _row(1, "1G Intel I350 4port", specs={"Link Speed": "1G"}, brand="Intel"),
    _row(2, "10G 2port 光口网卡", specs={"Link Speed": "10G"}, brand="Mellanox"),
    _row(3, "25G 2port 网卡", specs={"Link Speed": "25G"}),
]

_VEC = {1: [1.0, 0.0], 2: [0.95, 0.31], 3: [0.0, 1.0]}  # 3 与查询正交=无关


def _mock_sem(monkeypatch, part_vecs=None, qvec=None, available=True, cat="NIC"):
    pool = [{"part_id": pid, "category": cat, "embedding": v,
             "applicable": {"series": []}}
            for pid, v in (part_vecs or _VEC).items()]
    monkeypatch.setattr(psi, "semantic_available", lambda: available)
    monkeypatch.setattr(psi, "ensure_index", lambda repo=None: {"ok": True})
    monkeypatch.setattr(psi, "load_vectors", lambda *a, **k: pool)
    monkeypatch.setattr(psi, "embed_query",
                        lambda t: qvec if qvec is not None else [1.0, 0.0])


def test_degrades_to_pure_lexical_when_semantic_off(monkeypatch):
    monkeypatch.setattr(psi, "semantic_available", lambda: False)
    res = hybrid_search("NIC", text="万兆", limit=5, _repo=_StubRepo(_ROWS, ALIASES))
    assert res["ok"] and res["rows"]
    names = [r["name"] for r in res["rows"]]
    assert any("10G" in n for n in names)
    assert not any("I350" in n for n in names)
    assert all(r["match"] == ["lexical"] for r in res["rows"])
    assert res["channels"]["semantic"] == 0


def test_semantic_only_hit_surfaced_with_provenance(monkeypatch):
    """词形全对不上（查询口语、行名纯拉丁），语义通道把料捞回来并带 semantic 溯源。"""
    _mock_sem(monkeypatch)
    res = hybrid_search("NIC", text="多口网络接口卡", limit=5, _repo=_StubRepo(_ROWS, ALIASES))
    ids = {r["part_id"] for r in res["rows"]}
    assert "1" in ids  # 行 1 名字纯拉丁，词法零交集，只能来自语义通道
    assert "3" not in ids  # 正交向量低于阈值被拒
    hit = next(r for r in res["rows"] if r["part_id"] == "1")
    assert hit["match"] and all(m.startswith("semantic:") for m in hit["match"])


def test_rrf_both_channels_outrank_single(monkeypatch):
    """双通道命中的行 RRF 分 = 两项之和，应排在任何单通道行之前。"""
    _mock_sem(monkeypatch)  # 查询向量 [1,0]：与 1、2 同向 → 语义也命中
    res = hybrid_search("NIC", text="万兆", limit=5, _repo=_StubRepo(_ROWS, ALIASES))
    assert res["rows"], "万兆应至少词法命中 10G 行"
    dual = [r for r in res["rows"] if len(r["match"]) == 2]
    single = [r for r in res["rows"] if len(r["match"]) == 1]
    if dual and single:  # 双通道行存在时必居首
        assert res["rows"][0]["part_id"] == dual[0]["part_id"]


def test_spec_filter_blocks_semantic_candidates(monkeypatch):
    """语义命中的行也必须过确定性规格过滤（AND 不因语义通道放宽）。"""
    _mock_sem(monkeypatch, part_vecs={1: [1.0, 0.0], 2: [0.0, 1.0]})
    repo = _StubRepo(_ROWS, ALIASES)
    # 正控：filter=1G，语义命中行 1（与查询同向）且过过滤 → 唯一结果
    res = hybrid_search("NIC", text="多口网络接口卡",
                        spec_filters=[{"spec_key": "Link Speed", "op": "=", "value": "1G"}],
                        limit=5, _repo=repo)
    assert {r["part_id"] for r in res["rows"]} == {"1"}
    # 反控：filter=10G，语义命中的行 1（1G）被确定性过滤 → 不出结果
    res2 = hybrid_search("NIC", text="多口网络接口卡",
                         spec_filters=[{"spec_key": "Link Speed", "op": "=", "value": "10G"}],
                         limit=5, _repo=repo)
    assert "1" not in {r["part_id"] for r in res2["rows"]}


def test_no_keywords_browse_mode_returns_all(monkeypatch):
    """空关键词 = 浏览模式（part_query 同语义）：规格过滤后的全量行。"""
    monkeypatch.setattr(psi, "semantic_available", lambda: False)
    res = hybrid_search("NIC", text="", spec_filters=[{"spec_key": "Link Speed", "op": "=", "value": "1G"}],
                        limit=5, _repo=_StubRepo(_ROWS, ALIASES))
    names = [r["name"] for r in res["rows"]]
    assert names == ["1G Intel I350 4port"]


def test_semantic_index_failure_degrades_gracefully(monkeypatch):
    """ensure_index 抛异常 → 语义通道静默跳过，词法结果照常返回。"""
    def _boom(repo=None):
        raise RuntimeError("db down")
    monkeypatch.setattr(psi, "semantic_available", lambda: True)
    monkeypatch.setattr(psi, "ensure_index", _boom)
    res = hybrid_search("NIC", text="万兆", limit=5, _repo=_StubRepo(_ROWS, ALIASES))
    assert res["ok"] and any("10G" in r["name"] for r in res["rows"])
    assert res["channels"]["semantic"] == 0


def test_series_scope_excludes_semantic_hit(monkeypatch):
    """语义命中但行不适配当前系列 → 不出结果（_series_ok 在池侧过滤 + 行侧兜底）。"""
    _mock_sem(monkeypatch, part_vecs={1: [1.0, 0.0]})
    rows = [_row(1, "1G Intel I350 4port", specs={"Link Speed": "1G"}, series=["Orion"])]
    res = hybrid_search("NIC", text="多口网络接口卡", series="Polaris",
                        limit=5, _repo=_StubRepo(rows, ALIASES))
    # 池里 applicable.series=[Orion] ≠ Polaris → 语义不给；词法也无命中 → 零结果+真话note
    assert res["rows"] == []
    assert res.get("out_of_scope") or res.get("scope_note") or res.get("note")


def test_semantic_capacity_guard(monkeypatch):
    """查询点名容量（2T）时，语义候选必须过 ±1% 容量等值守卫——
    语义分不清 480G/2T，但容量是硬信号，不许把 480G 抬到 2T 之上。"""
    rows = [_row(1, "SSD A 480G", cat="HDD/SSD"), _row(2, "SSD B 2T", cat="HDD/SSD")]
    _mock_sem(monkeypatch, part_vecs={1: [1.0, 0.0], 2: [1.0, 0.0]}, cat="HDD/SSD")  # 语义「无差别」同分
    res = hybrid_search("HDD/SSD", text="2T 固态硬盘", limit=5,
                        _repo=_StubRepo(rows, ALIASES))
    assert res["rows"], "应至少召回 2T 行"
    assert res["rows"][0]["part_id"] == "2", "2T 行必须居首"
    assert res["channels"]["semantic"] == 1, "480G 行应被容量守卫挡在语义通道外"


def test_match_provenance_in_skill_tool_shape(monkeypatch):
    """返回行形状兼容工具消费（part_id/name/price/currency/specs/match）。"""
    _mock_sem(monkeypatch)
    res = hybrid_search("NIC", text="万兆", limit=5, _repo=_StubRepo(_ROWS, ALIASES))
    r = res["rows"][0]
    for k in ("part_id", "name", "price", "currency", "match"):
        assert k in r
