# -*- coding: utf-8 -*-
"""_duplicate_groups（疑似重复检测信号层）单测：纯函数直测，不碰 DB。
验证战役实证信号的分层与证据输出：SKU 精确 / 结构化键 / 语义 token 相等·子集+价格簇 /
名称相似兜底（封顶 0.69）；brand 不参与分桶；真不同件对照组降级+价差警示。

跑法（backend 目录）：python -X utf8 -m pytest tests/test_kp_duplicates.py -q
"""
from app.repository.kp_repo import _duplicate_groups


def R(id, name, category_id=1, category_name="NIC Card", brand=None,
      oem_sku=None, alt_sku=None, specs=None, latest_price=None):
    return {"id": id, "name": name, "brand": brand, "oem_sku": oem_sku,
            "alt_sku": alt_sku, "category_id": category_id,
            "category_name": category_name, "specs": specs or {},
            "latest_price": latest_price, "latest_currency": None}


def run(records, threshold=0.6):
    return _duplicate_groups(records, threshold)


class TestSKU精确:
    def test_oem与alt交叉跨分类(self):
        out = run([
            R(1, "A 卡", category_id=1, category_name="NIC Card", oem_sku="SKU-X"),
            R(2, "B 卡", category_id=2, category_name="GPU card", alt_sku="SKU-X"),
        ])
        assert out["total_groups"] == 1
        g = out["groups"][0]
        assert g["similarity"] == 1.0
        assert any("SKU 相同" in r for r in g["reasons"])

    def test_oem同值(self):
        out = run([R(1, "X", oem_sku="S1"), R(2, "Y", oem_sku="S1")])
        assert out["total_groups"] == 1 and out["groups"][0]["similarity"] == 1.0


class Test结构化键:
    def test_U2冗余标注同键(self):
        out = run([
            R(1, "1.92T NVMe SSD", category_id=3, category_name="HDD/SSD"),
            R(2, "1.92T NVMe U.2 SSD", category_id=3, category_name="HDD/SSD"),
        ])
        g = out["groups"][0]
        assert "结构化键一致" in g["reasons"]
        assert g["similarity"] == 0.95

    def test_specs参与键(self):
        out = run([
            R(1, "960G NVMe U.2", category_id=3, category_name="HDD/SSD",
              specs={"Capacity": "960 GB", "Type": "NVMe", "Media": "SSD", "Form Factor": "U.2"}),
            R(2, "960G NVMe U.2", category_id=3, category_name="HDD/SSD"),
        ])
        assert "结构化键一致" in out["groups"][0]["reasons"]


class Test语义token:
    def test_相等_品牌标注不一致也命中(self):
        # 旧机制 brand 分桶盲区回归例：brand 一填一空必须仍能比到
        out = run([
            R(1, "NVIDIA RTX 5090 32G", category_id=2, category_name="GPU card", brand="NVIDIA"),
            R(2, "RTX 5090 32G 涡轮卡", category_id=2, category_name="GPU card"),
        ])
        g = out["groups"][0]
        assert "语义 token 相等" in g["reasons"]
        assert g["similarity"] == 0.9

    def test_子集_价格簇升档(self):
        out = run([
            R(1, "25G 2port+光模块", latest_price=1200),
            R(2, "25G CX6 2port+光模块", latest_price=1250),
        ])
        g = out["groups"][0]
        assert g["similarity"] == 0.8
        assert any("最新价比 1.04" in r for r in g["reasons"])

    def test_子集_价差大降档并警示(self):
        out = run([
            R(1, "25G 2port+光模块", latest_price=1200),
            R(2, "25G CX6 2port+光模块", latest_price=2400),
        ])
        g = out["groups"][0]
        assert g["similarity"] == 0.7
        assert g["price_warning"] is True and g["price_ratio"] == 2.0
        assert any("可能真不同件" in r for r in g["reasons"])

    def test_子集_无价不升档(self):
        out = run([R(1, "25G 2port+光模块"), R(2, "25G CX6 2port+光模块")])
        assert "语义 token 子集" in out["groups"][0]["reasons"]


class Test名称相似兜底:
    def test_数字相同字母差异兜底(self):
        # 数字 token 双侧一致（6/2port），仅 Dx/Lx 字母位不同 → 兜底出对供人工复核
        out = run([
            R(1, "Mellanox CX6 Dx 2port"),
            R(2, "Mellanox CX6 Lx 2port"),
        ])
        g = out["groups"][0]
        assert any("名称相似" in r for r in g["reasons"])
        assert g["similarity"] == 0.69  # 兜底封顶，不与语义分层抢排序

    def test_数字token差异否决(self):
        # EPYC 家族同前缀刷屏教训：9334 vs 9554 的 difflib 比值 0.7+，但型号数字不同 = 不同件
        out = run([
            R(1, "AMD EPYC 9334", category_id=5, category_name="CPU"),
            R(2, "AMD EPYC 9554 64C", category_id=5, category_name="CPU"),
        ])
        assert out["total_groups"] == 0

    def test_PN码尾字母差异否决(self):
        out = run([
            R(1, "PWR-CFG-1234A", category_id=4, category_name="PSU"),
            R(2, "PWR-CFG-1234B", category_id=4, category_name="PSU"),
        ])
        assert out["total_groups"] == 0

    def test_单token信息不足不出子集对(self):
        # "400G多模模块"→{400g} 单 token 名会匹配一切 400G 件 → 不比
        out = run([R(1, "400G多模模块"), R(2, "400G CX7 1port")])
        assert out["total_groups"] == 0


class Test真不同件对照组:
    """战役已裁决保留的对照组：不得命中强信号；价差大且 token 真差异的完全不出对。"""

    def test_gen3与gen4_完全不报(self):
        # gen3/gen4 = 不同件（价差 1.79 战役裁决保留）；数字 token 3≠4 直接否决
        out = run([
            R(1, "1.92T NVMe SSD gen3", category_id=3, category_name="HDD/SSD", latest_price=9500),
            R(2, "1.92T NVMe SSD gen4", category_id=3, category_name="HDD/SSD", latest_price=17000),
        ])
        assert out["total_groups"] == 0

    def test_480G企业级与读密集_强信号加价差警示(self):
        # 名称去掉噪声词后 token 相等（真最强重复信号），但价差 1.45 → 警示行交给人工裁决
        out = run([
            R(1, "480G SATA SSD 企业级", category_id=3, category_name="HDD/SSD", latest_price=1200),
            R(2, "480G SATA SSD 读密集型", category_id=3, category_name="HDD/SSD", latest_price=1740),
        ])
        g = out["groups"][0]
        assert "语义 token 相等" in g["reasons"]
        assert g["price_warning"] is True and g["price_ratio"] == 1.45


class Test聚组与边界:
    def test_信号链传递聚成一组(self):
        out = run([
            R(1, "X", oem_sku="S1"),
            R(2, "Y", oem_sku="S1"),
            R(3, "RTX 5090 32G", category_id=2, category_name="GPU card"),
            R(4, "NVIDIA RTX 5090 32G", category_id=2, category_name="GPU card"),
        ])
        assert out["total_groups"] == 2

    def test_弱信号不级联巨组(self):
        # 真库教训：同类名经两两命中链式传递，弱信号若参与聚组会把整个分类并成巨组。
        # R1 与 R2、R3 各成弱对（CX6/CX7 数字 token 互异连兜底都否决）：
        # R1 分属两个独立 2 件组而非并成一组，即弱信号不级联
        out = run([
            R(1, "25G 2port+光模块"),
            R(2, "25G CX6 2port+光模块"),
            R(3, "25G CX7 2port+光模块"),
        ])
        assert out["total_groups"] == 2
        assert all(len(g["parts"]) == 2 for g in out["groups"])
        ids = [frozenset(p["id"] for p in g["parts"]) for g in out["groups"]]
        assert frozenset({1, 2}) in ids and frozenset({1, 3}) in ids

    def test_单件无组(self):
        out = run([R(1, "孤件")])
        assert out == {"total_groups": 0, "total_duplicate_parts": 0, "groups": []}

    def test_摘要带分类与规格(self):
        out = run([
            R(1, "960G NVMe U.2", category_id=3, category_name="HDD/SSD",
              specs={"Capacity": "960 GB", "Type": "NVMe"}),
            R(2, "960G NVMe U.2", category_id=3, category_name="HDD/SSD"),
        ])
        p = out["groups"][0]["parts"][0]
        assert p["category_name"] == "HDD/SSD"
        assert p["specs_brief"] == "Capacity: 960 GB · Type: NVMe"
