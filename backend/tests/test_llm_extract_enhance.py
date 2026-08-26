# -*- coding: utf-8 -*-
"""LLM 抽取增强：chat_json / schema 收口 / 确定性合并（R6 R7 场景）。

跑法（backend 目录）：python -X utf8 -m pytest tests/test_llm_extract_enhance.py -q
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import llm_client
from app.services.llm_extract_enhance import (
    EXTRACT_ENHANCE_SCHEMA,
    _has_drive_config_signal,
    _interface_norm,
    _model_tokens_of,
    _term_from_capacity,
    merge_into_ext,
)


# ============================================================
# clean_by_schema —— 多余键丢弃 / 类型强制 / 枚举收口
# ============================================================

def test_clean_by_schema_drops_extra_keys_and_coerces():
    data = {
        "cpu": {"model": "AMD EPYC 9254", "cores": "24", "tdp_w": 200, "hack": "x"},
        "memory": {"per_stick_gb": "32", "qty": 2, "type": "ddr5", "speed_mt": 4800},
        "form": "2U",
        "totally_extra": 1,
    }
    cleaned, dropped = llm_client.clean_by_schema(data, EXTRACT_ENHANCE_SCHEMA)
    assert "totally_extra" not in cleaned
    assert "hack" not in cleaned["cpu"]
    assert cleaned["cpu"]["cores"] == 24          # "24" 强制 int
    assert cleaned["memory"]["type"] == "DDR5"    # 枚举大小写不敏感 → 规范值
    assert cleaned["memory"]["per_stick_gb"] == 32
    assert cleaned["form"] == "2U"


def test_clean_by_schema_drops_invalid_enum_and_noninteger():
    data = {
        "memory": {"type": "LPDDR6"},          # 枚举外 → 丢弃
        "cpu": {"cores": 7.68},                # 非整数值 → 丢弃
        "drives": [{"capacity": "960G", "interface": "IDE", "qty": 1}],  # IDE 枚举外
    }
    cleaned, dropped = llm_client.clean_by_schema(data, EXTRACT_ENHANCE_SCHEMA)
    assert "type" not in cleaned.get("memory", {})
    assert "cores" not in cleaned.get("cpu", {})
    assert cleaned["drives"] == [{"capacity": "960G", "qty": 1}]  # interface 无效被丢弃，有效字段保留
    assert any("memory.type" in d for d in dropped)
    assert any("drives" in d for d in dropped)


def test_clean_by_schema_non_dict_returns_empty():
    cleaned, dropped = llm_client.clean_by_schema([1, 2], EXTRACT_ENHANCE_SCHEMA)
    assert cleaned == {}


# ============================================================
# chat_json —— JSON mode / schema / 重试 / 降级
# ============================================================

def _fake_client(responses):
    """responses: list of (content_str | Exception) 依次消费。"""
    class _Completions:
        def __init__(self):
            self.responses = list(responses)
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            r = self.responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=r))])

    comp = _Completions()
    return comp, SimpleNamespace(chat=SimpleNamespace(completions=comp))


def _patch_env(mock_client, comp):
    patch("app.services.llm_client._client", return_value=mock_client).start()
    patch("app.services.llm_client._get_llm_config", return_value={
        "base_url": "http://x", "api_key": "k", "model": "m",
        "system_prompt": "", "temperature": 0.2, "max_tokens": 8000, "capabilities_override": {"m": {"supports_json_mode": True}},
    }).start()


def test_chat_json_json_mode_and_schema_clean():
    comp, client = _fake_client([
        '{"cpu": {"model": "AMD EPYC 9254", "cores": "24"}, "extra": 1}',
    ])
    with patch("app.services.llm_client._client", return_value=client), \
         patch("app.services.llm_client._get_llm_config", return_value={
             "base_url": "http://x", "api_key": "k", "model": "m",
             "system_prompt": "", "temperature": 0.2, "max_tokens": 8000, "capabilities_override": {"m": {"supports_json_mode": True}}}):
        data = asyncio.run(llm_client.chat_json(
            [{"role": "user", "content": "hi"}], schema=EXTRACT_ENHANCE_SCHEMA))
    assert data["cpu"]["cores"] == 24
    assert "extra" not in data
    kw = comp.calls[0]
    assert kw["response_format"] == {"type": "json_object"}
    assert kw["model"] == "m"


def test_chat_json_retries_once_then_succeeds():
    comp, client = _fake_client([
        "not json {{{",                       # 第一次解析失败
        '{"form": "4U"}',                     # 第二次成功
    ])
    with patch("app.services.llm_client._client", return_value=client), \
         patch("app.services.llm_client._get_llm_config", return_value={
             "base_url": "http://x", "api_key": "k", "model": "m",
             "system_prompt": "", "temperature": 0.2, "max_tokens": 8000, "capabilities_override": {"m": {"supports_json_mode": True}}}):
        data = asyncio.run(llm_client.chat_json([{"role": "user", "content": "hi"}]))
    assert data["form"] == "4U"
    assert len(comp.calls) == 2


def test_chat_json_raises_after_retries():
    comp, client = _fake_client([
        RuntimeError("boom"), RuntimeError("boom again"),
    ])
    with patch("app.services.llm_client._client", return_value=client), \
         patch("app.services.llm_client._get_llm_config", return_value={
             "base_url": "http://x", "api_key": "k", "model": "m",
             "system_prompt": "", "temperature": 0.2, "max_tokens": 8000, "capabilities_override": {"m": {"supports_json_mode": True}}}):
        with pytest.raises(llm_client.LLMError):
            asyncio.run(llm_client.chat_json([{"role": "user", "content": "hi"}]))
    assert len(comp.calls) == 2


def test_chat_json_empty_content_raises():
    comp, client = _fake_client(["", ""])
    with patch("app.services.llm_client._client", return_value=client), \
         patch("app.services.llm_client._get_llm_config", return_value={
             "base_url": "http://x", "api_key": "k", "model": "m",
             "system_prompt": "", "temperature": 0.2, "max_tokens": 8000, "capabilities_override": {"m": {"supports_json_mode": True}}}):
        with pytest.raises(llm_client.LLMError):
            asyncio.run(llm_client.chat_json([{"role": "user", "content": "hi"}]))
    assert len(comp.calls) == 2


# ============================================================
# 确定性翻译工具
# ============================================================

def test_model_tokens_of_filters_capacity_fragments():
    assert _model_tokens_of("NVIDIA RTX PRO 4500 Server 32G") == ["4500"]
    assert _model_tokens_of("LSI 9560-8i") == ["9560-8i"]
    assert _model_tokens_of("AMD EPYC 9254") == ["9254"]
    assert _model_tokens_of("") == []


def test_term_from_capacity_and_interface_norm():
    assert _term_from_capacity("960G", None) == "960G"
    assert _term_from_capacity("7.68T", None) == "7.68T"
    assert _term_from_capacity(" 480 GB ", None) == "480G"
    assert _term_from_capacity(None, 7680) == "7680G"
    assert _term_from_capacity(None, None) is None
    assert _interface_norm("U.2") == "NVMe"
    assert _interface_norm("u3") == "NVMe"
    assert _interface_norm("SATA") == "SATA"
    assert _interface_norm("PCIe") is None


def test_has_drive_config_signal_capability_vs_config():
    # R6：N*容量 → 强配置信号
    assert _has_drive_config_signal("1* 960G NMVE")
    # R2：容量*N
    assert _has_drive_config_signal("2* 480GB SATA SSD")
    assert _has_drive_config_signal("4* 7.68 TB Enterprise-class SSD")
    # R7：能力声明 → 不是配置
    assert not _has_drive_config_signal("支持12个3.5英寸硬盘(前置8*SATA+4*NVMEU.2)")
    # R4：盘位能力
    assert not _has_drive_config_signal("12/24 bays HDDSupport of NVMe")
    # 字段行（R3）
    assert _has_drive_config_signal("系统固态硬盘:960GB企业级SSD，2.5寸热插拔*2")
    # 配N块…盘
    assert _has_drive_config_signal("配 2 块 800G 傲腾 NVMe 缓存盘")


# ============================================================
# merge_into_ext —— 只补缺、规则赢、能力声明不当配置
# ============================================================

def test_merge_r6_like_confirms_and_enriches():
    # 规则已抽到 9254 关键词/内存/盘组（R6 修复后状态），LLM 结构化补核数/TDP/完整型号
    ext = {
        "categories": ["CPU", "Memory", "HDD/SSD", "GPU", "Network(NIC) requirement"],
        "keywords": ["9254", "32G", "960G", "4500"],
        "cpu_signal": {"duality": True},
        "mem_signal": {"type": "DDR5", "speed": 4800, "total_gb": 64},
        "mem_groups": [{"term": "32G", "qty": 2}],
        "drive_groups": [{"term": "960G", "qty": 1, "kind": "NVMe"}],
        "gpu_groups": [{"tokens": ["4500"], "qty": 1}],
        "psu_signal": {"wattage": 1300, "qty": 2},
    }
    cleaned = {
        "cpu": {"model": "AMD EPYC 9254", "cores": 24, "tdp_w": 200, "qty": 2},
        "memory": {"per_stick_gb": 32, "qty": 2, "type": "DDR5", "speed_mt": 4800},
        "drives": [{"capacity": "960G", "interface": "NVMe", "qty": 1}],
        "gpu": [{"model": "NVIDIA RTX PRO 4500", "qty": 1}],
        "psu": {"wattage": 1300, "qty": 2},
        "form": "2U",
    }
    changes = merge_into_ext(ext, cleaned, requirement_text="2* AMD EPYC 9254\n1* 960G NMVE")
    joined = " ".join(changes)
    # CPU：补 cores/tdp/model（duality 规则已有不覆盖）
    assert ext["cpu_signal"]["cores"] == 24
    assert ext["cpu_signal"]["tdp_w"] == 200
    assert ext["cpu_signal"]["model"] == "AMD EPYC 9254"
    assert ext["cpu_signal"]["duality"] is True
    # 内存：规则已抽到 → 不覆盖、不重复成组
    assert ext["mem_signal"]["total_gb"] == 64
    assert len(ext["mem_groups"]) == 1
    # 盘：已有同 term+kind → 不重复
    assert len(ext["drive_groups"]) == 1
    # GPU：token 4500 已有 → 前置完整型号（更精确匹配）
    assert ext["gpu_groups"][0]["tokens"] == ["NVIDIA RTX PRO 4500", "4500"]
    # 电源：规则已有 → 不动
    assert ext["psu_signal"] == {"wattage": 1300, "qty": 2}
    # 形态：规则没有 → 补
    assert ext["form"] == "2U"
    assert "cpu.cores=24" in joined


def test_merge_r7_capability_never_becomes_config():
    # R7 典型报价单：能力声明（支持12盘/8GPU）+ 无单条容量 + CPU 系列号
    ext = {"categories": ["CPU", "Memory"]}
    cleaned = {
        "cpu": {"model": None, "cores": None, "qty": 2},
        "memory": {"per_stick_gb": None, "qty": None, "type": "DDR5", "speed_mt": 6400},
        "drives": [{"capacity": "12", "interface": "SATA", "qty": 12}],   # LLM 误把能力当配置
        "gpu": [{"model": None, "qty": 8}],                                # 无具体型号
        "psu": {"wattage": 2700, "qty": None},
        "form": "4U",
        "series": "AMD EPYC 9004",                                         # CPU 系列号，非平台系列
    }
    changes = merge_into_ext(
        ext, cleaned,
        requirement_text="2个AMD EPYC 9004/9005系列处理器\n支持12个3.5英寸硬盘\n支持8个GPU卡\n2700W电源")
    # 盘：能力声明 → 不产盘组、不补 HDD/SSD 品类
    assert not ext.get("drive_groups")
    assert "HDD/SSD" not in ext["categories"]
    # GPU：无具体型号 → 不产 GPU 组
    assert not ext.get("gpu_groups")
    assert "GPU" not in ext["categories"]
    # 内存：无单条容量 → 不产内存组；但 type/speed 补进信号
    assert not ext.get("mem_groups")
    assert ext["mem_signal"]["type"] == "DDR5"
    assert ext["mem_signal"]["speed"] == 6400
    # CPU：qty=2 → duality + cpu_signal.qty=2（唯一真值源，不再双写 qty_map）
    assert ext["cpu_signal"]["duality"] is True
    assert ext["cpu_signal"]["qty"] == 2
    # 电源：规则没有 → 补 2700W
    assert ext["psu_signal"]["wattage"] == 2700
    # 形态：补 4U
    assert ext["form"] == "4U"
    # 系列：非平台系列 → 拒绝
    assert "series" not in ext
    assert any("系列" in c for c in changes)


def test_merge_fills_sparse_requirement():
    # 规则词表够不到：傲腾缓存盘 → LLM 补盘组 + 品类
    ext = {"categories": ["CPU"], "keywords": ["9654"]}
    cleaned = {
        "cpu": {"model": "AMD EPYC 9654", "qty": 2},
        "drives": [{"capacity": "800G", "interface": "NVMe", "qty": 2}],
        "nic": [{"speed_g": 25, "ports": 2, "qty": 2, "with_optical_module": True}],
        "raid": {"model": "LSI 9560-8i", "qty": 1},
    }
    merge_into_ext(ext, cleaned, requirement_text="配 2 块 800G 傲腾 NVMe 缓存盘")
    assert ext["drive_groups"] == [{"term": "800G", "qty": 2, "kind": "NVMe"}]
    assert "HDD/SSD" in ext["categories"]
    assert "CPU" in ext["categories"]
    # 网卡：规则没抽到 → 补行
    nic_lines = ext["multi_spec_filters"]["Network(NIC) requirement"]
    assert nic_lines[0]["filters"] == [
        {"spec_key": "Link Speed", "op": "=", "value": "25G"},
        {"spec_key": "Ports", "op": "=", "value": "2"},
    ]
    assert nic_lines[0]["qty"] == 2
    assert "光模块" in nic_lines[0]["name_contains"]
    # RAID：补型号 token + 单真值源 raid_groups（不再写旧 raid_signal）
    assert "9560-8i" in ext["keywords"]
    assert ext["raid_groups"] == [{"model": "LSI 9560-8i", "qty": 1, "cache": None}]
    assert "Raid card" in ext["categories"]


def test_merge_rule_wins_on_psu_and_mem():
    ext = {"psu_signal": {"wattage": 2000}, "mem_signal": {"speed": 4800}}
    cleaned = {"psu": {"wattage": 1300, "qty": 2}, "memory": {"speed_mt": 6400}}
    merge_into_ext(ext, cleaned, requirement_text="1300W 电源")
    # 规则已有 wattage → LLM 不能覆盖；只补缺 qty
    assert ext["psu_signal"]["wattage"] == 2000
    assert ext["psu_signal"]["qty"] == 2
    # 内存 speed 已有 → 不覆盖
    assert ext["mem_signal"]["speed"] == 4800



# ============================================================
# agent 主理解路（P1.2）：ext 从空起步，LLM 槽位确定性全填
# ============================================================

def test_merge_agent_primary_fills_all_essential_keys():
    """agent 主理解路：ext 从空起步，LLM 槽位合并后 pick_kp_parts/build_plan 所需全键齐全。"""
    ext: dict = {}
    cleaned = {
        "cpu": {"model": "AMD EPYC 9124", "cores": 16, "qty": 1},
        "memory": {"per_stick_gb": 32, "qty": 16, "type": "DDR5", "speed_mt": 5600},
        "drives": [{"capacity": "3.84T", "interface": "NVMe", "qty": 2},
                   {"capacity": "480G", "interface": "SATA", "qty": 2}],
        "gpu": [{"model": "RTX 5090", "qty": 8}],
        "nic": [{"speed_g": 25, "ports": 2, "qty": 2, "with_optical_module": True}],
        "psu": {"wattage": 2700, "qty": 4},
        "raid": {"model": "LSI 9560-16i", "qty": 1},
        "form": "4U",
        "server_type": "AI / 加速计算服务器",
    }
    merge_into_ext(ext, cleaned,
                   requirement_text="EPYC 9124 / 32G*16 DDR5 / 2*3.84T NVMe / RTX 5090 32G*8 / 双口25G",
                   catalog={"server_types": ["AI / 加速计算服务器", "通用计算服务器", "存储服务器"]})
    cats = ext["categories"]
    for c in ("CPU", "Memory", "HDD/SSD", "GPU", "Network(NIC) requirement", "Raid card"):
        assert c in cats, f"缺品类 {c}"
    # CPU 型号唯一真值源 cpu_signal；不再注入 keywords（pick 阶段自行推导检索）
    assert ext["cpu_signal"]["model"] == "AMD EPYC 9124"
    assert "9124" not in ext["keywords"]
    # 内存：单真值源 mem_signal；数量与单条容量都在信号内，不再写 mem_groups
    assert ext["mem_signal"]["type"] == "DDR5"
    assert ext["mem_signal"]["per_stick_gb"] == 32
    assert ext["mem_signal"]["qty"] == 16
    # 盘组（两种盘）
    assert sorted(g["term"] for g in ext["drive_groups"]) == ["3.84T", "480G"]
    # GPU 组
    assert ext["gpu_groups"][0]["qty"] == 8
    # 网卡多规格行
    assert ext["multi_spec_filters"]["Network(NIC) requirement"][0]["qty"] == 2
    # 电源
    assert ext["psu_signal"]["wattage"] == 2700
    # RAID 组（P1.2 补丁：形状 {model,qty,cache}，对齐 _extract_raid_groups；只保留单真值源 raid_groups）
    assert ext["raid_groups"] == [{"model": "LSI 9560-16i", "qty": 1, "cache": None}]
    # 形态 + 服务器类型（P1.2：catalog 锚定）
    assert ext["form"] == "4U"
    assert ext["server_type_name"] == "AI / 加速计算服务器"
    assert ext["usage"] == "AI / 加速计算服务器"


def test_merge_server_type_catalog_anchored():
    """P1.2：server_type 命中 catalog 在售白名单才写（防 LLM 编造类型）；编造/无 catalog → 不写。"""
    catalog = {"server_types": ["AI / 加速计算服务器", "通用计算服务器", "存储服务器"]}
    ext = {}
    merge_into_ext(ext, {"server_type": "通用计算服务器"}, requirement_text="web", catalog=catalog)
    assert ext["server_type_name"] == "通用计算服务器"
    # 不在白名单（编造）→ 拒绝
    ext2 = {}
    merge_into_ext(ext2, {"server_type": "量子计算服务器"}, requirement_text="x", catalog=catalog)
    assert "server_type_name" not in ext2
    # 无 catalog（增强路）→ 不校验也不写 server_type（agent 路必传 catalog）
    ext3 = {}
    merge_into_ext(ext3, {"server_type": "AI"}, requirement_text="x")
    assert "server_type_name" not in ext3


def test_merge_cpu_model_token_enters_keywords_dedup():
    """P1.2：CPU 型号唯一真值源 cpu_signal.model（不再注入 keywords）；重复同型号去重。"""
    ext: dict = {}
    merge_into_ext(ext, {"cpu": {"model": "KH50000", "qty": 2}}, requirement_text="KH50000")
    assert ext["cpu_signal"]["model"] == "KH50000"
    assert "KH50000" not in ext.get("keywords", [])
    merge_into_ext(ext, {"cpu": {"model": "KH50000", "qty": 2}}, requirement_text="KH50000")
    assert ext["cpu_signal"]["model"] == "KH50000"
    assert "KH50000" not in ext.get("keywords", [])


def test_merge_raid_groups_shape_matches_extract():
    """P1.2：raid_groups 形状对齐 _extract_raid_groups（{model,qty,cache}），_pick_raid_groups 可消费；同型号去重。"""
    ext: dict = {}
    merge_into_ext(ext, {"raid": {"model": "9560-8i", "qty": 1}}, requirement_text="RAID卡 9560-8i")
    assert ext["raid_groups"] == [{"model": "9560-8i", "qty": 1, "cache": None}]
    merge_into_ext(ext, {"raid": {"model": "9560-8i", "qty": 1}}, requirement_text="RAID卡 9560-8i")
    assert len(ext["raid_groups"]) == 1

def test_merge_drive_capacity_gb_ai_first():
    """AI-first（2026-08 修）：LLM 把"1T以上的硬盘"归一成 capacity_gb=1024 →
    merge 必须产出 drive_group term=1024G + HDD/SSD 品类（此前只给 capacity:"1T以上" →
    _term_from_capacity 返回 None → 整条盘需求被静默跳过 → 方案零硬盘 + 审计误报）。"""
    ext: dict = {}
    merge_into_ext(
        ext,
        {"drives": [{"capacity": "1T以上", "capacity_gb": 1024, "qty": 1}]},
        requirement_text="配1T以上的硬盘",
    )
    assert ext["drive_groups"] == [{"term": "1024G", "qty": 1, "kind": None}]
    assert "HDD/SSD" in ext["categories"]

    # 缺 capacity_gb（AI 没归一）→ 比较短语不猜，保持跳过（不产错误盘）
    ext2: dict = {}
    merge_into_ext(
        ext2,
        {"drives": [{"capacity": "1T以上", "qty": 1}]},
        requirement_text="配1T以上的硬盘",
    )
    assert not ext2.get("drive_groups")
    assert "HDD/SSD" not in ext2.get("categories", [])


def test_merge_drive_comparison_gte_carried():
    """AI comparison（gte/lte）从 LLM 契约透传到 drive_groups（2026-08 可配置化）。"""
    ext: dict = {}
    merge_into_ext(
        ext,
        {"drives": [{"capacity": "1T以上", "capacity_gb": 1024, "comparison": "gte", "qty": 1}]},
        requirement_text="配1T以上的硬盘",
    )
    assert ext["drive_groups"][0]["term"] == "1024G"
    assert ext["drive_groups"][0]["comparison"] == "gte"
    # 无比较 → 不写 comparison 键
    ext2: dict = {}
    merge_into_ext(
        ext2,
        {"drives": [{"capacity": "960G", "capacity_gb": 960, "qty": 1}]},
        requirement_text="配960G硬盘",
    )
    assert "comparison" not in ext2["drive_groups"][0]


def test_merge_gpu_vram_only_comparison():
    """AI 显存约束（2026-08）：无型号的"48G以上显存"→ 纯显存组（tokens=[] + cap + comparison）。"""
    ext: dict = {}
    merge_into_ext(
        ext,
        {"gpu": [{"capacity_gb": 48, "comparison": "gte", "qty": 2}]},
        requirement_text="配2张48G以上显存的显卡",
    )
    g = ext["gpu_groups"]
    assert len(g) == 1
    assert g[0]["tokens"] == [] and g[0]["cap"] == 48
    assert g[0]["comparison"] == "gte" and g[0]["qty"] == 2
    assert "GPU" in ext["categories"]
