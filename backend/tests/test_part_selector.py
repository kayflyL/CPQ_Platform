# -*- coding: utf-8 -*-
"""part_selector 新契约：引擎只检索候选 + 落地占位缺口，语义选型交还 AI 角色。

不再做型号/别名/规格 token 匹配（旧解析器已删除）。select_parts 只把结构化
信号转成「交由 AI 选型」的缺口行；retrieve_part_candidates 返回库内真实候选池。
"""
from app.services import part_selector as ps


class _FakeRepo:
    _mu = {
        "CPU": [
            {"model": "AMD EPYC 9124", "price": 800.0, "currency": "RMB", "specs": {}},
            {"model": "Intel Xeon 8380", "price": 1200.0, "currency": "RMB", "specs": {}},
            {"model": "KH50000 96C", "price": 9000.0, "currency": "RMB", "specs": {}},
        ],
        "Memory": [
            {"model": "16G DDR4 3200", "price": 1200.0, "currency": "RMB",
             "specs": {"Type": "DDR4", "Speed": "3200", "Capacity": "16G"}},
            {"model": "32G DDR5", "price": 2600.0, "currency": "RMB",
             "specs": {"Type": "DDR5", "Speed": "4800", "Capacity": "32G"}},
        ],
        "HDD/SSD": [
            {"model": "480G SATA SSD", "price": 400.0, "currency": "RMB",
             "specs": {"Capacity": "480 GB", "Type": "SATA", "Media": "SSD"}},
            {"model": "6T SATA HDD", "price": 1000.0, "currency": "RMB",
             "specs": {"Capacity": "6 TB", "Type": "SATA", "Media": "HDD"}},
        ],
        "Raid card": [
            {"model": "LSI 9361-8i", "price": 2200.0, "currency": "RMB",
             "specs": {"Cache": "1 GB", "Ports": "8"}},
        ],
    }

    def __init__(self):
        self.closed = False

    def get_categories(self):
        return [{"category": k, "count": len(v)} for k, v in self._mu.items()]

    def get_by_category(self, category, search=""):
        rows = self._mu.get(category, [])
        if search:
            rows = [r for r in rows if search.lower() in r["model"].lower()]
        return rows

    def get_by_category_with_specs(self, category):
        return self._mu.get(category, [])

    def close(self):
        self.closed = True


def _stub(monkeypatch):
    monkeypatch.setattr(ps, "KPRepository", _FakeRepo)


def test_select_parts_emits_ai_ground_placeholder_for_cpu(monkeypatch):
    """CPU 不再静态匹配：引擎只产缺口行（含 cores/型号），选中交 AI。"""
    _stub(monkeypatch)
    parts = ps.select_parts(categories=["CPU"], cpu={"model": "兆芯50000", "cores": 96, "qty": 2})
    assert len(parts) == 1
    assert parts[0]["unmatched"] is True
    assert parts[0]["request_spec"] == "兆芯50000 96C"
    assert parts[0]["qty"] == 2
    assert parts[0]["pn"] == ""


def test_select_parts_emits_ai_ground_placeholder_for_raid_no_fake_fail(monkeypatch):
    """RAID 不再做 RAID Level 词表匹配，也不再输出「库内未登记 RAID 级别」误导。"""
    _stub(monkeypatch)
    parts = ps.select_parts(categories=["Raid card"],
                            raid=[{"raid_levels": ["0", "1", "5", "6", "JBOD"], "qty": 1}])
    assert len(parts) == 1
    assert parts[0]["unmatched"] is True
    assert "无法自动选卡" not in (parts[0].get("unmatched_reason") or "")
    assert "RAID 阵列卡" in parts[0]["request_spec"]


def test_select_parts_emits_placeholder_per_drive_group(monkeypatch):
    """多个盘组各产一行缺口（容量×介质），交 AI 从候选选型。"""
    _stub(monkeypatch)
    parts = ps.select_parts(categories=["HDD/SSD"], storage=[
        {"term": "480G", "qty": 2, "kind": "SSD"},
        {"term": "6T", "qty": 4, "kind": "HDD"},
    ])
    assert len(parts) == 2
    assert all(p["unmatched"] for p in parts)
    assert parts[0]["request_spec"] == "480G SSD"
    assert parts[1]["request_spec"] == "6T HDD"


def test_retrieve_part_candidates_returns_real_pool_with_desc(monkeypatch):
    """候选检索器：只检索库内真实件，带可读 desc，不做语义匹配。"""
    _stub(monkeypatch)
    pools = ps.retrieve_part_candidates(categories=["Raid card"])
    rd = pools["Raid card"]
    assert any("LSI 9361-8i" in c["model"] for c in rd)
    for c in rd:
        assert "desc" in c and "Cache" in c["desc"]


def test_resolve_part_alias_is_pure_name_search(monkeypatch):
    """别名解析退化为纯名称检索：不读字典词表、不做 token 归一。"""
    _stub(monkeypatch)
    res = ps.resolve_part_alias("9361-8i", "Raid card")
    assert res["count"] >= 1
    assert any("LSI 9361-8i" in c["pn"] for c in res["candidates"])
    assert res["reason"] == "名称检索"


def test_list_kp_categories_returns_db_mapping(monkeypatch):
    monkeypatch.setattr(ps, "KPRepository", _FakeRepo)
    cats = ps.list_kp_categories()
    memory = next(c for c in cats if c["key"] == "Memory")
    assert memory["db_category"] == "Memory"


def test_norm_search_matches_manual_model_input():
    # 手动输入型号入口用归一化包含检索（非 token 拆分）
    assert ps._norm_model("LSI 9560 16i") in ps._norm_model("LSI 9560-16i")
    assert ps._norm_model("9364 8i") in ps._norm_model("LSI 9364-8i")
