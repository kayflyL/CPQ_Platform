"""Role repository — RBAC 角色（rules.roles）+ 权限解析。

权限目录（哪些 key 存在）存 system_config.auth.permissions（管理员可维护）；
角色存 rules.roles（role_key / name / permissions JSON）。
permissions_of：admin 角色恒返回目录全部 key（超级管理员兜底，避免配置失误把自己锁死）；
其他角色按自己的 permissions 数组返回。
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select
import json

from app.models.role import Role
from app.models.base import Rules_SessionLocal
from app.repository.system_config_repo import SystemConfigRepository
from app.services.storage_adapter import now_iso

_PERMISSION_CATALOG_KEY = "auth.permissions"

_REMOVED_PERMISSION_KEYS = {"field.server.price"}


_DEFAULT_ROLES = [
    ("admin", "管理员", "拥有全部权限（含用户与权限管理）", None),
    ("business", "业务", "商机线索 + 服务器 + 配件", ["page.opportunities", "page.servers", "page.parts", "action.flow.submit.requirement", "action.opportunity.result"]),
    ("te", "技术支持工程师", "商机线索 + 服务器 + 配件", ["page.opportunities", "page.servers", "page.parts", "field.flow.bom", "action.flow.submit.boming", "action.flow.return.boming"]),
    ("quote", "市场报价专员", "商机线索 + 报价工作台（含价格）", ["page.opportunities", "field.quote.price", "field.opportunity.quote_price", "field.flow.bom", "field.flow.cost", "action.opportunity.result", "action.flow.return.quoting", "action.flow.submit.quoting"]),
    ("cost", "成本核算", "商机线索 + 报价/配件价格", ["page.opportunities", "field.quote.price", "field.opportunity.quote_price", "field.parts.price", "field.flow.bom", "field.flow.cost", "action.flow.submit.costing", "action.flow.return.costing"]),
    ("director", "总监", "看全量页面 + 价格 + 中间交付物 + 低毛利审批", ["page.opportunities_all", "page.opportunities", "page.servers", "page.parts", "page.strategies", "field.quote.price", "field.opportunity.quote_price", "field.parts.price", "field.flow.bom", "field.flow.cost", "action.flow.approve.pricing"]),
]


def _catalog_keys() -> List[str]:
    """权限目录全部 key（system_config.auth.permissions）。"""
    repo = SystemConfigRepository()
    try:
        catalog = repo.get_value(_PERMISSION_CATALOG_KEY, [])
    finally:
        repo.close()
    if not isinstance(catalog, list):
        return []
    return [p.get("key") for p in catalog if isinstance(p, dict) and p.get("key")]


class RoleRepository:
    def __init__(self):
        self._session: Optional[Session] = None

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = Rules_SessionLocal()
        return self._session

    def close(self):
        if self._session:
            self._session.close()

    # ── CRUD ──

    def list_all(self) -> List[dict]:
        rows = self.session.execute(
            select(Role).order_by(Role.role_key.asc())
        ).scalars().all()
        return [r.to_dict() for r in rows]

    def get(self, role_key: str) -> Optional[dict]:
        r = self.session.execute(
            select(Role).where(Role.role_key == role_key)
        ).scalar_one_or_none()
        return r.to_dict() if r else None

    def create(self, role_key: str, name: str, description: Optional[str] = None,
               permissions: Optional[List[str]] = None) -> dict:
        role = Role(
            role_key=(role_key or "").strip(),
            name=(name or "").strip(),
            description=description,
            permissions=json.dumps([p for p in (permissions or []) if isinstance(p, str)], ensure_ascii=False),
            updated_at=now_iso(),
        )
        self.session.add(role)
        self.session.commit()
        self.session.refresh(role)
        return role.to_dict()

    def update(self, role_key: str, name: Optional[str] = None, description: Optional[str] = None,
               permissions: Optional[List[str]] = None) -> Optional[dict]:
        r = self.session.execute(
            select(Role).where(Role.role_key == role_key)
        ).scalar_one_or_none()
        if not r:
            return None
        if name is not None:
            r.name = (name or "").strip()
        if description is not None:
            r.description = description
        if permissions is not None:
            r.permissions = json.dumps([p for p in permissions if isinstance(p, str)], ensure_ascii=False)
        r.updated_at = now_iso()
        self.session.commit()
        return r.to_dict()

    def delete(self, role_key: str) -> bool:
        r = self.session.execute(
            select(Role).where(Role.role_key == role_key)
        ).scalar_one_or_none()
        if not r:
            return False
        self.session.delete(r)
        self.session.commit()
        return True

    # ── 权限解析 ──

    def permissions_of(self, role_key: Optional[str]) -> List[str]:
        role_key = (role_key or "").strip() or "member"
        if role_key == "admin":
            return _catalog_keys()  # 超级管理员兜底：目录全量
        r = self.session.execute(
            select(Role).where(Role.role_key == role_key)
        ).scalar_one_or_none()
        if not r:
            return []
        return r.to_dict().get("permissions", [])

    # ── 种子（仅空表时写入一次，之后全部由页面维护）──

    def seed_defaults(self) -> int:
        existing = self.session.execute(select(Role.role_key)).all()
        if existing:
            return 0
        for key, name, desc, perms in _DEFAULT_ROLES:
            self.session.add(Role(
                role_key=key,
                name=name,
                description=desc,
                permissions=json.dumps(perms or [], ensure_ascii=False),
                updated_at=now_iso(),
            ))
        self.session.commit()
        return len(_DEFAULT_ROLES)

    def seed_missing_defaults(self) -> int:
        """非破坏补种默认角色的缺失权限（只追加，不删除用户自定义权限）。"""
        changed = 0
        for key, _name, _desc, perms in _DEFAULT_ROLES:
            if not perms:
                continue
            role = self.session.execute(
                select(Role).where(Role.role_key == key)
            ).scalar_one_or_none()
            if not role:
                continue
            current = set(role.to_dict().get("permissions", []))
            missing = set(perms) - current
            if missing:
                role.permissions = json.dumps(sorted(current | missing), ensure_ascii=False)
                role.updated_at = now_iso()
                changed += 1
        if changed:
            self.session.commit()
        return changed

    def prune_removed_permissions(self) -> int:
        """删除已下线的权限 key（如 serverconfig 无价后移除 field.server.price）。"""
        changed = 0
        for role in self.session.execute(select(Role)).scalars().all():
            current = role.to_dict().get("permissions") or []
            kept = [p for p in current if p not in _REMOVED_PERMISSION_KEYS]
            if len(kept) != len(current):
                role.permissions = json.dumps(kept, ensure_ascii=False)
                role.updated_at = now_iso()
                changed += 1
        if changed:
            self.session.commit()
        return changed
