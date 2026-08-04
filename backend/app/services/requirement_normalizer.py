# -*- coding: utf-8 -*-
"""需求输入规范化（normalize_input 节点）—— 纯函数、配置驱动、可单测。

职责：extract（关键词提取）之前的输入预处理，把千变万化的用户写法归一成系统可识别的
统一格式，让 extract 只做语义抽取、不再逐条堆格式正则。

数据驱动铁律：
- 全部归一规则（字符修正 / 表格行归一 / 噪音过滤 / 空白折叠）来自 normalize_input
  节点 config（推理流画布可编辑）；读失败/缺省用本模块 DEFAULT_NORMALIZE_CONFIG 兜底。
- 输出带 report（白盒：哪些规则命中、删了什么），供推理面板展示"我做了哪些归一"。

返回 (normalized_text, report)：
    report = [{"rule": "char_fix", "from": ..., "to": ...},
              {"rule": "noise", "pattern": ..., "note": ..., "removed": ...},
              {"rule": "table_rows", "lines": N}, ...]
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# 默认归一配置 —— 仅作节点 config 缺省/读失败兜底；权威来源是推理流画布的 normalize_input 节点。
DEFAULT_NORMALIZE_CONFIG: dict = {
    # 有序字符修正（常见拼写颠倒/全角归一），(from, to)
    "char_fixes": [
        ["NMVE", "NVMe"],   # "960G NMVE" → NVMe（训练 R6 常见拼写颠倒）
        ["＋", "+"],        # 全角加号 → 半角（GPU/内存组按 + 切段）
        ["×", "*"],         # 乘号统一为 *（数量解析 qty_multipliers 默认认 * 和 ×；统一后更稳）
    ],
    # Markdown/管道表格行归一：数量列 → *N 后缀（R21）
    "enable_table_rows": True,
    # 噪音过滤（正则列表，逐个从文本删除）：纯噪音词/时间戳/问候语，删了不影响任何规格解析
    "noise_patterns": [
        {"pattern": r"\b\d{1,2}:\d{2}(?::\d{2})?\b", "flags": "", "note": "时间戳（如 16:50）"},
        {"pattern": r"^\s*hi\s+[a-z][a-z0-9]*[,，]?\s*", "flags": "i", "note": "英文问候（Hi Rowling,）"},
        {"pattern": r"^\s*(?:你好|您好|哈喽|hello|hi)\s*[,，:：]?\s*", "flags": "i", "note": "中文/英文问候语"},
    ],
    # 连续空白/制表符 → 单空格（避免换行折行带来的碎片 token）
    "collapse_whitespace": True,
}


def load_normalize_config(config: Optional[dict]) -> dict:
    """读归一配置：节点 config（权威）→ 模块默认。任何缺失字段用默认补。"""
    merged = dict(DEFAULT_NORMALIZE_CONFIG)
    if isinstance(config, dict):
        for k, v in config.items():
            if v is not None:
                merged[k] = v
    return merged


def normalize_table_rows(text: str) -> str:
    """Markdown/管道表格行归一（R21）："| 处理器 | 兆芯...KH50000-72... | 4 |" →
    "处理器 兆芯...KH50000-72... *4"——把每行数量列拼成 *N 后缀，让现有数量绑定/盘组/内存组生效。
    分隔行（| :--- |）与表头（| 数量 |）非数字，原样保留。"""
    if "|" not in text:
        return text
    out = []
    for line in text.splitlines():
        line = line.rstrip()
        if "|" not in line:
            out.append(line)
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c]
        if len(cells) < 3:
            out.append(line)
            continue
        m = re.match(r"^(\d+)\s*(?:套|个|块|张|台|条)?$", cells[-1])
        if not m:
            out.append(line)
            continue
        body = " ".join(cells[:-1])
        out.append(f"{body} *{int(m.group(1))}")
    return "\n".join(out)


def _apply_char_fixes(text: str, fixes: list) -> tuple:
    report = []
    for pair in (fixes or []):
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        frm, to = pair[0], pair[1]
        if frm and frm in text:
            text = text.replace(frm, to)
            report.append({"rule": "char_fix", "from": frm, "to": to})
    return text, report


def _apply_noise(text: str, patterns: list) -> tuple:
    report = []
    for item in patterns or []:
        pat = item.get("pattern") if isinstance(item, dict) else item
        if not pat:
            continue
        try:
            flags = re.IGNORECASE if (isinstance(item, dict) and item.get("flags") and "i" in item["flags"]) else 0
            rx = re.compile(pat, flags)
        except re.error as e:
            logger.warning("normalize noise 正则编译失败，跳过: %s err=%s", pat, e)
            continue
        removed = rx.sub("", text)
        if removed != text:
            m = rx.search(text)
            sample = m.group(0) if m else ""
            report.append({"rule": "noise", "pattern": pat,
                           "note": item.get("note") if isinstance(item, dict) else "",
                           "removed": sample})
            text = removed
    return text, report


def normalize_text(text: str, config: Optional[dict] = None) -> tuple:
    """需求文本 → 归一文本 + report（白盒）。extract 之前调用。

    顺序：字符修正 → 表格行归一 → 噪音过滤 → 空白折叠。
    """
    text = (text or "").strip()
    cfg = load_normalize_config(config)
    report: list = []

    if not text:
        return text, report

    # 1) 字符修正（拼写颠倒/全角归一）
    text, r1 = _apply_char_fixes(text, cfg.get("char_fixes"))
    report += r1

    # 2) 表格行归一
    if cfg.get("enable_table_rows"):
        before = text
        text = normalize_table_rows(text)
        if text != before:
            report.append({"rule": "table_rows", "lines": before.count("\n") + 1})

    # 3) 噪音过滤
    text, r3 = _apply_noise(text, cfg.get("noise_patterns"))
    report += r3

    # 4) 空白折叠
    if cfg.get("collapse_whitespace"):
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)

    return text.strip(), report
