"""Unified field service - provides centralized field definitions"""
import json
from ..repository.business_field_repo import BusinessFieldRepository
from ..repository.dynamic_source_field_repo import DynamicSourceFieldRepository


class UnifiedFieldService:
    """统一字段服务 - 消除各页面硬编码字段"""
    
    def __init__(self):
        self.business_field_repo = BusinessFieldRepository()
        self.dynamic_source_field_repo = DynamicSourceFieldRepository()
    
    def get_fields_by_scope(self, scope: str, export_visible_only: bool = False) -> list[dict]:
        """
        按业务域获取字段
        scope: opportunity / config / pricing / export / parse / system
        """
        all_fields = self.business_field_repo.list_enabled()
        
        # 过滤出该 scope 的字段
        # 注意：当前所有字段的 scope 都是 'all'，需要后续迁移脚本设置正确的 scope
        filtered = []
        for field in all_fields:
            field_scope = field.get('scope', 'all')
            if field_scope != 'all' and field_scope != scope:
                continue
            if export_visible_only and not field.get('export_visible', True):
                continue
            filtered.append(field)
        
        return filtered
    
    def get_fields_by_page(self, page: str) -> list[dict]:
        """
        按页面获取字段（基于 used_in_pages 字段）
        page: opportunity_detail / export_template / workbench / parse_template / ...
        """
        all_fields = self.business_field_repo.list_enabled()
        
        filtered = []
        for field in all_fields:
            used_in_pages_str = field.get('used_in_pages', '[]')
            try:
                used_in_pages = json.loads(used_in_pages_str)
                if page in used_in_pages:
                    filtered.append(field)
            except json.JSONDecodeError:
                pass
        
        return filtered
    
    def get_dynamic_source_fields(self, source_key: str = None) -> dict | list[dict]:
        """
        获取动态数据源子字段
        source_key: l6_details / kp_details / config_summary
        如果 source_key 为 None，返回所有数据源的所有字段
        """
        if source_key:
            return self.dynamic_source_field_repo.list_by_source(source_key)
        else:
            # 返回按数据源分组的所有字段
            all_fields = self.dynamic_source_field_repo.list_enabled()
            grouped = {}
            for field in all_fields:
                source = field['source_key']
                if source not in grouped:
                    grouped[source] = []
                grouped[source].append(field)
            return grouped
    
    def get_type_keywords(self) -> dict:
        """
        获取部件类型关键词映射（从 rules 表读取）
        """
        from ..repository.rules_repo import RulesRepository
        rules_repo = RulesRepository()
        type_keywords = rules_repo.get_type_keywords()
        
        if not type_keywords:
            # Fallback defaults
            return {
                "cpu": ["cpu", "processor", "处理器", "epyc", "xeon"],
                "memory": ["memory", "ram", "内存", "ddr", "dimm"],
                "hdd": ["hdd", "硬盘", "disk", "storage"],
                "ssd": ["ssd", "固态"],
                "gpu": ["gpu", "显卡", "graphics", "nvidia", "amd radeon"],
                "nic": ["nic", "网卡", "network", "ethernet"],
                "raid": ["raid", "raid card"],
                "psu": ["psu", "电源", "power supply"]
            }
        return type_keywords
    
    def get_component_mapping(self) -> dict:
        """
        获取组件映射（替代 template_filler.py 的硬编码）
        """
        # TODO: 从数据库读取
        return {
            "cpu_model": {"source": "l6_details", "field": "spec", "type": "cpu"},
            "cpu_qty": {"source": "l6_details", "field": "qty", "type": "cpu"},
            "memory_model": {"source": "l6_details", "field": "spec", "type": "memory"},
            "memory_qty": {"source": "l6_details", "field": "qty", "type": "memory"},
            "disk_model": {"source": "l6_details", "field": "spec", "type": "hdd"},
            "disk_qty": {"source": "l6_details", "field": "qty", "type": "hdd"},
            "gpu_model": {"source": "l6_details", "field": "spec", "type": "gpu"},
            "gpu_qty": {"source": "l6_details", "field": "qty", "type": "gpu"},
            "nic_model": {"source": "l6_details", "field": "spec", "type": "nic"},
            "nic_qty": {"source": "l6_details", "field": "qty", "type": "nic"}
        }
    
    def close(self):
        self.business_field_repo.close()
        self.dynamic_source_field_repo.close()
