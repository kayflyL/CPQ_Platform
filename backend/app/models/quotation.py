"""Quotation model — one opportunity can have multiple quotations"""
import json
from typing import Optional
from sqlalchemy import Integer, String, Float, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class Quotation(Base):
    __tablename__ = "quotations"
    __table_args__ = {"schema": "opportunities"}

    quotation_id: Mapped[str] = mapped_column(String, primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[str] = mapped_column(String, default="v1")
    quotation_name: Mapped[Optional[str]] = mapped_column(String, default="")
    file_path: Mapped[Optional[str]] = mapped_column(Text, default=None)
    l6_price: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    total_qty: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    config_count: Mapped[Optional[int]] = mapped_column(Integer, default=1)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    status: Mapped[Optional[str]] = mapped_column(String, default="active")
    # 草稿/已导出状态机：NULL = 草稿（可进工作台编辑）；非空 = 已导出冻结（值=导出时间戳，点列表只看 Excel+成本快照）
    exported_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    # 导出时冻结的成本快照（整机/机箱/KP/质保 成本+售价+利润率，逐配置）——前端算、导出动作 POST 回来
    cost_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    
    # 报价单级字段（用户在报价单页面填写）
    quotation_date: Mapped[Optional[str]] = mapped_column(String, default=None)
    config_quantities: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    config_descriptions: Mapped[Optional[dict]] = mapped_column(JSON, default=None)  # 每个配置的描述
    config_server_models: Mapped[Optional[dict]] = mapped_column(JSON, default=None)  # 每个配置的服务器型号
    config_warranty_info: Mapped[Optional[dict]] = mapped_column(JSON, default=None)  # 每个配置的维保信息（年限/费率/描述）

    # 计算字段
    total_price: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    profit_margin: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    
    # 动态扩展字段（JSON 存储）
    extra_fields: Mapped[Optional[str]] = mapped_column(Text, default=None)
    
    # 多租户预留
    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default")

    # 主推标记
    is_primary: Mapped[Optional[bool]] = mapped_column(default=False)
    # L3 报价单来源：reasoning(推理流确认转草稿) / manual(工作台手动新建) / upload(Excel 上传)
    source: Mapped[str] = mapped_column(String, default="manual")
    # L3 策略溯源快照：导出时命中的定价策略（id/version/name/关键参数）；仅 reasoning 单有实际依据
    strategy_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, default=None)

    @staticmethod
    def _sanitize(obj):
        """Replace NaN/Inf with None so json.dumps won't fail."""
        if isinstance(obj, float) and (obj != obj or obj == float('inf') or obj == float('-inf')):
            return None
        if isinstance(obj, dict):
            return {k: Quotation._sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [Quotation._sanitize(v) for v in obj]
        return obj

    def to_dict(self) -> dict:
        result = {
            "quotation_id": self.quotation_id,
            "opportunity_id": self.opportunity_id,
            "version": self.version or "v1",
            "quotation_name": self.quotation_name or "",
            "file_path": self.file_path or "",
            "l6_price": self.l6_price or 0.0,
            "total_qty": self.total_qty or 0,
            "config_count": self.config_count or 1,
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
            "status": self.status or "active",
            "exported_at": self.exported_at or None,
            "cost_snapshot": self._sanitize(self.cost_snapshot) or None,
            "quotation_date": self.quotation_date or "",
            "config_quantities": self._sanitize(self.config_quantities) or {},
            "config_descriptions": self.config_descriptions or {},
            "config_server_models": self.config_server_models or {},
            "config_warranty_info": self.config_warranty_info or {},
            "total_price": self.total_price or 0.0,
            "profit_margin": self.profit_margin or 0.0,
            "is_primary": self.is_primary or False,
            "source": self.source or "manual",
            "strategy_snapshot": self._sanitize(self.strategy_snapshot) or None,
        }
        
        # 展开 extra_fields 到顶层
        if self.extra_fields:
            try:
                extra = json.loads(self.extra_fields)
                extra = {k: self._sanitize(v) for k, v in extra.items()}
                result.update(extra)
            except (json.JSONDecodeError, TypeError):
                pass
        
        return result
