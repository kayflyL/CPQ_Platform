# -*- coding: utf-8 -*-
"""需求分析 skill 的统一落地契约。

铁律（不 import agent_react / llm_client，只做确定性封装与校验）：
1. 事实必须真实存在于目录：料号/价格/规格来自工具返回，LLM 不编造。
2. 未命中白盒 unmatched，规格漂移白盒 spec_mismatch。
3. 替换/组合必须显式携带 reason + source，可审计、可回放。
4. 不允许“静默兜底选代表件”或“把放宽结果假装成精确匹配”。
"""
from __future__ import annotations


def grounding_envelope(parts: list) -> dict:
    """把 part_selector.select_parts 的扁平结果包成统一落地契约。"""
    matched: list = []
    unmatched: list = []
    spec_mismatch: list = []
    substitutions: list = []
    for p in (parts or []):
        if not isinstance(p, dict):
            continue
        if p.get("unmatched"):
            unmatched.append(p)
        elif p.get("spec_mismatch"):
            spec_mismatch.append(p)
        else:
            matched.append(p)
        sub = p.get("substitution")
        if isinstance(sub, dict) and sub.get("reason"):
            substitutions.append(sub)
    return {
        "matched": matched,
        "unmatched": unmatched,
        "spec_mismatch": spec_mismatch,
        "substitutions": substitutions,
        "count": len([p for p in (parts or []) if isinstance(p, dict)]),
    }


def validate_grounding(result: dict) -> list[str]:
    """契约校验：返回错误列表，空列表表示通过。"""
    errors: list[str] = []
    for part in (result.get("matched") or []):
        if not isinstance(part, dict) or not part.get("pn"):
            errors.append(f"matched 件缺料号: {part!r}")
    for part in (result.get("unmatched") or []):
        if not isinstance(part, dict) or not part.get("unmatched_reason"):
            errors.append(f"unmatched 件缺原因: {part!r}")
    for sub in (result.get("substitutions") or []):
        if not isinstance(sub, dict) or not sub.get("reason") or not sub.get("source"):
            errors.append(f"替换/组合缺 reason 或 source: {sub!r}")
    return errors
