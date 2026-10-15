"""产出物分享服务 — 网盘式分享的渲染与令牌逻辑。

三个出口一个组件：
- quote：走导出模板管线（load_preview_data + fill_snapshot），视角=敏感列揭示组合
  （scheme=无价格列 / cost=只显成本 / internal=留位清值；customer 一期锁定——等效外发，
  二期开放时创建须过 ensure_outbound_approved）。
- cost / scheme：configs JSON 是同构的 PortalSheetConfig（l6_rows+kp_rows），
  系统标准格式直出（openpyxl：数值+基本列宽，首版不追模板样式）。
- 分享文件落 storage 并归档商机附件桶（kind=export），链接=免登录 token 下载。
"""
import io
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Optional

from fastapi import HTTPException
from openpyxl import Workbook

from app.repository.dynamic_source_field_repo import DynamicSourceFieldRepository
from app.repository.flow_repo import FlowRepository
from app.repository.quotation_repo import QuotationRepository
from app.repository.univer_template_repo import UniverTemplateRepo
from app.services.preview_data_loader import load_preview_data
from app.services.template_filler import fill_snapshot

# 视角 → (揭示分组, 被掩蔽分组的处理模式)。customer 一期锁定。
VIEWS: dict = {
    "scheme": {"effective": set(), "modes": {"sell": "hide", "cost": "hide", "margin": "hide"}},
    "cost": {"effective": {"cost"}, "modes": {"sell": "hide", "margin": "hide"}},
    "internal": {"effective": set(), "modes": {"sell": "blank", "cost": "blank", "margin": "blank"}},
    "customer": {"effective": {"sell"}, "modes": {"cost": "hide", "margin": "hide"}},
}
# source_type → 附件归档桶（商机档案分类）
SOURCE_CATEGORY = {"quote": "sent_quote", "cost": "requirement", "scheme": "technical"}
SOURCE_TITLES = {"quote": "报价单", "cost": "成本表", "scheme": "方案表"}


def masked_fields_for(view: str) -> tuple:
    """按视角算敏感列掩蔽表（结构对齐 univer_templates._resolve_masked_fields，模式由视角决定）。"""
    conf = VIEWS.get(view) or VIEWS["internal"]
    effective, modes = conf["effective"], conf["modes"]
    masked: dict = {}
    region_fields: dict = {}
    repo = DynamicSourceFieldRepository()
    try:
        for f in repo.list_all():
            if f.get("scope") == "region":
                region_fields.setdefault(f["source_key"], set()).add(f["field_key"])
            group = f.get("sens_group")
            if group and group not in effective:
                masked.setdefault(f["source_key"], {})[f["field_key"]] = modes.get(group, "hide")
    finally:
        repo.close()
    return masked, region_fields


def _default_template_row(tpl_repo):
    """默认模板 = get_default() 优先，否则第一条。"""
    row = tpl_repo.get_default()
    if row:
        return row
    rows = tpl_repo.list()
    return rows[0] if rows else None


def _load_configs(source_type: str, opportunity_id: str, source_id: str) -> tuple:
    """读方案/成本表的 configs JSON，返回 (title, configs list)。"""
    flow_repo = FlowRepository()
    try:
        if source_type == "scheme":
            row = flow_repo.get_bom_scheme(opportunity_id, int(source_id))
        else:
            row = flow_repo.get_cost_sheet(opportunity_id, int(source_id))
    finally:
        flow_repo.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"{SOURCE_TITLES.get(source_type, '产出物')}不存在")
    return row.get("name") or "", row.get("configs") or []


def quasi_source_from_configs(configs: list, name: str) -> tuple:
    """方案/成本表 configs（PortalSheetConfig 同构）→ 形状同构 Quotation 的投影。

    L6 = 配置级一口价（l6_cost × (1+l6_margin/100)），走 live 模板路径展开明细行
    （bom_template.rows 单行，label=机型）；KP 行直通 Key Parts。这样三个节点共用
    同一条模板渲染管线，视角（敏感列揭示）天然同权生效。"""
    picks: dict = {}
    items: list = []
    for cfg in configs or []:
        cfg_name = cfg.get("name") or "Default"
        picks[cfg_name] = {
            "l6_custom_price": float(cfg.get("l6_cost") or 0),
            "l6_profit_margin": float(cfg.get("l6_margin") or 0),
            "bom_source": "live",
            "bom_template": {"rows": [{
                "slot": "l6", "type": "l6",
                "label": cfg.get("server_model") or "整机",
            }]},
            "bom_context": {"l6": {"desc": cfg.get("description") or "", "qty": 1}},
        }
        for r in cfg.get("kp_rows") or []:
            items.append({
                "config_name": cfg_name,
                "category": "Key Parts",
                "catalogue": r.get("catalogue") or "",
                "description": r.get("description") or "",
                "part_category": r.get("part_category") or "",
                "qty": r.get("qty") or 0,
                "base_price": r.get("base_price") or "",
                "final_price": r.get("final_price") or "",
                "profit_margin": r.get("profit_margin") or "",
                "currency": r.get("currency") or "RMB",
            })
    source = SimpleNamespace(
        quotation_date="", version="", created_at="",
        l6_price=0, total_price=0, profit_margin=0,
        config_relation="compose", primary_config="",
        config_descriptions={},
        config_server_models={(c.get("name") or ""): (c.get("server_model") or "") for c in (configs or [])},
        config_quantities={(c.get("name") or ""): (c.get("qty") or 1) for c in (configs or [])},
        config_warranty_info={},
        extra_fields=json.dumps({"config_l6_picks": picks}, ensure_ascii=False),
    )
    return source, items


def render_entity_snapshot(opportunity_id: str, source_type: str, source_id: str,
                           view: str, template_id: Optional[int] = None) -> tuple:
    """统一模板管线渲染（三节点同一条路），返回 (snapshot, title, filename)。"""
    masked, region_fields = masked_fields_for(view)
    tpl_repo = UniverTemplateRepo()
    template = tpl_repo.get_by_id(template_id) if template_id else _default_template_row(tpl_repo)
    if not template:
        raise HTTPException(status_code=404, detail="未找到可用的导出模板，请先在 设置→导出模板 创建")

    if source_type == "quote":
        repo = QuotationRepository()
        try:
            q = repo.get_by_id(str(source_id))
        finally:
            repo.close()
        if not q or q.opportunity_id != opportunity_id:
            raise HTTPException(status_code=404, detail="报价单不存在或不属于该商机")
        title = q.quotation_name or f"报价单v{q.version}"
        data = load_preview_data(opportunity_id, str(source_id))
    else:
        title, configs = _load_configs(source_type, opportunity_id, str(source_id))
        source, items = quasi_source_from_configs(configs, title)
        data = load_preview_data(opportunity_id, None, source=source, source_items=items)

    filled = fill_snapshot(
        template["workbook_snapshot"], template["bindings"], data,
        template.get("sheet_config", {}), masked_fields=masked, region_fields=region_fields)
    filename = f"{title}_{view_label(view)}.xlsx"
    return filled, title, filename


def grid_to_xlsx(grid: list) -> bytes:
    """网格 → xlsx 字节（数值+基本列宽；首版不追模板样式）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for row in grid:
        ws.append(row)
    # 基本列宽：按各列前 40 行的最长内容估
    width_by_col: dict = {}
    for row in grid[:40]:
        for i, v in enumerate(row):
            ln = len(str(v)) if v is not None else 0
            width_by_col[i] = max(width_by_col.get(i, 8), min(ln + 2, 42))
    for i, w in width_by_col.items():
        ws.column_dimensions[ws.cell(row=1, column=i + 1).column_letter].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_share_file(opportunity_id: str, source_type: str, source_id: str,
                     view: str, template_id: Optional[int] = None) -> tuple:
    """渲染并产出 (xlsx bytes, filename)——三节点同一模板管线。"""
    snapshot, _title, filename = render_entity_snapshot(
        opportunity_id, source_type, str(source_id), view, template_id)
    return grid_to_xlsx(snapshot_to_grid(snapshot)), filename


def view_label(view: str) -> str:
    return {"scheme": "方案", "cost": "成本", "internal": "内部", "customer": "报价"}.get(view, view)


def snapshot_to_grid(snapshot: dict) -> list:
    """Univer snapshot → 简单网格（取主 sheet 的单元格值；首版导出不追样式/公式）。"""
    sheets = (snapshot or {}).get("sheets") or {}
    grid: list = []
    for sheet in sheets.values():
        cell_data = (sheet or {}).get("cellData") or {}
        max_row = 0
        raw: dict = {}
        for r_str, cols in cell_data.items():
            try:
                r = int(r_str)
            except ValueError:
                continue
            max_row = max(max_row, r)
            for c_str, cell in (cols or {}).items():
                try:
                    c = int(c_str)
                except ValueError:
                    continue
                v = cell.get("v") if isinstance(cell, dict) else None
                if v is not None:
                    raw[(r, c)] = v
        if not raw:
            continue
        max_col = max(c for (_, c) in raw.keys())
        grid = [[] for _ in range(max_row + 1)]
        for r in range(max_row + 1):
            grid[r] = [raw.get((r, c), "") for c in range(max_col + 1)]
        break  # 主 sheet 即可（首版）
    if not grid:
        grid = [["（空）"]]
    return grid


def expiry_from_days(days: int) -> str:
    return (datetime.now() + timedelta(days=max(1, min(int(days or 7), 90)))).isoformat()


def resolve_share(token: str, code: Optional[str]) -> dict:
    """免登录取分享：校验过期/撤销/提取码。返回 token 行 dict，否则抛 4xx。"""
    from app.models.artifact_share import ArtifactShareToken
    from app.models.base import Opportunity_SessionLocal
    from sqlalchemy import select
    with Opportunity_SessionLocal() as session:
        row = session.execute(
            select(ArtifactShareToken).where(ArtifactShareToken.token == token)
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="分享不存在或已失效")
        if row.revoked_at:
            raise HTTPException(status_code=410, detail="该分享已被撤销")
        if row.expires_at:
            try:
                if datetime.now() > datetime.fromisoformat(row.expires_at):
                    raise HTTPException(status_code=410, detail="分享链接已过期")
            except ValueError:
                pass
        if row.extract_code and (code or "").strip() != row.extract_code:
            raise HTTPException(status_code=403, detail="提取码不正确")
        row.download_count = (row.download_count or 0) + 1
        row.last_download_at = datetime.now().isoformat()
        session.commit()
        return row.to_dict()
