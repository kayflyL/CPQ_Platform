"""
Pricing Engine — pure business logic layer.

Replaces the DB-coupled parts of legacy data_processor.py.
All data access goes through injected Repository instances.
No sqlite3, no direct DB connections.
"""

import re
import math
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional

from app.core.config import get_settings

from app.repository.kp_repo import KPRepository, category_family, _inorm_general, part_identity_key, semantic_match
from app.repository.l6_repo import L6Repository
from app.repository.opportunity_repo import OpportunityRepository
from app.repository.rules_repo import RulesRepository
from app.repository.univer_template_repo import UniverTemplateRepo
from app.engine.excel_parser import ExcelParser


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
                 opportunity_repo: OpportunityRepository, rules_repo: RulesRepository = None):
        self.kp_repo = kp_repo
        self.l6_repo = l6_repo
        self.opportunity_repo = opportunity_repo
        self.rules_repo = rules_repo
        
        # Initialize ExcelParser if rules_repo is available
        self._excel_parser = ExcelParser(rules_repo) if rules_repo else None

        # Load rules from DB (with hardcoded fallbacks)
        self._load_rules()

    def _load_rules(self):
        """Load configurable rules from rules.db, with hardcoded fallbacks.

        解析区域/字段规则现由 ExcelParser 自管（读 parse_regions/parse_field_rules），
        这里只保留 enrich_config 用的 KP 分类映射。旧的 L6/KP region_config 已随旧
        解析代码一并移除。
        """
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
        self._price_diff_threshold = 0.01

        if not self.rules_repo:
            return

        try:
            kp_mappings = self.rules_repo.get_kp_category_mappings()
            if kp_mappings:
                self._kp_cat_map = {m['keyword']: m['category'] for m in kp_mappings}
        except Exception as e:
            print(f"⚠️ Failed to load rules from DB, using defaults: {e}")

    # ==================== 1. Excel Parsing (pure algorithm) ====================

    def parse_file(self, sheet_dict: dict, template_id: int = None, parse_overrides: dict = None) -> tuple:
        """Parse uploaded Excel into configs + first_meta.

        统一走规则驱动的 ExcelParser（解析规则页配置）。不再有旧解析兜底——
        若某 sheet 解析异常会直接抛出，暴露问题而非用旧实现掩盖。
        template_id/parse_overrides：模板匹配链结果与会话补丁（解析弹窗点着修）。
        """
        configs = {}
        first_meta = None

        for sheet_name, df in sheet_dict.items():
            if '原始需求' in sheet_name or 'Reference' in sheet_name or df.empty:
                continue

            if not self._excel_parser:
                raise RuntimeError("ExcelParser 未初始化（rules_repo 缺失），无法解析报价单")

            parse_result = self._excel_parser.parse(
                df, return_trace=False,
                template_id=template_id, overrides=parse_overrides,
            )
            meta = self._convert_parser_meta(parse_result["static_fields"])
            items = self._convert_parser_items(parse_result["dynamic_regions"])

            if items.empty:
                continue

            # l6_rows: L6 区域作 excel 模式参考快照（不计价、不进 items），
            # 供 config_l6_picks.bom_excel_rows 喂左栏 BomTable + 规格书导出。
            configs[sheet_name] = {
                'meta': meta,
                'items': items,
                'l6_rows': self._convert_l6_rows(parse_result["dynamic_regions"]),
            }
            if first_meta is None:
                first_meta = meta

        return configs, first_meta
    
    def _convert_parser_meta(self, static_fields: dict) -> dict:
        """Convert ExcelParser static_fields to the service meta contract.

        Parser field_key 是用户可配置的（当前模板使用 server_model/description），
        这里统一归一为上层消费方都能识别的字段：server_model、description、
        model_qty，同时保留 model_name/l6_desc 等历史别名，避免链路另一端再各写映射。
        """
        meta = {}

        # 非机型字段直接透传；机型字段统一收敛到 server_model。
        field_mapping = {
            "model_name": "model_name",
            "server_model": "server_model",
            "fae": "fae",
            "quotation_date": "date",
            "description": "description",
        }

        for parser_key, meta_key in field_mapping.items():
            if parser_key not in static_fields:
                continue
            value = static_fields[parser_key].get("value")
            if value is None:
                continue

            if parser_key in ("model_name", "server_model"):
                raw = str(value).strip()
                clean_model = raw.split("(")[0].strip()
                meta["server_model"] = clean_model
                if parser_key == "model_name":
                    meta["model_name"] = clean_model
                m = re.search(r'\((\d+)', raw)
                if m:
                    meta["model_qty"] = int(m.group(1))
            else:
                meta[meta_key] = str(value).strip()

        if meta.get("description"):
            meta["l6_desc"] = meta["description"]

        return meta
    
    def _convert_parser_items(self, dynamic_regions: dict) -> pd.DataFrame:
        """Convert ExcelParser dynamic_regions to legacy items DataFrame format.

        Note: L6 region is NOT included in items. L6 data is stored separately in
        config_l6_picks.bom_excel_rows to avoid duplication. This aligns with the
        live mode where L6 comes from bom_template + bom_context.
        """
        items = []

        # L6 region - SKIPPED (stored in config_l6_picks.bom_excel_rows instead)
        # This prevents data duplication when loading preview

        # KP region（region_key 可能为 KP/kp/Keyparts 等，统一按不区分大小写匹配）
        kp_rows = self._get_region_rows(dynamic_regions, "KP", "kp", "Keyparts", "Keypats")
        if kp_rows:
            for item in kp_rows:
                catalogue = item.get("kp_category", "")
                model = item.get("kp_model", "")
                qty = 1
                if "qty" in item:
                    try:
                        qty = int(float(item["qty"]))
                    except:
                        qty = 1
                
                price = None
                raw_price = str(item.get("kp_price", "")).strip().replace(',', '')
                if raw_price:
                    try:
                        price = round(float(raw_price), 2)
                    except ValueError:
                        pass

                # 空类别=绑定错列的残行，跳过（区块标记/表头残留已由
                # parse_regions.exclude_keywords 行级排除词规则在引擎层剔除）
                if not catalogue:
                    continue

                # 行级货币：型号含 usd/$ → USD，否则 RMB（不限 CPU；上传后可在报价工作台逐行改）
                model_low = (model or '').lower()
                is_usd = 'usd' in model_low or '$' in (model or '')

                items.append({
                    'category': 'Key Parts',
                    'catalogue': model,
                    'part_category': catalogue,
                    'description': '',
                    'qty': qty,
                    'price': price,
                    'currency': 'USD' if is_usd else 'RMB'
                })
        
        # Warranty region（region_key 可能为 Warranty/warranty）
        warranty_rows = self._get_region_rows(dynamic_regions, "Warranty", "warranty")
        if warranty_rows:
            for item in warranty_rows:
                warranty_type = item.get("part_name", "")
                description = item.get("description", "")
                
                if not description or description.lower() in ['nan', 'none', '']:
                    continue
                
                # Extract warranty years — let user fill in manually
                years = None
                
                items.append({
                    'category': 'Warranty',
                    'catalogue': description or warranty_type,
                    'description': '',
                    'part_category': None,
                    'qty': 1,
                    'currency': 'RMB',
                    'warranty_years': years
                })
        
        return pd.DataFrame(items) if items else pd.DataFrame()

    def _convert_l6_rows(self, dynamic_regions: dict) -> list:
        """把新解析器的 L6 区域（dynamic_regions['L6']）转成 bom_excel_rows 格式。

        L6 在 excel 模式是参考快照（不计价、不进 items），喂 config_l6_picks.bom_excel_rows
        → 工作台左栏 BomTable + 规格书导出。字段映射对齐旧 _parse_l6_rows 输出：
        l6_chassis→catalogue、spec→description、qty→qty（见 parse_field_rules 的 L6 区域配置）。

        注：列定位只用固定的列字母（parse_field_rules 里 source_config.col）。早先的
        表头自适应列定位（读 Catalogue/Description/Quantity 标签、以及后来按 header_labels
        标签扫描）都因频繁定位错列已移除——如不同模板 L6 列偏移，在解析规则页按模板配列即可。
        """
        rows = []
        for item in self._get_region_rows(dynamic_regions, "L6", "l6"):
            catalogue = str(item.get("l6_chassis", "")).strip()
            if not catalogue or catalogue.lower() in ('nan', 'none', '', 'catalogue', 'description', 'qty', 'quantity'):
                continue
            description = str(item.get("spec", "")).strip()
            if description.lower() in ('nan', 'none'):
                description = ''
            qty = 1
            try:
                qty = int(float(item.get("qty", 1)))
            except (ValueError, TypeError):
                qty = 1
            rows.append({
                'category': 'L6',
                'catalogue': catalogue,
                'description': description,
                'qty': qty,
            })
        return rows

    @staticmethod
    def _get_region_rows(dynamic_regions: dict, *keys: str) -> list:
        """按区域标识兼容查找行数据，忽略大小写与首尾空格。

        ExcelParser 新版本把 dynamic_regions 的键统一小写为 region_key（如 kp/l6），
        而计价引擎历史上按 KP/L6/Warranty 大写键读取。这里保留一个兼容层，避免
        区域键命名策略调整时再次出现「解析成功但 items 为空」的隐性断链。
        """
        target = {str(k).strip().lower() for k in keys}
        for key, rows in (dynamic_regions or {}).items():
            if (str(key or "")).strip().lower() in target:
                return rows or []
        return []
    # ==================== 2. Price Enrichment (via Repository) ====================

    @staticmethod
    def _is_json_unsafe(v) -> bool:
        """True if v is None / NaN / Inf / pandas-NA (incl. numpy float variants) — i.e. must be
        nullified before JSON serialization, because starlette's JSONResponse uses
        json.dumps(allow_nan=False) and any NaN/Inf raises a 500."""
        if v is None:
            return True
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return True
        try:
            return bool(pd.isna(v))
        except (TypeError, ValueError):
            return False

    def enrich_config(self, items_df: pd.DataFrame, meta: Optional[dict] = None,
                      kp_latest: Optional[list] = None) -> pd.DataFrame:
        """Enrich items with DB price match status (NO auto-fill).
        Uses kp_repo instead of direct sqlite3 queries.

        kp_latest：外部预取的最新价列表（process_upload 一次拉取、跨 CFG 共享同一份快照）；
        为 None 时内部按需拉取（兼容单独调用场景）。
        """
        if items_df.empty:
            return items_df

        # Fetch all latest KP prices at once (one query via repo)
        if kp_latest is None:
            kp_latest = self.kp_repo.get_latest_prices(include_record_count=False)
        latest_by_model = {r.get('model'): r for r in kp_latest if r.get('model')}
        exact_all: dict = {}
        for r in kp_latest:
            key = _inorm_general(r.get('model') or '')
            if key:
                exact_all.setdefault(key, []).append(r)

        items = items_df.copy()
        items['match_status'] = ""
        items['db_price'] = None
        items['db_currency'] = None
        items['base_price'] = items.get('price', 0)
        items['profit_margin'] = 10.0  # default

        family_cache: dict = {}

        def _family_parts(family: str) -> list:
            if family not in family_cache:
                family_cache[family] = self.kp_repo.get_parts_for_matching(
                    [family], latest_map=latest_by_model) if family else []
            return family_cache[family]

        def _uniform(p: dict) -> dict:
            return {
                'name': p.get('model') or p.get('name') or '',
                'price': p.get('price'),
                'currency': p.get('currency', 'RMB'),
            }

        for idx, row in items.iterrows():
            cat = row['category']
            catalogue = str(row.get('catalogue', '')).lower().strip()      # 型号（KP）/ 零件名（L6）
            part_category = str(row.get('part_category', '')).lower().strip()  # 类别（KP）
            original_price = row.get('price')
            db_price = None
            db_currency = None
            matched = None

            if cat == 'Key Parts':
                family = category_family(part_category)
                if catalogue and len(catalogue) > 2:
                    # 结构化同一性键：HDD/Memory 按 spec 维度判同件，其余品类按归一名；
                    # 与 KP 库导入去重(part_identity_key)同口径——不再靠纯名字，避免「写法差一点就误判新料」。
                    q_key = part_identity_key(catalogue, family or part_category)
                    if family:
                        family_parts = _family_parts(family)
                        # L0 SKU 精确（最强信号）
                        sku_hits = [p for p in family_parts
                                    if p.get('oem_sku') and str(p['oem_sku']).strip().lower() == catalogue]
                        # L1 结构化同一性键
                        key_hits = [p for p in family_parts
                                    if part_identity_key(p.get('name') or '', family,
                                                         p.get('specs') or {}) == q_key]
                        if len(sku_hits) == 1:
                            matched = _uniform(sku_hits[0])
                        elif len(key_hits) == 1:
                            matched = _uniform(key_hits[0])
                        else:
                            # L1.5 语义 token：输入 token ⊆ 库件 token 且族内唯一
                            # （对语序/品牌前缀/冗余词/连写差免疫；歧义不匹配，宁缺勿错）
                            sem_hits = semantic_match(catalogue, family_parts)
                            if len(sem_hits) == 1:
                                matched = _uniform(sem_hits[0])
                    else:
                        # 无分类旧单：全局归一名精确兜底，再走旧 fuzzy（不丢已有匹配）
                        hits = exact_all.get(_inorm_general(catalogue)) or []
                        if len(hits) == 1:
                            matched = _uniform(hits[0])
                        else:
                            fuzzy = self.kp_repo.fuzzy_match_price(catalogue)
                            if fuzzy:
                                matched = _uniform(fuzzy)

                if matched is not None:
                    db_price = matched.get('price')
                    db_currency = matched.get('currency') or 'RMB'

            items.at[idx, 'db_price'] = db_price
            items.at[idx, 'db_currency'] = db_currency

            if matched is not None and db_price is None:
                items.at[idx, 'match_status'] = f"⚠️ 已匹配无价格 [DB={matched.get('name') or ''}]"
            elif db_price is not None:
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

        # NaN/Inf sanitization for JSON serialization — must cover ALL columns.
        # starlette's JSONResponse uses json.dumps(allow_nan=False), so any NaN/Inf in the
        # response raises a 500. Two gotchas the old .apply()-based code hit:
        #   1) A plain .apply(lambda v: None if pd.isna(v) else v) on an object column holding
        #      None+float (e.g. db_price = None for unmatched rows, float for matched) makes
        #      pandas re-infer the result as float64 and silently turn those Nones back into NaN.
        #   2) .fillna(0) does not touch Inf, so Inf in a numeric column still 500s.
        for col in items.columns:
            s = items[col]
            if s.dtype == object or str(s.dtype) == 'str':
                # Rebuild as an EXPLICIT object Series so None stays None (no dtype re-inference).
                items[col] = pd.Series(
                    [None if self._is_json_unsafe(v) else v for v in s],
                    dtype=object, index=items.index,
                )
            else:
                # Numeric columns: NaN & Inf → 0 (Inf guard only on float cols).
                if pd.api.types.is_float_dtype(s):
                    s = s.replace([np.inf, -np.inf], 0)
                items[col] = s.fillna(0)

        return items

    # ==================== 3. KP Sync & History (via Repository) ====================

    def get_kp_price_history(self, model: str, limit: int = 10, category: str = "") -> list:
        return self.kp_repo.get_price_history(model, limit, category=category or None)

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
                part_category = str(row.get('part_category', '')).strip()  # 类别（CPU/Memory…）
                catalogue = str(row.get('catalogue', '')).strip()          # 型号

                category = None
                model = None
                lower_pc = part_category.lower()
                for keyword, std_cat in cat_map.items():
                    if keyword in lower_pc:
                        category = std_cat
                        model = catalogue if catalogue else part_category
                        break
                if category is None:
                    category = part_category or 'Key Parts'
                    model = catalogue
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

    # ==================== 5. Excel Export (template-driven) ====================

    def _load_config(self) -> dict:
        """Load config from system_config DB table (single source of truth)."""
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            return {
                "tax_rate": repo.get_value("tax_rate", 0.13),
                "usd_to_rmb": repo.get_value("usd_to_rmb", 7.0),
                "profit_margin": repo.get_value("profit_margin", 0.1),
                "warranty_fee_rate": repo.get_value("warranty_fee_rate", 0.02),
            }
        finally:
            repo.close()
