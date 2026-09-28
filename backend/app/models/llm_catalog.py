"""LLM 目录三软库（schema=rules）—— AI 推理配置器的参考数据层（P0b）。
llm_models: 大模型架构参数库（供应商/结构参数/注意力类型/置信度；字段与 Excel v10「模型库」sheet 对齐，
  另加 max_ctx（原生上下文上限）/ measured_size_gb（实测量化大小，置信度高可覆盖公式估算））。
inference_frameworks: 推理框架特性库（量化系数/张量并行/额外开销 GB）；**开销系数进表不写死**，
  随框架版本漂移在管理面可调。
scene_params: 应用场景参数表（推荐上下文/最低速度/多模态要求）。
首版数据 = Excel v10 首版导入（dry_run 报告 → 用户确认），此后 DB 权威，代码零种子逻辑。"""
from typing import Optional
from sqlalchemy import Boolean, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class LlmModel(Base):
    __tablename__ = "llm_models"
    __table_args__ = (
        UniqueConstraint("vendor", "name", name="uq_llm_models_vendor_name"),
        {"schema": "rules"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    params_b: Mapped[float] = mapped_column(Float, nullable=False)
    default_bits: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    hidden_dim: Mapped[Optional[int]] = mapped_column(Integer)
    num_layers: Mapped[Optional[int]] = mapped_column(Integer)
    attn: Mapped[str] = mapped_column(String(16), nullable=False, default="GQA")   # GQA/MHA/MLA
    num_heads: Mapped[Optional[int]] = mapped_column(Integer)
    kv_heads: Mapped[Optional[int]] = mapped_column(Integer)
    vision_gb: Mapped[Optional[float]] = mapped_column(Float)                      # 视觉投影层固定开销(GB)
    note: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(8), nullable=False, default="mid")  # high/mid/low
    max_ctx: Mapped[Optional[int]] = mapped_column(Integer)                        # 原生上下文上限(tokens)，管理面可补
    measured_size_gb: Mapped[Optional[float]] = mapped_column(Float)               # 实测量化文件大小(GB)
    created_at: Mapped[Optional[str]] = mapped_column(String(32))


class InferenceFramework(Base):
    __tablename__ = "inference_frameworks"
    __table_args__ = (
        UniqueConstraint("name", name="uq_inference_frameworks_name"),
        {"schema": "rules"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    default_quant: Mapped[Optional[str]] = mapped_column(String(32))
    coeff_4bit: Mapped[Optional[float]] = mapped_column(Float)
    coeff_8bit: Mapped[Optional[float]] = mapped_column(Float)
    coeff_16bit: Mapped[Optional[float]] = mapped_column(Float)
    tensor_parallel: Mapped[Optional[bool]] = mapped_column(Boolean)
    offload: Mapped[Optional[str]] = mapped_column(String(16))          # 原生/有限/不支持
    overhead_gb: Mapped[Optional[float]] = mapped_column(Float)         # 框架额外开销(GB/卡)
    kv_cache_note: Mapped[Optional[str]] = mapped_column(String(64))
    note: Mapped[Optional[str]] = mapped_column(Text)


class SceneParam(Base):
    __tablename__ = "scene_params"
    __table_args__ = (
        UniqueConstraint("name", name="uq_scene_params_name"),
        {"schema": "rules"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    recommend_ctx: Mapped[Optional[int]] = mapped_column(Integer)       # 推荐 num_ctx(tokens)
    min_tok_s: Mapped[Optional[float]] = mapped_column(Float)           # 最低速度要求(tok/s)
    need_vision: Mapped[Optional[bool]] = mapped_column(Boolean)        # 是否需多模态
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
