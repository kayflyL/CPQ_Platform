"""
模板数据填充服务（核心逻辑）

职责：
- 在 workbook_snapshot 的 cellData 上填充数据
- 处理静态绑定和动态绑定
- 保证预览和导出使用同一套逻辑，确保一致性
"""
import json
import copy
from typing import Any
from app.repository.system_config_repo import SystemConfigRepository


def fill_snapshot(workbook_snapshot: dict, bindings: list, data: dict, sheet_config: dict = None) -> dict:
    """
    在 workbook_snapshot 的 cellData 上填充数据
    
    Args:
        workbook_snapshot: Univer workbook 快照
        bindings: 绑定配置列表
        data: 数据源 {
            "customer_name": "XX公司",
            "l6_details": [{"part_name": "...", "qty": 1, ...}, ...],
            ...
        }
        sheet_config: 可选，sheet 配置信息（含 cover/config 定义）
    
    Returns:
        填充后的 workbook_snapshot（深拷贝，不修改原数据）
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # 调试：打印数据源长度
    for key in ['l6_details', 'kp_details', 'config_summary']:
        if key in data:
            logger.info(f"[fill_snapshot] data[{key}] length: {len(data[key])}")
            if len(data[key]) > 0:
                logger.info(f"[fill_snapshot] data[{key}] first item: {data[key][0]}")
    
    # 深拷贝 snapshot，避免修改原数据
    filled = copy.deepcopy(workbook_snapshot)
    
    # 处理配置页 sheet 动态复制
    sheet_id_remap = {}  # old_id -> [new_ids]
    if sheet_config and sheet_config.get("config", {}).get("splitByConfig"):
        filled, sheet_id_remap = _duplicate_config_sheets(filled, sheet_config, data)
    
    # 去重 bindings（相同 sheetId + cellAddress + fieldKey 只保留一个）
    seen_bindings = set()
    unique_bindings = []
    for binding in bindings:
        key = (binding.get("sheetId"), binding.get("cellAddress"), binding.get("fieldKey"))
        if key not in seen_bindings:
            seen_bindings.add(key)
            unique_bindings.append(binding)
        else:
            logger.warning(f"[fill_snapshot] Duplicate binding removed: {key}")
    
    # 动态 bindings 按行号从大到小排序（从下往上处理，避免行插入影响后续 binding）
    def get_row_from_cell_address(cell_address):
        if not cell_address:
            return 0
        import re
        match = re.match(r"([A-Z]+)(\d+)", cell_address.upper())
        return int(match.group(2)) if match else 0
    
    dynamic_bindings = [b for b in unique_bindings if b.get("dataType") == "dynamic"]
    static_bindings = [b for b in unique_bindings if b.get("dataType") == "static"]
    dynamic_bindings.sort(key=lambda b: get_row_from_cell_address(b.get("cellAddress")), reverse=True)
    
    # 合并：先处理动态（从下往上），再处理静态
    sorted_bindings = dynamic_bindings + static_bindings
    
    # 每个 sheet 的行偏移表：{after_row_idx: total_inserted_rows}
    # 用于让静态绑定的行号感知动态插入产生的偏移
    sheet_row_offsets = {}
    
    for binding in sorted_bindings:
        sheet_id = binding.get("sheetId")
        if not sheet_id:
            continue
        
        # 如果该 sheet 被拆分为多个配置页，对每个新 sheet 都应用绑定
        if sheet_id in sheet_id_remap:
            for new_id in sheet_id_remap[sheet_id]:
                sheet = filled["sheets"].get(new_id)
                if not sheet:
                    continue
                config_name = sheet.get("_config_name")  # 读取配置标记
                if binding.get("dataType") == "static":
                    row_offsets = sheet_row_offsets.get(new_id, {})
                    _fill_static_binding(sheet, binding, data, config_name=config_name, row_offsets=row_offsets)
                elif binding.get("dataType") == "dynamic":
                    inserted = _fill_dynamic_binding(sheet, binding, data, config_name=config_name)
                    if inserted > 0:
                        # 记录偏移：在哪个行号之后插入了多少行
                        import re
                        match = re.match(r"([A-Z]+)(\d+)", binding.get("cellAddress", "").upper())
                        if match:
                            template_row = int(match.group(2)) - 1  # 转为 0-indexed
                            if new_id not in sheet_row_offsets:
                                sheet_row_offsets[new_id] = {}
                            offsets = sheet_row_offsets[new_id]
                            offsets[template_row] = offsets.get(template_row, 0) + inserted
            continue
        
        if sheet_id not in filled["sheets"]:
            continue
        
        sheet = filled["sheets"][sheet_id]
        
        if binding.get("dataType") == "static":
            row_offsets = sheet_row_offsets.get(sheet_id, {})
            _fill_static_binding(sheet, binding, data, row_offsets=row_offsets)
        elif binding.get("dataType") == "dynamic":
            inserted = _fill_dynamic_binding(sheet, binding, data)
            if inserted > 0:
                import re
                match = re.match(r"([A-Z]+)(\d+)", binding.get("cellAddress", "").upper())
                if match:
                    template_row = int(match.group(2)) - 1  # 转为 0-indexed
                    if sheet_id not in sheet_row_offsets:
                        sheet_row_offsets[sheet_id] = {}
                    offsets = sheet_row_offsets[sheet_id]
                    offsets[template_row] = offsets.get(template_row, 0) + inserted
    
    return filled


def _duplicate_config_sheets(workbook: dict, sheet_config: dict, data: dict) -> tuple:
    """
    根据配置数量复制配置页 sheet
    
    Returns:
        (workbook, sheet_id_remap) where sheet_id_remap = {old_id: [new_ids]}
    """
    config_cfg = sheet_config.get("config", {})
    template_sheet_id = config_cfg.get("sheetId")
    name_template = config_cfg.get("nameTemplate", "{cfg_name}")
    
    if not template_sheet_id or template_sheet_id not in workbook["sheets"]:
        return workbook, {}
    
    # 获取配置列表
    configs = data.get("config_summary", [])
    if not configs:
        # 没有配置数据，保留原始配置页
        return workbook, {}
    
    template_sheet = workbook["sheets"][template_sheet_id]
    sheet_order = workbook.get("sheetOrder", [])
    
    # 找到模板 sheet 在 sheetOrder 中的位置
    try:
        template_idx = sheet_order.index(template_sheet_id)
    except ValueError:
        template_idx = len(sheet_order)
    
    # 为每个配置创建新 sheet
    new_sheet_ids = []
    
    for i, cfg in enumerate(configs):
        cfg_name = cfg.get("config_name", f"Config{i+1}")
        new_sheet_id = f"sheet-config-{i+1}"
        
        # 深拷贝模板 sheet
        new_sheet = copy.deepcopy(template_sheet)
        new_sheet["name"] = name_template.format(cfg_name=cfg_name)
        new_sheet["id"] = new_sheet_id
        new_sheet["_config_name"] = cfg_name  # 标记该 sheet 属于哪个配置
        
        workbook["sheets"][new_sheet_id] = new_sheet
        new_sheet_ids.append(new_sheet_id)
    
    # 更新 sheetOrder：在模板位置后插入新 sheet
    sheet_order[template_idx:template_idx+1] = new_sheet_ids
    workbook["sheetOrder"] = sheet_order
    
    # 删除原始模板 sheet（避免多余页面）
    del workbook["sheets"][template_sheet_id]
    
    # 返回映射：旧 sheet_id -> [新 sheet_ids]
    sheet_id_remap = {template_sheet_id: new_sheet_ids}
    
    return workbook, sheet_id_remap


def _fill_static_binding(sheet: dict, binding: dict, data: dict, config_name: str = None, row_offsets: dict = None):
    """填充静态绑定
    
    Args:
        config_name: 如果提供，当字段值是 dict 时按配置名取值
        row_offsets: 行偏移表 {after_row_idx: inserted_count}，用于感知动态插入产生的偏移
    """
    cell_address = binding.get("cellAddress")
    field_key = binding.get("fieldKey")
    
    if not cell_address or not field_key:
        # 绑定配置不完整，清除标记
        if cell_address:
            _clear_cell_binding_marker(sheet, cell_address)
        return
    
    # 解析单元格地址 (如 "B3" → row=2, col=1)
    row_idx, col_idx = _parse_cell_address(cell_address)
    
    # 应用行偏移：如果该静态绑定的行号在某个动态插入点之后，需要下移
    if row_offsets:
        total_offset = 0
        for after_row, inserted_count in row_offsets.items():
            if row_idx > after_row:
                total_offset += inserted_count
        row_idx += total_offset
    
    # 获取值（None 转为空字符串）
    value = data.get(field_key, "")

    # cfg_ 前缀字段：从 config_summary 数组按 config_name 取值
    if (value == "" or value is None) and config_name and field_key.startswith("cfg_"):
        source_col = field_key[4:]  # "cfg_unit_price" → "unit_price"
        for cfg in data.get("config_summary", []):
            if cfg.get("config_name") == config_name:
                value = cfg.get(source_col, "")
                break

    # 如果值是 dict 且有 config_name，按配置名取值
    if isinstance(value, dict) and config_name:
        # 尝试精确匹配
        if config_name in value:
            value = value[config_name]
        else:
            # 尝试模糊匹配（去除空格，不区分大小写）
            normalized_config_name = config_name.strip().lower()
            matched = False
            for key, val in value.items():
                if key.strip().lower() == normalized_config_name:
                    value = val
                    matched = True
                    break
            if not matched:
                value = ""
    
    # 如果值是 dict（绑定在封面页），合并所有配置的值
    if isinstance(value, dict):
        values = [v for v in value.values() if v]
        value = "\n".join(values) if values else ""
    
    # 如果值为空，尝试从 system_config 获取默认值
    if value == "":
        try:
            sys_repo = SystemConfigRepository()
            fallback = sys_repo.get_value(field_key, "")
            if fallback:
                value = fallback
        except Exception:
            pass
    
    if value is None:
        value = ""
    
    # 写入 cellData
    row_idx_str = str(row_idx)
    col_idx_str = str(col_idx)
    
    if row_idx_str not in sheet["cellData"]:
        sheet["cellData"][row_idx_str] = {}
    
    if col_idx_str not in sheet["cellData"][row_idx_str]:
        sheet["cellData"][row_idx_str][col_idx_str] = {}
    
    sheet["cellData"][row_idx_str][col_idx_str]["v"] = value


def _clear_cell_binding_marker(sheet: dict, cell_address: str):
    """清除单元格中的绑定标记（{{...}}格式）"""
    if not cell_address:
        return
    
    try:
        row_idx, col_idx = _parse_cell_address(cell_address)
        row_idx_str = str(row_idx)
        col_idx_str = str(col_idx)
        
        if row_idx_str in sheet.get("cellData", {}):
            if col_idx_str in sheet["cellData"][row_idx_str]:
                cell = sheet["cellData"][row_idx_str][col_idx_str]
                value = cell.get("v", "")
                # 如果值是 {{...}} 格式的绑定标记，清空它
                if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                    cell["v"] = ""
    except Exception:
        pass  # 解析失败时忽略


def _fill_dynamic_binding(sheet: dict, binding: dict, data: dict, config_name: str = None) -> int:
    """填充动态绑定
    
    Args:
        config_name: 如果提供，只填充属于该配置的数据
    
    Returns:
        插入的行数（用于更新行偏移表）
    """
    region_key = binding.get("regionFieldKey") or binding.get("fieldKey")
    template_row = binding.get("templateRow")
    field_mapping = binding.get("fieldMapping", {})
    
    # 如果没有 templateRow，尝试从 cellAddress 推断
    if not template_row and binding.get("cellAddress"):
        import re
        match = re.match(r"([A-Z]+)(\d+)", binding["cellAddress"].upper())
        if match:
            template_row = int(match.group(2))
    
    if not region_key or not template_row:
        # 绑定配置不完整，清除标记
        if binding.get("cellAddress"):
            _clear_cell_binding_marker(sheet, binding["cellAddress"])
        return 0
    
    # 如果 field_mapping 为空，自动从数据的第一条记录推断
    if not field_mapping:
        data_rows = data.get(region_key, [])
        if data_rows and isinstance(data_rows[0], dict):
            # 自动映射所有字段到从起始列开始的连续列
            start_col = 0
            if binding.get("cellAddress"):
                import re
                match = re.match(r"([A-Z]+)(\d+)", binding["cellAddress"].upper())
                if match:
                    col_letter = match.group(1)
                    start_col = _column_letter_to_index(col_letter)
            
            for i, field_key in enumerate(data_rows[0].keys()):
                col_letter = _index_to_column_letter(start_col + i)
                field_mapping[field_key] = col_letter
    
    # 获取数据源
    data_rows = data.get(region_key, [])
    
    # 如果指定了 config_name，过滤只保留该配置的数据
    if config_name and data_rows:
        data_rows = [r for r in data_rows if r.get("config_name") == config_name]
    
    # 重新编号 item_no（从1开始）
    for idx, row in enumerate(data_rows, 1):
        row["item_no"] = idx
    
    if not data_rows:
        # 数据为空，清除绑定标记
        if binding.get("cellAddress"):
            _clear_cell_binding_marker(sheet, binding["cellAddress"])
        return 0
    
    # 模板行索引（0-indexed）
    template_row_idx = template_row - 1
    
    # 计算需要扩展的行数
    extra_rows = len(data_rows) - 1  # 模板已有 1 行
    
    if extra_rows > 0:
        # 插入新行（复制模板行的样式）
        _insert_rows(sheet, template_row_idx, extra_rows)
    
    # 填充数据
    for i, row_data in enumerate(data_rows):
        current_row_idx = template_row_idx + i  # 0-indexed
        
        for field_key, col_letter in field_mapping.items():
            col_idx = _column_letter_to_index(col_letter)
            
            row_idx_str = str(current_row_idx)
            col_idx_str = str(col_idx)
            
            if row_idx_str not in sheet["cellData"]:
                sheet["cellData"][row_idx_str] = {}
            
            if col_idx_str not in sheet["cellData"][row_idx_str]:
                sheet["cellData"][row_idx_str][col_idx_str] = {}
            
            # 获取值
            value = row_data.get(field_key, "")
            
            sheet["cellData"][row_idx_str][col_idx_str]["v"] = value
    
    return max(extra_rows, 0)


def _insert_rows(sheet: dict, after_row_idx: int, count: int):
    """
    在 after_row_idx 之后插入 count 行
    复制 after_row_idx 的样式到新行
    
    修复：确保所有有内容的行都被正确下移，不仅仅是 cellData 中有 key 的行
    """
    cell_data = sheet.get("cellData", {})
    row_data = sheet.get("rowData", {})
    merge_data = sheet.get("mergeData", [])
    
    # 获取模板行的样式
    template_styles = {}
    if str(after_row_idx) in cell_data:
        for col_idx, cell in cell_data[str(after_row_idx)].items():
            if "s" in cell:
                template_styles[col_idx] = cell["s"]
    
    # 找出所有需要下移的行（从后往前处理，避免索引错位）
    # 修复：不仅检查 cellData 中的 key，还要考虑 rowData 中的行高定义
    existing_rows_set = set()
    for key in cell_data.keys():
        existing_rows_set.add(int(key))
    for key in row_data.keys():
        existing_rows_set.add(int(key))
    
    existing_rows = sorted(list(existing_rows_set), reverse=True)
    rows_to_shift = [r for r in existing_rows if r > after_row_idx]
    
    # 下移现有行
    for old_row_idx in rows_to_shift:
        new_row_idx = old_row_idx + count
        # 移动 cellData
        if str(old_row_idx) in cell_data:
            cell_data[str(new_row_idx)] = cell_data.pop(str(old_row_idx))
        # 移动 rowData
        if str(old_row_idx) in row_data:
            row_data[str(new_row_idx)] = row_data.pop(str(old_row_idx))
    
    # 修复：下移 mergeData 中的合并区域
    # 如果合并区域的 startRow > after_row_idx，说明它在插入点下方，需要下移
    for merge in merge_data:
        if merge.get("startRow", 0) > after_row_idx:
            merge["startRow"] = merge.get("startRow", 0) + count
            merge["endRow"] = merge.get("endRow", 0) + count
    
    # 插入新行（复制模板行样式）
    for i in range(1, count + 1):
        new_row_idx = after_row_idx + i
        cell_data[str(new_row_idx)] = {}
        
        # 复制样式
        for col_idx, style in template_styles.items():
            cell_data[str(new_row_idx)][col_idx] = {"v": "", "s": copy.deepcopy(style)}
        
        # 复制行高
        if str(after_row_idx) in row_data:
            row_data[str(new_row_idx)] = copy.deepcopy(row_data[str(after_row_idx)])


def _parse_cell_address(address: str) -> tuple[int, int]:
    """
    解析单元格地址 (如 "B3" → row=2, col=1)
    返回 (row_idx, col_idx)，都是 0-indexed
    """
    import re
    
    match = re.match(r"([A-Z]+)(\d+)", address.upper())
    if not match:
        raise ValueError(f"Invalid cell address: {address}")
    
    col_letter = match.group(1)
    row_num = int(match.group(2))
    
    col_idx = _column_letter_to_index(col_letter)
    row_idx = row_num - 1  # 转为 0-indexed
    
    return row_idx, col_idx


def _column_letter_to_index(letter: str) -> int:
    """列字母转索引 (A→0, B→1, ..., Z→25, AA→26, ...)"""
    result = 0
    for char in letter.upper():
        result = result * 26 + (ord(char) - ord("A") + 1)
    return result - 1


def _index_to_column_letter(index: int) -> str:
    """列索引转字母 (0→A, 1→B, ..., 25→Z, 26→AA, ...)"""
    result = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result




