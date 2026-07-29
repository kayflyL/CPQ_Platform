"""Quote Service — coordinates PricingEngine + Repositories."""
import json
import logging
import os
import re
import tempfile
from datetime import datetime
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
        self._quotation_repo = None
        self.config = self._load_config()

    def _get_quotation_repo(self):
        """Lazy-init QuotationRepository (avoids per-call instantiation)."""
        if self._quotation_repo is None:
            from app.repository.quotation_repo import QuotationRepository
            self._quotation_repo = QuotationRepository()
        return self._quotation_repo

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

                    if item.get('currency') == 'USD':
                        final_price = base * usd_rate * (1 + tax) * (1 + margin_dec)
                    else:
                        final_price = base * (1 + margin_dec)

                    item['final_price'] = round(final_price, 2)
                    items_list.append(item)

                    cat = item.get('category', '')
                    line_total = item['final_price'] * item['qty']
                    
                    # 分类统计
                    if cat == 'L6':
                        l6_total += line_total
                    else:
                        kp_total += line_total

                # bom_excel_rows：excel 模式左栏参考快照（L6 参考行 + KP 行），与
                # candidate_search.build_plan 同源同形。L6 行不计价（items 不含 L6），
                # 仅作参考；持久化进 config_l6_picks 供左栏 BomTable + 规格书导出共用。
                l6_rows = cfg_data.get('l6_rows') or []
                kp_rows = [{
                    'category': 'Key Parts',
                    'catalogue': it.get('catalogue') or '',
                    'description': it.get('description') or '',
                    'part_category': it.get('part_category') or '',
                    'qty': it.get('qty', 1),
                    'base_price': it.get('base_price', 0),
                    'currency': it.get('currency') or 'RMB',
                } for it in items_list if it.get('category') == 'Key Parts']

                result_configs[cfg_name] = {
                    "items": items_list,
                    "bom_excel_rows": l6_rows + kp_rows,
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
        """获取商机 + 报价单 items（供详情/导出）。原 PricingEngine 实现，搬入 service。"""
        q_repo = self._get_quotation_repo()
        try:
            project_dict = self.opportunity_repo.get_opportunity(opportunity_id)
            if not project_dict:
                return {"status": "error", "message": "Project not found"}

            quotations = q_repo.get_by_opportunity(opportunity_id)
            meta = dict(project_dict)
            meta['date'] = ''
            if quotations:
                latest = quotations[0]  # 已按 version desc 排序
                meta['date'] = latest.quotation_date or meta.get('date', '')
                meta['quotation_id'] = latest.quotation_id
                meta['version'] = latest.version
                if hasattr(latest, 'config_quantities') and latest.config_quantities:
                    meta['config_quantities'] = latest.config_quantities
                if hasattr(latest, 'config_descriptions') and latest.config_descriptions:
                    meta['config_descriptions'] = latest.config_descriptions
                if hasattr(latest, 'config_server_models') and latest.config_server_models:
                    meta['config_server_models'] = latest.config_server_models
                if hasattr(latest, 'config_warranty_info') and latest.config_warranty_info:
                    meta['config_warranty_info'] = latest.config_warranty_info

            configs = {}
            for quo in quotations:
                cfg_items = [item.to_dict() for item in q_repo.get_items(quo.quotation_id)]
                for item in cfg_items:
                    cfg_name = item.get('config_name', 'CFG1')
                    configs.setdefault(cfg_name, []).append(item)
            if not configs:
                configs['CFG1'] = []

            return {"status": "success", 'meta': meta, 'configs': configs,
                    'quotations': [q.to_dict() for q in quotations]}
        finally:
            q_repo.close()

    def save_opportunity(self, opportunity_info: dict, configs_data: dict, config_quantities: dict = None) -> dict:
        """保存商机 meta + items（创建报价单）。原 PricingEngine 实现，搬入 service。"""
        import time, random

        # 1) 清理 configs → DataFrame + 抽取 per-config 描述/机型/维保
        cleaned = {}
        config_descriptions = {}
        config_server_models = {}
        config_warranty_info = {}
        for cfg_name, cfg in configs_data.items():
            items = cfg.get('items', [])
            if items:
                try:
                    cleaned[cfg_name] = pd.DataFrame(items)
                    if 'description' in cfg:
                        config_descriptions[cfg_name] = cfg['description']
                    if 'server_model' in cfg:
                        config_server_models[cfg_name] = cfg['server_model']
                    if 'warranty_info' in cfg:
                        config_warranty_info[cfg_name] = cfg['warranty_info']
                except Exception as e:
                    logger.error("DataFrame failed for %s: %s", cfg_name, e)
                    return {"status": "error", "message": f"Data processing error: {e}"}

        # 2) 持久化（opportunity + quotation + items + 配置字段）
        try:
            opportunity_id = opportunity_info.get('opportunity_id', '').strip()
            if not opportunity_id:
                ts = time.strftime('%m%d%H%M%S')
                rand = f'{random.randint(0, 0xFFFF):04x}'
                opportunity_id = f'opportunity_{ts}_{rand}'
                opportunity_info['opportunity_id'] = opportunity_id
            self.opportunity_repo.create_or_update_opportunity(opportunity_id, opportunity_info)

            q_repo = self._get_quotation_repo()
            try:
                quotation = q_repo.create(
                    opportunity_id=opportunity_id,
                    quotation_date=datetime.now().strftime('%Y-%m-%d'),
                )
                quotation_id = quotation.quotation_id

                all_items = []
                for cfg_name, cfg_data in cleaned.items():
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
                        item.setdefault('base_price', 0.0)
                        item.setdefault('final_price', 0.0)
                        item.setdefault('profit_margin', 0.0)
                        item.setdefault('catalogue', '')
                        item.setdefault('description', '')
                        item.setdefault('category', '')
                        item.setdefault('part_category', None)
                        item.setdefault('qty', 0)
                        item.setdefault('currency', 'RMB')
                    all_items.extend(items)

                l6_total = sum(i.get('final_price', 0) for i in all_items if i.get('category') == 'L6')
                kp_total = sum(i.get('final_price', 0) for i in all_items if i.get('category') == 'Key Parts')
                grand_total = l6_total + kp_total
                if config_quantities:
                    total_qty = sum(int(q) for q in config_quantities.values() if q)
                else:
                    total_qty = sum(i.get('qty', 0) for i in all_items if i.get('category') == 'L6')
                config_count = len(set(i.get('config_name', 'CFG1') for i in all_items))

                q_repo.update(quotation_id, l6_price=l6_total, total_price=grand_total,
                              total_qty=total_qty, config_count=config_count)
                if config_descriptions:
                    q_repo.update(quotation_id, config_descriptions=config_descriptions)
                if config_quantities:
                    q_repo.update(quotation_id, config_quantities=config_quantities)
                if config_server_models:
                    q_repo.update(quotation_id, config_server_models=config_server_models)
                if config_warranty_info:
                    q_repo.update(quotation_id, config_warranty_info=config_warranty_info)
                item_count = q_repo.save_items(quotation_id, all_items)
            finally:
                q_repo.close()

            result = {"status": "success", "items_saved": item_count,
                      "opportunity_id": opportunity_id, "quotation_id": quotation_id}
        except Exception as e:
            logger.error("save_opportunity failed: %s", e)
            return {"status": "error", "message": f"Database save error: {e}"}

        # 3) KP 价格同步 — 默认关闭（工作台单条手动同步）；KP_AUTO_SYNC_ENABLED=true 恢复
        if os.environ.get("KP_AUTO_SYNC_ENABLED", "false").lower() == "true":
            try:
                new_kp = self.engine.sync_kp_prices_to_db(cleaned)
                if new_kp > 0:
                    result['kp_synced'] = new_kp
            except Exception as e:
                print(f"[WARN QuoteService.save_opportunity] KP sync failed (non-fatal): {e}")

        if 'opportunity_id' not in result:
            result['opportunity_id'] = opportunity_info.get('opportunity_id', '')
        return result

    def get_kp_history(self, model: str) -> list:
        return self.engine.get_kp_price_history(model)

    def close(self):
        self.kp_repo.close()
        self.l6_repo.close()
        self.opportunity_repo.close()

