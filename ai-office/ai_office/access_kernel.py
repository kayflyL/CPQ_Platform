# -*- coding: utf-8 -*-
"""access_kernel —— 权限谓词内核（第 5 步画边界解耦产出，2026-10-31）。

权限判断的纯逻辑（配置驱动 + 价格键族 fail-closed）住这里；app/api/deps 反向引用
本模块（api→服务=合法方向），服务层不再 import api 层。语义零变更，原实现见
deps.py 历史（2026-10-17 用户定调：价格机密级，灰度期无授权即无价）。
"""
from __future__ import annotations

from typing import Optional

# 价格字段键族：机密级，fail-closed——AUTH_ENABLED=false 灰度期也不对匿名/无授权者开放
# （2026-10-17 用户定调「被授权的账户可以看，其他都看不了」；含报价价/商机报价金额/配件库价）。
PRICE_FAILCLOSED_KEYS = {"field.quote.price", "field.opportunity.quote_price", "field.parts.price"}


def user_permissions(user: Optional[dict]) -> list:
    """按请求惰性解析用户权限并缓存到 user dict，避免同一次请求内反复查库。
    user 由 get_current_user 每次请求重建，权限仍是（该请求时刻）最新值。"""
    if not user:
        return []
    cached = user.get("_permissions")
    if cached is not None:
        return cached
    from app.repository.role_repo import RoleRepository
    repo = RoleRepository()
    try:
        perms = repo.permissions_of(user.get("role"))
    finally:
        repo.close()
    if isinstance(user, dict):
        user["_permissions"] = perms
    return perms


def field_visible(user: Optional[dict], key: str) -> bool:
    """字段级权限判断：AUTH_ENABLED=false（灰度）恒可见；否则需角色含 key。
    例外：价格键族 fail-closed，灰度期一律要求显式授权。"""
    from app.core.config import get_settings
    if not get_settings().AUTH_ENABLED:
        return key not in PRICE_FAILCLOSED_KEYS
    if not user:
        return False
    return key in user_permissions(user)


def user_has_permission(user: Optional[dict], key: str) -> bool:
    """权限判断（配置驱动）：AUTH_ENABLED=false 灰度期恒放行；否则按角色权限目录判断。
    例外：价格键族 fail-closed（同 field_visible）——灰度期无授权即无价格。"""
    if not key:
        return True
    if not user:
        return False
    from app.core.config import get_settings
    if not get_settings().AUTH_ENABLED:
        return key not in PRICE_FAILCLOSED_KEYS
    return key in user_permissions(user)
