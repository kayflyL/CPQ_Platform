"""
Excel Parser Engine — 独立的 Excel 解析服务

从 pricing_engine.py 剥离，专门负责：
1. 根据 parse_regions 规则定位 Excel 中的逻辑区域
2. 根据 parse_field_rules 规则提取字段值
3. 返回带溯源信息的解析结果（白盒化）

所有解析逻辑可配置、可修改，作为统一的 Excel 解析服务提供商。
"""

import re
import json
import pandas as pd
from typing import Optional
from app.repository.rules_repo import RulesRepository


class ExcelParser:
    """独立的 Excel 解析引擎，规则驱动，支持白盒化溯源"""
    
    def __init__(self, rules_repo: RulesRepository):
        self.rules_repo = rules_repo
        self._parse_regions = None
        self._parse_field_rules = None
    
    def _load_rules(self):
        """从数据库加载解析规则"""
        if self._parse_regions is None:
            self._parse_regions = self.rules_repo.get_parse_regions()
        if self._parse_field_rules is None:
            self._parse_field_rules = self.rules_repo.get_parse_field_rules()
    
    def parse(self, df: pd.DataFrame, return_trace: bool = True) -> dict:
        """解析 Excel DataFrame，返回结构化数据 + 溯源信息
        
        Args:
            df: Excel 工作表转换的 DataFrame
            return_trace: 是否返回溯源信息（白盒化）
        
        Returns:
            {
                "static_fields": {field_key: {"value": ..., "source": {...}}},
                "dynamic_regions": {region_name: [{field_key: ..., value: ..., source: ...}]},
                "trace": [...]  # 如果 return_trace=True
            }
        """
        self._load_rules()
        
        result = {
            "static_fields": {},
            "dynamic_regions": {},
            "trace": []
        }
        
        # 1. 定位所有区域
        region_bounds = self._locate_regions(df)
        
        # 2. 提取静态字段（header 区域）
        header_rules = [r for r in self._parse_field_rules if r["region"] == "header" and r["enabled"]]
        for rule in sorted(header_rules, key=lambda x: x["sort_order"]):
            field_key = rule["field_key"]
            source_config = rule["source_config"]
            
            if rule["source_type"] == "keyword":
                value, source = self._extract_by_keyword(df, source_config, max_rows=10)
                if value:
                    result["static_fields"][field_key] = {
                        "value": value,
                        "source": source
                    }
                    if return_trace:
                        result["trace"].append({
                            "type": "static_field",
                            "field_key": field_key,
                            "value": value,
                            "source": source
                        })
        
        # 3. 提取动态区域字段（L6/KP/Warranty）
        for region_name, bounds in region_bounds.items():
            if region_name == "header" or bounds["start_row"] < 0:
                continue
            
            region_rules = [r for r in self._parse_field_rules 
                          if r["region"] == region_name and r["enabled"]]
            if not region_rules:
                continue
            
            region_items = []
            start_row = bounds["start_row"] + bounds["skip_rows"]
            end_row = bounds["end_row"] if bounds["end_row"] > start_row else len(df)
            
            for r in range(start_row, end_row):
                item = {}
                item_trace = []
                
                for rule in sorted(region_rules, key=lambda x: x["sort_order"]):
                    field_key = rule["field_key"]
                    source_config = rule["source_config"]
                    
                    if rule["source_type"] == "column":
                        col_letter = source_config.get("col", "A")
                        col_idx = self._col_letter_to_index(col_letter)
                        
                        if col_idx < df.shape[1]:
                            cell_val = df.iloc[r, col_idx]
                            if pd.notna(cell_val):
                                value = str(cell_val).strip()
                                if value and value.lower() not in ['nan', 'none', '']:
                                    # 处理公式
                                    if isinstance(cell_val, str) and cell_val.startswith('='):
                                        try:
                                            from app.engine.pricing_engine import _safe_eval_math
                                            value = str(_safe_eval_math(cell_val[1:]))
                                        except:
                                            pass
                                    
                                    item[field_key] = value
                                    source = {"row": r, "col": col_idx, "col_letter": col_letter}
                                    item_trace.append({
                                        "field_key": field_key,
                                        "value": value,
                                        "source": source
                                    })
                
                # 只添加有内容的行
                if item:
                    item["_row"] = r
                    item["_trace"] = item_trace
                    region_items.append(item)
            
            if region_items:
                result["dynamic_regions"][region_name] = region_items
                if return_trace:
                    result["trace"].append({
                        "type": "dynamic_region",
                        "region": region_name,
                        "bounds": bounds,
                        "item_count": len(region_items)
                    })
        
        return result
    
    def _locate_regions(self, df: pd.DataFrame) -> dict:
        """定位所有区域边界
        
        Returns:
            {region_name: {"start_row": int, "end_row": int, "skip_rows": int}}
        """
        bounds = {}
        
        # 按 sort_order 排序区域
        sorted_regions = sorted(self._parse_regions, key=lambda x: x["sort_order"])
        
        prev_end_row = 0
        for region in sorted_regions:
            region_name = region["name"]
            start_keywords = region["start_keywords"]
            end_keywords = region["end_keywords"]
            skip_rows = region["skip_header_rows"]
            
            # 定位起始行
            if start_keywords:
                start_row = self._find_region_row(df, start_keywords, start_row=prev_end_row)
            else:
                # header 区域从第 0 行开始
                start_row = 0
            
            # 定位结束行
            if end_keywords and start_row >= 0:
                end_row = self._find_region_row(df, end_keywords, start_row=start_row + 1)
            else:
                end_row = len(df)
            
            bounds[region_name] = {
                "start_row": start_row,
                "end_row": end_row,
                "skip_rows": skip_rows
            }
            
            # 更新下一区域的起始位置
            if end_row > start_row:
                prev_end_row = end_row
            else:
                prev_end_row = start_row + 1
        
        return bounds
    
    def _find_region_row(self, df: pd.DataFrame, keywords_str: str, start_row: int = 0) -> int:
        """查找包含任一关键词的首行
        
        三阶段匹配：(1) 词边界 (2) 子串 (3) 模糊匹配（编辑距离≤2）
        返回行索引或 -1
        """
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        
        # 第一轮：词边界匹配
        for r in range(start_row, len(df)):
            for c in range(min(10, df.shape[1])):
                cell_val = str(df.iloc[r, c]).strip() if pd.notna(df.iloc[r, c]) else ''
                if not cell_val:
                    continue
                cell_lower = cell_val.lower()
                for kw in keywords:
                    kw_lower = kw.lower()
                    pattern = r'\b' + re.escape(kw_lower) + r'\b'
                    if re.search(pattern, cell_lower):
                        return r
        
        # 第二轮：子串匹配
        for r in range(start_row, len(df)):
            for c in range(min(10, df.shape[1])):
                cell_val = str(df.iloc[r, c]).strip() if pd.notna(df.iloc[r, c]) else ''
                if not cell_val:
                    continue
                cell_lower = cell_val.lower()
                for kw in keywords:
                    kw_lower = kw.lower()
                    if kw_lower in cell_lower:
                        return r
        
        # 第三轮：模糊匹配（编辑距离≤2，仅对≥4字符的关键词）
        def _edit_distance(s1: str, s2: str) -> int:
            if len(s1) < len(s2):
                return _edit_distance(s2, s1)
            if len(s2) == 0:
                return len(s1)
            prev_row = list(range(len(s2) + 1))
            for i, c1 in enumerate(s1):
                curr_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = prev_row[j + 1] + 1
                    deletions = curr_row[j] + 1
                    substitutions = curr_row[j] + (c1 != c2)
                    curr_row.append(min(insertions, deletions, substitutions))
                prev_row = curr_row
            return prev_row[-1]
        
        for r in range(start_row, len(df)):
            for c in range(min(10, df.shape[1])):
                cell_val = str(df.iloc[r, c]).strip() if pd.notna(df.iloc[r, c]) else ''
                if not cell_val:
                    continue
                cell_lower = cell_val.lower()
                for kw in keywords:
                    kw_lower = kw.lower()
                    if len(kw_lower) <= 3:
                        continue
                    cell_words = re.findall(r'[a-z]+', cell_lower)
                    for word in cell_words:
                        if abs(len(word) - len(kw_lower)) <= 2:
                            if _edit_distance(word, kw_lower) <= 2:
                                return r
        
        return -1
    
    def _extract_by_keyword(self, df: pd.DataFrame, source_config: dict, max_rows: int = 10) -> tuple:
        """根据关键词提取值（用于静态字段）
        
        Args:
            source_config: {"keywords": [...], "value_offset": int}
        
        Returns:
            (value, source_info)
        """
        keywords = source_config.get("keywords", [])
        value_offset = source_config.get("value_offset", 1)
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            for r in range(min(max_rows, len(df))):
                for c in range(min(10, df.shape[1])):
                    cell_val = str(df.iloc[r, c]).strip() if pd.notna(df.iloc[r, c]) else ''
                    if keyword_lower in cell_val.lower():
                        # 提取右侧值
                        target_col = c + value_offset
                        if target_col < df.shape[1]:
                            val = df.iloc[r, target_col]
                            if pd.notna(val):
                                extracted = str(val).strip()
                                if extracted and extracted.lower() not in ['', 'nan', 'none']:
                                    source = {
                                        "row": r,
                                        "col": target_col,
                                        "keyword": keyword,
                                        "keyword_col": c
                                    }
                                    return extracted, source
        return None, None
    
    def _col_letter_to_index(self, letter: str) -> int:
        """列字母转索引（A=0, B=1, ..., Z=25, AA=26）"""
        letter = letter.strip().upper()
        result = 0
        for ch in letter:
            result = result * 26 + (ord(ch) - ord('A') + 1)
        return result - 1
    
    def preview_parse(self, df: pd.DataFrame, max_row: int = 15, max_col: int = 15) -> dict:
        """生成热力图预览数据（用于前端可视化）
        
        Returns:
            {
                "grid": [[cell_value, ...], ...],
                "cell_marks": [{"row": r, "col": c, "value": v, "type": t, "target": tgt}, ...],
                "region_bounds": {...}
            }
        """
        self._load_rules()
        
        # 构建网格
        rows = min(max_row, len(df)) if max_row else len(df)
        cols = min(max_col, df.shape[1]) if max_col else df.shape[1]
        
        grid = []
        for r in range(rows):
            row_data = []
            for c in range(cols):
                val = df.iloc[r, c] if r < len(df) and c < df.shape[1] else None
                row_data.append(str(val) if pd.notna(val) else '')
            grid.append(row_data)
        
        # 定位区域
        region_bounds = self._locate_regions(df)
        
        # 生成 cell_marks
        cell_marks = []
        
        # 标记静态字段
        header_rules = [r for r in self._parse_field_rules if r["region"] == "header" and r["enabled"]]
        for rule in header_rules:
            source_config = rule["source_config"]
            if rule["source_type"] == "keyword":
                value, source = self._extract_by_keyword(df, source_config, max_rows=10)
                if source:
                    cell_marks.append({
                        "row": source["keyword_row"] if "keyword_row" in source else source["row"],
                        "col": source["keyword_col"],
                        "value": source.get("keyword", ""),
                        "type": "keyword",
                        "target": rule["field_key"]
                    })
                    cell_marks.append({
                        "row": source["row"],
                        "col": source["col"],
                        "value": value,
                        "type": "extracted",
                        "target": rule["field_key"]
                    })
        
        # 标记动态区域
        for region_name, bounds in region_bounds.items():
            if region_name == "header" or bounds["start_row"] < 0:
                continue
            
            # 标记区域起始行
            region_color = f"{region_name.lower()}_region"
            start_row = bounds["start_row"]
            if start_row < rows:
                for c in range(min(10, cols)):
                    cell_val = str(df.iloc[start_row, c]).strip() if pd.notna(df.iloc[start_row, c]) else ''
                    if cell_val:
                        cell_marks.append({
                            "row": start_row,
                            "col": c,
                            "value": cell_val,
                            "type": region_color,
                            "target": f"{region_name} Start"
                        })
            
            # 标记数据行
            region_rules = [r for r in self._parse_field_rules 
                          if r["region"] == region_name and r["enabled"]]
            
            data_start = start_row + bounds["skip_rows"]
            data_end = bounds["end_row"] if bounds["end_row"] > data_start else len(df)
            
            for r in range(data_start, min(data_end, rows)):
                for rule in region_rules:
                    source_config = rule["source_config"]
                    if rule["source_type"] == "column":
                        col_letter = source_config.get("col", "A")
                        col_idx = self._col_letter_to_index(col_letter)
                        
                        if col_idx < cols:
                            cell_val = str(df.iloc[r, col_idx]).strip() if pd.notna(df.iloc[r, col_idx]) else ''
                            if cell_val and cell_val.lower() not in ['nan', 'none', '']:
                                cell_marks.append({
                                    "row": r,
                                    "col": col_idx,
                                    "value": cell_val,
                                    "type": region_color,
                                    "target": f"{region_name}.{rule['field_key']}"
                                })
        
        return {
            "grid": grid,
            "cell_marks": cell_marks,
            "region_bounds": region_bounds
        }
