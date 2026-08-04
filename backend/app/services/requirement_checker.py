# -*- coding: utf-8 -*-
"""方案校对（review 节点）—— 阻塞式校对：通过/不通过 + 必改项（≤2 条）。

与已删的 requirement_check（需求核对差异报告）本质区别：
  校对 = "确认方案可用"（通过/不通过 + 必改项），差异报告 = "列出所有差异"。

硬校验（任一命中即 blocked）：
  1) 缺关键件：KP 无 CPU / 无内存实件 → 方案不可用；
  2) 平台冲突：需求显式点名厂商/信创/AMD/Intel，方案系列对不上（跨厂商是硬错误）；
  3) 严重超预算：over_budget.ratio > 阈值 → 需确认降配。
其余（替代/库缺口/措辞）不算 blocked —— 那是正常业务，不是错误。
"""
from __future__ import annotations

import re
from typing import Optional

# ============================================================
# 方案校对（review 节点，2026-08-04 流程重构 R29）—— 阻塞式，不是警告清单。
# 与 requirement_check（已删的差异报告）本质区别：
#   校对 = "确认方案可用"（通过/不通过 + 必改项≤2），差异报告 = "列出所有差异"。
# ============================================================

_XINCHUANG_RE = re.compile(r"信创|国产|鲲鹏|飞腾|海光|兆芯|龙芯|麒麟|开先|开胜|hygon|phytium|kunpeng|loongson|zhaoxin", re.I)
# 厂商感知（Polaris 只配兆芯）：需求显式点名厂商 → 按厂商核对，海光/飞腾/鲲鹏/龙芯 ≠ Polaris
_ZHAOXIN_RE = re.compile(r"(?:^|[^A-Za-z0-9])(?:KH|KX|ZX)|兆芯|zhaoxin|开胜|开先", re.I)
_HYGON_RE = re.compile(r"海光|hygon|\bC86", re.I)
_PHYTIUM_RE = re.compile(r"飞腾|phytium|腾锐|腾云", re.I)
_KUNPENG_RE = re.compile(r"鲲鹏|kunpeng|\b920\b", re.I)
_LOONGSON_RE = re.compile(r"龙芯|loongson", re.I)
_AMD_RE = re.compile(r"AMD|EPYC|霄龙", re.I)
_INTEL_RE = re.compile(r"Intel|Xeon|至强", re.I)

def audit_plan(plan: dict, requirement_text: str = "", ext: Optional[dict] = None,
               budget_over_ratio: float = 0.3) -> dict:
    """阻塞式校对：通过/不通过 + 必改项（≤2 条）。挂在 plan.audit，前端方案卡展示。

    硬校验（任一命中即 blocked）：
      1) 缺关键件：KP 无 CPU / 无内存实件 → 方案不可用；
      2) 平台冲突：需求显式信创/AMD/Intel，方案系列对不上（跨平台是硬错误）；
      3) 严重超预算：over_budget.ratio > 阈值 → 需确认降配。
    其余（替代/库缺口/措辞）不算 blocked —— 那是正常业务，不是错误。
    """
    issues: list = []
    kp_rows = [r for r in (plan.get("cfg") or {}).get("bom_excel_rows") or []
               if (r.get("category") or "") == "Key Parts"]
    cats = [(r.get("part_category") or "").upper() for r in kp_rows]
    has_cpu = any("CPU" in c for c in cats)
    has_mem = any("MEM" in c or "内存" in c for c in cats)
    if not has_cpu:
        issues.append("方案缺少 CPU 实件，请补充处理器")
    if not has_mem:
        issues.append("方案缺少内存实件，请补充内存")

    req_low = (requirement_text or "").lower()
    series = str(plan.get("series") or "")
    # 厂商显式点名优先：海光/飞腾/鲲鹏/龙芯 ≠ Polaris（Polaris 只配兆芯），库内无对应机型即 blocked
    if _HYGON_RE.search(req_low) and series.upper() != "HYGON":
        _msg = "需求为海光平台，方案系列不匹配（库内无海光机型，兆芯不能替代）" if series.upper() != "POLARIS" \
            else "需求为海光平台，方案系列不匹配（Polaris 是兆芯，不能替代海光）"
        issues.append(_msg)
    elif _PHYTIUM_RE.search(req_low) and series.upper() != "PHYTIUM":
        issues.append("需求为飞腾平台，方案系列不匹配（库内无飞腾机型）")
    elif _KUNPENG_RE.search(req_low) and series.upper() != "KUNPENG":
        issues.append("需求为鲲鹏平台，方案系列不匹配（库内无鲲鹏机型）")
    elif _LOONGSON_RE.search(req_low) and series.upper() != "LOONGSON":
        issues.append("需求为龙芯平台，方案系列不匹配（库内无龙芯机型）")
    elif _ZHAOXIN_RE.search(req_low) and series.upper() != "POLARIS":
        issues.append("需求为兆芯平台，方案系列不匹配（应为 Polaris）")
    elif _XINCHUANG_RE.search(req_low) and series.upper() != "POLARIS":
        issues.append("需求为信创平台，方案系列不匹配（应为 Polaris）")
    elif _AMD_RE.search(req_low) and not re.search(r"orion|amd|epyc", series, re.I):
        issues.append("需求为 AMD 平台，方案系列不匹配（应为 Orion）")
    elif _INTEL_RE.search(req_low) and "INTEL" not in series.upper():
        issues.append("需求为 Intel 平台，方案系列不匹配")

    over = plan.get("over_budget")
    if over and over.get("ratio") and float(over["ratio"]) > budget_over_ratio:
        issues.append(f"超预算 {over.get('amount')}（{over['ratio']:.0%}），需降配或确认")

    return {
        "status": "blocked" if issues else "ok",
        "issues": issues[:2],
        "issue_count": len(issues),
        "checked_at": "review",
    }
