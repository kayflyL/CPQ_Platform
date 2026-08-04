# -*- coding: utf-8 -*-
"""normalize_input 节点单测：需求输入规范化（格式归一/噪音过滤/白盒报告）。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[0]))  # backend/tests

from app.services.requirement_normalizer import normalize_text, normalize_table_rows


def test_table_rows_to_star_qty():
    """Markdown 表格数量列 → *N 后缀（R21）。"""
    out, report = normalize_text("| 处理器 | 兆芯开胜 KH50000-72（72 核） | 4 |\n| 内存 | 64GB DDR5 5200 | 16 |")
    assert "KH50000-72（72 核） *4" in out
    assert "64GB DDR5 5200 *16" in out
    assert any(r["rule"] == "table_rows" for r in report)


def test_table_header_and_separator_untouched():
    """表头/分隔行（非数字数量列）原样保留。"""
    out, _ = normalize_text("| 配件类型 | 型号 | 数量 |\n| :--- | :--- | :--- |")
    assert "| 配件类型 | 型号 | 数量 |" in out
    assert "| :--- | :--- | :--- |" in out


def test_char_fix_nmve():
    """拼写颠倒归一：NMVE → NVMe（R6）。"""
    out, report = normalize_text("1* 960G NMVE")
    assert "NVMe" in out and "NMVE" not in out
    assert any(r["rule"] == "char_fix" and r["from"] == "NMVE" for r in report)


def test_noise_timestamp_removed():
    """时间戳噪音（16:50）删除。"""
    out, report = normalize_text("Rackmount 2U, Redundant PSU.16:50")
    assert "16:50" not in out
    assert any(r["rule"] == "noise" and r["removed"] == "16:50" for r in report)


def test_noise_greeting_removed():
    """英文问候（Hi Rowling,）删除（R4）。"""
    out, report = normalize_text("Hi Rowling, can help for 27 unit server")
    assert out.startswith("can help for 27 unit server")
    assert any(r["rule"] == "noise" and "Hi Rowling" in (r["removed"] or "") for r in report)


def test_fullwidth_multiplier_unified():
    """全角乘号 × → *（数量解析统一）。"""
    out, _ = normalize_text("32G×8 960G×2")
    assert "32G*8" in out and "960G*2" in out


def test_collapse_whitespace():
    """连续空白折叠为单空格。"""
    out, _ = normalize_text("CPU:  AMD  9654  *  2")
    assert "  " not in out


def test_empty_text():
    """空文本直接返回，无报告。"""
    out, report = normalize_text("   ")
    assert out == "" and report == []


def test_config_disable_table_rows():
    """配置关闭表格归一（enable_table_rows=False）。"""
    cfg = {"enable_table_rows": False}
    out, _ = normalize_text("| 处理器 | KH50000 | 4 |", cfg)
    assert "| 处理器 | KH50000 | 4 |" in out


def test_rule_mismatch_preserves_text():
    """无规则命中时文本原样（不误删规格内容）。"""
    text = "2U 服务器 CPU:AMD 9654 内存:32G*16 硬盘:960G SSD*2"
    out, report = normalize_text(text)
    assert out == text
    assert report == []
