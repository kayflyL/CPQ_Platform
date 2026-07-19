"""
预览数据加载服务

职责：
- 加载商机级数据（meta）
- 加载报价单级数据（quotation）
- 加载配置项明细（L6/KP/Warranty）—— 从 DB 的 opportunity_items 表
- 组装完整的预览数据源
"""
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

def _load_item_details(data: dict, items: list, quotation=None, bindings=None):
    """加载配置项明细到 data"""
    l6_items = []
    kp_items = []
    
    for idx, item in enumerate(items):
        # 统一字段名：unit_price = final_price（兼容前端显示）
        item_with_no = {
            **item,
            "item_no": item.get("item_no", idx + 1),
            "unit_price": item.get("final_price", 0),
        }
        category = item.get("category", "")
        
        if category == "L6":
            l6_items.append(item_with_no)
        elif category == "Key Parts":
            kp_items.append(item_with_no)
    
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
        # 计算 unit_price = L6 + KP + Warranty (final_price × qty)
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
    
    parts = []
    
    # 按用户选择的部件类型筛选
    for part_type in selected_parts:
        keywords = type_keywords.get(part_type.lower(), [part_type])
        
        # 查找匹配的部件
        for item in cfg_items:
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
