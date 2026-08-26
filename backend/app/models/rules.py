"""
Rules database models for configurable business logic.
"""
from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from app.models.base import Base


class KPCategoryMapping(Base):
    """KP 分类映射：关键词 → 标准分类"""
    __tablename__ = 'kp_category_mapping'
    __table_args__ = {'schema': 'rules'}
    
    id = Column(Integer, primary_key=True)
    keyword = Column(String(50), nullable=False, comment='关键词')
    category = Column(String(50), nullable=False, comment='标准分类名称')
    priority = Column(Integer, default=0, comment='优先级')


class MatchingRule(Base):
    """匹配规则配置"""
    __tablename__ = 'matching_rules'
    __table_args__ = {'schema': 'rules'}
    
    id = Column(Integer, primary_key=True)
    rule_name = Column(String(50), nullable=False, unique=True, comment='规则名称')
    rule_value = Column(Text, nullable=False, comment='规则值（JSON 或数值）')
    description = Column(String(200), comment='规则说明')


class ParseRegion(Base):
    """解析区域定义：Excel 中的逻辑区域"""
    __tablename__ = 'parse_regions'
    __table_args__ = {'schema': 'rules'}
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, comment='区域名：header/L6/KP/Warranty')
    start_keywords = Column(String(200), nullable=True, comment='起始关键词（逗号分隔）')
    end_keywords = Column(String(200), nullable=True, comment='结束关键词（逗号分隔）')
    skip_header_rows = Column(Integer, default=0, comment='区域内跳过几行')
    sort_order = Column(Integer, default=0, comment='区域排列顺序')
    region_key = Column(String(80), nullable=True, unique=True, comment='区域稳定标识')
    region_type = Column(String(20), nullable=False, default='dynamic', comment='static/dynamic')
    enabled = Column(Integer, nullable=False, default=1, comment='是否启用')
    start_mode = Column(String(20), nullable=False, default='keyword', comment='起始定位方式')
    end_mode = Column(String(20), nullable=False, default='eof', comment='结束定位方式')
    start_config = Column(Text, nullable=True, comment='起始定位参数 JSON')
    end_config = Column(Text, nullable=True, comment='结束定位参数 JSON')


class ParseFieldRule(Base):
    """解析字段规则：字段从哪个区域哪一列取值"""
    __tablename__ = 'parse_field_rules'
    __table_args__ = {'schema': 'rules'}
    
    id = Column(Integer, primary_key=True)
    field_key = Column(String(100), nullable=False, comment='关联 business_fields.key')
    region = Column(String(50), nullable=False, comment='所属区域：header/L6/KP/Warranty')
    region_id = Column(Integer, ForeignKey('rules.parse_regions.id', ondelete='SET NULL'), nullable=True, comment='关联区域 ID')
    source_type = Column(String(20), nullable=False, comment='提取方式：keyword/column')
    source_config = Column(Text, nullable=False, comment='提取参数 JSON')
    fallback_config = Column(Text, nullable=True, comment='兜底方案 JSON')
    enabled = Column(Integer, default=1, comment='是否启用')
    sort_order = Column(Integer, default=0, comment='排序')
