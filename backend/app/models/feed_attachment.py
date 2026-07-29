"""Feed attachment model — the file index for an opportunity.

Table: opportunities.opportunity_attachments
Replaces the old opportunity_files table + ad-hoc disk scans. Listing is a
query, not a filesystem walk. storage_key is UUID-based and NEVER derived
from business fields, so editing sales/chassis/platform no longer orphans
files. Versions share a version_group so re-uploads of the same logical
file keep history.
"""
from typing import Optional
from sqlalchemy import String, Text, Integer, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class FeedAttachment(Base):
    __tablename__ = "opportunity_attachments"
    __table_args__ = {"schema": "opportunities"}

    attachment_id: Mapped[str] = mapped_column(String, primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    # nullable: an attachment can float free in the file view without a message
    message_id: Mapped[Optional[str]] = mapped_column(String, default=None, index=True)
    uploader_user_id: Mapped[str] = mapped_column(String)
    original_filename: Mapped[str] = mapped_column(String)
    # Relative path within storage base, e.g. opportunities/{opp_id}/{aid}{ext}
    storage_key: Mapped[str] = mapped_column(Text)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    mime_type: Mapped[Optional[str]] = mapped_column(String, default=None)
    # 'upload' (user-uploaded) | 'export' (system-generated) | 'attachment'
    kind: Mapped[str] = mapped_column(String, default="upload")
    # Business semantics for the archive view: requirement | technical | sent_quote (NULL = uncategorized)
    category: Mapped[Optional[str]] = mapped_column(String, default=None, index=True)
    quotation_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    version_group: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_at: Mapped[str] = mapped_column(String)
    deleted_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "attachment_id": self.attachment_id,
            "opportunity_id": self.opportunity_id,
            "message_id": self.message_id or "",
            "uploader_user_id": self.uploader_user_id,
            "uploader_name": "",
            "original_filename": self.original_filename,
            "storage_key": self.storage_key,
            "file_size": self.file_size or 0,
            "mime_type": self.mime_type or "",
            "kind": self.kind or "upload",
            "category": self.category or "",
            "quotation_id": self.quotation_id or "",
            "version": self.version or 1,
            "version_group": self.version_group or "",
            "created_at": self.created_at or "",
            "deleted_at": self.deleted_at or "",
        }
