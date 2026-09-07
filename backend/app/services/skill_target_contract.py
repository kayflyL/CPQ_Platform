"""目标层插头解释器（kind 注册表）— 2026-09-06 通电改造。

插头 = 节点配置 target.artifacts[]（DB 唯一权威）；插座 = 节点机制（本模块 + 消费方）。
机制只认注册表不认具体 kind：换插头（table→document→image）= 注册新解释器三件套，
节点机制零改动（铁律⑤"换目标层不碰代码生效"的验收口径）。

通电消费方：
  ① make_agent_brain / make_agent_brain → format_contract(art)：输出契约注入大脑 sys_prompt
     （改抽屉列定义 → 下一轮大脑收到的契约文本跟着变）
  ② skill_plan_runtime → shape_rows(art, rows)：产物行整形
     （from/fallback 抽值 + visible 列过滤；行键不再硬编码）
  ③ 下游渲染按 artifact.columns/kind（columns 随事件下行，已有）
"""
from __future__ import annotations

from typing import Any

# 白盒状态键：随行透传给前端做 ⚠️ 标记，不参与列契约
STATUS_KEYS = ("unmatched", "unmatched_reason", "spec_mismatch", "row", "part_id")


def first_artifact(node_cfg: dict | None) -> dict:
    """节点配置 → 第一个输出物描述符（无配置返回空 dict，消费方自行兜底）。"""
    cfg = node_cfg if isinstance(node_cfg, dict) else {}
    arts = ((cfg.get("target") or {}).get("artifacts") or [])
    return arts[0] if arts and isinstance(arts[0], dict) else {}


def visible_columns(art: dict) -> list[dict]:
    cols = [c for c in (art.get("columns") or []) if isinstance(c, dict)]
    return [c for c in cols if c.get("visible", True)]


def _non_empty(v: Any) -> bool:
    return v is not None and str(v).strip() != ""


def _dig(row: dict, path: str) -> Any:
    """点分路径取值：'name' / 'specs.Capacity'。"""
    cur: Any = row
    for seg in str(path or "").strip().split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(seg)
    return cur


def _cell(row: dict, col: dict) -> Any:
    """按列契约取单元格：from 主字段，空则走 fallback 链（'|' 分隔；纯数字字面量兜底）。"""
    val = _dig(row, col.get("from") or col.get("key") or "")
    if _non_empty(val):
        return val
    for fb in str(col.get("fallback") or "").split("|"):
        fb = fb.strip()
        if not fb:
            continue
        if fb.isdigit():
            return int(fb)
        val = _dig(row, fb)
        if _non_empty(val):
            return val
    return ""


def shape_table_rows(art: dict, rows: list, extra_keys: tuple = ()) -> list[dict]:
    """行数据按列契约整形：键=描述符列 key（visible 过滤），值=from/fallback 抽值。

    extra_keys（如白盒状态键）原样随行透传，供前端 ⚠️ 标记——列契约管形状，
    状态键管白盒，两者分离。
    """
    cols = visible_columns(art)
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        shaped = {str(c.get("key") or ""): _cell(r, c) for c in cols}
        for k in extra_keys:
            if k in r:
                shaped[k] = r[k]
        out.append(shaped)
    return out


def format_table_contract(art: dict) -> str:
    """table 插头 → 大脑可读的输出契约文本（改抽屉列定义，这里跟着变）。"""
    cols = visible_columns(art)
    if not cols:
        return ""
    parts = []
    for c in cols:
        label = str(c.get("label") or c.get("key") or "")
        src = str(c.get("from") or c.get("key") or "")
        fbs = [x.strip() for x in str(c.get("fallback") or "").split("|") if x.strip()]
        cell = f"{label} ← 行数据 {src}" + (f"（缺则依次取 {' / '.join(fbs)}）" if fbs else "")
        parts.append(cell)
    rows_from = str(art.get("rows_from") or "").strip()
    text = "输出物《" + str(art.get("name") or "表格") + "》(table) 列契约：" + "；".join(parts) + "。"
    if rows_from:
        text += f" 行来源声明：{rows_from}（引擎供给行数据，你只负责按契约选型/落值）。"
    return text


def format_generic_contract(art: dict) -> str:
    """未知 kind 的通用契约（注册表未覆盖时白盒降级，不静默装懂）。"""
    return (f"输出物《{art.get('name') or ''}》kind={art.get('kind')} "
            f"(rows_from={art.get('rows_from') or ''})——该 kind 暂无结构化契约解释器，"
            "按节点任务说明输出。")


# kind 注册表：新增插头类型 = 注册一对解释器，机制不认具体 kind
_CONTRACT_FORMATTERS = {
    "table": format_table_contract,
    "sheet_section": format_table_contract,  # 兼容现有描述符 kind
}
_ROW_SHAPERS = {
    "table": shape_table_rows,
    "sheet_section": shape_table_rows,
}


def format_contract(art: dict) -> str:
    if not art:
        return ""
    fmt = _CONTRACT_FORMATTERS.get(str(art.get("kind") or ""))
    return (fmt or format_generic_contract)(art)


def shape_rows(art: dict, rows: list, extra_keys: tuple = ()) -> list[dict]:
    if not art:
        return [r for r in (rows or []) if isinstance(r, dict)]
    shaper = _ROW_SHAPERS.get(str(art.get("kind") or ""))
    if shaper is None:
        return [r for r in (rows or []) if isinstance(r, dict)]
    return shaper(art, rows, extra_keys)
