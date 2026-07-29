"""
预览数据加载服务

职责：
- 加载商机级数据（meta）
- 加载报价单级数据（quotation）
- 加载配置项明细（L6/KP/Warranty）—— 从 DB 的 quotation_items 表
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
            ...
            
            # 报价单级字段
            "quotation_date": "2024-01-15",
            ...
            
            # 动态区域数据
            "l6_details": [
                {"catalogue": "...", "qty": 1, "unit_price": 100, "final_price": 100, ...},
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
                    "catalogue": item.catalogue or "",
                    "description": item.description or "",
                    "part_category": item.part_category or "",
                    "qty": item.qty or 0,
                    "base_price": item.base_price or 0.0,
                    "final_price": item.final_price or 0.0,
                    "profit_margin": item.profit_margin or 0.0,
                })
            _load_item_details(data, items, quotation, bindings)
    
    return data

def _load_l6_from_template(quotation):
    """从 quotation.extra_fields.config_l6_picks 读 L6 预览行——对齐左栏 BomTable 的渲染。

    两种来源：
    - bom_source=='excel'：从持久化的 bom_excel_rows 取 L6/整机 行（catalogue/description/qty 直通）。
      与左栏同源，不依赖可变的 quotation_items。老数据无快照则不加入 covered，
      交给 _load_item_details 的扁平回落（items 未污染，仍正确）。
    - live + 有 bom_template.rows：按模板 + bom_context 展开（catalogue=label, description=ctx.desc, qty=ctx.qty）。
      无模板的 live cfg 不产出 L6 行（不显示机箱原版料）。

    行字段 key 统一为展示列 catalogue/description/part_category/qty/config_name，
    与 Univer 绑定语义一致（catalogue→Catalogue 列、description→Description 列、qty→Qty 列）。

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
                        "catalogue": r.get("catalogue", "") or "",
                        "description": r.get("description", "") or "",
                        "part_category": r.get("part_category", "") or "",
                        "qty": 0 if qty_val is None else qty_val,
                        "base_price": r.get("base_price", 0) or 0,
                        "final_price": r.get("final_price", 0) or 0,
                        "profit_margin": r.get("profit_margin", 0) or 0,
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
            # 统一展示列：catalogue=零件名(label)、description=规格(desc)，与左栏 BomTable 及绑定语义一致。
            rows_out.append({
                "config_name": cfg_name,
                "category": "L6",
                "catalogue": r.get("label", "") or "",     # Catalogue = 零件名
                "description": v.get("desc", "") or "",      # Description = 规格
                "part_category": "",
                "qty": "" if qty_val is None else qty_val,
                "base_price": 0,
                "final_price": 0,
                "profit_margin": 0,
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
        item_with_no = {
            **item,
            "item_no": item.get("item_no", idx + 1),
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

    # 🔧 修复：只从有实际 items 的配置构建 config_summary
    # 避免把已删除/改名的历史配置也加进来
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

    # 不再从 config_descriptions 等收集所有配置名，避免旧配置残留
    # 只有有 items 的配置才会出现在 config_summary 和 configs 中
    
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

    # ── 按配置分组 L6/KP/Warranty 数据，构建 configs 数组 ─────────────────────────────
    # 从 data 获取维保描述（在 load_preview_data 中已设置）
    warranty_desc_l6 = data.get("warranty_desc_l6", {})
    warranty_desc_kp = data.get("warranty_desc_kp", {})

    config_items_map = {}  # cfg_key → {"l6": [], "kp": [], "warranty": []}
    for item in items:
        cfg_name = item.get("config_name", "Default")
        if cfg_name == "Default":
            continue
        cfg_key = cfg_name.strip().upper()
        if cfg_key not in config_items_map:
            config_items_map[cfg_key] = {"l6": [], "kp": [], "warranty": []}
        category = item.get("category", "")
        if category == "L6":
            # 与第 245-248 行逻辑一致：已覆盖的配置不从 items 添加，避免与 tpl_l6_rows 重复
            if cfg_name not in covered_cfgs and cfg_name in excel_cfgs:
                config_items_map[cfg_key]["l6"].append(item)
        elif category == "Key Parts":
            config_items_map[cfg_key]["kp"].append(item)
        elif category == "Warranty":
            config_items_map[cfg_key]["warranty"].append(item)
    # 将模板展开的 L6 行也加入对应配置
    for r in tpl_l6_rows:
        cfg_name = r.get("config_name", "Default")
        if cfg_name == "Default":
            continue
        cfg_key = cfg_name.strip().upper()
        if cfg_key not in config_items_map:
            config_items_map[cfg_key] = {"l6": [], "kp": [], "warranty": []}
        config_items_map[cfg_key]["l6"].append(r)

    # 构建 configs 数组
    configs = []
    config_quantities = (quotation.config_quantities or {}) if quotation else {}
    config_server_models = (quotation.config_server_models or {}) if quotation else {}

    # 从 extra_fields 解析 config_l6_picks，获取背板类型、电源、基准配置等信息
    config_l6_picks = {}
    if quotation and quotation.extra_fields:
        try:
            extra = json.loads(quotation.extra_fields)
            config_l6_picks = extra.get("config_l6_picks") or {}
        except (json.JSONDecodeError, TypeError):
            pass

    for summary in config_summary:
        cfg_name = summary.get("config_name", "Default")
        cfg_key = cfg_name.strip().upper()
        items_by_cfg = config_items_map.get(cfg_key, {"l6": [], "kp": []})

        # 获取该配置的 L6 picks 信息
        l6_pick = config_l6_picks.get(cfg_name, {})
        # picks 可能显式存为 null（键存在、值为 None），.get("picks", {}) 此时返回 None 而非默认值
        picks = (l6_pick.get("picks") or {}) if isinstance(l6_pick, dict) else {}

        # 背板类型：tri=三模, dc=直连
        bp_type = picks.get("bp_type", "dc")
        bp_display = "Tri-Mode Backplane" if bp_type == "tri" else "Pass-Thru Backplane"

        # 电源：从 bom_context 获取 psu 信息
        # bom_context 结构: { psu_requirement: {desc: "1300W", qty: 2}, ... }
        bom_context = l6_pick.get("bom_context") if isinstance(l6_pick, dict) else {}
        psu_wattage = ""
        psu_qty = 2  # 默认 2 个电源
        if bom_context and isinstance(bom_context, dict):
            psu_req = bom_context.get("psu_requirement", {})
            if isinstance(psu_req, dict):
                psu_desc = psu_req.get("desc", "")
                psu_qty_val = psu_req.get("qty", 2)
                if psu_qty_val:
                    psu_qty = int(psu_qty_val) if isinstance(psu_qty_val, int) else 2
                # 从 desc 提取瓦数（如 "1300W"）
                if psu_desc:
                    import re
                    match = re.search(r'(\d+)\s*W', str(psu_desc))
                    if match:
                        psu_wattage = match.group(1)
                    else:
                        psu_wattage = str(psu_desc)  # 没有数字+W就直接用desc

        # 基准配置ID，用于获取 form（机箱形态）和 bays（盘位）和 series
        base_config_id = l6_pick.get("base_config_id")
        form = ""
        bays = 0
        series = ""
        if base_config_id:
            try:
                from app.repository.base_config_repo import BaseConfigRepository
                base_repo = BaseConfigRepository()
                base_cfg = base_repo.get(base_config_id)
                if base_cfg:
                    form = base_cfg.get("form", "")
                    bays = base_cfg.get("bays", 0) or 0
                    series = base_cfg.get("series", "") or ""
            except Exception:
                pass

        # L6 机箱总价（含税售价：成本 × (1 + 利润率/100)）
        if cfg_name in l6_price_map:
            cost = float(l6_price_map.get(cfg_name) or 0)
            margin = float(l6_margin_map.get(cfg_name) or 0)
            l6_sum = cost * (1 + margin / 100)
        elif cfg_name in excel_cfgs:
            l6_sum = 0
        else:
            l6_sum = sum(
                (i.get("final_price", 0) or 0) * (i.get("qty", 1) or 1)
                for i in items_by_cfg["l6"]
            )
        # KP 配件总价
        kp_sum = sum(
            (i.get("final_price", 0) or 0) * (i.get("qty", 1) or 1)
            for i in items_by_cfg["kp"]
        )
        # 从 config_summary 获取 unit_price/total_price
        unit_price = summary.get("unit_price", 0)
        qty = summary.get("quantity", config_quantities.get(cfg_name, 1))
        total_price = summary.get("total_price", unit_price * qty)

        # 统一展示映射：所有 category 共用 catalogue/description/part_category，无交换。
        # （旧实现里 KP/Warranty 把 spec→name、part_name→category 做交换；字段去重载后直通即可。）
        def _map_detail(i, default_cat):
            return {
                "catalogue": i.get("catalogue", ""),
                "description": i.get("description", ""),
                "part_category": i.get("part_category", ""),
                "qty": i.get("qty", 0),
                "category": i.get("category", default_cat),
                "final_price": i.get("final_price", 0),
            }

        l6_details_mapped = [_map_detail(i, "L6") for i in items_by_cfg["l6"]]
        kp_details_mapped = [_map_detail(i, "Key Parts") for i in items_by_cfg["kp"]]

        # 维保明细
        warranty_details_mapped = [_map_detail(i, "Warranty") for i in items_by_cfg.get("warranty", [])]
        warranty_total = sum(
            (i.get("final_price", 0) or 0) * (i.get("qty", 1) or 1)
            for i in items_by_cfg.get("warranty", [])
        )

        configs.append({
            "config_name": cfg_name,
            "server_model": config_server_models.get(cfg_name, ""),
            "quantity": qty,
            "l6_details": l6_details_mapped,
            "kp_details": kp_details_mapped,
            "warranty_details": warranty_details_mapped,
            "warranty_desc_l6": warranty_desc_l6.get(cfg_name, ""),
            "warranty_desc_kp": warranty_desc_kp.get(cfg_name, ""),
            "l6_total": l6_sum,
            "kp_total": kp_sum,
            "warranty_total": warranty_total,
            "unit_price": unit_price,
            "total_price": total_price,
            # 机箱规格
            "chassis_form": form,                      # 机箱形态
            "chassis_bays": f"{bays} 盘位" if bays else "",  # 盘位
            "chassis_series": series,                   # 系列（Orion/Polaris）
            "backplane_type": bp_display,              # 背板类型（Tri-Mode/Pass-Thru）
            "power_supply": f"{psu_wattage}W x {psu_qty}" if psu_wattage else f"x {psu_qty}",  # 电源
        })
    data["configs"] = configs


def _build_description(cfg_items: list, selected_parts: list = None, separator: str = ", ") -> str:
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
            part_category = str(item.get("part_category", "") or "").lower()  # 类别（CPU/Memory…）
            catalogue = str(item.get("catalogue", "") or "").lower()          # 型号

            # 检查是否匹配（关键词命中类别或型号）
            if any(kw in part_category or kw in catalogue for kw in keywords):
                # 优先使用型号（catalogue），fallback 到类别
                display = item.get("catalogue", "") or item.get("part_category", "")
                qty = item.get("quantity", 0) or item.get("qty", 0) or 0
                
                if display:
                    if qty > 1:
                        parts.append(f"{display} × {qty}")
                    else:
                        parts.append(f"{display}")
                break  # 每个类型只取第一个匹配
    
    return separator.join(parts)
