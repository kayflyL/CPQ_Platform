"""Opportunity file repository - handles file tracking database operations"""
from sqlalchemy.orm import Session
from app.models.opportunity_file import OpportunityFile
from app.models.base import Opp_SessionLocal
from typing import List, Optional
from datetime import datetime


class OpportunityFileRepository:
    """Repository for opportunity file operations"""
    
    def __init__(self):
        self._session: Optional[Session] = None
    
    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = Opp_SessionLocal()
        return self._session
    
    def close(self):
        """Close database session"""
        if self._session:
            self._session.close()
    
    def add_file(self, opportunity_id: str, file_type: str, original_name: str, 
                 stored_path: str, file_size: int, created_by: Optional[str] = None) -> OpportunityFile:
        """Add a new file record"""
        file_record = OpportunityFile(
            opportunity_id=opportunity_id,
            file_type=file_type,
            original_name=original_name,
            stored_path=stored_path,
            file_size=file_size,
            created_at=datetime.now().isoformat(),
            created_by=created_by
        )
        self.session.add(file_record)
        self.session.commit()
        self.session.refresh(file_record)
        return file_record
    
    def get_files_by_opportunity(self, opportunity_id: str, file_type: Optional[str] = None) -> List[dict]:
        """Get all files for an opportunity"""
        query = self.session.query(OpportunityFile).filter(OpportunityFile.opportunity_id == opportunity_id)
        if file_type:
            query = query.filter(OpportunityFile.file_type == file_type)
        query = query.order_by(OpportunityFile.created_at.desc())
        files = query.all()
        return [f.to_dict() for f in files]
    
    def get_file_by_id(self, file_id: int) -> Optional[dict]:
        """Get file by ID"""
        file = self.session.query(OpportunityFile).filter(OpportunityFile.file_id == file_id).first()
        return file.to_dict() if file else None
    
    def delete_file(self, file_id: int) -> bool:
        """Delete a file record"""
        file = self.session.query(OpportunityFile).filter(OpportunityFile.file_id == file_id).first()
        if file:
            self.session.delete(file)
            self.session.commit()
            return True
        return False
    
    def delete_files_by_opportunity(self, opportunity_id: str) -> int:
        """Delete all file records for an opportunity"""
        files = self.session.query(OpportunityFile).filter(OpportunityFile.opportunity_id == opportunity_id).all()
        count = len(files)
        for file in files:
            self.session.delete(file)
        self.session.commit()
        return count
    
    def get_file_counts_by_opportunity(self, opportunity_id: str) -> dict:
        """Get file counts for an opportunity"""
        upload_count = self.session.query(OpportunityFile).filter(
            OpportunityFile.opportunity_id == opportunity_id,
            OpportunityFile.file_type == 'upload'
        ).count()
        
        export_count = self.session.query(OpportunityFile).filter(
            OpportunityFile.opportunity_id == opportunity_id,
            OpportunityFile.file_type == 'export'
        ).count()
        
        return {
            "upload_count": upload_count,
            "export_count": export_count
        }
