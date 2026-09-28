"""
Rules database models for configurable business logic.
"""
from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from app.models.base import Base


class ParseTemplate(Base):
    """解析模板：区域/字段规则按模板隔离；标准文件与自检挂在模板上"""
    __tablename__ = 'parse_templates'
    __table_args__ = {'schema': 'rules'}

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True, comment='模板名')
    is_fallback = Column(Integer, nullable=False, default=0, comment='1=通用兜底模板（匹配不到时使用）')
    fingerprint_tag = Column(String(100), nullable=True, unique=True, comment='已退役(2026-09-27 匹配链删除)：列惰性保留，代码不再读写')
    # 标准文件层（storage key 指向 backend/storage 下的中性桶）
    std_file_key = Column(Text, nullable=True, comment='标准文件 storage key')
    std_source_key = Column(Text, nullable=True, comment='生成标准文件所用的原始底稿 storage key')
    std_version = Column(Integer, nullable=False, default=0, comment='标准文件版本号（每次生成/替换 +1）')
    std_generated_at = Column(String(40), nullable=True, comment='标准文件最后生成时间')
    # 自检层：样例文件 + 期望快照回归；规则改动置 stale，失败拦下发
    sample_file_key = Column(Text, nullable=True, comment='自检样例文件 storage key')
    expected_snapshot = Column(Text, nullable=True, comment='期望解析快照 JSON')
    selfcheck_status = Column(String(20), nullable=False, default='none', comment='none/passed/failed/stale')
    selfcheck_ran_at = Column(String(40), nullable=True, comment='自检最后运行时间')
    selfcheck_detail = Column(Text, nullable=True, comment='自检结果明细 JSON')
    enabled = Column(Integer, nullable=False, default=1, comment='是否参与匹配链')
    sort_order = Column(Integer, nullable=False, default=0, comment='模板排列顺序')
    note = Column(String(200), nullable=True, comment='备注')
    created_at = Column(String(40), nullable=True)
    updated_at = Column(String(40), nullable=True)


class ParseScopeBinding(Base):
    """解析模板使用位置绑定：入口 scope_key 由后端注册表定死，绑到哪个模板在设置页配"""
    __tablename__ = 'parse_scope_bindings'
    __table_args__ = {'schema': 'rules'}

    scope_key = Column(String(80), primary_key=True, comment='使用位置键（后端注册表）')
    template_id = Column(Integer, nullable=False, comment='绑定的解析模板 id')
    updated_at = Column(String(40), nullable=True)


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
    template_id = Column(Integer, ForeignKey('rules.parse_templates.id', ondelete='CASCADE'), nullable=True, index=True, comment='所属解析模板')
    exclude_keywords = Column(String(200), nullable=True, comment='行级排除词（逗号分隔；任一字段值整词命中即弃行）')


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
    template_id = Column(Integer, ForeignKey('rules.parse_templates.id', ondelete='CASCADE'), nullable=True, index=True, comment='所属解析模板')
