"""
Rules database models for configurable business logic.
"""
from sqlalchemy import Column, Integer, String, Float, Text
from app.models.base import Base


class L6RegionConfig(Base):
    """L6 区域识别规则"""
    __tablename__ = 'l6_region_config'
    
    id = Column(Integer, primary_key=True)
    region_start_keywords = Column(String(200), nullable=False, comment='区域起始关键词，逗号分隔')
    field_mapping = Column(Text, nullable=False, comment='字段列映射 JSON')
    region_end_keywords = Column(String(200), nullable=False, comment='区域结束关键词，逗号分隔')


class KPRegionConfig(Base):
    """KP 区域识别规则"""
    __tablename__ = 'kp_region_config'
    
    id = Column(Integer, primary_key=True)
    region_start_keywords = Column(String(200), nullable=False, comment='区域起始关键词，逗号分隔')
    field_mapping = Column(Text, nullable=False, comment='字段列映射 JSON')
    region_end_keywords = Column(String(200), nullable=False, comment='区域结束关键词，逗号分隔')


class KPCategoryMapping(Base):
    """KP 分类映射：关键词 → 标准分类"""
    __tablename__ = 'kp_category_mapping'
    
    id = Column(Integer, primary_key=True)
    keyword = Column(String(50), nullable=False, comment='关键词')
    category = Column(String(50), nullable=False, comment='标准分类名称')
    priority = Column(Integer, default=0, comment='优先级')


class MotherboardMapping(Base):
    """主板映射：CPU 特征 → 主板型号"""
    __tablename__ = 'motherboard_mapping'
    
    id = Column(Integer, primary_key=True)
    cpu_feature = Column(String(100), nullable=False, comment='CPU 特征关键词')
    motherboard_model = Column(String(100), nullable=False, comment='主板型号')
    priority = Column(Integer, default=0, comment='优先级')


class MatchingRule(Base):
    """匹配规则配置"""
    __tablename__ = 'matching_rules'
    
    id = Column(Integer, primary_key=True)
    rule_name = Column(String(50), nullable=False, unique=True, comment='规则名称')
    rule_value = Column(Text, nullable=False, comment='规则值（JSON 或数值）')
    description = Column(String(200), comment='规则说明')
