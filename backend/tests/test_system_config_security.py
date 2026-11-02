# -*- coding: utf-8 -*-
"""system_config 密钥出站掩码 / write-only 契约（2026-09-14 安全加固）。

全函数级单测：掩码、写回保留、实测剥离三件事各自的形状由这里锚定；
另含「仓库零硬编码库密码」宪法断言（app/ 与 scripts/ 全量正则扫描）。
"""
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.system_config import (
    _drop_masked_key,
    _mask_row,
    _mask_value,
    _write_only_api_key,
)
from ai_office.llm_client import _normalize_providers_value

_URL_PWD_RE = re.compile(r"(postgres(ql)?\+?\w*://[^/@\s:{}]+):([^@\s/{}]+)@")  # 密码段禁 {…}（f-string 插值不是字面量）


# ── GET 出站掩码 ─────────────────────────────────────────────────────────────

def test_mask_value_hides_api_key_keeps_rest():
    v = {"api_key": "sk-real-9999", "model": "m1", "base_url": "http://x"}
    out = _mask_value(v)
    assert out["api_key"] == "****9999"
    assert out["api_key_configured"] is True
    assert out["model"] == "m1"
    assert out["base_url"] == "http://x"


def test_mask_value_handles_json_string_row_form():
    """GET /{key} 行字典的 value 是原始 JSON 串：同样解析并掩码。"""
    raw = '{"api_key": "sk-real-9999", "model": "m1"}'
    out = _mask_value(raw)
    assert isinstance(out, dict)
    assert out["api_key"] == "****9999"
    assert out["model"] == "m1"


def test_mask_value_non_dict_passthrough():
    assert _mask_value("plain") == "plain"


def test_mask_row_touches_only_llm_config():
    row = {"key": "llm_config", "value": '{"api_key": "sk-real-9999"}'}
    out = _mask_row("llm_config", row)
    assert out["value"]["api_key"] == "****9999"
    other = {"key": "server_series", "value": ["Orion"]}
    assert _mask_row("server_series", other)["value"] == ["Orion"]


# ── 多供应商形状：掩码 / write-only / 归一化 ─────────────────────────────────

def _fake_repo_providers(stored: dict):
    class _Repo:
        def get_value(self, key, default=None):
            return stored
    return _Repo()


_PROVIDERS_STORED = {
    "active_id": "zhipu",
    "providers": [
        {"id": "zhipu", "name": "智谱官方", "api_key": "sk-zhipu-aaaa", "model": "glm-5.3-flash",
         "base_url": "https://api.z.ai/api/anthropic", "upstream_format": "anthropic"},
        {"id": "cloudprime", "name": "CloudPrime", "api_key": "sk-cp-bbbb", "model": "glm-5.3-flash",
         "base_url": "http://api.cloudprime.com.cn:5567", "upstream_format": "openai"},
    ],
}


def test_mask_value_providers_masks_each_independently():
    out = _mask_value(_PROVIDERS_STORED)
    keys = [p["api_key"] for p in out["providers"]]
    assert keys == ["****aaaa", "****bbbb"], "每个供应商密钥独立掩码（尾4位）"
    assert all(p["api_key_configured"] is True for p in out["providers"])
    assert out["active_id"] == "zhipu"
    assert out["providers"][0]["model"] == "glm-5.3-flash", "非密钥字段原样保留"


def test_mask_value_providers_json_string_form():
    raw = json.dumps(_PROVIDERS_STORED)
    out = _mask_value(raw)
    assert [p["api_key"] for p in out["providers"]] == ["****aaaa", "****bbbb"]


def test_write_only_providers_preserves_masked_by_id():
    incoming = {
        "active_id": "zhipu",
        "providers": [
            {**_PROVIDERS_STORED["providers"][0], "api_key": "****aaaa"},   # 掩码回传 → 保留原值
            {**_PROVIDERS_STORED["providers"][1], "api_key": "sk-cp-new"},  # 新明文 → 直接入库
        ],
    }
    out = _write_only_api_key(_fake_repo_providers(_PROVIDERS_STORED), incoming)
    assert out["providers"][0]["api_key"] == "sk-zhipu-aaaa", "掩码回传按 id 保留库内原值"
    assert out["providers"][1]["api_key"] == "sk-cp-new"
    assert "api_key_configured" not in out["providers"][0], "出站辅助标志不入库"


def test_write_only_providers_masked_new_id_clears():
    """库内没有该 id（新增供应商却带着掩码）：掩码视为无效，置空。"""
    incoming = {
        "active_id": "zhipu",
        "providers": [
            {"id": "brand-new", "name": "新供应商", "api_key": "****beef", "model": "m"},
        ],
    }
    out = _write_only_api_key(_fake_repo_providers(_PROVIDERS_STORED), incoming)
    assert out["providers"][0]["api_key"] == ""


def test_normalize_legacy_single_layer_to_providers():
    out = _normalize_providers_value({"api_key": "sk-old", "model": "m1"})
    assert out["active_id"] == "default"
    assert len(out["providers"]) == 1
    assert out["providers"][0]["id"] == "default"
    assert out["providers"][0]["api_key"] == "sk-old"


def test_normalize_providers_dedupes_ids_and_falls_back_active():
    out = _normalize_providers_value({
        "active_id": "ghost",
        "providers": [{"id": "a", "name": "b"}, "junk", {"id": "a", "name": "dup"}],
    })
    ids = [p["id"] for p in out["providers"]]
    assert len(set(ids)) == len(ids), "重复 id 必须去重"
    assert out["active_id"] in ids, "active_id 失效时回落存在的供应商"


def test_normalize_assigns_ids_when_missing():
    out = _normalize_providers_value({"active_id": "", "providers": [{"name": "x"}, {"name": "y"}]})
    ids = [p["id"] for p in out["providers"]]
    assert all(ids), "缺失 id 自动补齐"
    assert len(set(ids)) == len(ids)
    assert out["active_id"] == ids[0], "空 active_id 回落第一个供应商"


def test_normalize_empty_returns_empty():
    out = _normalize_providers_value({})
    assert out == {"active_id": "", "providers": []}
    assert _normalize_providers_value("junk") == {"active_id": "", "providers": []}


# ── 实测端点：掩码 key 按 provider_id 还原 ───────────────────────────────────

_LEGACY_STORED = {"api_key": "sk-real-9999", "model": "m1"}


class _FakeRepo:
    def get_value(self, key, default=None):
        return _LEGACY_STORED


def test_write_only_preserves_on_masked_roundtrip():
    out = _write_only_api_key(_FakeRepo(), {"api_key": "****9999", "model": "m1"})
    assert out["api_key"] == "sk-real-9999", "回传掩码必须保留库内原值"


def test_write_only_explicit_empty_clears():
    out = _write_only_api_key(_FakeRepo(), {"api_key": "", "api_key_configured": True})
    assert out["api_key"] == ""
    assert "api_key_configured" not in out


class _FakeRepoById:
    """按给定存储值伪造仓库（_drop_masked_key 读库解析掩码 key 时注入）。"""

    def __init__(self, stored: dict):
        self._stored = stored

    def get_value(self, key, default=None):
        return self._stored

    def close(self):
        pass


def test_drop_masked_key_resolves_by_provider_id(monkeypatch):
    monkeypatch.setattr("app.api.system_config.SystemConfigRepository",
                        lambda: _FakeRepoById(_PROVIDERS_STORED))
    cfg = {"provider_id": "cloudprime", "api_key": "****bbbb", "model": "glm-5.3-flash",
           "base_url": "http://api.cloudprime.com.cn:5567"}
    out = _drop_masked_key(cfg)
    assert out["api_key"] == "sk-cp-bbbb", "掩码按 provider_id 还原为该供应商原 key"
    assert out["model"] == "glm-5.3-flash"


def test_drop_masked_key_without_provider_id_falls_back_to_root(monkeypatch):
    monkeypatch.setattr("app.api.system_config.SystemConfigRepository",
                        lambda: _FakeRepoById(_LEGACY_STORED))
    out = _drop_masked_key({"api_key": "****acy", "model": "m1"})
    assert out["api_key"] == "sk-real-9999", "无 provider_id 时回落库内根 api_key"


def test_drop_masked_key_real_key_passthrough():
    cfg = {"api_key": "sk-new-input", "model": "m1"}
    assert _drop_masked_key(dict(cfg)) == cfg


# ── 宪法：仓库零硬编码库密码（app/ + scripts/ 全量扫描）──────────────────────

def test_no_embedded_password_in_db_urls():
    """连接串里不再允许出现内嵌密码字面量；密码只能来自 env/_localdb。"""
    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for sub in ("app", "scripts"):
        for p in (root / sub).rglob("*.py"):
            if _URL_PWD_RE.search(p.read_text(encoding="utf-8")):
                offenders.append(str(p.relative_to(root)))
    assert not offenders, f"连接串内嵌密码回流：{offenders}"
