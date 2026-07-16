"""Quote Service — coordinates PricingEngine + Repositories."""
import json
import logging
import os
import re
import tempfile
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)

from app.engine.pricing_engine import PricingEngine
from app.repository.kp_repo import KPRepository
from app.repository.l6_chassis_repo import L6ChassisRepository
from app.repository.opportunity_repo import OpportunityRepository
from app.repository.rules_repo import RulesRepository
from app.core.config import get_settings

_settings = get_settings()
DATA_DIR = Path(_settings.DATA_PATH)
CONFIG_PATH = DATA_DIR / "config.json"


class QuoteService:
    def __init__(self):
        self.kp_repo = KPRepository()
        self.l6_repo = L6ChassisRepository()
        self.opportunity_repo = OpportunityRepository()
        self.rules_repo = RulesRepository()
        self.engine = PricingEngine(
            self.kp_repo, self.l6_repo, self.opportunity_repo,
            self.rules_repo
        )
        self.config = self._load_config()

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

    def process_upload(self, file_content: bytes, filename: str) -> dict:
        """Process uploaded Excel: parse 鈫?enrich 鈫?L6 match 鈫?return JSON for frontend."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            sheet_dict = pd.read_excel(tmp_path, sheet_name=None, header=None)
            configs, first_meta = self.engine.parse_file(sheet_dict)
            if not configs:
                return {"status": "error", "message": "No valid configs found in file."}

            # Enrich with KP prices
            result_configs = {}
            for cfg_name, cfg_data in configs.items():
                items_df = cfg_data['items']
                enriched_df = self.engine.enrich_config(items_df, cfg_data.get('meta'))

                # Default profit_margin to config value
                default_margin = self.config.get('profit_margin', 0.1) * 100
                enriched_df['profit_margin'] = enriched_df['profit_margin'].apply(
                    lambda x: default_margin if (pd.isna(x) or x == 0) else x
                )

                # Ensure base_price is numeric
                enriched_df['base_price'] = pd.to_numeric(enriched_df['base_price'], errors='coerce').fillna(0)

                items_list = []
                l6_total = 0
                kp_total = 0

                # 质保信息结构（前端需要，后端不再处理）
                warranty_info = {
                    "l6": {"years": None, "rate": 0.02, "description": ""},
                    "kp": {"years": None, "rate": 0.02, "description": ""}
                }
                
                for _, row in enriched_df.iterrows():
                    item = row.to_dict()
                    item['qty'] = int(item.get('qty', 1) or 1)
                    item['base_price'] = float(item.get('base_price', 0) or 0)
                    item['profit_margin'] = float(item.get('profit_margin', default_margin) or default_margin)

                    # Compute final_price matching legacy logic:
                    # RMB: base * (1 + margin/100)
                    # USD CPU: base * usd_to_rmb * (1 + tax_rate) * (1 + margin/100)
                    base = item['base_price']
                    margin_pct = item['profit_margin']
                    margin_dec = margin_pct / 100 if margin_pct > 1 else margin_pct
                    tax = self.config.get('tax_rate', 0.13)
                    usd_rate = self.config.get('usd_to_rmb', 7.0)

                    if item.get('is_usd_cpu', False) or item.get('currency') == 'USD':
                        final_price = base * usd_rate * (1 + tax) * (1 + margin_dec)
                    else:
                        final_price = base * (1 + margin_dec)

                    item['final_price'] = round(final_price, 2)
                    items_list.append(item)

                    cat = item.get('category', '')
                    part_name = str(item.get('part_name', '')).lower()
                    spec = str(item.get('spec', ''))
                    line_total = item['final_price'] * item['qty']
                    
                    # 分类统计
                    if cat == 'L6':
                        l6_total += line_total
                    else:
                        kp_total += line_total

                result_configs[cfg_name] = {
                    "items": items_list,
                    "summary": {
                        "l6_total": round(l6_total, 2),
                        "kp_total": round(kp_total, 2),
                        "warranty_total": 0,  # 维保价格由前端计算
                        "grand_total": round(l6_total + kp_total, 2)
                    },
                    "warranty_info": warranty_info
                }

            return {
                "status": "success",
                "message": "Quotation parsed and enriched successfully",
                "configs": result_configs
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"status": "error", "message": str(e)}
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _normalize_date(self, date_str) -> str:
        """鏍囧噯鍖栨棩鏈熸牸寮忎负 YYYY-MM-DD锛屾敮鎸?'2026.6.17' / '2026/6/17' / '2026-6-17' 绛夈€?"""
        s = str(date_str).strip()
        for sep in ['.', '/', '-']:
            if sep in s:
                parts = s.split(sep)
                if len(parts) == 3:
                    try:
                        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                        return f"{y:04d}-{m:02d}-{d:02d}"
                    except ValueError:
                        pass
                break
        return s  # 鏃犳硶瑙ｆ瀽鍒欏師鏍疯繑鍥?
    def get_opportunity_details(self, opportunity_id: str) -> dict:
        details = self.engine.get_opportunity_details(opportunity_id)
        if not details:
            return {"status": "error", "message": "Project not found"}
        return {"status": "success", **details}

    def save_opportunity(self, opportunity_info: dict, configs_data: dict, config_quantities: dict = None) -> dict:
        import traceback

        cleaned = {}
        config_descriptions = {}
        config_server_models = {}
        for cfg_name, cfg in configs_data.items():
            items = cfg.get('items', [])
            if items:
                try:
                    df = pd.DataFrame(items)
                    cleaned[cfg_name] = df
                    # Extract description from config
                    if 'description' in cfg:
                        config_descriptions[cfg_name] = cfg['description']
                    # Extract server_model from config
                    if 'server_model' in cfg:
                        config_server_models[cfg_name] = cfg['server_model']
                except Exception as e:
                    logger.error("DataFrame failed for %s: %s", cfg_name, e)
                    return {"status": "error", "message": f"Data processing error: {e}"}
        try:
            result = self.engine.save_opportunity(opportunity_info, cleaned, config_descriptions, config_quantities, config_server_models)
        except Exception as e:
            logger.error("engine.save_opportunity failed: %s", e)
            return {"status": "error", "message": f"Database save error: {e}"}

        # Sync KP prices
        try:
            new_kp = self.engine.sync_kp_prices_to_db(cleaned)
            if new_kp > 0:
                result['kp_synced'] = new_kp
        except Exception as e:
            print(f"[WARN QuoteService.save_opportunity] KP sync failed (non-fatal): {e}")

        # Ensure opportunity_id is in result
        if 'opportunity_id' not in result:
            result['opportunity_id'] = opportunity_info.get('opportunity_id', '')

        return result

    def export_opportunity(self, opportunity_id: str, template_id: str = None):
        return self.engine.generate_excel(opportunity_id, template_id)

    def get_kp_history(self, model: str) -> list:
        return self.engine.get_kp_price_history(model)

    def close(self):
        self.kp_repo.close()
        self.l6_repo.close()
        self.opportunity_repo.close()

