# -*- coding: utf-8 -*-
"""part_identity_key 同一性判据单测：导入去重 / 疑似重复检测的核心。
验证：冗余词→同件(合)、真差异→不同件(不合)、specs 优先、非硬盘品类归一。

跑法（backend 目录）：python -X utf8 -m pytest tests/test_kp_identity.py -q
"""
from app.repository.kp_repo import part_identity_key

K = lambda name, category="HDD/SSD", specs=None: part_identity_key(name, category, specs)
SPECS = lambda ff: {"Capacity": "960 GB", "Type": "NVMe", "Media": "SSD", "Form Factor": ff}


class Test冗余词归一为同件:
    """已结构化维度的冗余标注(SSD/U.2/形态)→ 同一 identity，导入时判为 update。"""
    def test_SSD冗余(self):
        assert K("1.92T NVMe") == K("1.92T NVMe SSD")
    def test_U2冗余(self):
        assert K("1.92T NVMe SSD") == K("1.92T NVMe U.2 SSD")
    def test_形态冗余(self):
        assert K("480G SATA SSD") == K("480G SATA SSD 2.5inch")
    def test_容量单位(self):
        assert K("480G SATA SSD") == K("480GB SATA SSD")
    def test_长链(self):
        assert K("7.68T NVMe") == K("7.68 TB NVMe Enterprise-class SSD")
    def test_大小写空格(self):
        assert K("3.84T NVMe SSD") == K("3.84T NVMe SSD")


class Test真差异保留为不同件:
    """M.2/U.2、HDD/SSD、gen3/gen4、工作负载、接口 → 不同 identity，不误合。"""
    def test_M2_vs_U2(self):
        assert K("960G NVMe M.2") != K("960G NVMe U.2")
    def test_HDD_vs_SSD(self):
        assert K("8T SATA HDD") != K("8T SATA SSD")
    def test_gen4保留(self):
        assert K("1.92T NVMe SSD") != K("1.92T NVMe SSD gen4")
    def test_gen3_vs_gen4(self):
        assert K("3.84T NVMe SSD gen3") != K("3.84T NVMe SSD gen4")
    def test_工作负载保留(self):
        assert K("480G SATA SSD") != K("480G SATA SSD 读密集型")
    def test_接口不同(self):
        assert K("1.92T SATA SSD") != K("1.92T NVMe SSD")
    def test_转速保留(self):
        assert K("2.4T SAS HDD 10K") != K("2.4T SAS HDD 15K")


class Test库内件specs优先:
    """库内件传 specs → 用 spec，不被 name 里的冗余标注干扰。"""
    def test_specs定形态(self):
        # name 都写 U.2，但 specs 一 M.2 一 U.2 → 不同件(specs 主导)
        assert K("960G NVMe U.2", specs=SPECS("M.2")) != K("960G NVMe U.2", specs=SPECS("U.2"))
    def test_specs填齐与name解析对齐(self):
        # specs 完整(U.2) vs 纯 name 解析(U.2) → 同
        assert K("960G NVMe U.2", specs=SPECS("U.2")) == K("960G NVMe U.2")


class Test非硬盘品类用归一名:
    CAT = "Network(NIC) requirement"
    def test_大小写(self):
        assert K("1G I350 2Port", self.CAT) == K("1G I350 2port", self.CAT)
    def test_空格(self):
        assert K("25G CX4 2port+光模块", self.CAT) == K("25G CX4 2Port +光模块", self.CAT)
    def test_容量单位归一(self):
        assert K("25G 网卡", self.CAT) == K("25G 网卡", self.CAT)


class TestMemory属性参与同一性:
    """Memory 用容量/代数/速率/DIMM 形态/rank/ECC 做 key，避免同容量同速不同形态误合。"""
    def test_容量代数速率归一(self):
        assert K("32G 4800 DDR5 RDIMM", "Memory") == K("32GB DDR5 4800MHz RDIMM", "Memory")
    def test_容量单位差异(self):
        assert K("64G 5600 DDR5 RDIMM", "Memory") == K("64GB DDR5 5600MHz RDIMM", "Memory")
    def test_dimm形态不同不误合(self):
        assert K("32GB DDR5 4800 UDIMM", "Memory") != K("32GB DDR5 4800 RDIMM", "Memory")
    def test_代数不同不误合(self):
        assert K("32G 4800 DDR4 RDIMM", "Memory") != K("32G 4800 DDR5 RDIMM", "Memory")
    def test_速率不同不误合(self):
        assert K("64G 5600 DDR5 RDIMM", "Memory") != K("64G 4800 DDR5 RDIMM", "Memory")
    def test_rank保留(self):
        assert K("16GB DDR5-6400 Single Rank x8", "Memory") != K("16GB DDR5-6400 Dual Rank x8", "Memory")
    def test_specs优先(self):
        assert K("32GB DDR5 4800", "Memory", {"DIMM Type": "RDIMM"}) == K("32G 4800 DDR5 RDIMM", "Memory")
