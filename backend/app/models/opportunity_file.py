"""Opportunity file tracking model — maps opportunity_files table"""
from typing import Optional
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class OpportunityFile(Base):
    """Tracks files associated with opportunities (uploads and exports)"""
    __tablename__ = "opportunity_files"

    file_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    file_type: Mapped[str] = mapped_column(String)  # 'upload' or 'export'
    original_name: Mapped[str] = mapped_column(String)
    stored_path: Mapped[str] = mapped_column(Text)  # Relative path within storage
    file_size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String)
    created_by: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "file_id": self.file_id,
            "opportunity_id": self.opportunity_id,
            "file_type": self.file_type,
            "original_name": self.original_name,
            "stored_path": self.stored_path,
            "file_size": self.file_size,
            "created_at": self.created_at,
            "created_by": self.created_by or "",
        }
