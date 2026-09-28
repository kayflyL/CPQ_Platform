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

import ast
import operator

# === Safe arithmetic evaluator (replaces eval() for Excel formulas) ===
# 解析单元格里的算式公式（如 =A1*B1）时安全求值；不支持 ** 以防 9**9**9 式 DoS。
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
    Does NOT support ** (exponentiation), preventing DoS via 9**9**9.
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


class ExcelParser:
    """独立的 Excel 解析引擎，规则驱动，支持白盒化溯源。

    模板层：规则按解析模板隔离（template_id）；不指定时自动解析默认模板
    （唯一启用模板 → 它；否则通用兜底 → 再否则全部规则=无模板层的旧语义）。
    会话补丁（overrides）：不落库的一次性修正，作用于本次 parse/preview：
      {"skip_rows": [行号...], "col_binds": {field_key: 列字母},
       "region_ends": {region_key: 结束行(不含)}}
    """

    # 灰字示例行标记：任一格整词命中即整行跳过（标准文件示例行由引擎确定性跳过）
    EXAMPLE_TOKEN = "示例"

    def __init__(self, rules_repo: RulesRepository):
        self.rules_repo = rules_repo
        self._rules_cache = {}  # template_id -> (regions, field_rules)
        self._default_template_id = None
        self._default_template_resolved = False
        self._parse_regions = None
        self._parse_field_rules = None
        self._loaded_template_id = None

    def _resolve_template_id(self, template_id=None):
        """显式指定优先；否则唯一启用模板 / 通用兜底；无模板层时 None=全部规则。"""
        if template_id is not None:
            return template_id
        if not self._default_template_resolved:
            try:
                templates = self.rules_repo.get_parse_templates()
            except Exception:
                templates = []
            enabled = [t for t in templates if t.get("enabled")]
            chosen = None
            if len(enabled) == 1:
                chosen = enabled[0]["id"]
            else:
                for t in enabled:
                    if t.get("is_fallback"):
                        chosen = t["id"]
                        break
                if chosen is None and enabled:
                    chosen = enabled[0]["id"]
            self._default_template_id = chosen
            self._default_template_resolved = True
        return self._default_template_id

    def _load_rules(self, template_id=None):
        """从数据库加载解析规则（按模板缓存；None=全部规则，兼容无模板层/测试）。"""
        if template_id not in self._rules_cache:
            if template_id is None:
                regions = self.rules_repo.get_parse_regions()
                rules = self.rules_repo.get_parse_field_rules()
            else:
                regions = self.rules_repo.get_parse_regions(template_id)
                rules = self.rules_repo.get_parse_field_rules(template_id)
            self._rules_cache[template_id] = (regions, rules)
        self._parse_regions, self._parse_field_rules = self._rules_cache[template_id]

    def _ensure_rules(self, template_id=None):
        """未装规则或模板切换时才从 DB 取（测试可直接注入 _parse_regions 绕过）。"""
        if self._parse_regions is None or self._loaded_template_id != template_id:
            self._load_rules(template_id)
            self._loaded_template_id = template_id
    

    def _region_by_id(self) -> dict:
        """Build an id -> region map for stable field-rule binding."""
        return {r["id"]: r for r in self._parse_regions if r.get("id") is not None}

    def _rule_matches_region(self, rule: dict, region: dict) -> bool:
        """True when a field rule binds to a region by region_id or legacy string."""
        if rule.get("region_id") is not None:
            region_id = region.get("id", region.get("region_id"))
            return rule["region_id"] == region_id
        ref = (rule.get("region") or "").strip().lower()
        return ref in {
            (region.get("region_key") or "").strip().lower(),
            (region.get("name") or "").strip().lower(),
        }

    def _is_static_rule(self, rule: dict, region_map: dict) -> bool:
        """A rule is static when its region has region_type=static, with legacy header fallback."""
        region_id = rule.get("region_id")
        if region_id is not None and region_id in region_map:
            return region_map[region_id].get("region_type") == "static"
        return (rule.get("region") or "").strip().lower() == "header"

    def parse(self, df: pd.DataFrame, return_trace: bool = True,
              template_id: int = None, overrides: dict = None) -> dict:
        """解析 Excel DataFrame，返回结构化数据 + 溯源信息

        Args:
            df: Excel 工作表转换的 DataFrame
            return_trace: 是否返回溯源信息（白盒化）
            template_id: 解析模板作用域（None=自动解析默认模板）
            overrides: 会话级补丁（不落库）：
                {"skip_rows": [行号], "col_binds": {field_key: 列字母},
                 "region_ends": {region_key: 结束行(不含)}}

        Returns:
            {
                "static_fields": {field_key: {"value": ..., "source": {...}}},
                "dynamic_regions": {region_name: [{field_key: ..., value: ..., source: ...}]},
                "trace": [...]  # 如果 return_trace=True
            }
        """
        template_id = self._resolve_template_id(template_id)
        self._ensure_rules(template_id)
        overrides = overrides or {}
        skip_rows = {int(r) for r in overrides.get("skip_rows") or []}
        col_binds = {str(k): str(v).strip().upper() for k, v in (overrides.get("col_binds") or {}).items()
                     if re.fullmatch(r"[A-Z]{1,3}", str(v).strip().upper())}
        region_ends = overrides.get("region_ends") or {}

        result = {
            "static_fields": {},
            "dynamic_regions": {},
            "trace": []
        }

        # 1. 定位所有区域（region_ends 收口补丁在此生效）
        region_bounds = self._locate_regions(df, region_ends=region_ends)
        region_map = self._region_by_id()

        # 2. 提取静态字段：按 region_type=static 判断，保留 legacy header 兜底
        static_rules = [r for r in self._parse_field_rules
                        if r.get("enabled") and self._is_static_rule(r, region_map)]
        for rule in sorted(static_rules, key=lambda x: x.get("sort_order", 0)):
            field_key = rule["field_key"]
            source_config = rule["source_config"]

            if rule["source_type"] == "keyword":
                value, source = self._extract_by_keyword(df, source_config, max_rows=30)
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

        # 3. 提取动态区域字段：静态区域跳过，字段规则按 region_id/key 绑定
        header_cols = self._resolve_header_columns(df)
        for region_key, bounds in region_bounds.items():
            if bounds.get("region_type") == "static" or bounds["start_row"] < 0:
                continue
            region_name = bounds.get("region_name") or region_key

            region_rules = [r for r in self._parse_field_rules
                            if r.get("enabled") and self._rule_matches_region(r, bounds)]
            if not region_rules:
                continue

            region_items = []
            start_row = bounds["start_row"] + bounds["skip_rows"]
            end_row = bounds["end_row"]
            exclude_words = self._exclude_word_set(bounds.get("region_id"))

            for r in range(start_row, end_row):
                # 会话补丁：手动跳过的行
                if r in skip_rows:
                    continue
                # 标准文件灰字示例行：引擎确定性跳过
                if self._is_example_row(df, r):
                    continue
                item = {}
                item_trace = []

                for rule in sorted(region_rules, key=lambda x: x.get("sort_order", 0)):
                    field_key = rule["field_key"]
                    source_config = rule["source_config"]

                    if rule["source_type"] == "column":
                        # 会话补丁：手动绑定的列优先于表头投票/固定列
                        if field_key in col_binds:
                            col_letter = col_binds[field_key]
                            col_idx = self._col_letter_to_index(col_letter)
                        else:
                            col_letter, col_idx = self._resolve_rule_column(source_config, header_cols)

                        if col_idx < df.shape[1]:
                            cell_val = df.iloc[r, col_idx]
                            if pd.notna(cell_val):
                                if not isinstance(cell_val, str):
                                    # 数值单元格整值化：qty 2 → "2" 而非 "2.0"（字符串原样，避免动到编码类文本）
                                    try:
                                        num = round(float(cell_val), 6)  # Excel 浮点尾差：24520.999999999996 → 24521
                                        value = str(int(num)) if num.is_integer() else str(num)
                                    except (TypeError, ValueError):
                                        value = str(cell_val).strip()
                                else:
                                    value = str(cell_val).strip()
                                if value and value.lower() not in ['nan', 'none', '']:
                                    # 处理公式
                                    if isinstance(cell_val, str) and cell_val.startswith('='):
                                        try:
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

                # 只添加有内容的行；行级排除词命中（区域标记行/表头残留）则弃行
                if item and not self._hit_exclude_words(item, exclude_words):
                    item["_row"] = r
                    item["_trace"] = item_trace
                    region_items.append(item)

            if region_items:
                result["dynamic_regions"][region_key] = region_items
                if return_trace:
                    result["trace"].append({
                        "type": "dynamic_region",
                        "region": region_name,
                        "region_key": region_key,
                        "bounds": bounds,
                        "item_count": len(region_items)
                    })

        return result

    def _exclude_word_set(self, region_id) -> set:
        """区域行级排除词集合（小写整词）。"""
        for region in self._parse_regions:
            if region.get("id") is not None and region.get("id") == region_id:
                return {w.strip().lower() for w in (region.get("exclude_keywords") or "").split(",") if w.strip()}
        return set()

    @staticmethod
    def _hit_exclude_words(item: dict, exclude_words: set) -> bool:
        """任一已提取字段值（strip+lower 整词）命中排除词 → 弃行。"""
        if not exclude_words:
            return False
        for value in item.values():
            if isinstance(value, str) and value.strip().lower() in exclude_words:
                return True
        return False

    def _is_example_row(self, df: pd.DataFrame, r: int) -> bool:
        """标准文件灰字示例行：前 10 列任一格整词等于「示例」。"""
        for c in range(min(10, df.shape[1])):
            cell = df.iloc[r, c]
            if pd.notna(cell) and str(cell).strip() == self.EXAMPLE_TOKEN:
                return True
        return False

    def _locate_regions(self, df: pd.DataFrame, region_ends: dict = None) -> dict:
        """定位所有区域边界。

        Args:
            region_ends: 会话收口补丁 {region_key: 结束行(不含)}，仅当合法
                （大于起始行）时覆盖计算值。

        Returns:
            {region_name: {"region_id", "region_key", "region_type", "start_row", "end_row", "skip_rows"}}
        """
        sorted_regions = sorted(
            (r for r in self._parse_regions if r.get("enabled", True)),
            key=lambda x: x.get("sort_order", 0)
        )

        # First pass: resolve region starts sequentially.
        starts = {}
        search_from = 0
        for idx, region in enumerate(sorted_regions):
            start_mode = (region.get("start_mode") or "keyword").strip()
            start_keywords = (region.get("start_keywords") or "").strip()
            start_config = region.get("start_config") or {}

            if start_mode == "row":
                start_row = int(start_config.get("row", search_from))
            elif start_keywords:
                start_row = self._find_region_row(df, start_keywords, start_row=search_from)
            else:
                start_row = search_from

            starts[idx] = start_row
            if start_row >= 0:
                search_from = start_row + 1

        bounds = {}
        for idx, region in enumerate(sorted_regions):
            start_row = starts[idx]
            next_start = starts.get(idx + 1)
            end_keywords = (region.get("end_keywords") or "").strip()
            # 唯一收口法则：配了结束关键词→首个命中行，且不越过下一区域起点；
            # 没配→下一区域起点/表尾。（end_mode 已退役：允许「配了关键词却不用」
            # 的显式覆盖正是 2026-09-22 质保段吞进 KP 事故的根因。）
            fallback_end = next_start if next_start is not None and next_start > start_row else len(df)

            if start_row < 0:
                # 区域未命中：边界保持 (-1, -1)，下游（parse/预览/补丁归属）按 start<0 跳过
                end_row = start_row
            elif end_keywords:
                found = self._find_region_row(df, end_keywords, start_row=start_row + 1)
                end_row = min(found, fallback_end) if found >= 0 else fallback_end
            else:
                end_row = fallback_end

            region_name = (region.get("name") or "").strip()
            region_key = (region.get("region_key") or "").strip() or region_name.lower()

            # 会话收口补丁：用户拖定的结束行直接生效（越过起始行即合法）
            if region_ends:
                override_end = region_ends.get(region_key)
                if override_end is not None:
                    try:
                        override_end = int(override_end)
                    except (TypeError, ValueError):
                        override_end = None
                    if override_end is not None and override_end > start_row:
                        end_row = override_end

            bounds[region_key] = {
                "region_id": region.get("id"),
                "region_key": region_key,
                "region_name": region_name,
                "region_type": region.get("region_type") or ("static" if region_name.lower() == "header" else "dynamic"),
                "start_row": start_row,
                "end_row": end_row,
                "skip_rows": region.get("skip_header_rows", 0) or 0
            }

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
        
        # 第二轮：子串匹配（短拉丁词跳过——"L6"/"KP" 子串会命中 ML600 之类型号，
        # 劫持区域起点；中文关键词无词边界概念，仍靠子串兜底）
        for r in range(start_row, len(df)):
            for c in range(min(10, df.shape[1])):
                cell_val = str(df.iloc[r, c]).strip() if pd.notna(df.iloc[r, c]) else ''
                if not cell_val:
                    continue
                cell_lower = cell_val.lower()
                for kw in keywords:
                    kw_lower = kw.lower()
                    if kw_lower.isascii() and len(kw_lower) < 4:
                        continue
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
                    if len(kw_lower) <= 3:
                        continue
                    cell_words = re.findall(r'[a-z]+', cell_lower)
                    for word in cell_words:
                        if abs(len(word) - len(kw_lower)) <= 2:
                            if _edit_distance(word, kw_lower) <= 2:
                                return r
        
        return -1
    
    def _extract_by_keyword(self, df: pd.DataFrame, source_config: dict, max_rows: int = 30) -> tuple:
        """根据关键词提取值（用于静态字段）
        
        Args:
            source_config: {"keywords": [...], "value_offset": int}
        
        Returns:
            (value, source_info)
        """
        keywords = source_config.get("keywords", [])
        value_offset = source_config.get("value_offset", 1)
        value_pattern = source_config.get("value_pattern")
        # 关键词右侧最大查找跨度：兼容不同模板的空列 / 偏移差异
        max_right_scan = max(int(value_offset or 1), 1) + 3
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            for r in range(min(max_rows, len(df))):
                for c in range(min(10, df.shape[1])):
                    cell_val = str(df.iloc[r, c]).strip() if pd.notna(df.iloc[r, c]) else ''
                    if keyword_lower in cell_val.lower():
                        # 提取关键词右侧第一个非空单元格，避免模板间空列/偏移不一致导致取值落空
                        target_col = self._first_nonempty_col_right(df, r, c, max_right_scan)
                        if target_col is not None:
                            val = df.iloc[r, target_col]
                            if pd.notna(val):
                                extracted = str(val).strip()
                                if extracted and extracted.lower() not in ['', 'nan', 'none']:
                                    if value_pattern:
                                        try:
                                            match = re.search(value_pattern, extracted)
                                            if match:
                                                extracted = (match.group(1) if match.groups() else match.group(0)).strip()
                                        except re.error:
                                            pass
                                    if extracted and extracted.lower() not in ['', 'nan', 'none']:
                                        source = {
                                            "row": r,
                                            "col": target_col,
                                            "keyword": keyword,
                                            "keyword_col": c
                                        }
                                        return extracted, source
        return None, None

    def _first_nonempty_col_right(self, df: pd.DataFrame, row: int, col: int, max_scan: int):
        """返回关键词右侧第一个非空单元格的列索引；找不到返回 None。"""
        for d in range(1, max_scan + 1):
            target_col = col + d
            if target_col >= df.shape[1]:
                break
            cell = df.iloc[row, target_col]
            value = str(cell).strip() if pd.notna(cell) else ''
            if value and value.lower() not in ['', 'nan', 'none']:
                return target_col
        return None
    
    def _col_letter_to_index(self, letter: str) -> int:
        """列字母转索引（A=0, B=1, ..., Z=25, AA=26）"""
        letter = letter.strip().upper()
        result = 0
        for ch in letter:
            result = result * 26 + (ord(ch) - ord('A') + 1)
        return result - 1

    @staticmethod
    def _col_index_to_letter(idx: int) -> str:
        """0-based 列号 → Excel 列字母（A, B, ..., Z, AA, ...）。"""
        letter = ""
        n = idx + 1
        while n > 0:
            n, rem = divmod(n - 1, 26)
            letter = chr(ord('A') + rem) + letter
        return letter

    def _resolve_header_columns(self, df: pd.DataFrame, scan_rows: int = 50) -> dict:
        """按所有列规则配置的 header_keywords 投票找表头行，返回 {小写关键词: 列号}。

        同一供应商的不同 sheet 表格会整体左右偏移（表头前的空列数目不同），固定列
        字母只对录规则时的样例有效。这里扫描前 scan_rows 行，命中关键词最多的一行
        视为表头行（精确相等优先于包含，并列取最早）。命中少于 2 个关键词则认为
        没有可靠表头行，返回空表（各规则退回固定列，行为与旧版一致）。
        """
        labels = set()
        for rule in self._parse_field_rules or []:
            if not rule.get("enabled") or rule.get("source_type") != "column":
                continue
            for kw in (rule.get("source_config") or {}).get("header_keywords") or []:
                k = str(kw).strip().lower()
                if k:
                    labels.add(k)
        if not labels:
            return {}

        best, best_score = {}, (0, 0)
        for r in range(min(scan_rows, len(df))):
            exact, partial = {}, {}
            for c in range(min(15, df.shape[1])):
                cell = df.iat[r, c]
                s = str(cell).strip().lower() if pd.notna(cell) else ''
                if not s:
                    continue
                for k in labels:
                    if s == k:
                        exact.setdefault(k, c)
                    elif k in s:
                        partial.setdefault(k, c)
            score = (len(exact), len(partial))
            if score > best_score:
                best_score = score
                best = {**partial, **exact}
        if sum(best_score) < 2:
            return {}
        return best

    def _resolve_rule_column(self, source_config: dict, header_cols: dict) -> tuple:
        """列规则的取值列：优先 header_keywords 在表头行命中的列，退回固定 col 字母。

        Returns:
            (col_letter, col_idx)
        """
        for kw in source_config.get("header_keywords") or []:
            hit = header_cols.get(str(kw).strip().lower())
            if hit is not None:
                return self._col_index_to_letter(hit), hit
        letter = source_config.get("col") or "A"
        return letter, self._col_letter_to_index(letter)

    def preview_parse(self, df: pd.DataFrame, max_row: int = 15, max_col: int = 15,
                      template_id: int = None, overrides: dict = None) -> dict:
        """生成热力图预览数据（用于前端可视化）

        Returns:
            {
                "grid": [[cell_value, ...], ...],
                "cell_marks": [{"row": r, "col": c, "value": v, "type": t, "target": tgt}, ...],
                "region_bounds": {...}
            }
        """
        template_id = self._resolve_template_id(template_id)
        self._ensure_rules(template_id)
        overrides = overrides or {}

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

        # 定位区域（收口补丁同样生效）
        region_bounds = self._locate_regions(df, region_ends=overrides.get("region_ends") or {})
        region_map = self._region_by_id()
        
        # 生成 cell_marks
        cell_marks = []
        
        # 标记静态字段
        static_rules = [r for r in self._parse_field_rules if r.get("enabled") and self._is_static_rule(r, region_map)]
        for rule in static_rules:
            source_config = rule["source_config"]
            if rule["source_type"] == "keyword":
                value, source = self._extract_by_keyword(df, source_config, max_rows=30)
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
        for region_key, bounds in region_bounds.items():
            if bounds.get("region_type") == "static" or bounds["start_row"] < 0:
                continue
            region_name = bounds.get("region_name") or region_key
            
            # 标记区域起始行
            region_color = f"{region_key.lower()}_region"
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
                            if r.get("enabled") and self._rule_matches_region(r, bounds)]
            
            data_start = start_row + bounds["skip_rows"]
            data_end = bounds["end_row"] if bounds["end_row"] > data_start else data_start
            
            for r in range(data_start, min(data_end, rows)):
                for rule in region_rules:
                    source_config = rule["source_config"]
                    if rule["source_type"] == "column":
                        col_idx = self._col_letter_to_index(source_config.get("col", "A"))

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
