"""服务器3D模型管理 — 参数化3D配置台的模型登记持久层。

Table: l6.server_3d_models
一个3D模型=一套参数化场景登记:名称可改、可关联具体服务器产品机型(像图纸那样的绑定),
关联后服务器配置页中部以3D场景替代2D图纸展示。layout_config 为前端不透明JSON
(布局覆盖参数,如盘位行列/CPU上限),后端整存整取不做解释。
对应 migrations/20261101_create_server_3d_models.sql。
"""
from typing import Optional
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class Server3dModel(Base):
    __tablename__ = "server_3d_models"
    __table_args__ = {"schema": "l6"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, default="")
    # 关联 l6.server_models.id;NULL=未关联(仅登记,不出现在配置页)
    model_id: Mapped[Optional[int]] = mapped_column(Integer, default=None, index=True)
    # 前端不透明JSON:布局覆盖(可空=用前端内置默认布局)
    layout_config: Mapped[Optional[str]] = mapped_column(Text, default=None)
    # 绑定 model_id 即上架(配置页中部显示该3D场景),解绑即隐藏——无独立上下架状态
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
