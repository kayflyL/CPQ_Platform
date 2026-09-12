"""KP (Key Parts) models — 配件管理 6 张规范化表

kp_categories      — 分类主表（支持层级）
kp_parts           — 配件主表
kp_part_specs      — 规格参数（键值对，按分类差异化）
kp_price_history   — 价格历史
kp_part_compat     — 兼容机型关联
kp_part_related    — 关联配件推荐

旧表 kp_records 保留作为备份，不再使用。
"""
from typing import Optional, List
from datetime import datetime, date
from sqlalchemy import Integer, String, Float, Text, Date, DateTime, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class KPCategory(Base):
    """配件分类"""
    __tablename__ = "kp_categories"
    __table_args__ = {"schema": "kp"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kp.kp_categories.id"))
    icon: Mapped[Optional[str]] = mapped_column(String(50))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    parent: Mapped[Optional["KPCategory"]] = relationship("KPCategory", remote_side=[id], backref="children")
    parts: Mapped[List["KPPart"]] = relationship("KPPart", back_populates="category")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "icon": self.icon,
            "sort_order": self.sort_order,
            "description": self.description,
        }


class KPPart(Base):
    """配件主表 — 一个型号一条记录"""
    __tablename__ = "kp_parts"
    __table_args__ = {"schema": "kp"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kp.kp_categories.id"))
    oem_sku: Mapped[Optional[str]] = mapped_column(String(200))
    alt_sku: Mapped[Optional[str]] = mapped_column(String(200))
    brand: Mapped[Optional[str]] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    short_desc: Mapped[Optional[str]] = mapped_column(Text)
    full_desc: Mapped[Optional[str]] = mapped_column(Text)
    condition: Mapped[str] = mapped_column(String(50), default="全新")
    lead_time: Mapped[Optional[str]] = mapped_column(String(100))
    image_url: Mapped[Optional[str]] = mapped_column(Text)
    datasheet_url: Mapped[Optional[str]] = mapped_column(Text)
    moq: Mapped[int] = mapped_column(Integer, default=1)
    applicable: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    category: Mapped[Optional["KPCategory"]] = relationship("KPCategory", back_populates="parts")
    specs: Mapped[List["KPPartSpec"]] = relationship("KPPartSpec", back_populates="part", cascade="all, delete-orphan")
    price_history: Mapped[List["KPPriceHistory"]] = relationship("KPPriceHistory", back_populates="part", cascade="all, delete-orphan")
    compat_servers: Mapped[List["KPPartCompat"]] = relationship("KPPartCompat", back_populates="part", cascade="all, delete-orphan")

    def to_dict(self, include_specs=False, include_history=False, include_compat=False) -> dict:
        d = {
            "id": self.id,
            "category_id": self.category_id,
            "category_name": self.category.name if self.category else None,
            "oem_sku": self.oem_sku,
            "alt_sku": self.alt_sku,
            "brand": self.brand,
            "name": self.name,
            "short_desc": self.short_desc,
            "full_desc": self.full_desc,
            "condition": self.condition,
            "lead_time": self.lead_time,
            "image_url": self.image_url,
            "datasheet_url": self.datasheet_url,
            "moq": self.moq,
            "applicable": self.applicable,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_specs:
            d["specs"] = [s.to_dict() for s in sorted(self.specs, key=lambda x: x.sort_order)]
        if include_history:
            d["price_history"] = [h.to_dict() for h in sorted(self.price_history, key=lambda x: x.price_date or datetime.min.date(), reverse=True)]
        if include_compat:
            d["compat_servers"] = [c.to_dict() for c in self.compat_servers]
        return d


class KPPartSpec(Base):
    """配件规格参数（键值对，按分类差异化）"""
    __tablename__ = "kp_part_specs"
    __table_args__ = (
        UniqueConstraint("part_id", "spec_key"),
        {"schema": "kp"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[int] = mapped_column(Integer, ForeignKey("kp.kp_parts.id", ondelete="CASCADE"))
    spec_key: Mapped[str] = mapped_column(String(200), nullable=False)
    spec_value: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    part: Mapped["KPPart"] = relationship("KPPart", back_populates="specs")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "part_id": self.part_id,
            "spec_key": self.spec_key,
            "spec_value": self.spec_value,
            "sort_order": self.sort_order,
        }


class KPPriceHistory(Base):
    """价格历史记录"""
    __tablename__ = "kp_price_history"
    __table_args__ = {"schema": "kp"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[int] = mapped_column(Integer, ForeignKey("kp.kp_parts.id", ondelete="CASCADE"))
    price: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="RMB")
    price_date: Mapped[Optional[date]] = mapped_column(Date)
    note: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    part: Mapped["KPPart"] = relationship("KPPart", back_populates="price_history")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "part_id": self.part_id,
            "price": self.price,
            "currency": self.currency,
            "price_date": self.price_date.isoformat() if self.price_date else None,
            "note": self.note,
            "source": self.source,
        }


class KPPartCompat(Base):
    """配件兼容机型关联（多对多）"""
    __tablename__ = "kp_part_compat"
    __table_args__ = (
        UniqueConstraint("part_id", "server_model"),
        {"schema": "kp"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[int] = mapped_column(Integer, ForeignKey("kp.kp_parts.id", ondelete="CASCADE"))
    server_model: Mapped[str] = mapped_column(String(200), nullable=False)

    part: Mapped["KPPart"] = relationship("KPPart", back_populates="compat_servers")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "part_id": self.part_id,
            "server_model": self.server_model,
        }


class KPPartRelated(Base):
    """关联配件推荐"""
    __tablename__ = "kp_part_related"
    __table_args__ = (
        UniqueConstraint("source_part_id", "target_part_id"),
        {"schema": "kp"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_part_id: Mapped[int] = mapped_column(Integer, ForeignKey("kp.kp_parts.id", ondelete="CASCADE"))
    target_part_id: Mapped[int] = mapped_column(Integer, ForeignKey("kp.kp_parts.id", ondelete="CASCADE"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_part_id": self.source_part_id,
            "target_part_id": self.target_part_id,
            "sort_order": self.sort_order,
        }


class KPSearchAlias(Base):
    """检索别名：口语词 → 库内词形扩展（万兆→10G、千兆→1G、智凯→智铠）。

    part_lexicon 词法引擎的别名数据唯一来源（DB 权威源，startup 空表种子）；
    expansion 是空格分隔的 token 串，命中 alias 子串后全部并入查询 token。
    """
    __tablename__ = "kp_search_aliases"
    __table_args__ = (
        UniqueConstraint("alias"),
        {"schema": "kp"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alias: Mapped[str] = mapped_column(String(100), nullable=False)
    expansion: Mapped[str] = mapped_column(String(500), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "alias": self.alias,
            "expansion": self.expansion,
            "note": self.note,
            "enabled": bool(self.enabled),
        }


class KPPartSearchIndex(Base):
    """配件语义索引：料 → 检索文档 → 向量（BAAI/bge-small-zh-v1.5，本地 fastembed）。

    embedding 存 JSON 数组（512 维）；万件级内存余弦即可，不依赖 pgvector。
    content_hash 防重复嵌入（文档没变不重算）；applicable 快照供语义通道做系列作用域。
    新鲜度由 part_search 的 COUNT/MAX(updated_at) 对账保证——料增改后检索自动触发重建。
    """
    __tablename__ = "kp_part_search_index"
    __table_args__ = (
        UniqueConstraint("part_id"),
        {"schema": "kp"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[int] = mapped_column(Integer, ForeignKey("kp.kp_parts.id", ondelete="CASCADE"))
    category: Mapped[Optional[str]] = mapped_column(String(100))
    doc_text: Mapped[Optional[str]] = mapped_column(Text)
    embedding: Mapped[Optional[dict]] = mapped_column(JSON)
    applicable: Mapped[Optional[dict]] = mapped_column(JSON)
    model_name: Mapped[Optional[str]] = mapped_column(String(100))
    dim: Mapped[Optional[int]] = mapped_column(Integer)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "part_id": self.part_id,
            "category": self.category,
            "doc_text": self.doc_text,
            "applicable": self.applicable,
            "model_name": self.model_name,
            "dim": self.dim,
            "content_hash": self.content_hash,
        }


# ============================================================
# 旧模型保留（向后兼容，不再新增数据）
# ============================================================
class KPRecord(Base):
    """旧表单表 — 已迁移到上述 6 张表，保留只读兼容"""
    __tablename__ = "kp_records"
    __table_args__ = {"schema": "kp"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[Optional[str]] = mapped_column(String, default=None)
    model: Mapped[Optional[str]] = mapped_column(String, default=None)
    price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    currency: Mapped[Optional[str]] = mapped_column(String, default="RMB")
    date: Mapped[Optional[str]] = mapped_column(String, default=None)
    note: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category or "",
            "model": self.model or "",
            "price": self.price or 0.0,
            "currency": self.currency or "RMB",
            "date": self.date or "",
            "note": self.note or "",
        }
