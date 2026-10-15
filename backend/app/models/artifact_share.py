"""产出物分享链接模型 — 网盘式分享（M：各节点产出物可转发/下载）的持久层。

Table: opportunities.artifact_share_tokens
分享 = 渲染落盘的 xlsx 文件 + 免登录下载令牌。token 即凭证（随机 32 字节），
可过期/可撤销/可选提取码；每次下载计数+时间留痕（审计）。
客户（报价）视角一期锁定——它等效外发，二期开放时创建须过外发审批闸。
"""
import secrets
from typing import Optional
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


def generate_share_token() -> str:
    # 32 字节 ≈ 43 字符 url-safe；免登录端点的唯一凭证
    return secrets.token_urlsafe(32)


class ArtifactShareToken(Base):
    __tablename__ = "artifact_share_tokens"
    __table_args__ = {"schema": "opportunities"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String, unique=True, index=True)
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    # quote / cost / scheme（requirement 二期）
    source_type: Mapped[str] = mapped_column(String)
    source_id: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String, default="")
    # scheme / cost / internal（customer 一期锁定）
    view: Mapped[str] = mapped_column(String, default="internal")
    template_id: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    filename: Mapped[str] = mapped_column(String, default="")
    storage_key: Mapped[str] = mapped_column(Text, default="")
    attachment_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    extract_code: Mapped[Optional[str]] = mapped_column(String, default=None)
    expires_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    revoked_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    last_download_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "token": self.token,
            "opportunity_id": self.opportunity_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "title": self.title or "",
            "view": self.view or "internal",
            "template_id": self.template_id,
            "filename": self.filename or "",
            "attachment_id": self.attachment_id or "",
            "has_extract_code": bool(self.extract_code),
            "expires_at": self.expires_at or "",
            "revoked_at": self.revoked_at or "",
            "download_count": self.download_count or 0,
            "last_download_at": self.last_download_at or "",
            "created_by": self.created_by or "",
            "created_at": self.created_at or "",
        }
