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
    build_messages,
    merge_into_ext,
    run_extract_enhance,
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
        "system_prompt": "", "temperature": 0.2, "max_tokens": 8000,
    }).start()


def test_chat_json_json_mode_and_schema_clean():
    comp, client = _fake_client([
        '{"cpu": {"model": "AMD EPYC 9254", "cores": "24"}, "extra": 1}',
    ])
    with patch("app.services.llm_client._client", return_value=client), \
         patch("app.services.llm_client._get_llm_config", return_value={
             "base_url": "http://x", "api_key": "k", "model": "m",
             "system_prompt": "", "temperature": 0.2, "max_tokens": 8000}):
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
             "system_prompt": "", "temperature": 0.2, "max_tokens": 8000}):
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
             "system_prompt": "", "temperature": 0.2, "max_tokens": 8000}):
        with pytest.raises(llm_client.LLMError):
            asyncio.run(llm_client.chat_json([{"role": "user", "content": "hi"}]))
    assert len(comp.calls) == 2


def test_chat_json_empty_content_raises():
    comp, client = _fake_client(["", ""])
    with patch("app.services.llm_client._client", return_value=client), \
         patch("app.services.llm_client._get_llm_config", return_value={
             "base_url": "http://x", "api_key": "k", "model": "m",
             "system_prompt": "", "temperature": 0.2, "max_tokens": 8000}):
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
    # CPU：qty=2 → duality + qty_map.CPU=2
    assert ext["cpu_signal"]["duality"] is True
    assert ext["qty_map"]["CPU"] == 2
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
    # RAID：补型号 token + raid_signal
    assert "9560-8i" in ext["keywords"]
    assert ext["raid_signal"] == {"model": "LSI 9560-8i", "qty": 1}
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
# run_extract_enhance —— handler 编排 + 失败降级
# ============================================================

def _patch_chat_json(return_value=None, exc=None):
    m = AsyncMock()
    if exc:
        m.side_effect = exc
    else:
        m.return_value = return_value
    return patch("app.services.llm_client.chat_json", m)


def test_run_extract_enhance_merges_and_reports():
    ext = {"categories": ["CPU"]}
    slots = {"cpu": {"model": "AMD EPYC 9254", "cores": 24, "qty": 2}, "form": "2U"}
    with _patch_chat_json(return_value=slots):
        payload = asyncio.run(run_extract_enhance(
            "2* AMD EPYC 9254 24 2.9 GHz 128 MB 200W", ext, {"enable_llm": True}))
    assert payload["llm_called"] is True
    assert payload["merged"] is True
    assert ext["cpu_signal"]["cores"] == 24      # 就地增强
    assert ext["form"] == "2U"
    assert payload["llm_slots"]["cpu"]["cores"] == 24


def test_run_extract_enhance_llm_failure_degrades_silently():
    ext = {"categories": ["CPU"]}
    with _patch_chat_json(exc=llm_client.LLMError("no key")):
        payload = asyncio.run(run_extract_enhance("服务器", ext, {"enable_llm": True}))
    assert payload["merged"] is False
    assert payload["error"]
    assert ext == {"categories": ["CPU"]}        # ctx 不变


def test_run_extract_enhance_empty_text_skips():
    payload = asyncio.run(run_extract_enhance("", {"categories": []}, {}))
    assert payload["reason"] == "empty_text"


def test_run_extract_enhance_sparse_threshold_skips():
    ext = {"categories": ["CPU", "Memory", "HDD/SSD", "GPU"]}
    with _patch_chat_json(return_value={"form": "2U"}) as m:
        payload = asyncio.run(run_extract_enhance("服务器", ext, {"sparse_max_categories": 3}))
    assert payload["merged"] is False
    m.assert_not_awaited()

def test_build_messages_contains_text_and_digest():
    msgs = build_messages("1* 960G NMVE", {"categories": ["HDD/SSD"]})
    assert msgs[0]["role"] == "system"
    assert "960G NMVE" in msgs[1]["content"]
    assert "HDD/SSD" in msgs[1]["content"]