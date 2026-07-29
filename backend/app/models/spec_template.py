"""
规格书模板模型

核心设计：
- branding: 品牌配置（Logo、公司名、联系方式等）
- display_options: 显示控制（价格列、合计行、校验标记等）

数据流：
- 编辑：用户在表单中配置 → 保存 branding/display_options
- 预览：读取配置 → SpecSheet.vue 渲染 → 实时预览
- 打印：读取配置 → SpecSheet.vue 渲染 → window.print()
"""
from sqlalchemy import Column, Integer, String, JSON, Boolean
from app.models.base import Base, opp_engine


class SpecTemplate(Base):
    __tablename__ = "spec_templates"
    __table_args__ = {"schema": "opportunities"}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200), nullable=False)
    is_default = Column(Boolean, default=False)

    # 品牌配置
    branding = Column(JSON, nullable=False, default={}, comment="品牌配置")

    # 布局配置（旧字段，保留兼容）
    layout = Column(JSON, nullable=False, default={}, comment="布局配置")

    # 字段配置（旧字段，保留兼容）
    fields = Column(JSON, nullable=False, default={}, comment="字段配置")

    # 显示控制
    display_options = Column(JSON, nullable=True, default={}, comment="显示控制")

    created_at = Column(String(50), nullable=False)
    updated_at = Column(String(50), nullable=False)
