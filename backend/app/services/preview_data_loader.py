"""
预览数据加载服务

职责：
- 加载商机级数据（meta）
- 加载报价单级数据（quotation）
- 加载配置项明细（L6/KP/Warranty）—— 从 DB 的 opportunity_items 表
- 组装完整的预览数据源
"""
import json
from datetime import datetime
from typing import Optional
from app.repository.opportunity_repo import OpportunityRepository
from app.repository.quotation_repo import QuotationRepository
from app.repository.rules_repo import RulesRepository
from app.repository.system_config_repo import SystemConfigRepository


def load_preview_data(opportunity_id: str, quotation_id: Optional[str] = None, bindings: list = None) -> dict:
    """
    加载预览所需的全部数据
    
    Returns:
        {
            # 商机级字段
            "customer_name": "XX公司",
            "opportunity_name": "XX项目",
            ...
            
            # 报价单级字段
            "quotation_date": "2024-01-15",
            ...
            
            # 动态区域数据
            "l6_details": [
                {"part_name": "...", "qty": 1, "unit_price": 100, "final_price": 100, ...},
                ...
            ],
            "kp_details": [...],
            "config_summary": [
                {"cfg_name": "Config1", "unit_price": 50000, "description": "...", ...},
                ...
            ]
        }
    """
    opp_repo = OpportunityRepository()
    quote_repo = QuotationRepository()
    
    # 1. 加载商机数据
    opportunity = opp_repo.get_opportunity(opportunity_id)
    if not opportunity:
        raise ValueError(f"Opportunity not found: {opportunity_id}")
    
    # 直接使用 opportunity dict（已经是 to_dict() 的结果，包含所有字段）
    # 这样新增字段自动包含，不需要手动同步
    data = dict(opportunity)
    
    # 补充系统字段和占位字段
    data.update({
        "l6_spec": "",
        "business_person": opportunity.get("sales_person", ""),  # 别名
        "export_date": datetime.now().strftime("%Y-%m-%d"),
        "export_time": datetime.now().strftime("%H:%M"),
        "l6_count": 0,
        "kp_count": 0,
    })
    
    # 2. 加载报价单数据
    if quotation_id:
        quotation = quote_repo.get_by_id(quotation_id)
        if quotation:
            data["quotation_date"] = quotation.quotation_date or (quotation.created_at or "")[:10]
            data["version"] = quotation.version or ""
            data["l6_price"] = quotation.l6_price or 0
            data["total_price"] = quotation.total_price or 0
            data["profit_margin"] = quotation.profit_margin or 0
            # 暴露配置级字段供静态绑定使用（保留整个字典，按配置页取值）
            data["config_descriptions"] = quotation.config_descriptions or {}
            data["server_model"] = quotation.config_server_models or {}
            data["quantity"] = quotation.config_quantities or {}
            
            # 暴露维保描述（per-config，静态字段）
            config_warranty_info = quotation.config_warranty_info or {}
            
            # 获取系统默认值作为 fallback
            sys_repo = SystemConfigRepository()
            default_l6_desc = sys_repo.get_value("warranty_desc_l6", "")
            default_kp_desc = sys_repo.get_value("warranty_desc_kp", "")
            
            # 构建 warranty_desc_l6 和 warranty_desc_kp
            warranty_desc_l6 = {}
            warranty_desc_kp = {}
            
            # 从 config_warranty_info 获取值
            for cfg_name, warr in config_warranty_info.items():
                l6_desc = warr.get("l6", {}).get("description", "")
                kp_desc = warr.get("kp", {}).get("description", "")
                warranty_desc_l6[cfg_name] = l6_desc or default_l6_desc
                warranty_desc_kp[cfg_name] = kp_desc or default_kp_desc
            
            # 如果 config_warranty_info 为空，从其他配置字段获取配置名，用默认值填充
            if not warranty_desc_l6:
                all_config_names = set()
                all_config_names.update((quotation.config_descriptions or {}).keys())
                all_config_names.update((quotation.config_server_models or {}).keys())
                all_config_names.update((quotation.config_quantities or {}).keys())
                
                for cfg_name in all_config_names:
                    warranty_desc_l6[cfg_name] = default_l6_desc
                    warranty_desc_kp[cfg_name] = default_kp_desc
            
            data["warranty_desc_l6"] = warranty_desc_l6
            data["warranty_desc_kp"] = warranty_desc_kp
            
            # 从 DB 加载完整配置项明细（包含单价、数量、final_price 等）
            db_items = quote_repo.get_items(quotation_id)
            items = []
            for item in db_items:
                items.append({
                    "config_name": item.config_name or "Default",
                    "category": item.category or "",
                    "part_name": item.part_name or "",
                    "spec": item.spec or "",
                    "qty": item.qty or 0,
                    "base_price": item.base_price or 0.0,
                    "final_price": item.final_price or 0.0,
                    "profit_margin": item.profit_margin or 0.0,
                    "description": (quotation.config_descriptions or {}).get(item.config_name or "Default", ""),
                })
            _load_item_details(data, items, quotation, bindings)
    
    return data

def _load_l6_from_template(quotation):
    """从 quotation.extra_fields.config_l6_picks 读 L6 预览行——对齐左栏 BomTable 的渲染。

    两种来源：
    - bom_source=='excel'：从持久化的 bom_excel_rows 取 L6/整机 行（catalogue=part_name, desc=spec, qty）。
      与左栏同源，不依赖可变的 opportunity_items。老数据无快照则不加入 covered，
      交给 _load_item_details 的扁平回落（items 未污染，仍正确）。
    - live + 有 bom_template.rows：按模板 + bom_context 展开（catalogue=label, desc=ctx.desc, qty=ctx.qty）。
      无模板的 live cfg 不产出 L6 行（不显示机箱原版料）。

    行字段 key 与扁平料号行保持完全一致（part_name/spec/qty/config_name/...），
    这样 Univer 模板里的 binding（part_name→Catalogue 列、spec→Description 列、qty→Qty 列）无需改动。

    Returns:
        (rows_out, covered, excel_cfgs, l6_price_map, l6_margin_map):
          rows_out 是展开的 L6 行；
          covered 是已产出行的 cfg 名集合（模板行 / excel 快照）；
          excel_cfgs 是所有 bom_source=='excel' 的 cfg 名（含无快照老数据，供 _load_item_details 回落判断）；
          l6_price_map 是 {cfg_name: l6_custom_price}（L6 成本，新方案显式持久化）；
          l6_margin_map 是 {cfg_name: l6_profit_margin}（L6 利润率%，与成本配对算售价）。
    """
    if not quotation or not quotation.extra_fields:
        return [], set(), set(), {}, {}
    try:
        extra = json.loads(quotation.extra_fields)
    except (json.JSONDecodeError, TypeError):
        return [], set(), set()

    picks = extra.get("config_l6_picks") or {}
    rows_out = []
    covered = set()
    excel_cfgs = set()
    l6_price_map = {}
    l6_margin_map = {}
    for cfg_name, pick in picks.items():
        if not isinstance(pick, dict):
            continue
        if pick.get("l6_custom_price") is not None:
            l6_price_map[cfg_name] = pick.get("l6_custom_price") or 0
        if pick.get("l6_profit_margin") is not None:
            l6_margin_map[cfg_name] = pick.get("l6_profit_margin") or 0
        if pick.get("bom_source") == "excel":
            excel_cfgs.add(cfg_name)
            excel_rows = pick.get("bom_excel_rows") or []
            if excel_rows:
                for r in excel_rows:
                    if not isinstance(r, dict):
                        continue
                    if r.get("category") not in ("L6", "整机"):
                        continue
                    qty_val = r.get("qty", 0)
                    rows_out.append({
                        "config_name": cfg_name,
                        "category": r.get("category") or "L6",
                        "part_name": r.get("part_name", "") or "",
                        "spec": r.get("spec", "") or "",
                        "qty": 0 if qty_val is None else qty_val,
                        "base_price": r.get("base_price", 0) or 0,
                        "final_price": r.get("final_price", 0) or 0,
                        "unit_price": r.get("final_price", 0) or 0,
                        "profit_margin": r.get("profit_margin", 0) or 0,
                        "description": "",
                        "item_no": 0,
                    })
                covered.add(cfg_name)
            continue
        tpl = pick.get("bom_template") or {}
        rows = tpl.get("rows") if isinstance(tpl, dict) else None
        if not rows:
            continue
        ctx = pick.get("bom_context") or {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            key = r.get("slot") or r.get("type")
            v = ctx.get(key, {}) if isinstance(ctx, dict) else {}
            v = v if isinstance(v, dict) else {}
            qty_val = v.get("qty", "")
            rows_out.append({
                "config_name": cfg_name,
                "category": "L6",
                "part_name": r.get("label", "") or "",
                "spec": v.get("desc", "") or "",
                "qty": "" if qty_val is None else qty_val,
                "base_price": 0,
                "final_price": 0,
                "unit_price": 0,
                "profit_margin": 0,
                "description": "",
                "item_no": 0,
            })
        covered.add(cfg_name)
    return rows_out, covered, excel_cfgs, l6_price_map, l6_margin_map


def _load_item_details(data: dict, items: list, quotation=None, bindings=None):
    """加载配置项明细到 data"""
    l6_items = []
    kp_items = []

    # L6 优先按基准配置绑定的 BOM 模板 / excel 快照展开（对齐左栏 BomTable）；
    # 已被覆盖的 cfg 不再走扁平料号行。
    # 无模板 live cfg 不收集机箱原版料；excel 无快照老数据（未 covered 但 in excel_cfgs）允许扁平回落。
    tpl_l6_rows, covered_cfgs, excel_cfgs, l6_price_map, l6_margin_map = _load_l6_from_template(quotation)

    for idx, item in enumerate(items):
        # 统一字段名：unit_price = final_price（兼容前端显示）
        item_with_no = {
            **item,
            "item_no": item.get("item_no", idx + 1),
            "unit_price": item.get("final_price", 0),
        }
        category = item.get("category", "")
        cfg_name = item.get("config_name", "")

        if category == "L6":
            # excel 无快照老数据回落扁平；其余未覆盖情况（live 无模板）不显机箱料
            if cfg_name not in covered_cfgs and cfg_name in excel_cfgs:
                l6_items.append(item_with_no)
        elif category == "Key Parts":
            kp_items.append(item_with_no)

    l6_items = tpl_l6_rows + l6_items
    data["l6_details"] = l6_items
    data["kp_details"] = kp_items
    data["all_items"] = items
    data["l6_count"] = len(l6_items)
    data["kp_count"] = len(kp_items)
    
    # 从 bindings 中提取 config_summary 的 selectedParts
    selected_parts = None
    if bindings:
        for binding in bindings:
            if binding.get("fieldKey") == "config_summary" and binding.get("selectedParts"):
                selected_parts = binding["selectedParts"]
                break
    
    # 🔧 修复：从 config_descriptions/config_server_models/config_quantities 收集所有配置名
    # 确保即使没有 items 的配置也能出现在导出预览中
    all_config_names = set()
    if quotation:
        all_config_names.update((quotation.config_descriptions or {}).keys())
        all_config_names.update((quotation.config_server_models or {}).keys())
        all_config_names.update((quotation.config_quantities or {}).keys())
    
    # 构建 config_groups（每个配置一行）
    config_groups = {}
    for item in items:
        cfg_name = item.get("config_name", "Default")
        # 过滤掉 "Default" 配置，只处理有效配置
        if cfg_name == "Default":
            continue
        # 标准化 config_name（去除首尾空格，统一转大写用于去重）
        cfg_key = cfg_name.strip().upper()
        if cfg_key not in config_groups:
            config_groups[cfg_key] = {"name": cfg_name, "items": []}
        config_groups[cfg_key]["items"].append(item)
    
    # 确保所有配置名都在 config_groups 中（即使没有 items）
    for cfg_name in all_config_names:
        if cfg_name == "Default":
            continue
        cfg_key = cfg_name.strip().upper()
        if cfg_key not in config_groups:
            config_groups[cfg_key] = {"name": cfg_name, "items": []}
    
    # 从 quotation 获取每个配置的独立数量和服务器型号
    config_quantities = {}
    config_server_models = {}
    if quotation:
        config_quantities = quotation.config_quantities or {}
        config_server_models = quotation.config_server_models or {}
    
    config_summary = []
    seq = 1
    for cfg_key, group in config_groups.items():
        cfg_name = group["name"]
        cfg_items = group["items"]
        # 计算 unit_price = L6 + KP + Warranty（售价口径：final_price × qty）
        # L6 售价 = l6_custom_price(成本) × (1 + l6_profit_margin/100)，与原 items L6 行 final_price 一致；
        # 老数据（无持久化价格）回落 items L6 行 final_price 求和。
        if cfg_name in l6_price_map:
            cost = float(l6_price_map.get(cfg_name) or 0)
            margin = float(l6_margin_map.get(cfg_name) or 0)
            l6_sum = cost * (1 + margin / 100)
        elif cfg_name in excel_cfgs:
            # excel 模式 L6 仅参考，不参与算价
            l6_sum = 0
        else:
            l6_sum = sum(
                (i.get("final_price", 0) or 0) * (i.get("qty", 1) or 1)
                for i in cfg_items if i.get("category") == "L6"
            )
        kp_sum = sum(
            (i.get("final_price", 0) or 0) * (i.get("qty", 1) or 1)
            for i in cfg_items if i.get("category") == "Key Parts"
        )
        warranty_sum = sum(
            (i.get("final_price", 0) or 0) * (i.get("qty", 1) or 1)
            for i in cfg_items if i.get("category") == "Warranty"
        )
        unit_price = l6_sum + kp_sum + warranty_sum
        
        # 提取 server_model（从 quotation.config_server_models）
        server_model = config_server_models.get(cfg_name, "")
        
        # 获取该配置的独立数量（从 quotation.config_quantities）
        qty = config_quantities.get(cfg_name, data.get("total_qty", 0))
        
        # 生成描述：始终使用 selectedParts 动态生成（CPU/GPU 等）
        # 如果 selected_parts 为空，不显示任何内容
        description = _build_description(cfg_items, selected_parts) if cfg_items else ""
        
        config_summary.append({
            "seq": seq,
            "config_name": cfg_name,
            "server_model": server_model,
            "description": description,
            "desc": description,
            "unit_price": round(unit_price, 2),
            "qty": qty,
            "quantity": qty,  # alias
            "total_price": round(unit_price * qty, 2),
        })
        seq += 1
    
    data["config_summary"] = config_summary


def _build_description(cfg_items: list, selected_parts: list = None, separator: str = ",") -> str:
    """
    根据配置项和选择的部件类型生成描述
    
    selected_parts: 用户选择的部件类型列表（如 ['cpu', 'gpu', 'memory']）
    如果 selected_parts 为空，则不显示任何部件
    """
    if not cfg_items:
        return ""
    
    # 如果没有选择任何部件类型，返回空字符串
    if not selected_parts:
        return ""
    
    # 部件类型关键词映射 - 从 DB 读取
    rules_repo = RulesRepository()
    type_keywords = rules_repo.get_type_keywords()
    
    if not type_keywords:
        # 数据库未配置关键词映射，返回空描述
        return ""
    
    # 描述只汇总 Key Parts（CPU/GPU/Memory/Disk 等关键配件）；L6 机箱级料号不参与——
    # 否则 'cpu' 关键词会把 L6 的 "CPU Heatsink" 误匹配为 CPU，显示成散热器 PN（如 S.E.M.0000189 × 2）。
    # Key Parts 在 items 里排在 L6 之后，全集遍历会先命中散热器，故必须限定类别。
    search_pool = [it for it in cfg_items if it.get("category") == "Key Parts"]

    parts = []

    # 按用户选择的部件类型筛选
    for part_type in selected_parts:
        keywords = type_keywords.get(part_type.lower(), [part_type])

        # 查找匹配的部件
        for item in search_pool:
            part_name = str(item.get("part_name", "") or "").lower()
            spec = str(item.get("spec", "") or "").lower()
            
            # 检查是否匹配
            if any(kw in part_name or kw in spec for kw in keywords):
                # 优先使用 spec（实际型号），fallback 到 part_name
                display = item.get("spec", "") or item.get("part_name", "")
                qty = item.get("quantity", 0) or item.get("qty", 0) or 0
                
                if display:
                    if qty > 1:
                        parts.append(f"{display} × {qty}")
                    else:
                        parts.append(f"{display}")
                break  # 每个类型只取第一个匹配
    
    return separator.join(parts)
