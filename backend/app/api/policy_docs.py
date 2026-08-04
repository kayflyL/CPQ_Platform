"""策略文档库 API（/api/policy-docs）—— 无数字 id，增删改查用「创建时间戳」定位。

2026-08-04：文档从 rules.strategies（策略规则混表 + 自增 id）独立到 rules.policy_docs：
- 返回对象【无 id / doc_key】；
- 定位键 = (module, created_at)：新建返回 created_at，编辑/删除传回即可；
- 删除 = 永久删除，无任何 seed/补种。
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.repository.policy_doc_repo import PolicyDocRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/policy-docs", tags=["policy-docs"])


@router.get("")
def list_docs(module: Optional[str] = None, status: Optional[str] = None):
    """文档列表（可按 module/status 过滤）。返回对象无 id。"""
    repo = PolicyDocRepository()
    try:
        return {"docs": repo.list_docs(module=module, status=status)}
    finally:
        repo.close()


@router.post("")
def create_doc(data: dict):
    """新建文档。返回含 created_at（定位键，编辑/删除用）。"""
    repo = PolicyDocRepository()
    try:
        try:
            doc = repo.create_doc(data)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return doc
    finally:
        repo.close()


@router.put("")
def update_doc(data: dict):
    """按 (module, created_at) 定位更新；created_at 不变。version +1。"""
    module = data.get("module")
    created_at = data.get("created_at")
    if not module or not created_at:
        raise HTTPException(400, "缺少定位键：module + created_at")
    repo = PolicyDocRepository()
    try:
        doc = repo.update_doc(module, created_at, data)
        if doc is None:
            raise HTTPException(404, "未找到该文档（module + created_at 不匹配）")
        return doc
    finally:
        repo.close()


@router.delete("")
def delete_doc(module: str = Query(...), created_at: str = Query(...)):
    """按 (module, created_at) 定位删除（永久，无补种）。"""
    repo = PolicyDocRepository()
    try:
        ok = repo.delete_doc(module, created_at)
        if not ok:
            raise HTTPException(404, "未找到该文档（module + created_at 不匹配）")
        return {"success": True}
    finally:
        repo.close()
