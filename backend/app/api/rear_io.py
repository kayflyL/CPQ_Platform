"""后面板配置 API — 按机型系列返回槽位选项"""
from fastapi import APIRouter
from app.repository.rear_io_repo import RearIORepository
from app.repository.psu_options_repo import PsuOptionsRepository

router = APIRouter(prefix="/api/rear-io", tags=["rear-io"])


@router.get("/options")
def list_options(series: str = None):
    """获取后面板所有槽位的选项"""
    repo = RearIORepository()
    return {"slots": repo.get_all_slots(series)}


@router.get("/options/{slot}")
def slot_options(slot: str, series: str = None):
    """获取指定槽位的选项"""
    repo = RearIORepository()
    return {"options": repo.get_slot_options(slot, series)}


@router.get("/psu-options")
def list_psu_options(series: str = None):
    """获取电源选项"""
    repo = PsuOptionsRepository()
    return {"options": repo.list_options(series)}
