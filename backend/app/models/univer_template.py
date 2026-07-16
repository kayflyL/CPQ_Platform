"""
Univer 导出模板模型（全新，与旧 export_templates 完全独立）

核心设计：
- workbook_snapshot: Univer 原生格式，存储完整的 workbook 数据（cellData/rowData/columnData/merges）
- bindings: 字段绑定配置（静态/动态）
- sheet_config: Sheet 角色标记（cover/config）+ 命名模板

数据流：
- 编辑：用户在 Univer 中编辑 → 保存 workbook_snapshot + bindings
- 预览：读取 snapshot + bindings → 填充数据 → 返回填充后的 snapshot → Univer 渲染
- 导出：读取 snapshot + bindings → 填充数据 → 转为 Excel → 下载
"""
from sqlalchemy import Column, Integer, String, JSON, Boolean
from app.models.base import Base, opp_engine


class UniverTemplate(Base):
    __tablename__ = "univer_templates"
    __table_args__ = {"schema": "opportunities"}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200), nullable=False)
    is_default = Column(Boolean, default=False)

    # 核心数据
    workbook_snapshot = Column(JSON, nullable=False, comment="Univer workbook 完整快照")
    bindings = Column(JSON, nullable=False, default=[], comment="字段绑定配置")
    sheet_config = Column(JSON, nullable=False, default={}, comment="Sheet 角色标记 + 命名模板")

    created_at = Column(String(50), nullable=False)
    updated_at = Column(String(50), nullable=False)
