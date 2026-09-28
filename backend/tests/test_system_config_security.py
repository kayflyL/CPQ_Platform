# -*- coding: utf-8 -*-
"""system_config 密钥出站掩码 / write-only 契约（2026-09-14 安全加固）。

全函数级单测：掩码、写回保留、实测剥离三件事各自的形状由这里锚定；
另含「仓库零硬编码库密码」宪法断言（app/ 与 scripts/ 全量正则扫描）。
"""
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


# ── PUT write-only：回传掩码=保留原值，显式空串=清除 ─────────────────────────

class _FakeRepo:
    def get_value(self, key, default=None):
        return {"api_key": "sk-real-9999", "model": "m1"}


def test_write_only_preserves_on_masked_roundtrip():
    out = _write_only_api_key(_FakeRepo(), {"api_key": "****9999", "model": "m1"})
    assert out["api_key"] == "sk-real-9999", "回传掩码必须保留库内原值"


def test_write_only_explicit_empty_clears():
    out = _write_only_api_key(_FakeRepo(), {"api_key": "", "api_key_configured": True})
    assert out["api_key"] == ""
    assert "api_key_configured" not in out


def test_drop_masked_key_drops_and_keeps_rest():
    out = _drop_masked_key({"api_key": "****9999", "model": "m1"})
    assert "api_key" not in out
    assert out["model"] == "m1"


def test_drop_masked_key_keeps_real_key_passthrough():
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
