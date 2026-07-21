"""料号库 API（parts_master 统一 L6+KP 料号）"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from app.repository.parts_master_repo import PartsMasterRepository

router = APIRouter(prefix="/api/parts", tags=["parts"])


@router.get("")
def list_parts(category: Optional[str] = None, section: Optional[str] = None, search: Optional[str] = None):
    parts = PartsMasterRepository().list(category, search, section)
    return {"parts": parts, "total": len(parts)}


@router.get("/sections")
def list_sections():
    return {"sections": PartsMasterRepository().sections()}


@router.get("/categories")
def list_categories():
    return {"categories": PartsMasterRepository().categories()}


@router.get("/{pn}")
def get_part(pn: str):
    p = PartsMasterRepository().get(pn)
    if not p:
        raise HTTPException(404, "料号不存在")
    return p


@router.post("")
def create_part(data: dict):
    try:
        return {"pn": PartsMasterRepository().insert(data)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{pn}")
def update_part(pn: str, updates: dict):
    PartsMasterRepository().update(pn, updates)
    return {"ok": True}


@router.delete("/{pn}")
def delete_part(pn: str):
    PartsMasterRepository().delete(pn)
    return {"ok": True}
