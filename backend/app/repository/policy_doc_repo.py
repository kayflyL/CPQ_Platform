"""策略文档库仓储（rules.policy_docs 独立表）—— 无数字 id，增删改查用「创建时间戳」定位。

2026-08-04：文档从 rules.strategies（与定价/选型规则混表 + 自增数字 id）独立出来：
- doc_key（UUID）仅作数据库主键，前端/API 永不暴露、永不递增；
- 业务定位键 = (module, created_at)：创建时间戳不可变、微秒精度，手动创建不会重复；
- 列表不返回任何 id；编辑/删除传 module + created_at 即可定位。
"""
import logging
from typing import Optional

from ..models.base import Rules_SessionLocal
from ..models.policy_doc import PolicyDoc

logger = logging.getLogger(__name__)

# 对外返回的文档结构：无 id/doc_key；body 保留旧结构兼容前端 readDocBody
def _to_dict(d: PolicyDoc) -> dict:
    def _iso(v) -> Optional[str]:
        return v.isoformat() if v else None
    return {
        "name": d.name,
        "module": d.module,
        "category": d.category,
        "sort_order": d.sort_order,
        "content_markdown": d.content_markdown,
        "description": d.description,
        "status": d.status,
        "version": d.version,
        "created_at": _iso(d.created_at),
        "updated_at": _iso(d.updated_at),
        "created_by": d.created_by,
        "updated_by": d.updated_by,
        # body 兼容旧前端 readDocBody(d.body)
        "body": {
            "module": d.module,
            "category": d.category,
            "sort_order": d.sort_order,
            "content_markdown": d.content_markdown,
        },
    }


class PolicyDocRepository:
    """策略文档库仓储（rules.policy_docs）。CRUD 全部以 (module, created_at) 定位，无数字 id。"""

    def __init__(self):
        self.session = Rules_SessionLocal()

    def list_docs(self, module: Optional[str] = None, status: Optional[str] = None) -> list:
        q = self.session.query(PolicyDoc)
        if module:
            q = q.filter(PolicyDoc.module == module)
        if status:
            q = q.filter(PolicyDoc.status == status)
        return [_to_dict(d) for d in q.order_by(PolicyDoc.sort_order, PolicyDoc.created_at).all()]

    def create_doc(self, data: dict) -> dict:
        """新建文档。返回含 created_at（定位键）。"""
        d = PolicyDoc(
            module=data.get("module") or "pricing",
            name=(data.get("name") or "").strip(),
            category=data.get("category") or "总览",
            sort_order=int(data.get("sort_order") or 1),
            content_markdown=data.get("content_markdown") or "",
            description=data.get("description"),
            status=data.get("status") or "active",
            created_by=data.get("operator") or "system",
            updated_by=data.get("operator") or "system",
        )
        if not d.name:
            raise ValueError("文档标题 name 必填")
        self.session.add(d)
        self.session.commit()
        self.session.refresh(d)
        return _to_dict(d)

    def _find(self, module: str, created_at: str) -> Optional[PolicyDoc]:
        if not module or not created_at:
            return None
        return self.session.query(PolicyDoc).filter(
            PolicyDoc.module == module,
            PolicyDoc.created_at == created_at,
        ).first()

    def update_doc(self, module: str, created_at: str, data: dict) -> Optional[dict]:
        """按 (module, created_at) 定位更新；created_at 不变（创建时间）。version +1。"""
        d = self._find(module, created_at)
        if not d:
            return None
        if "name" in data:
            d.name = (data["name"] or "").strip()
        if "category" in data:
            d.category = data["category"]
        if "sort_order" in data:
            d.sort_order = int(data.get("sort_order") or 1)
        if "content_markdown" in data:
            d.content_markdown = data["content_markdown"] or ""
        if "description" in data:
            d.description = data["description"]
        if "status" in data:
            d.status = data["status"]
        d.version = (d.version or 1) + 1
        d.updated_by = data.get("operator") or "system"
        self.session.commit()
        self.session.refresh(d)
        return _to_dict(d)

    def delete_doc(self, module: str, created_at: str) -> bool:
        """按 (module, created_at) 定位删除；删了就是删了，无任何补种机制。"""
        d = self._find(module, created_at)
        if not d:
            return False
        self.session.delete(d)
        self.session.commit()
        return True

    def close(self):
        self.session.close()
