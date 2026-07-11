"""
Pricing Engine — pure business logic layer.

Replaces the DB-coupled parts of legacy data_processor.py.
All data access goes through injected Repository instances.
No sqlite3, no direct DB connections.
"""

import re
import os
import ast
import json
import operator
import io
import pandas as pd
import openpyxl
from pathlib import Path
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime
from typing import Optional

from app.core.config import get_settings

from app.repository.kp_repo import KPRepository
from app.repository.l6_repo import L6Repository
from app.repository.opportunity_repo import OpportunityRepository
from app.repository.rules_repo import RulesRepository
from app.repository.export_template_repo import ExportTemplateRepository


# === Safe arithmetic evaluator (replaces eval() for Excel formulas) ===
_SAFE_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_SAFE_UNARY_OPS = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval_math(expr: str) -> float:
    """Safely evaluate a simple arithmetic expression (numbers + - * / parentheses).

    Unlike eval(), this does NOT support ** (exponentiation), so it cannot be
    abused for DoS via expressions like 9**9**9.
    """
    tree = ast.parse(expr, mode='eval')

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_BIN_OPS:
            return _SAFE_BIN_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_UNARY_OPS:
            return _SAFE_UNARY_OPS[type(node.op)](_eval(node.operand))
        raise ValueError(f"Unsafe or unsupported expression: {ast.dump(node)}")

    return _eval(tree)


# === V49 Excel export style constants (unchanged from legacy) ===
_F_22_LISU = Font(name='隶书', size=22, bold=False, color='000000')
_F_11_SONG = Font(name='宋体', size=11, bold=False, color='000000')
_F_11_TNR = Font(name='Times New Roman', size=11, bold=False, color='000000')
_F_11_DENG_B = Font(name='等线', size=11, bold=True, color='000000')
_F_11_TNR_C = Font(name='Times New Roman', size=11, bold=False, color='000000')
_F_11_SONG_11 = Font(name='宋体', size=11, bold=False, color='000000')
_F_11_TNR_B = Font(name='Times New Roman', size=11, bold=True, color='000000')
_F_11_EQ = Font(name='等线', size=11, bold=False, color='000000')

_NO_FILL = PatternFill(start_color='00000000', end_color='00000000', fill_type='solid')
_THIN_B = Border(
    left=Side(style='thin', color='000000'), right=Side(style='thin', color='000000'),
    top=Side(style='thin', color='000000'), bottom=Side(style='thin', color='000000')
)

def _s(cell, font=None, fill=None, align=None, border=True):
    if font: cell.font = font
    if fill: cell.fill = fill
    if align: cell.alignment = align
    if border: cell.border = _THIN_B


# Data paths (from config)
_settings = get_settings()
DATA_DIR = Path(_settings.DATA_PATH)
CONFIG_PATH = DATA_DIR / "config.json"


class PricingEngine:
    """
    Business logic engine.
    Receives Repositories via constructor — never creates DB connections directly.
    """

    def __init__(self, kp_repo: KPRepository, l6_repo: L6Repository,
                 opportunity_repo: OpportunityRepository, rules_repo: RulesRepository = None,
                 export_template_repo: ExportTemplateRepository = None,
                 quotation_repo=None, business_field_repo=None):
        self.kp_repo = kp_repo
        self.l6_repo = l6_repo
        self.opportunity_repo = opportunity_repo
        self.rules_repo = rules_repo
        self.export_template_repo = export_template_repo
        self._quotation_repo = quotation_repo
        self._business_field_repo = business_field_repo

    def _get_quotation_repo(self):
        """Lazy-init QuotationRepository (avoids per-call instantiation)."""
        if self._quotation_repo is None:
            from app.repository.quotation_repo import QuotationRepository
            self._quotation_repo = QuotationRepository()
        return self._quotation_repo

    def _get_business_field_repo(self):
        """Lazy-init BusinessFieldRepository (avoids per-cell instantiation)."""
        if self._business_field_repo is None:
            from app.repository.business_field_repo import BusinessFieldRepository
            self._business_field_repo = BusinessFieldRepository()
        return self._business_field_repo

        
        # Load rules from DB (with hardcoded fallbacks)
        self._load_rules()
    
    def _load_rules(self):
        """Load configurable rules from rules.db, with hardcoded fallbacks."""
        # Default hardcoded fallbacks for L6/KP region configs
        self._l6_region_config = {
            "region_start_keywords": "L6",
            "field_mapping": {"catalogue": "D", "description": "E", "quantity": "F"},
            "region_end_keywords": "Keyparts,KP"
        }
        self._kp_region_config = {
            "region_start_keywords": "Keyparts,KP",
            "field_mapping": {"catalogue": "D", "model": "E", "quantity": "F", "price": "G"},
            "region_end_keywords": "Warranty,Total"
        }
        self._kp_cat_map = {
            'cpu': 'CPU', 'processor': 'CPU',
            'memory': 'Memory', 'ram': 'Memory',
            'hdd': 'HDD/SSD', 'ssd': 'HDD/SSD',
            'raid': 'Raid card',
            'network': 'NIC', 'nic': 'NIC',
            'gpu': 'GPU',
            'power': 'Power', 'psu': 'Power',
            'fan': 'Fan',
            'heatsink': 'Heatsink', 'cooler': 'Heatsink',
            'cable': 'Cable', 'wire': 'Cable',
            'rail': 'Rail'
        }
        self._mb_mappings = [
            ("KH50000", "Polaris MB"),
            ("KH30000", "Orion MB"),
            ("KH20000", "Orion MB"),
            ("AMD", "TTY TG658V3"),
            ("EPYC", "TTY TG658V3"),
            ("INTEL", "TTY TG658V3"),
            ("XEON", "TTY TG658V3"),
        ]
        self._l6_match_dims = ["chassis", "model", "drive_bays", "psu", "motherboard"]
        self._l6_fallback_dims = ["chassis", "model", "drive_bays"]
        self._price_diff_threshold = 0.01
        # Fuzzy/degrade matching rules (defaults)
        self._allow_chassis_fuzzy = False
        self._chassis_fuzzy_rules = []  # [{"from": "2U", "to": "2.5U"}, ...]
        self._allow_motherboard_fallback = False
        
        if not self.rules_repo:
            return
        
        # Override from DB
        try:
            l6_config = self.rules_repo.get_l6_region_config()
            if l6_config:
                self._l6_region_config = l6_config
            
            kp_config = self.rules_repo.get_kp_region_config()
            if kp_config:
                self._kp_region_config = kp_config
            
            kp_mappings = self.rules_repo.get_kp_category_mappings()
            if kp_mappings:
                self._kp_cat_map = {m['keyword']: m['category'] for m in kp_mappings}
                # Store raw mappings for heatmap preview
                self._kp_cat_mappings_raw = kp_mappings
            
            mb_mappings = self.rules_repo.get_motherboard_mappings()
            if mb_mappings:
                self._mb_mappings = [(m['cpu_feature'], m['motherboard_model']) for m in mb_mappings]
            
            l6_dims_rule = self.rules_repo.get_matching_rule("l6_match_dimensions")
            if l6_dims_rule:
                self._l6_match_dims = json.loads(l6_dims_rule['rule_value'])
            
            l6_fb_rule = self.rules_repo.get_matching_rule("l6_fallback_dimensions")
            if l6_fb_rule:
                self._l6_fallback_dims = json.loads(l6_fb_rule['rule_value'])
            
            threshold_rule = self.rules_repo.get_matching_rule("price_diff_threshold")
            if threshold_rule:
                self._price_diff_threshold = float(threshold_rule['rule_value'])
            
            # Load fuzzy/degrade rules
            chassis_fuzzy_flag = self.rules_repo.get_matching_rule("allow_chassis_fuzzy")
            if chassis_fuzzy_flag:
                self._allow_chassis_fuzzy = chassis_fuzzy_flag['rule_value'].lower() == 'true'
            
            chassis_fuzzy_rules = self.rules_repo.get_matching_rule("chassis_fuzzy_rules")
            if chassis_fuzzy_rules:
                self._chassis_fuzzy_rules = json.loads(chassis_fuzzy_rules['rule_value'])
            
            mb_fallback_flag = self.rules_repo.get_matching_rule("allow_motherboard_fallback")
            if mb_fallback_flag:
                self._allow_motherboard_fallback = mb_fallback_flag['rule_value'].lower() == 'true'
        except Exception as e:
            print(f"⚠️ Failed to load rules from DB, using defaults: {e}")

    # ==================== 1. Excel Parsing (pure algorithm) ====================

    def parse_file(self, sheet_dict: dict) -> tuple:
        """Parse uploaded Excel into configs + first_meta."""
        configs = {}
        first_meta = None
        for sheet_name, df in sheet_dict.items():
            if '原始需求' in sheet_name or 'Reference' in sheet_name or df.empty:
                continue
            meta = self._extract_meta(df)
            items = self._parse_items(df)
            if items.empty:
                continue
            configs[sheet_name] = {'meta': meta, 'items': items}
            if first_meta is None:
                first_meta = meta
        return configs, first_meta

    def preview_parse(self, df: pd.DataFrame, max_row: int = 15, max_col: int = 15, kp_mappings: list = None) -> dict:
        """Parse a single sheet for heatmap preview. Returns grid data + cell marks + meta."""
        meta, cell_marks = self._extract_meta(df, return_cell_marks=True)
        
        # Mark L6 region on the heatmap
        l6_cfg = self._l6_region_config
        l6_start = self._find_region_row(df, l6_cfg.get('region_start_keywords', 'L6'))
        l6_end = self._find_region_row(df, l6_cfg.get('region_end_keywords', 'Keyparts,KP'), start_row=l6_start + 1 if l6_start >= 0 else 0)
        
        if l6_start >= 0:
            end_row = l6_end if l6_end > l6_start else len(df)
            # Mark start keyword row
            for c in range(min(10, df.shape[1])):
                cell_val = str(df.iloc[l6_start, c]).strip() if pd.notna(df.iloc[l6_start, c]) else ''
                if cell_val:
                    cell_marks.append({'row': l6_start, 'col': c, 'value': cell_val, 'type': 'l6_region', 'target': 'L6 Start'})
            # Mark data rows
            l6_field_map = l6_cfg.get('field_mapping', {})
            if isinstance(l6_field_map, str):
                try: l6_field_map = json.loads(l6_field_map)
                except: l6_field_map = {}
            for r in range(l6_start + 1, end_row):
                for field_name, col_letter in l6_field_map.items():
                    col_idx = self._col_letter_to_index(col_letter)
                    if col_idx < df.shape[1]:
                        cell_val = str(df.iloc[r, col_idx]).strip() if pd.notna(df.iloc[r, col_idx]) else ''
                        if cell_val and cell_val.lower() not in ['nan', 'none', '']:
                            cell_marks.append({'row': r, 'col': col_idx, 'value': cell_val, 'type': 'l6_region', 'target': f'L6.{field_name}'})
        
        # Mark KP region on the heatmap
        kp_cfg = self._kp_region_config
        kp_start = l6_end if l6_end >= 0 else self._find_region_row(df, kp_cfg.get('region_start_keywords', 'Keyparts,KP'))
        kp_end = self._find_region_row(df, kp_cfg.get('region_end_keywords', 'Warranty,Total'), start_row=kp_start + 1 if kp_start >= 0 else 0)
        
        if kp_start >= 0:
            end_row = kp_end if kp_end > kp_start else len(df)
            # Mark start keyword row
            for c in range(min(10, df.shape[1])):
                cell_val = str(df.iloc[kp_start, c]).strip() if pd.notna(df.iloc[kp_start, c]) else ''
                if cell_val:
                    cell_marks.append({'row': kp_start, 'col': c, 'value': cell_val, 'type': 'kp_region', 'target': 'KP Start'})
            # Mark data rows
            kp_field_map = kp_cfg.get('field_mapping', {})
            if isinstance(kp_field_map, str):
                try: kp_field_map = json.loads(kp_field_map)
                except: kp_field_map = {}
            for r in range(kp_start + 1, end_row):
                for field_name, col_letter in kp_field_map.items():
                    col_idx = self._col_letter_to_index(col_letter)
                    if col_idx < df.shape[1]:
                        cell_val = str(df.iloc[r, col_idx]).strip() if pd.notna(df.iloc[r, col_idx]) else ''
                        if cell_val and cell_val.lower() not in ['nan', 'none', '']:
                            cell_marks.append({'row': r, 'col': col_idx, 'value': cell_val, 'type': 'kp_region', 'target': f'KP.{field_name}'})
        
        # Mark KP category keywords on the heatmap
        if kp_mappings:
            for mapping in kp_mappings:
                # Support both database format (keyword/category) and frontend format (keywords/variable)
                keyword = mapping.get('keyword') or mapping.get('keywords')
                category = mapping.get('category') or mapping.get('variable')
                
                if not keyword or not category:
                    continue
                
                # Handle keyword as single string or list
                keywords_list = keyword if isinstance(keyword, list) else [keyword]
                
                for kw in keywords_list:
                    kw_lower = kw.lower()
                    for r in range(len(df)):
                        for c in range(df.shape[1]):
                            cell_val = str(df.iloc[r, c]).strip() if pd.notna(df.iloc[r, c]) else ''
                            if cell_val and kw_lower in cell_val.lower():
                                # Only mark if not already marked
                                if not any(m.get('row') == r and m.get('col') == c for m in cell_marks):
                                    cell_marks.append({
                                        'row': r, 'col': c,
                                        'value': cell_val,
                                        'type': 'kp_category',
                                        'target': category
                                    })
        
        # Build grid: list of rows, each row is list of cell values
        rows = len(df) if max_row is None else min(max_row, len(df))
        cols = df.shape[1] if max_col is None else min(max_col, df.shape[1])
        grid = []
        for r in range(rows):
            row_data = []
            for c in range(cols):
                val = df.iloc[r, c]
                row_data.append(str(val).strip() if pd.notna(val) else '')
            grid.append(row_data)
        
        return {
            'grid': grid,
            'max_row': rows,
            'max_col': cols,
            'cell_marks': cell_marks,
            'meta': meta
        }

    def _extract_meta(self, df: pd.DataFrame, return_cell_marks: bool = False) -> dict:
        """Extract opportunity metadata from Excel sheet header area.
        
        Scans the first 10 rows for known keywords and extracts values.
        Also extracts L6 matching dimensions (chassis, drive_bays, psu, motherboard).
        
        Args:
            df: DataFrame from Excel sheet
            return_cell_marks: If True, return (meta, cell_marks) tuple for heatmap preview
        
        Returns:
            dict: Extracted metadata
            tuple: (meta, cell_marks) if return_cell_marks=True
        """
        meta = {}
        cell_marks = [] if return_cell_marks else None
        
        # Helper: find keyword in first N rows, return value to its right (scan entire row for first non-empty value after keyword)
        def find_keyword_value(keyword: str, max_rows: int = 10, mark_type: str = 'meta') -> str:
            keyword_lower = keyword.lower()
            for r in range(min(max_rows, len(df))):
                for c in range(min(10, df.shape[1])):
                    cell_val = str(df.iloc[r, c]).strip() if pd.notna(df.iloc[r, c]) else ''
                    if keyword_lower in cell_val.lower():
                        if return_cell_marks:
                            cell_marks.append({
                                'row': r, 'col': c,
                                'value': cell_val,
                                'type': mark_type,
                                'target': keyword
                            })
                        # Scan from c+1 to end of row for first non-empty value
                        for next_c in range(c + 1, min(10, df.shape[1])):
                            val = df.iloc[r, next_c]
                            if pd.notna(val):
                                extracted = str(val).strip()
                                if extracted and extracted.lower() not in ['', 'nan', 'none']:
                                    if return_cell_marks:
                                        cell_marks.append({
                                            'row': r, 'col': next_c,
                                            'value': extracted,
                                            'type': 'extracted',
                                            'target': keyword
                                        })
                                    return extracted
            return ''
        
        # Extract opportunity metadata from header (try multiple keyword variants)
        opportunity_name = find_keyword_value('Project Name') or find_keyword_value('商机名称')
        if opportunity_name:
            meta['opportunity_name'] = opportunity_name
        
        model_info = find_keyword_value('Model') or find_keyword_value('型号')
        if model_info:
            m = re.search(r'\((\d+)', model_info)
            if m:
                meta['model_qty'] = m.group(1)
                meta['model_name'] = model_info.split('(')[0].strip()
            else:
                meta['model_name'] = model_info
        
        fae = find_keyword_value('FAE')
        if fae and fae not in ['/', '']:
            meta['fae'] = fae
        
        # Try multiple keyword variants for l6_desc
        l6_desc = find_keyword_value('L6 Description') or find_keyword_value('PRODUCT SPEC') or find_keyword_value('产品规格')
        if l6_desc and len(l6_desc) > 10:
            meta['l6_desc'] = l6_desc
        
        date_val = find_keyword_value('Date') or find_keyword_value('日期')
        if date_val:
            meta['date'] = date_val
        
        # Track missing fields for frontend warnings
        meta_warnings = []
        
        # L6 matching dimensions - scan body rows for spec keywords
        spec_text = meta.get('l6_desc', '')
        if not spec_text:
            meta_warnings.append('PRODUCT_SPEC')
        
        m = re.search(r'(\d+(?:\.\d+)?)\s*[Uu]\b', spec_text)
        if m:
            meta['chassis_form'] = m.group(1) + 'U'
        elif spec_text:
            meta_warnings.append('CHASSIS_FORM')
        
        if re.search(r'switch', spec_text, re.IGNORECASE):
            meta['l6_model_type'] = 'Switch机型'
        elif spec_text:
            # Don't hardcode default model type — leave empty if not detected
            meta_warnings.append('MODEL_TYPE')
        
        # Drive bays - scan for Backplane keyword in body
        for r in range(4, len(df)):
            col_d = str(df.iloc[r, 3]).strip() if pd.notna(df.iloc[r, 3]) else ''
            if 'backplane' in col_d.lower():
                spec_bp = str(df.iloc[r, 4]).strip() if pd.notna(df.iloc[r, 4]) else ''
                m = re.match(r'^(\d+)\*', spec_bp)
                if m:
                    meta['drive_bays'] = m.group(1)
                meta['backplane_desc'] = spec_bp
                if return_cell_marks:
                    cell_marks.append({'row': r, 'col': 3, 'value': col_d, 'type': 'meta', 'target': 'drive_bays'})
                break
        else:
            if spec_text:
                meta_warnings.append('DRIVE_BAYS')
        
        # PSU - scan for Power Supply keyword in body
        for r in range(4, len(df)):
            col_d = str(df.iloc[r, 3]).strip() if pd.notna(df.iloc[r, 3]) else ''
            if 'power supply' in col_d.lower():
                spec_psu = str(df.iloc[r, 4]).strip() if pd.notna(df.iloc[r, 4]) else ''
                psu_base = None
                psu_qty = None
                m = re.match(r'(\d+W)', spec_psu)
                if m:
                    psu_base = m.group(1)
                try:
                    qty_val = df.iloc[r, 5]
                    if pd.notna(qty_val):
                        psu_qty = int(float(qty_val))
                except:
                    pass
                if psu_base and psu_qty:
                    meta['psu'] = f"{psu_base} * {psu_qty}"
                if return_cell_marks:
                    cell_marks.append({'row': r, 'col': 3, 'value': col_d, 'type': 'meta', 'target': 'psu'})
                break
        else:
            if spec_text:
                meta_warnings.append('PSU')
        
        # Motherboard - scan for CPU keyword, then match against mb_mappings
        cpu_spec = ''
        for r in range(4, len(df)):
            col_d = str(df.iloc[r, 3]).strip() if pd.notna(df.iloc[r, 3]) else ''
            if col_d.lower() == 'cpu':
                cpu_spec = str(df.iloc[r, 4]).strip() if pd.notna(df.iloc[r, 4]) else ''
                if return_cell_marks:
                    cell_marks.append({'row': r, 'col': 3, 'value': col_d, 'type': 'meta', 'target': 'motherboard'})
                break
        
        if cpu_spec:
            cpu_upper = cpu_spec.upper()
            for feature, mb_model in self._mb_mappings:
                if feature.upper() in cpu_upper:
                    meta['motherboard'] = mb_model
                    break
        elif spec_text:
            meta_warnings.append('MOTHERBOARD')
        
        # Store warnings in meta for frontend display
        if meta_warnings:
            meta['warnings'] = meta_warnings
        
        # Fallback: try hardcoded positions if nothing found
        if 'opportunity_name' not in meta:
            try:
                val = df.iloc[1, 3]
                if pd.notna(val):
                    meta['opportunity_name'] = str(val).strip()
            except:
                pass
        if 'model_name' not in meta:
            try:
                val = df.iloc[2, 3]
                if pd.notna(val):
                    raw = str(val).strip()
                    m = re.search(r'\((\d+)', raw)
                    if m:
                        meta['model_qty'] = m.group(1)
                        meta['model_name'] = raw.split('(')[0].strip()
                    else:
                        meta['model_name'] = raw
            except:
                pass
        
        if return_cell_marks:
            return meta, cell_marks
        return meta

    def _find_region_row(self, df: pd.DataFrame, keywords_str: str, start_row: int = 0) -> int:
        """Find the first row containing any of the given keywords.
        Three-pass matching: (1) word boundary, (2) substring, (3) fuzzy match (edit distance ≤2).
        Returns row index or -1.
        """
        import re
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        
        # First pass: word boundary matching
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
        
        # Second pass: substring matching
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
        
        # Third pass: fuzzy matching (edit distance ≤2 for typo tolerance)
        # Only apply to keywords with ≥4 chars to avoid false positives on short keywords
        def _edit_distance(s1: str, s2: str) -> int:
            """Compute Levenshtein edit distance between two strings."""
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
                    substitutions = prev_row[j] + (c1 != c2)
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
                    # Skip fuzzy matching for short keywords (≤3 chars) to avoid false positives
                    if len(kw_lower) <= 3:
                        continue
                    # Check if any word in the cell is within edit distance 2 of the keyword
                    cell_words = re.findall(r'[a-z]+', cell_lower)
                    for word in cell_words:
                        if abs(len(word) - len(kw_lower)) <= 2:  # Quick length filter
                            if _edit_distance(word, kw_lower) <= 2:
                                return r
        
        return -1
    
    def _col_letter_to_index(self, letter: str) -> int:
        """Convert column letter (A=0, B=1, ..., Z=25, AA=26) to 0-based index."""
        letter = letter.strip().upper()
        result = 0
        for ch in letter:
            result = result * 26 + (ord(ch) - ord('A') + 1)
        return result - 1

    def _parse_items(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parse BOM items from Excel sheet using configured L6 and KP region configs.
        
        Uses region_start_keywords and region_end_keywords to identify L6 and KP sections,
        then extracts items using field_mapping column letters.
        """
        items = []
        
        # Parse L6 region config
        l6_cfg = self._l6_region_config
        l6_field_map = l6_cfg.get('field_mapping', {})
        if isinstance(l6_field_map, str):
            try:
                l6_field_map = json.loads(l6_field_map)
            except:
                l6_field_map = {"catalogue": "D", "description": "E", "quantity": "F"}
        
        # Parse KP region config
        kp_cfg = self._kp_region_config
        kp_field_map = kp_cfg.get('field_mapping', {})
        if isinstance(kp_field_map, str):
            try:
                kp_field_map = json.loads(kp_field_map)
            except:
                kp_field_map = {"catalogue": "D", "model": "E", "quantity": "F", "price": "G"}
        
        # Find L6 region
        l6_start = self._find_region_row(df, l6_cfg.get('region_start_keywords', 'L6'))
        l6_end = self._find_region_row(df, l6_cfg.get('region_end_keywords', 'Keyparts,KP'), start_row=l6_start + 1 if l6_start >= 0 else 0)
        
        # Find KP region
        kp_start = l6_end if l6_end >= 0 else self._find_region_row(df, kp_cfg.get('region_start_keywords', 'Keyparts,KP'))
        kp_end = self._find_region_row(df, kp_cfg.get('region_end_keywords', 'Warranty,Total'), start_row=kp_start + 1 if kp_start >= 0 else 0)
        
        # Extract L6 items
        if l6_start >= 0:
            end_row = l6_end if l6_end > l6_start else len(df)
            for r in range(l6_start + 1, end_row):  # skip header row
                try:
                    cat_col = self._col_letter_to_index(l6_field_map.get('catalogue', 'D'))
                    desc_col = self._col_letter_to_index(l6_field_map.get('description', 'E'))
                    qty_col = self._col_letter_to_index(l6_field_map.get('quantity', 'F'))
                    
                    catalogue = str(df.iloc[r, cat_col]).strip() if cat_col < df.shape[1] and pd.notna(df.iloc[r, cat_col]) else ''
                    description = str(df.iloc[r, desc_col]).strip() if desc_col < df.shape[1] and pd.notna(df.iloc[r, desc_col]) else ''
                    qty = 1
                    if qty_col < df.shape[1] and pd.notna(df.iloc[r, qty_col]):
                        try:
                            qty = int(float(df.iloc[r, qty_col]))
                        except:
                            qty = 1
                    
                    if not catalogue or catalogue.lower() in ['nan', 'none', '', 'catalogue', 'component description']:
                        continue
                    
                    items.append({
                        'category': 'L6',
                        'part_name': catalogue,
                        'spec': description,
                        'qty': qty,
                        'confirmed_price': None,
                        'currency': 'RMB'
                    })
                except:
                    continue
        
        # Extract KP items
        if kp_start >= 0:
            end_row = kp_end if kp_end > kp_start else len(df)
            for r in range(kp_start + 1, end_row):  # skip header row
                try:
                    cat_col = self._col_letter_to_index(kp_field_map.get('catalogue', 'D'))
                    model_col = self._col_letter_to_index(kp_field_map.get('model', 'E'))
                    qty_col = self._col_letter_to_index(kp_field_map.get('quantity', 'F'))
                    price_col = self._col_letter_to_index(kp_field_map.get('price', 'G'))
                    
                    catalogue = str(df.iloc[r, cat_col]).strip() if cat_col < df.shape[1] and pd.notna(df.iloc[r, cat_col]) else ''
                    model = str(df.iloc[r, model_col]).strip() if model_col < df.shape[1] and pd.notna(df.iloc[r, model_col]) else ''
                    qty = 1
                    if qty_col < df.shape[1] and pd.notna(df.iloc[r, qty_col]):
                        try:
                            qty = int(float(df.iloc[r, qty_col]))
                        except:
                            qty = 1
                    
                    price = None
                    if price_col < df.shape[1] and pd.notna(df.iloc[r, price_col]):
                        price_val = df.iloc[r, price_col]
                        if isinstance(price_val, str) and price_val.startswith('='):
                            try:
                                formula = price_val[1:]
                                price = _safe_eval_math(formula)
                            except:
                                pass
                        else:
                            try:
                                price = float(price_val)
                            except:
                                pass
                    
                    if not catalogue or catalogue.lower() in ['nan', 'none', '', 'catalogue']:
                        continue
                    
                    # Determine if USD (e.g., CPU items)
                    is_usd = False
                    if 'cpu' in catalogue.lower() or 'processor' in catalogue.lower():
                        if 'usd' in model.lower() or '$' in model:
                            is_usd = True
                    
                    items.append({
                        'category': 'Key Parts',
                        'part_name': catalogue,
                        'spec': model,
                        'qty': qty,
                        'confirmed_price': price,
                        'currency': 'USD' if is_usd else 'RMB'
                    })
                except:
                    continue
        
        # Extract Warranty items (if Warranty region exists)
        warranty_start = self._find_region_row(df, 'Warranty', start_row=kp_start + 1 if kp_start >= 0 else 0)
        warranty_end = self._find_region_row(df, 'Total,Total Price', start_row=warranty_start + 1 if warranty_start >= 0 else 0)
        
        if warranty_start >= 0:
            end_row = warranty_end if warranty_end > warranty_start else len(df)
            for r in range(warranty_start + 1, end_row):
                try:
                    # Warranty format: row number, type (L6/KP), description
                    type_col = 2  # Column C (0-indexed)
                    desc_col = 3  # Column D
                    
                    warranty_type = str(df.iloc[r, type_col]).strip() if pd.notna(df.iloc[r, type_col]) else ''
                    description = str(df.iloc[r, desc_col]).strip() if pd.notna(df.iloc[r, desc_col]) else ''
                    
                    if not description or description.lower() in ['nan', 'none', '']:
                        continue
                    
                    # Extract warranty years from description
                    years = None
                    m = re.search(r'质保(\d+)年', description)
                    if m:
                        years = int(m.group(1))
                    
                    items.append({
                        'category': 'Warranty',
                        'part_name': warranty_type,
                        'spec': description,
                        'qty': 1,
                        'confirmed_price': None,
                        'currency': 'RMB',
                        'warranty_years': years
                    })
                except:
                    continue
        
        return pd.DataFrame(items) if items else pd.DataFrame()

    # ==================== 2. Price Enrichment (via Repository) ====================

    def enrich_config(self, items_df: pd.DataFrame, meta: Optional[dict] = None) -> pd.DataFrame:
        """Enrich items with DB price match status (NO auto-fill).
        Uses kp_repo instead of direct sqlite3 queries."""
        if items_df.empty:
            return items_df

        # Fetch all latest KP prices at once (one query via repo)
        kp_latest = self.kp_repo.get_latest_prices()
        kp_dict = {r['model'].lower().strip(): r['price'] for r in kp_latest}

        items = items_df.copy()
        items['match_status'] = ""
        items['db_price'] = None
        items['base_price'] = items['confirmed_price']
        items['is_usd_cpu'] = items.get('currency', 'RMB') == 'USD'
        items['profit_margin'] = 10.0  # default

        for idx, row in items.iterrows():
            cat = row['category']
            name = str(row['part_name']).lower().strip()
            spec = str(row.get('spec', '')).lower().strip()
            original_price = row['confirmed_price']
            db_price = None

            if cat == 'Key Parts':
                if name in kp_dict:
                    db_price = kp_dict[name]
                elif spec and len(spec) > 2:
                    fuzzy = self.kp_repo.fuzzy_match_price(spec)
                    if fuzzy:
                        db_price = fuzzy['price']

            items.at[idx, 'db_price'] = db_price

            if db_price is not None:
                if pd.isna(original_price) or original_price == 0:
                    items.at[idx, 'match_status'] = f"⚠️ 待填入 [DB={db_price}]"
                else:
                    if abs(float(original_price) - db_price) > self._price_diff_threshold:
                        items.at[idx, 'match_status'] = f"⚠️ 差异 (Excel: {original_price}, DB: {db_price})"
                    else:
                        items.at[idx, 'match_status'] = f"✅ 一致 [DB={db_price}]"
            else:
                if pd.isna(original_price) or original_price == 0:
                    items.at[idx, 'match_status'] = "❌ 缺失 (请填写)"
                else:
                    items.at[idx, 'match_status'] = "🆕 新部件"

        # NaN sanitization for JSON serialization
        for col in items.columns:
            if items[col].dtype == object:
                items[col] = items[col].fillna("")
            else:
                items[col] = items[col].fillna(0)

        return items

    def match_l6_total(self, meta: dict) -> tuple:
        """Match L6 price using configurable dimensions via l6_repo."
        Returns (price, matched_record) tuple.
        matched_record includes match_score, matched_dims, total_dims, match_type.
        """
        l6_records = self.l6_repo.get_all_for_matching()
        if not l6_records:
            return None, None

        l6_df = pd.DataFrame(l6_records)

        # Build dimension values from meta
        dim_values = {
            'chassis': str(meta.get('chassis_form', '')).strip(),
            'model': str(meta.get('l6_model_type', '')).strip(),
            'drive_bays': str(meta.get('drive_bays', '')).strip(),
            'psu': str(meta.get('psu', '')).strip(),
            'motherboard': str(meta.get('motherboard', '')).strip(),
        }

        total_dims = len(self._l6_match_dims)

        def _match_dim(candidates_df, dim, val):
            """Match a single dimension with fuzzy/degrade support.
            Returns (filtered_df, matched: bool, is_fuzzy: bool, skipped: bool).
            skipped=True means the dimension was not evaluated (val was empty)."""
            if not val:
                return candidates_df, True, False, True
            # Exact match
            mask = candidates_df[dim].str.strip() == val
            if mask.any():
                return candidates_df[mask], True, False, False
            # Chassis fuzzy match
            if dim == 'chassis' and self._allow_chassis_fuzzy and self._chassis_fuzzy_rules:
                for rule in self._chassis_fuzzy_rules:
                    if val == rule.get('from', ''):
                        fuzzy_val = rule.get('to', '')
                        mask = candidates_df[dim].str.strip() == fuzzy_val
                        if mask.any():
                            return candidates_df[mask], True, True, False
            # Motherboard degrade match: allow other known motherboards
            if dim == 'motherboard' and self._allow_motherboard_fallback and self._mb_mappings:
                for cpu_feat, mb_model in self._mb_mappings:
                    if mb_model == val:
                        alt_mask = candidates_df[dim].str.strip().isin(
                            [m for _, m in self._mb_mappings if m != val]
                        )
                        if alt_mask.any():
                            return candidates_df[alt_mask], True, True, False
                        break
            return candidates_df.iloc[0:0], False, False, False

        # Try full match using configured dimensions
        candidates = l6_df.copy()
        matched_count = 0
        evaluated_dims = 0
        fuzzy_used = False
        for dim in self._l6_match_dims:
            val = dim_values.get(dim, '')
            candidates, matched, is_fuzzy, skipped = _match_dim(candidates, dim, val)
            if skipped:
                continue
            evaluated_dims += 1
            if matched:
                matched_count += 1
                if is_fuzzy:
                    fuzzy_used = True
            else:
                candidates = candidates.iloc[0:0]
            if candidates.empty:
                break

        if not candidates.empty and evaluated_dims > 0:
            matched = candidates.iloc[0].to_dict()
            match_score = int((matched_count / evaluated_dims) * 100)
            matched['match_score'] = match_score
            matched['matched_dims'] = matched_count
            matched['total_dims'] = evaluated_dims
            if fuzzy_used:
                matched['match_type'] = f'模糊匹配({matched_count}/{evaluated_dims})'
            elif matched_count == evaluated_dims:
                matched['match_type'] = '精确匹配'
            else:
                matched['match_type'] = f'部分匹配({matched_count}/{evaluated_dims})'
            # 确保 update_date 字段存在
            if 'update_date' not in matched:
                matched['update_date'] = matched.get('date', '')
            return float(matched['price']), matched

        # Fallback: try configured fallback dimensions
        candidates = l6_df.copy()
        fallback_matched = 0
        fallback_evaluated = 0
        for dim in self._l6_fallback_dims:
            val = dim_values.get(dim, '')
            candidates, matched, _, skipped = _match_dim(candidates, dim, val)
            if skipped:
                continue
            fallback_evaluated += 1
            if matched:
                fallback_matched += 1
            else:
                candidates = candidates.iloc[0:0]
            if candidates.empty:
                break

        if candidates.empty:
            # 未匹配：返回最佳部分匹配记录（用于前端展示）
            best = self._find_best_partial_match(l6_df, dim_values)
            if best:
                return None, best
            return None, None

        matched = candidates.iloc[0].to_dict()
        score_base = fallback_evaluated if fallback_evaluated > 0 else total_dims
        match_score = int((fallback_matched / score_base) * 100) if score_base > 0 else 80
        matched['match_score'] = match_score
        matched['matched_dims'] = fallback_matched
        matched['total_dims'] = score_base
        matched['match_type'] = '降级匹配'
        return float(matched['price']), matched

    def _find_best_partial_match(self, l6_df: pd.DataFrame, dim_values: dict) -> dict:
        """Find the record with the most matching dimensions, for display when no full match.
        Returns top 3 candidates as a dict with 'best' and 'candidates' keys."""
        total_dims = len(self._l6_match_dims)
        scored_records = []

        for _, row in l6_df.iterrows():
            score = 0
            for dim in self._l6_match_dims:
                val = dim_values.get(dim, '')
                if val and str(row.get(dim, '')).strip() == val:
                    score += 1
            if score > 0:
                record = row.to_dict()
                record['match_score'] = int((score / total_dims) * 100) if total_dims > 0 else 0
                record['matched_dims'] = score
                record['total_dims'] = total_dims
                record['match_type'] = '未匹配'
                scored_records.append(record)

        if not scored_records:
            return None

        # Sort by score descending, take top 3
        scored_records.sort(key=lambda x: x['match_score'], reverse=True)
        top_candidates = scored_records[:3]

        # Return structure: best record + all candidates
        result = top_candidates[0].copy()
        result['candidates'] = top_candidates
        return result

    def preview_l6_match(self, dim_values: dict) -> dict:
        """Preview L6 matching process step by step."
        dim_values: {chassis, model, drive_bays, psu, motherboard}
        Returns: {steps: [...], final_match: {...} or None}
        """
        l6_records = self.l6_repo.get_all_for_matching()
        if not l6_records:
            return {"steps": [], "final_match": None, "error": "L6价格库为空"}

        l6_df = pd.DataFrame(l6_records)
        steps = []
        
        # Normalize dim_values
        normalized = {
            'chassis': str(dim_values.get('chassis', '')).strip(),
            'model': str(dim_values.get('model', '')).strip(),
            'drive_bays': str(dim_values.get('drive_bays', '')).strip(),
            'psu': str(dim_values.get('psu', '')).strip(),
            'motherboard': str(dim_values.get('motherboard', '')).strip(),
        }

        # Step 1: Full match on all provided dimensions
        candidates = l6_df.copy()
        filter_desc_parts = []
        evaluated_count = 0
        matched_count = 0
        for dim in self._l6_match_dims:
            val = normalized.get(dim, '')
            if not val:
                continue
            evaluated_count += 1
            mask = candidates[dim].str.strip() == val
            if mask.any():
                candidates = candidates[mask]
                matched_count += 1
                filter_desc_parts.append(f"{dim}={val}")
            else:
                candidates = candidates.iloc[0:0]
                filter_desc_parts.append(f"{dim}={val} (无匹配)")
            if candidates.empty:
                break

        steps.append({
            "step": 1,
            "description": f"精确匹配({matched_count}/{evaluated_count}维)" if evaluated_count > 0 else "无条件",
            "filter_desc": " + ".join(filter_desc_parts) if filter_desc_parts else "无条件",
            "candidates": candidates.to_dict('records') if not candidates.empty else [],
            "matched": not candidates.empty
        })

        if not candidates.empty:
            matched = candidates.iloc[0].to_dict()
            return {"steps": steps, "final_match": matched}

        # Step 2: Motherboard fallback (if enabled) — use _mb_mappings like match_l6_total
        if self._allow_motherboard_fallback and normalized.get('motherboard') and self._mb_mappings:
            mb_val = normalized['motherboard']
            # Check if this is a known motherboard and find alternatives
            alt_motherboards = [m for _, m in self._mb_mappings if m != mb_val]
            if alt_motherboards:
                candidates = l6_df.copy()
                filter_desc_parts = []

                for dim in self._l6_match_dims:
                    val = normalized.get(dim, '')
                    if dim == 'motherboard':
                        # Use alternative motherboards from mappings
                        mask = candidates[dim].str.strip().isin(alt_motherboards)
                        if mask.any():
                            candidates = candidates[mask]
                            filter_desc_parts.append(f"motherboard=任意已知主板(降级)")
                        else:
                            candidates = candidates.iloc[0:0]
                            filter_desc_parts.append(f"motherboard=无匹配")
                    elif val:
                        mask = candidates[dim].str.strip() == val
                        if mask.any():
                            candidates = candidates[mask]
                            filter_desc_parts.append(f"{dim}={val}")
                        else:
                            candidates = candidates.iloc[0:0]
                            filter_desc_parts.append(f"{dim}={val} (无匹配)")
                    if candidates.empty:
                        break

                steps.append({
                    "step": len(steps) + 1,
                    "description": f"主板降级匹配 (原值: {mb_val})",
                    "filter_desc": " + ".join(filter_desc_parts),
                    "candidates": candidates.to_dict('records') if not candidates.empty else [],
                    "matched": not candidates.empty
                })

                if not candidates.empty:
                    matched = candidates.iloc[0].to_dict()
                    return {"steps": steps, "final_match": matched}

        # Step 3: Chassis fuzzy match (if enabled)
        if self._allow_chassis_fuzzy and normalized.get('chassis'):
            chassis_val = normalized['chassis']
            # Find fuzzy rule
            fuzzy_rule = None
            for rule in self._chassis_fuzzy_rules:
                if rule.get('from') == chassis_val:
                    fuzzy_rule = rule
                    break
            
            if fuzzy_rule:
                candidates = l6_df.copy()
                filter_desc_parts = []
                
                for dim in self._l6_match_dims:
                    val = normalized.get(dim, '')
                    if dim == 'chassis':
                        val = fuzzy_rule['to']
                    if val:
                        mask = candidates[dim].str.strip() == val
                        if mask.any():
                            candidates = candidates[mask]
                            if dim == 'chassis':
                                filter_desc_parts.append(f"chassis={fuzzy_rule['to']} (模糊至{chassis_val})")
                            else:
                                filter_desc_parts.append(f"{dim}={val}")
                        else:
                            candidates = candidates.iloc[0:0]
                            filter_desc_parts.append(f"{dim}={val} (无匹配?")
                    if candidates.empty:
                        break

                steps.append({
                    "step": 3,
                    "description": f"机箱模糊匹配 ({chassis_val} →{fuzzy_rule['to']})",
                    "filter_desc": " + ".join(filter_desc_parts),
                    "candidates": candidates.to_dict('records') if not candidates.empty else [],
                    "matched": not candidates.empty
                })

                if not candidates.empty:
                    matched = candidates.iloc[0].to_dict()
                    return {"steps": steps, "final_match": matched}

        # Step 4: No match
        steps.append({
            "step": len(steps) + 1,
            "description": "报错：找不到匹配的L6价格",
            "filter_desc": "",
            "candidates": [],
            "matched": False
        })

        return {"steps": steps, "final_match": None}

    # ==================== 3. KP Sync & History (via Repository) ====================

    def get_kp_price_history(self, model: str, limit: int = 10) -> list:
        return self.kp_repo.get_price_history(model, limit)

    def sync_kp_prices_to_db(self, configs_data: dict) -> int:
        """Compare and insert new KP prices into DB if different from latest."""
        today = datetime.now().strftime('%Y-%m-%d')
        new_records = 0

        # Use configurable category mapping
        cat_map = self._kp_cat_map

        # Batch-load all latest prices once (avoid N+1 queries)
        latest_prices = {}
        try:
            all_latest = self.kp_repo.get_latest_prices()
            latest_prices = {
                r['model'].lower().strip(): float(r['price'])
                for r in all_latest
                if r.get('model') and r.get('price') is not None
            }
        except Exception:
            pass

        pending_inserts = []  # Collect for batch insert

        for cfg_name, items_df in configs_data.items():
            if items_df.empty:
                continue
            if 'category' not in items_df.columns:
                continue

            kp_items = items_df[items_df['category'] == 'Key Parts'].copy()
            if kp_items.empty:
                continue
            for idx, row in kp_items.iterrows():
                part_name = str(row.get('part_name', '')).strip()
                spec = str(row.get('spec', '')).strip()

                category = None
                model = None
                lower_name = part_name.lower()
                for keyword, std_cat in cat_map.items():
                    if keyword in lower_name:
                        category = std_cat
                        model = spec if spec else part_name
                        break
                if category is None:
                    category = row.get('category', 'Key Parts')
                    model = part_name
                if not model:
                    continue

                new_price = row.get('base_price', 0)
                if pd.isna(new_price) or new_price == 0:
                    continue

                # In-memory lookup instead of DB query per item
                db_price = latest_prices.get(model.lower().strip())
                if db_price is not None and abs(float(new_price) - db_price) < 0.01:
                    continue

                pending_inserts.append((category, model, round(float(new_price), 2)))

        # Batch insert all new prices
        for category, model, price in pending_inserts:
            self.kp_repo.insert_price(category, model, price, 'RMB', today, '报价系统更新')
            new_records += 1

        return new_records

    # ==================== 4. Project CRUD (via Repository) ====================

    def save_opportunity(self, opportunity_info: dict, configs_data: dict, config_descriptions: dict = None, config_quantities: dict = None, config_server_models: dict = None) -> dict:
        """Save opportunity meta + items to projects.db + quotations.db."""
        import time, random
        opportunity_id = opportunity_info.get('opportunity_id', '').strip()
        if not opportunity_id:
            # Auto-generate: {opportunity_name}_{timestamp}_{random4}
            name = opportunity_info.get('opportunity_name', 'opportunity')
            ts = time.strftime('%m%d%H%M%S')
            rand = f'{random.randint(0, 0xFFFF):04x}'
            opportunity_id = f'{name}_{ts}_{rand}'
            opportunity_info['opportunity_id'] = opportunity_id
        self.opportunity_repo.create_or_update_opportunity(opportunity_id, opportunity_info)
        
        # Convert configs_data to items and save via QuotationRepository
        q_repo = self._get_quotation_repo()
        try:
            # Create a quotation for this opportunity
            quotation = q_repo.create(
                opportunity_id=opportunity_id,
                quotation_date=datetime.now().strftime('%Y-%m-%d')
            )
            quotation_id = quotation.quotation_id
            
            # Flatten all config items into a single list
            all_items = []
            for cfg_name, cfg_data in configs_data.items():
                if isinstance(cfg_data, pd.DataFrame):
                    items = cfg_data.to_dict('records')
                elif isinstance(cfg_data, dict):
                    items = [cfg_data]
                elif isinstance(cfg_data, list):
                    items = cfg_data
                else:
                    continue
                for item in items:
                    item['config_name'] = item.get('config_name', cfg_name)
                    # Ensure required fields
                    item.setdefault('confirmed_price', 0.0)
                    item.setdefault('base_price', 0.0)
                    item.setdefault('final_price', 0.0)
                    item.setdefault('profit_margin', 0.0)
                    item.setdefault('spec', '')
                    item.setdefault('category', '')
                    item.setdefault('part_name', '')
                    item.setdefault('qty', 0)
                    item.setdefault('is_usd_cpu', False)
                all_items.extend(items)
            
            # Calculate totals before saving
            l6_total = sum(i.get('final_price', 0) for i in all_items if i.get('category') == 'L6')
            kp_total = sum(i.get('final_price', 0) for i in all_items if i.get('category') == 'Key Parts')
            grand_total = l6_total + kp_total
            total_qty = sum(i.get('qty', 0) for i in all_items if i.get('category') == 'L6')
            config_count = len(set(i.get('config_name', 'CFG1') for i in all_items))
            
            # Update quotation with computed totals
            q_repo.update(quotation_id,
                l6_price=l6_total,
                total_price=grand_total,
                total_qty=total_qty,
                config_count=config_count
            )
            
            # Save config descriptions if provided
            if config_descriptions:
                q_repo.update(quotation_id, config_descriptions=config_descriptions)
            
            # Save config quantities if provided
            if config_quantities:
                q_repo.update(quotation_id, config_quantities=config_quantities)
            
            # Save config server_models if provided
            if config_server_models:
                q_repo.update(quotation_id, config_server_models=config_server_models)
            
            # Save items
            item_count = q_repo.save_items(quotation_id, all_items)
        finally:
            q_repo.close()
        
        return {"status": "success", "items_saved": item_count, "opportunity_id": opportunity_id, "quotation_id": quotation_id}

    def get_opportunity_details(self, opportunity_id: str) -> Optional[dict]:
        """Get opportunity with its latest quotation's items (for export)."""
        q_repo = self._get_quotation_repo()
        try:
            project_dict = self.opportunity_repo.get_opportunity(opportunity_id)

            if not project_dict:
                return None
            
            # Get all active quotations for this opportunity
            quotations = q_repo.get_by_opportunity(opportunity_id)
            
            meta = {
                'opportunity_id': project_dict.get('opportunity_id', ''),
                'folder_name': project_dict.get('folder_name', ''),
                'opportunity_name': project_dict.get('opportunity_name', ''),
                'customer_name': project_dict.get('customer_name', ''),
                'sales_person': project_dict.get('sales_person', ''),
                'fae': project_dict.get('fae', ''),
                'platform_type': project_dict.get('platform_type', ''),
                'chassis_form': project_dict.get('chassis_form', ''),
                'total_qty': project_dict.get('total_qty', 0),
                'status': project_dict.get('status', 'active'),
                'created_at': project_dict.get('created_at', ''),
                'updated_at': project_dict.get('updated_at', ''),
                'date': '',
            }
            
            # Enrich meta from the latest quotation
            if quotations:
                latest = quotations[0]  # already ordered by version desc
                meta['date'] = latest.quotation_date or meta.get('date', '')
                meta['quotation_id'] = latest.quotation_id
                meta['version'] = latest.version
                # Pass config_quantities for cover sheet rendering
                if hasattr(latest, 'config_quantities') and latest.config_quantities:
                    meta['config_quantities'] = latest.config_quantities
                # Pass config_descriptions for config sheet rendering
                if hasattr(latest, 'config_descriptions') and latest.config_descriptions:
                    meta['config_descriptions'] = latest.config_descriptions
                # Pass config_server_models for config sheet rendering
                if hasattr(latest, 'config_server_models') and latest.config_server_models:
                    meta['config_server_models'] = latest.config_server_models
            
            # Build configs from quotations
            configs = {}
            for quo in quotations:
                items = q_repo.get_items(quo.quotation_id)
                cfg_items = [item.to_dict() for item in items]
                # Group by config_name
                for item in cfg_items:
                    cfg_name = item.get('config_name', 'CFG1')
                    if cfg_name not in configs:
                        configs[cfg_name] = []
                    configs[cfg_name].append(item)
            
            # Fallback: if no quotations, try to return empty configs
            if not configs:
                configs['CFG1'] = []
            
            return {'meta': meta, 'configs': configs, 'quotations': [q.to_dict() for q in quotations]}
        finally:
            q_repo.close()

    def update_project_meta(self, opportunity_id: str, updates: dict) -> bool:
        return self.opportunity_repo.update_meta(opportunity_id, updates)

    # ==================== 5. Excel Export (template-driven) ====================

    def _load_config(self) -> dict:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"tax_rate": 0.13, "usd_to_rmb": 7.0, "profit_margin": 0.1, "warranty_fee_rate": 0.02}

    def _resolve_font(self, font_dict: dict) -> Font:
        """Convert font dict from template JSON to openpyxl Font."""
        return Font(
            name=font_dict.get('name', '宋体'),
            size=font_dict.get('size', 11),
            bold=font_dict.get('bold', False),
            italic=font_dict.get('italic', False),
            color=font_dict.get('color', '000000')
        )

    def _load_template(self, template_id: str = None) -> dict:
        """Load export template from DB. Returns None if not found."""
        if not self.export_template_repo:
            return None
        
        if template_id:
            return self.export_template_repo.get_by_id(int(template_id))
        else:
            # Get default template
            templates = self.export_template_repo.list()
            for t in templates:
                if t.get('is_default'):
                    return t
            return None

    def generate_excel(self, opportunity_id: str, template_id: str = None):
        """Generate Excel using template from DB. Requires template with fileBuffer."""
        details = self.get_opportunity_details(opportunity_id)
        if not details:
            return None, "Error: Project not found"
        meta = details['meta']
        configs = details['configs']
        template = self._load_template(template_id)
        if not template:
            return None, "请先在导出模板管理页创建模板"
        template_json = template.get('template_json', {})
        cover_tpl = template_json.get('cover', {})
        config_tpl = template_json.get('config_sheet', {})

        # Get template files - MUST have fileBuffer
        cover_file, config_file = self._get_template_files(template)
        if not cover_file and not config_file:
            return None, "导出模板缺少 Excel 文件，请重新上传模板"

        # Load workbook: merge cover + config template sheets into one
        if cover_file:
            wb = openpyxl.load_workbook(cover_file)
        else:
            wb = openpyxl.Workbook()
            # Remove default sheet if config will add its own
            wb.remove(wb.active)

        if config_file:
            config_wb = openpyxl.load_workbook(config_file)
            for src_ws in config_wb.worksheets:
                # Skip if sheet name already exists (avoid duplicate)
                if src_ws.title in wb.sheetnames:
                    # Rename to avoid conflict
                    new_title = f"{src_ws.title}_config"
                    self._copy_worksheet(wb, src_ws, new_title)
                else:
                    self._copy_worksheet(wb, src_ws, src_ws.title)
            config_wb.close()

        # Convert configs from list-of-dicts to DataFrames
        config_dfs = {}
        for cfg_name, items_list in configs.items():
            config_dfs[cfg_name] = pd.DataFrame(items_list)

        # Add computed fields to meta for config sheet bindings
        # model_name: from first L6 item's spec or part_name
        model_name = ''
        for cfg_name, df in config_dfs.items():
            l6_df = df[df['category'] == 'L6'] if not df.empty else pd.DataFrame()
            if not l6_df.empty:
                model_name = l6_df.iloc[0].get('spec', '') or l6_df.iloc[0].get('part_name', '') or ''
                break
        meta['model_name'] = model_name
        meta['model_name_with_qty'] = f"{model_name} x{meta.get('total_qty', 0)}" if model_name else ''
        
        # l6_desc: summary of L6 part names
        l6_desc_parts = []
        for cfg_name, df in config_dfs.items():
            l6_df = df[df['category'] == 'L6'] if not df.empty else pd.DataFrame()
            if not l6_df.empty:
                for _, row in l6_df.iterrows():
                    part_name = row.get('part_name', '')
                    if part_name and part_name not in l6_desc_parts:
                        l6_desc_parts.append(part_name)
        meta['l6_desc'] = ', '.join(l6_desc_parts[:5])  # Limit to first 5
        
        # business_person: fallback to sales_person if not set
        if 'business_person' not in meta or not meta.get('business_person'):
            meta['business_person'] = meta.get('sales_person', '')

        # Fill cover sheet - use actual Excel sheet, not configured sheet_name
        # wb.sheetnames[0] is cover sheet (from cover_fileBuffer)
        # wb.sheetnames[1] is config sheet (from config_fileBuffer)
        if len(wb.sheetnames) >= 1:
            ws1 = wb[wb.sheetnames[0]]
        else:
            ws1 = wb.create_sheet(title='封面')

        cover_bindings = cover_tpl.get('bindings', [])
        if cover_bindings:
            self._fill_from_bindings(ws1, cover_bindings, meta, config_dfs, inherit_style=True)

        # Fill config sheets
        config_bindings = config_tpl.get('bindings', [])
        
        if len(wb.sheetnames) >= 2:
            # Keep the original template sheet untouched; each config gets a
            # fresh copy so filling one config never bleeds into the next.
            ws_config_original = wb[wb.sheetnames[1]]
            filled_any = False
            for cfg_name, items_df in config_dfs.items():
                sheet_name = self._generate_sheet_name(wb, meta, items_df, cfg_name, config_tpl)
                ws_copy = self._copy_worksheet(wb, ws_config_original, sheet_name)
                if config_bindings:
                    self._fill_from_bindings(ws_copy, config_bindings, meta, {cfg_name: items_df}, inherit_style=True)
                filled_any = True
            # Remove the pristine template sheet once all configs are filled
            if filled_any:
                wb.remove(ws_config_original)
        else:
            # No config sheet in template, create from scratch
            for cfg_name, items_df in config_dfs.items():
                sheet_name = self._generate_sheet_name(wb, meta, items_df, cfg_name, config_tpl)
                ws = wb.create_sheet(title=sheet_name)
                
                if config_bindings:
                    self._fill_from_bindings(ws, config_bindings, meta, {cfg_name: items_df}, inherit_style=False)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        tpl_name = template.get('name', 'formal')
        return output, f"{opportunity_id}_{tpl_name}.xlsx"
    
    def _get_template_files(self, template: dict) -> tuple[Optional[io.BytesIO], Optional[io.BytesIO]]:
        """Decode cover/config template fileBuffers into in-memory streams.

        openpyxl.load_workbook accepts file-like objects, so we avoid writing
        temp files that would never be cleaned up.
        """
        import base64

        template_json = template.get('template_json', {})
        cover_tpl = template_json.get('cover', {})
        config_tpl = template_json.get('config_sheet', {})

        def _decode(buf):
            if not buf:
                return None
            try:
                return io.BytesIO(base64.b64decode(buf))
            except Exception as e:
                print(f"Warning: Failed to decode template fileBuffer: {e}")
                return None

        return _decode(cover_tpl.get('fileBuffer')), _decode(config_tpl.get('fileBuffer'))
    
    def _copy_worksheet(self, wb, source_ws, new_title: str):
        """Copy a worksheet within the same workbook."""
        from copy import copy
        
        # Create new sheet
        new_ws = wb.create_sheet(title=new_title)
        
        # Copy all cells and styles
        for row in source_ws.iter_rows():
            for cell in row:
                new_cell = new_ws.cell(row=cell.row, column=cell.column, value=cell.value)
                if cell.has_style:
                    new_cell.font = copy(cell.font)
                    new_cell.border = copy(cell.border)
                    new_cell.fill = copy(cell.fill)
                    new_cell.number_format = cell.number_format
                    new_cell.protection = copy(cell.protection)
                    new_cell.alignment = copy(cell.alignment)
        
        # Copy merged cells
        for merged_range in source_ws.merged_cells.ranges:
            new_ws.merge_cells(str(merged_range))
        
        # Copy column widths
        for col_letter, dim in source_ws.column_dimensions.items():
            new_ws.column_dimensions[col_letter].width = dim.width
        
        # Copy row heights
        for row_num, dim in source_ws.row_dimensions.items():
            if dim.height:
                new_ws.row_dimensions[row_num].height = dim.height
        
        return new_ws

    def _generate_sheet_name(self, wb, meta, items_df, cfg_name, config_tpl=None) -> str:
        """Generate unique sheet name for config.
        
        Supports template variables: {cfg_name}, {chassis_form}, {cpu_model}
        Default template: {cfg_name}
        """
        # Get sheet name template from config, default to {cfg_name}
        if config_tpl and 'sheetNameTemplate' in config_tpl:
            name_template = config_tpl['sheetNameTemplate']
        else:
            name_template = '{cfg_name}'
        
        # Extract variables
        chassis = meta.get('chassis_form', '')
        cpu_name = ''
        
        kp_items_df = items_df[items_df['category'] == 'Key Parts']
        if not kp_items_df.empty:
            cpu_rows = kp_items_df[kp_items_df['part_name'].str.contains('CPU|Processor', case=False, na=False)]
            if not cpu_rows.empty:
                cpu_name = cpu_rows.iloc[0].get('spec', '').strip()
        
        # Replace template variables
        sheet_name = name_template.format(
            cfg_name=cfg_name,
            chassis_form=chassis,
            cpu_model=cpu_name
        )
        
        # Clean invalid characters for Excel sheet names
        # Excel does not allow: \ / ? * [ ]
        import re
        sheet_name = re.sub(r'[\\/?*\[\]]', '', sheet_name)
        
        sheet_name = sheet_name[:31]
        base_name = sheet_name
        suffix = 1
        while sheet_name in wb.sheetnames:
            sheet_name = f"{base_name} ({suffix})"[:31]
            suffix += 1
        return sheet_name

    def _parse_cell_ref(self, cell_ref: str) -> tuple[int, int]:
        """Parse cell reference like 'A1' to (row, col) tuple."""
        import re
        match = re.match(r'([A-Z]+)(\d+)', cell_ref)
        if not match:
            return 1, 1
        col_str, row_str = match.groups()
        col = sum((ord(c) - ord('A') + 1) * (26 ** i) for i, c in enumerate(reversed(col_str)))
        return int(row_str), col

    def _col_letter_to_idx(self, col_letter: str) -> int:
        """Convert column letter(s) like 'A' or 'AA' to a 1-indexed column number."""
        col_letter = (col_letter or '').upper()
        return sum((ord(c) - ord('A') + 1) * (26 ** i) for i, c in enumerate(reversed(col_letter)))

    def _get_number_format(self) -> str:
        """Get Excel number_format string based on global precision config."""
        precision = self.rules_repo.get_number_precision() if self.rules_repo else 2
        format_map = {0: '#,##0', 2: '#,##0.00', 4: '#,##0.0000'}
        return format_map.get(precision, '#,##0.00')
    
    def _fill_from_bindings(self, ws, bindings: list, meta: dict, config_dfs: dict, inherit_style: bool = False):
        """Fill worksheet cells based on bindings configuration.
        
        Args:
            ws: openpyxl worksheet
            bindings: list of binding objects with cellAddress, fieldKey, dataType, etc.
            meta: opportunity metadata dict
            config_dfs: dict of {cfg_name: DataFrame} for config items
            inherit_style: if True, copy style from template row for dynamic rows
        """
        from copy import copy
        
        number_format = self._get_number_format()
        
        # Separate static and dynamic bindings
        static_bindings = [b for b in bindings if b.get('dataType') == 'static']
        dynamic_bindings = [b for b in bindings if b.get('dataType') == 'dynamic']
        
        # Fill static fields
        for binding in static_bindings:
            cell_address = binding.get('cellAddress')
            field_key = binding.get('fieldKey')
            if not cell_address or not field_key:
                continue
            
            row, col = self._parse_cell_ref(cell_address)
            
            # Check if this field should come from config description
            source = binding.get('source')
            source_column = binding.get('sourceColumn')
            
            if binding.get('staticValue') is not None:
                # Use staticValue directly if provided
                cell = ws.cell(row=row, column=col, value=binding.get('staticValue'))
                if isinstance(binding.get('staticValue'), (int, float)):
                    cell.number_format = number_format
            elif source == 'Config' and source_column == 'description':
                # Get description from the first config in config_dfs
                if config_dfs:
                    first_cfg_name = list(config_dfs.keys())[0]
                    # Try to get description from config metadata
                    # Note: description is stored in Workspace, not in DataFrame
                    # We need to pass it through meta or another mechanism
                    value = meta.get('config_descriptions', {}).get(first_cfg_name, '')
                    if value:
                        ws.cell(row=row, column=col, value=value)
            elif source == 'Config' and source_column == 'server_model':
                # Get server_model from the first config
                if config_dfs:
                    first_cfg_name = list(config_dfs.keys())[0]
                    value = meta.get('config_server_models', {}).get(first_cfg_name, '')
                    if value:
                        ws.cell(row=row, column=col, value=value)
            else:
                # Map fieldKey to meta field
                value = self._get_meta_value(field_key, meta)
                if value is not None:
                    cell = ws.cell(row=row, column=col, value=value)
                    if isinstance(value, (int, float)):
                        cell.number_format = number_format
        
        # Fill dynamic regions. Process from bottom to top so an insertion for
        # an upper binding correctly shifts lower bindings (and any static cells
        # below) down.
        dynamic_bindings.sort(
            key=lambda b: self._parse_cell_ref(b.get('cellAddress') or 'A1')[0],
            reverse=True,
        )
        for binding in dynamic_bindings:
            cell_address = binding.get('cellAddress')
            region_field_key = binding.get('regionFieldKey')
            field_mapping = binding.get('fieldMapping', {})
            template_row = binding.get('templateRow')
            
            if not cell_address or not region_field_key or not field_mapping:
                continue
            
            start_row, _ = self._parse_cell_ref(cell_address)
            
            # Get data for this region
            # regionFieldKey maps to config items (L6/KP/Warranty/config_summary)
            region_data = self._get_region_data(region_field_key, config_dfs, meta=meta, binding=binding)
            
            if not region_data:
                continue
            
            # The row to inherit style from: explicit templateRow, else the data start row
            style_source_row = template_row or start_row

            # Capture template row style + height BEFORE inserting any rows
            template_styles = {}
            template_height = None
            if inherit_style:
                for field_name, col_letter in field_mapping.items():
                    col_idx = self._col_letter_to_idx(col_letter)
                    template_cell = ws.cell(row=style_source_row, column=col_idx)
                    if template_cell.has_style:
                        template_styles[col_idx] = {
                            'font': copy(template_cell.font),
                            'border': copy(template_cell.border),
                            'fill': copy(template_cell.fill),
                            'number_format': template_cell.number_format,
                            'alignment': copy(template_cell.alignment),
                        }
                template_height = ws.row_dimensions[style_source_row].height

            # Insert physical rows for the additional data rows. start_row itself
            # is kept (first data row); insert (n-1) rows below it so data never
            # overwrites template content (e.g. totals, signatures below).
            extra_rows = max(0, len(region_data) - 1)
            if extra_rows > 0:
                ws.insert_rows(start_row + 1, extra_rows)
                for i in range(extra_rows):
                    target_row = start_row + 1 + i
                    if template_height is not None:
                        ws.row_dimensions[target_row].height = template_height
                    for col_idx, style in template_styles.items():
                        nc = ws.cell(row=target_row, column=col_idx)
                        nc.font = copy(style['font'])
                        nc.border = copy(style['border'])
                        nc.fill = copy(style['fill'])
                        nc.number_format = style['number_format']
                        nc.alignment = copy(style['alignment'])
            
            # Fill rows based on fieldMapping
            for idx, item in enumerate(region_data):
                current_row = start_row + idx
                for field_name, col_letter in field_mapping.items():
                    col_idx = self._col_letter_to_idx(col_letter)

                    # Map field_name to actual data key
                    value = self._map_field_to_value(field_name, item, meta)
                    
                    # Check if cell is part of a merged range
                    cell_ref = f'{col_letter}{current_row}'
                    is_merged = False
                    is_top_left = False
                    
                    for merged_range in ws.merged_cells.ranges:
                        if cell_ref in merged_range:
                            is_merged = True
                            # Check if this is the top-left cell
                            top_left = f'{merged_range.min_col}{merged_range.min_row}'
                            if cell_ref == top_left:
                                is_top_left = True
                            break
                    
                    # Only write if not merged or is top-left of merge
                    if not is_merged or is_top_left:
                        cell = ws.cell(row=current_row, column=col_idx, value=value)
                        
                        # Apply number_format for numeric values
                        if isinstance(value, (int, float)):
                            cell.number_format = number_format
                        
                        # Apply template row style if available
                        if inherit_style and col_idx in template_styles:
                            style = template_styles[col_idx]
                            cell.font = style['font']
                            cell.border = style['border']
                            cell.fill = style['fill']
                            # Don't override number_format if we just set it for numeric values
                            if not isinstance(value, (int, float)):
                                cell.number_format = style['number_format']
                            cell.alignment = style['alignment']
    
    def _map_field_to_value(self, field_name: str, item: dict, meta: dict = None) -> any:
        """Map field name from binding to actual data value.
        
        Args:
            field_name: field name from binding (e.g., 'item_no', 'catalogue', 'description')
            item: data item dict from region data
            meta: opportunity metadata (optional, for special fields)
        
        Returns:
            Mapped value or empty string if not found
        """
        # Direct mapping: field_name exists in item
        if field_name in item and item[field_name] is not None:
            return item[field_name]
        
        # Semantic mapping: map common field names to actual data keys
        mapping = {
            'item_no': lambda: item.get('item_no') or '',  # Numeric index, set by _get_region_data
            'catalogue': lambda: item.get('catalogue') or item.get('spec') or '',
            'description': lambda: item.get('description') or item.get('part_name') or '',
            'component': lambda: item.get('component') or item.get('part_name') or '',
            'quantity': lambda: item.get('quantity') or item.get('qty') or 0,
            'quotation': lambda: item.get('quotation') or item.get('final_price') or item.get('confirmed_price') or 0,
            'unit_price': lambda: item.get('unit_price') or item.get('final_price') or item.get('base_price') or 0,
            'total_price': lambda: item.get('total_price') or (item.get('final_price', 0) * item.get('qty', 1)) or 0,
            'note': lambda: item.get('note') or '',
        }
        
        if field_name in mapping:
            return mapping[field_name]()
        
        # Fallback: return empty string
        return ''
    
    def _get_meta_value(self, field_key: str, meta: dict):
        """Get value from meta dict based on fieldKey.
        
        Now supports dynamic field resolution via business_fields config.
        Falls back to legacy alias mapping for backward compatibility.
        """
        # Try dynamic resolution first
        value = self._resolve_field_dynamically(field_key, meta)
        if value is not None:
            return value
        
        # Legacy alias mapping (backward compatibility)
        aliases = {
            'opportunity_name': 'opportunity_name',
            'customer_name': 'customer_name',
            'sales_person': 'sales_person',
            'date': 'date',
            'quotation_date': 'date',
            'model_name': 'model_name',
            'total_qty': 'total_qty',
            'fae': 'fae',
            'description': 'description',
            'l6_spec': 'l6_spec',
            'l6_desc': 'l6_desc',
            'title': 'title',
            'version': 'version',
            'business_person': 'business_person',
            'model_name_with_qty': 'model_name_with_qty',
        }
        
        mapped_key = aliases.get(field_key)
        if mapped_key and mapped_key in meta:
            return meta[mapped_key]
        
        return None
    
    def _resolve_field_dynamically(self, field_key: str, meta: dict):
        """Resolve field value dynamically based on business_fields config.
        
        Uses the field's source and source_column to fetch from appropriate data source.
        """
        # Get field config
        repo = self._get_business_field_repo()
        try:
            field = repo.get_by_key(field_key)
            if not field:
                return None
            
            source = field.get('source', '')
            source_column = field.get('source_column')
            
            # Route based on source
            if source == 'System':
                # System fields: export_date, export_user, export_timestamp
                from datetime import datetime
                if field_key == 'export_date':
                    return datetime.now().strftime('%Y-%m-%d')
                elif field_key == 'export_user':
                    return 'System'  # TODO: get from auth context
                elif field_key == 'export_timestamp':
                    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                return None
            
            elif source == 'Opportunity' and source_column:
                # Opportunity fields: customer_name, opportunity_name, etc.
                return meta.get(source_column)
            
            elif source in ('L6Record', 'KPRecord') and source_column:
                # L6/KP fields are resolved in _get_region_data, not here
                # These are for static display (e.g., showing L6 price in header)
                # For now, return None (dynamic region data handles these)
                return None
            
            elif source == 'Config' and source_column:
                # Config-level fields: description, server_model, quantity
                # These are per-config, so we need to know which config
                # For static bindings, use first config
                if source_column == 'description':
                    config_descriptions = meta.get('config_descriptions', {})
                    if config_descriptions:
                        first_cfg = list(config_descriptions.keys())[0]
                        return config_descriptions.get(first_cfg, '')
                elif source_column == 'server_model':
                    config_server_models = meta.get('config_server_models', {})
                    if config_server_models:
                        first_cfg = list(config_server_models.keys())[0]
                        return config_server_models.get(first_cfg, '')
                elif source_column == 'quantity':
                    config_quantities = meta.get('config_quantities', {})
                    if config_quantities:
                        first_cfg = list(config_quantities.keys())[0]
                        return config_quantities.get(first_cfg, 0)
                return None
            
            else:
                # Unknown source, try direct meta lookup
                return meta.get(field_key)
        finally:
            repo.close()
    
    def _get_region_data(self, region_field_key: str, config_dfs: dict, meta: dict = None, binding: dict = None) -> list:
        """Get region data (list of dicts) based on regionFieldKey.

        regionFieldKey values:
        - 'l6_details': all L6 items
        - 'kp_details': all Key Parts items
        - 'warranty_details': all Warranty items
        - 'all_items': all items from all configs
        - 'config_summary': one row per config (for cover sheet)
        """
        all_items = []

        if region_field_key == 'config_summary':
            return self._build_config_summary(config_dfs, meta or {}, binding or {})

        for cfg_name, df in config_dfs.items():
            if region_field_key == 'l6_details':
                l6_items = df[df['category'] == 'L6'].to_dict('records')
                all_items.extend(l6_items)
            elif region_field_key == 'kp_details':
                kp_items = df[df['category'] == 'Key Parts'].to_dict('records')
                all_items.extend(kp_items)
            elif region_field_key == 'warranty_details':
                warranty_items = df[df['category'] == 'Warranty'].to_dict('records')
                all_items.extend(warranty_items)
            elif region_field_key == 'all_items':
                all_items.extend(df.to_dict('records'))

        # Add numeric item_no to each item (1, 2, 3, ...)
        for idx, item in enumerate(all_items, 1):
            if 'item_no' not in item or not item['item_no']:
                item['item_no'] = idx

        return all_items
    
    def _build_config_summary(self, config_dfs: dict, meta: dict, binding: dict) -> list:
        """Build one summary row per config for cover sheet.
        
        Generates: seq, model_name, description (from template), unit_price, quantity, total_price.
        unit_price = L6 final_price sum + KP final_price sum + Warranty final_price sum
        quantity = from meta.config_quantities[cfg_name], fallback to meta.total_qty
        """
        import pandas as pd
        
        # Description template: e.g. "{kp_list}" or "{l6_list} + {kp_list}"
        desc_template = binding.get('descriptionTemplate', '{kp_list}')
        separator = binding.get('descriptionSeparator', ',')
        
        # Per-config quantities
        config_quantities = meta.get('config_quantities') or {}
        default_qty = meta.get('total_qty', 0) or 0
        
        # Per-config descriptions (from Workspace)
        config_descriptions = meta.get('config_descriptions') or {}
        
        summaries = []
        for idx, (cfg_name, df) in enumerate(config_dfs.items(), 1):
            if not isinstance(df, pd.DataFrame) or df.empty:
                continue
            
            # Calculate unit_price = L6 + KP + Warranty (all final_price × qty)
            l6_sum = (df[df['category'] == 'L6']['final_price'] * df[df['category'] == 'L6']['qty']).sum() if 'final_price' in df.columns and 'qty' in df.columns else 0
            kp_sum = (df[df['category'] == 'Key Parts']['final_price'] * df[df['category'] == 'Key Parts']['qty']).sum() if 'final_price' in df.columns and 'qty' in df.columns else 0
            warranty_sum = (df[df['category'] == 'Warranty']['final_price'] * df[df['category'] == 'Warranty']['qty']).sum() if 'final_price' in df.columns and 'qty' in df.columns else 0
            unit_price = float(l6_sum or 0) + float(kp_sum or 0) + float(warranty_sum or 0)
            
            # Quantity for this config
            quantity = config_quantities.get(cfg_name, default_qty)
            
            # Description: prefer user input from Workspace, fallback to template
            description = config_descriptions.get(cfg_name, '')
            if not description:
                description = self._render_description_template(desc_template, df, separator)
            
            # Model name: extract from L6 data (first L6 item's model_name or spec)
            model_name = ''
            l6_df = df[df['category'] == 'L6']
            if not l6_df.empty:
                # Try model_name first, then spec
                model_name = l6_df.iloc[0].get('model_name', '') or l6_df.iloc[0].get('spec', '') or ''
            
            # Server model: from config_server_models
            config_server_models = meta.get('config_server_models') or {}
            server_model = config_server_models.get(cfg_name, '')
            
            summaries.append({
                'seq': idx,
                'model_name': model_name,
                'server_model': server_model,
                'desc': description,
                'description': description,  # alias
                'unit_price': round(unit_price, 2),
                'qty': quantity,
                'quantity': quantity,  # alias
                'total_price': round(unit_price * quantity, 2),
            })
        
        return summaries
    
    def _render_description_template(self, template: str, df, separator: str) -> str:
        """Render description template like '{kp_list}' or '{l6_list} + {kp_list}'.
        
        Each list expands to: 'part_name × qty' entries joined by separator.
        """
        import pandas as pd
        
        if not isinstance(df, pd.DataFrame) or df.empty:
            return ''
        
        def build_list(category: str) -> str:
            subset = df[df['category'] == category]
            if subset.empty:
                return ''
            parts = []
            for _, row in subset.iterrows():
                name = row.get('part_name', '') or ''
                qty = row.get('qty', 0) or 0
                if name:
                    parts.append(f"{name} × {qty}")
            return separator.join(parts)
        
        # Replace template variables
        result = template
        result = result.replace('{l6_list}', build_list('L6'))
        result = result.replace('{kp_list}', build_list('Key Parts'))
        result = result.replace('{warranty_list}', build_list('Warranty'))
        result = result.replace('{all_list}', build_list('L6') + separator + build_list('Key Parts') + separator + build_list('Warranty'))
        
        # Clean up empty separators
        result = result.strip(separator).strip()
        return result


    def _build_export_description(self, items_df: pd.DataFrame, template_override: str = None) -> str:
        """Build export description from template with loop syntax support.
        
        Loop syntax: [${category_model}*${category_qty}; separator]
        Example: [${disk_model}*${disk_qty}; ] expands to all disk items
        """
        # Get template: override > rules DB > hardcoded default
        default_template = "${cpu_model}*${cpu_qty}, ${memory_model}*${memory_qty}, [${disk_model}*${disk_qty}; ]"
        template = template_override or default_template
        
        if not template_override and self.rules_repo:
            try:
                rule = self.rules_repo.get_matching_rule("export_description_template")
                if rule and rule.get('rule_value'):
                    template = rule['rule_value']
            except Exception:
                pass
        
        # Extract components grouped by category
        categories = self._extract_categories(items_df)
        
        # Process loop blocks - replace each with its expanded content
        # Insert separator between adjacent loop blocks (][ with nothing between)
        normalized = re.sub(r'\](\s*)\[', '], [', template)
        result = normalized
        loop_pattern = r'\[([^\]]+)\]'
        
        def replace_loop(match):
            block = match.group(1)
            # Split by ; to get content and separator
            parts = block.split(';')
            if len(parts) == 1:
                content = parts[0]
                separator = ', '
            else:
                content = parts[0]
                separator = ';'.join(parts[1:]).strip()
                if not separator:
                    separator = ', '
            
            # Detect category from variables in content
            var_pattern = r'\$\{(\w+?)_(model|qty)\}'
            matches = re.findall(var_pattern, content)
            if not matches:
                return ''
            
            category = matches[0][0].lower()  # Convert to lowercase to match categories dict
            if category not in categories:
                return ''
            
            items = categories[category]
            expansions = []
            for item in items:
                expanded = content
                expanded = expanded.replace(f'${{{category}_model}}', item['model'])
                expanded = expanded.replace(f'${{{category}_qty}}', str(item['qty']))
                expansions.append(expanded)
            
            return separator.join(expansions)
        
        result = re.sub(loop_pattern, replace_loop, result)
        
        # Now substitute non-loop variables (single items)
        variables = self._extract_single_items(categories)
        for key, value in variables.items():
            result = result.replace(f'${{{key}}}', value)
        
        # Clean up and add separators between loop blocks
        # Clean up multiple commas
        result = re.sub(r',\s*,', ',', result)
        # Remove leading/trailing commas
        result = re.sub(r'^\s*,\s*', '', result)
        result = re.sub(r'\s*,\s*$', '', result)
        # Clean up * followed by comma
        result = re.sub(r'\*\s*,', ',', result)
        result = result.strip()
        
        return result
    
    def _extract_categories(self, items_df: pd.DataFrame) -> dict:
        """Extract components grouped by category.
        
        Maps part_name to logical category using configurable mappings from DB.
        Mappings are stored in rules table as 'export_category_mappings'.
        
        Returns:
            {
                'cpu': [{'model': 'Intel Xeon', 'qty': 2}],
                'disk': [
                    {'model': 'Samsung SSD', 'qty': 4},
                    {'model': 'Intel SSD', 'qty': 2}
                ]
            }
        """
        categories = {}
        if items_df.empty:
            return categories
        
        # Load configurable mappings from DB, fallback to defaults
        rules_repo = self.rules_repo
        mappings = rules_repo.get_export_category_mappings()
        
        if not mappings:
            # Default mappings (used when no custom mappings configured)
            mappings = [
                {"keywords": ["cpu", "processor"], "variable": "cpu"},
                {"keywords": ["memory", "ram"], "variable": "memory"},
                {"keywords": ["hdd", "ssd"], "variable": "disk"},
                {"keywords": ["raid"], "variable": "raid"},
                {"keywords": ["nic", "network"], "variable": "nic"},
                {"keywords": ["gpu"], "variable": "gpu"},
                {"keywords": ["power supply", "psu"], "variable": "psu"},
                {"keywords": ["power cord"], "variable": "power_cord"},
                {"keywords": ["fan"], "variable": "fan"},
                {"keywords": ["heatsink"], "variable": "heatsink"},
                {"keywords": ["chassis"], "variable": "chassis"},
                {"keywords": ["backplane"], "variable": "backplane"},
                {"keywords": ["cable"], "variable": "cable"},
                {"keywords": ["rail"], "variable": "rail"},
            ]

        for _, item in items_df.iterrows():
            category = str(item.get('category', '')).strip()
            part_name = str(item.get('part_name', '')).strip()
            spec = str(item.get('spec', '')).strip()

            if not part_name:
                continue

            # For L6/KP/Warranty/Key Parts categories, use part_name to determine logical category
            logical_category = category
            part_lower = part_name.lower()

            if part_lower == 'l6' or part_lower == '整机':
                logical_category = 'L6'
            elif '质保' in part_lower or 'warranty' in part_lower:
                logical_category = 'Warranty'

            export_categories.setdefault(logical_category, []).append({
                'part_name': part_name,
                'spec': spec,
                'category': category,
            })

        return export_categories
