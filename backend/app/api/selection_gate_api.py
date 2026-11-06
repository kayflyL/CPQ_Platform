"""选型配置引擎 resolve 端点(/api/selection-gate)。

匿名只读可达(get_optional_user,公开向导需要);**响应零价格**——候选目录取数后剥价,
价格面照旧走 price_ok 门控的其他端点。规则编辑权照旧收 page.strategies(compatibility-rules)。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.api.deps import get_optional_user
from app.repository.base_config_repo import BaseConfigRepository
from app.repository.compatibility_rule_repo import CompatibilityRuleRepository
from app.services.part_specs import kp_repository
from app.services.selection_gate import build_context, fired_rule_ids, resolve

router = APIRouter(prefix="/api/selection-gate", tags=["selection-gate"],
                   dependencies=[Depends(get_optional_user)])


def _strip_price(row: dict) -> dict:
    """候选目录行剥价(匿名端点零价格);只留引擎判定与展示需要的字段。"""
    return {"id": row.get("id"), "model": row.get("model") or "",
            "brand": row.get("brand") or "", "category": row.get("category") or "",
            "applicable": row.get("applicable"),
            "specs": row.get("specs") or {}}


def _load_compat_by_part() -> dict:
    """kp.kp_part_compat 展开:{part_id: [server_model…]}(机型级适配,平台判定优先层)。"""
    out: dict = {}
    repo = kp_repository()
    try:
        rows = repo.session.execute(
            text("SELECT part_id, server_model FROM kp.kp_part_compat")).all()
        for pid, sm in rows:
            if pid is not None and sm:
                out.setdefault(int(pid), []).append(str(sm))
        return out
    finally:
        repo.close()


def _load_candidates() -> dict:
    """全类目候选目录(剥价)。223 件 × 全类目,单进程内 <1s,不做缓存。"""
    repo = kp_repository()
    try:
        cats = [c.get("category") for c in repo.get_categories() if c.get("category")]
        out = {}
        for cat in cats:
            out[cat] = [_strip_price(r) for r in repo.get_by_category_with_specs(cat)]
        return out
    finally:
        repo.close()


@router.post("/resolve")
def resolve_selection(data: dict):
    """resolve 协议:入参 {base_config_id, parts:[{category,pn,name,qty,id?,specs?}],
    options? (默认 true 出候选过滤), trace? (默认 false);出参见 selection_gate.resolve。"""
    base_config_id = data.get("base_config_id")
    parts_in = data.get("parts") or []
    want_options = data.get("options", True)
    want_trace = bool(data.get("trace"))

    cfg_repo = BaseConfigRepository()
    model_row = cfg_repo.get(base_config_id) if base_config_id else None
    if base_config_id and not model_row:
        raise HTTPException(404, f"base_config {base_config_id} not found")

    selected: dict = {}
    for p in parts_in:
        if not isinstance(p, dict):
            continue
        cat = str(p.get("category") or "").strip()
        if not cat:
            continue
        selected.setdefault(cat, []).append({
            "pn": p.get("pn") or "", "name": p.get("name") or "",
            "qty": p.get("qty") or 1, "id": p.get("id"), "specs": p.get("specs") or {},
        })

    compat = _load_compat_by_part() if (model_row and (model_row.get("series") or model_row.get("model"))) else {}
    candidates = _load_candidates() if want_options else {}
    # id→目录行映射:已选件平台校验(_selected_platform_violations)需要 applicable,选项不必开
    catalog_by_id = {}
    if model_row:
        try:
            for rows in (candidates.values() if candidates else []):
                for row in rows:
                    if row.get("id") is not None:
                        catalog_by_id[row["id"]] = {"applicable": row.get("applicable")}
        except Exception:
            catalog_by_id = {}

    ctx = build_context(model_row, selected, candidates=candidates, compat_by_part=compat,
                        opportunity=data.get("opportunity") or {})
    ctx["catalog_by_id"] = catalog_by_id

    rule_repo = CompatibilityRuleRepository()
    try:
        rules = rule_repo.list(status="active", domain="selection")
        result = resolve(rules, ctx, with_trace=want_trace)
        try:
            rule_repo.record_hits(fired_rule_ids(rules, ctx))
        except Exception:
            pass  # 命中计数失败不影响判定输出(降级纪律)
        return result
    finally:
        rule_repo.close()
