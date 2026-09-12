"""目标层插头解释器（kind 注册表）— 2026-09-06 通电改造。

插头 = 节点配置 target.artifacts[]（DB 唯一权威）；插座 = 节点机制（本模块 + 消费方）。
机制只认注册表不认具体 kind：换插头（table→document→image）= 注册新解释器三件套，
节点机制零改动（铁律⑤"换目标层不碰代码生效"的验收口径）。

通电消费方：
  ① steps_payload → 节点插件的 artifact_contract(art)：输出契约注入大脑 sys_prompt
     （改抽屉列定义 → 下一轮大脑收到的契约文本跟着变）
  ② skill_plan_runtime → shape_rows(art, rows)：产物行整形
     （from/fallback 抽值 + visible 列过滤；行键不再硬编码）
  ③ 下游渲染按 artifact.columns/kind（columns 随事件下行，已有）
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 白盒状态键：随行透传给前端做 ⚠️ 标记，不参与列契约
STATUS_KEYS = ("unmatched", "unmatched_reason", "spec_mismatch", "row", "part_id", "waived")


def target_artifacts(node_cfg: dict | None) -> list[dict]:
    """节点配置 → 输出物描述符列表。

    注意：不是每个节点的 `target` 都是插头字典——交付节点（output）的 target 是
    下游产物引用字符串（如 'bom_scheme'）。非字典即「没有插头」，返回空表，不抛错。
    """
    cfg = node_cfg if isinstance(node_cfg, dict) else {}
    target = cfg.get("target")
    arts = target.get("artifacts") if isinstance(target, dict) else None
    return [a for a in (arts or []) if isinstance(a, dict)]


def first_artifact(node_cfg: dict | None) -> dict:
    """节点配置 → 第一个输出物描述符（无配置返回空 dict，消费方自行兜底）。"""
    arts = target_artifacts(node_cfg)
    return arts[0] if arts else {}


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


def format_requirement_slots_contract(art: dict) -> str:
    """线索登记表插头（slot=requirement_slots）→ 大脑可读的**登记契约**。

    契约只描述「这张表长什么样、有哪些合法值」——全部读配置与数据：
    字段契约（system_config.requirement_slots，与商机详情页表单同源）、目录字段值域
    （在售目录）、部件大类（KP 类目）。**填写规则/话术属于抽屉 description**（节点使命），
    不在这里二次复述（历史事故：契约与节点说明各写一套规则，改一处漏一处）。
    """
    spec: list = []
    try:
        from app.services.slot_contract import slot_spec
        spec = [s for s in slot_spec() if str(s.get("key") or "").strip()]
    except Exception:
        logger.exception("读取登记表字段契约失败")
    kp_cats: list = []
    try:
        from app.services.requirement_slots import _load_kp_categories
        kp_cats = [str(c).strip() for c in (_load_kp_categories() or []) if str(c).strip()]
    except Exception:
        logger.exception("读取 KP 大类失败")
    if not spec:
        return format_generic_contract(art)
    basic = [f"{str(s.get('key'))}({str(s.get('label') or s.get('key'))})"
             for s in spec if s.get("src_type") != "kp"]
    vocab_lines: list = []
    try:
        from app.services.catalog_options import catalog_whitelist
        wl = catalog_whitelist({}, {}, "")
        for s in spec:
            key = str(s.get("key") or "")
            if s.get("src_type") == "kp" or s.get("candidate_source") != "catalog":
                continue
            dim = str(s.get("catalog_dimension") or "").strip()
            vals = [str(v) for v in (wl.get(dim) or []) if str(v).strip()]
            if vals:
                vocab_lines.append(f"{key}({str(s.get('label') or key)})：{' / '.join(vals)}")
    except Exception:
        logger.exception("读取目录词表失败")
    head = (f"输出物《{str(art.get('name') or '线索登记表')}》(requirement_slots) 字段契约："
            + "；".join(basic) + "。")
    parts = [head]
    if vocab_lines:
        parts.append("目录字段值域（按规范值登记）：\n" + "\n".join(vocab_lines))
    if kp_cats:
        parts.append("部件大类（kp_rows 的 part_category 取这里的值）：" + " / ".join(kp_cats))
    return "\n".join(parts)


def format_generic_contract(art: dict) -> str:
    """未知 kind 的通用契约（注册表未覆盖时白盒降级，不静默装懂）。"""
    return (f"输出物《{art.get('name') or ''}》kind={art.get('kind')} "
            f"(rows_from={art.get('rows_from') or ''})——该 kind 暂无结构化契约解释器，"
            "按节点任务说明输出。")


def broken_column_specs(art: dict) -> list[str]:
    """列契约自检：key 缺失/重复（针脚定义本身坏了）。返回问题列 key 列表。"""
    seen: set = set()
    bad: list = []
    for c in (art.get("columns") or []):
        if not isinstance(c, dict):
            bad.append("")
            continue
        k = str(c.get("key") or "").strip()
        if not k or k in seen:
            bad.append(k)
            continue
        seen.add(k)
    return bad


def unresolved_columns(art: dict, sample_row: dict) -> list[str]:
    """边沿一致性：列契约的 from/fallback 链在真实行数据上必须取得出值。

    下游插头声明的列必须对得上上游产物的行结构（字段唯一权威 = 真实业务表 schema）；
    取不到值的列（列名对不上 / 上游改了字段名）在这里判红，不等到渲染时静默空列。
    返回未解析的列 key（空列表 = 一致）。
    """
    bad: list = []
    for c in visible_columns(art):
        key = str(c.get("key") or "").strip()
        if not key:
            continue
        if not _non_empty(_cell(sample_row or {}, c)):
            bad.append(key)
    return bad


def validate_artifact(art: dict, sample_row: dict) -> dict:
    """节点插头 × 真实行数据的边沿校验（供单测/装配前自检）。"""
    broken = broken_column_specs(art)
    unresolved = unresolved_columns(art, sample_row)
    return {"ok": not broken and not unresolved,
            "broken_columns": broken, "unresolved_columns": unresolved}


# 产物槽注册表：新增插头类型 = 注册一对解释器，机制不认具体 slot
_CONTRACT_FORMATTERS = {
    "table": format_table_contract,
    "sheet_section": format_table_contract,  # 兼容现有描述符 kind
    "requirement_slots": format_requirement_slots_contract,
}
_ROW_SHAPERS = {
    "table": shape_table_rows,
    "sheet_section": shape_table_rows,
}


def format_contract(art: dict) -> str:
    """插头 → 输出契约文本：先认 slot（装什么），再认 kind（怎么显示）。

    slot 是产物槽（换插头换的是它）；kind 是渲染类型，沿用既有的 table 解释器，
    所以只声明渲染类型的节点（如机型 L6 表）行为不变。
    """
    if not art:
        return ""
    for probe in (art.get("slot"), art.get("kind")):
        fmt = _CONTRACT_FORMATTERS.get(str(probe or ""))
        if fmt is not None:
            return fmt(art)
    return format_generic_contract(art)


def shape_rows(art: dict, rows: list, extra_keys: tuple = ()) -> list[dict]:
    if not art:
        return [r for r in (rows or []) if isinstance(r, dict)]
    shaper = _ROW_SHAPERS.get(str(art.get("kind") or ""))
    if shaper is None:
        return [r for r in (rows or []) if isinstance(r, dict)]
    return shaper(art, rows, extra_keys)
