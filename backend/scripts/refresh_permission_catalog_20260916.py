# -*- coding: utf-8 -*-
"""权限目录对齐菜单迁移（2026-09-16，一次性幂等）。

背景：用户与权限页的角色勾选目录与导航菜单严重脱节——page.opportunities 与
page.opportunities_all 共用「商机线索」名、策略中心/解决方案名不一致、AI 办公室
无页面权限、目录里有三个零 enforcement 死键。本次对齐：
  ① 目录：跑 ensure_permission_catalog（已知 key 标签对齐菜单 + 补 page.office + 删死键）
  ② 角色：给全部存量角色补 page.office（此前菜单恒开，升级不得有人掉权）；
     顺手清掉角色 permissions 里的死键残留。
admin 角色是目录全量兜底（permissions_of 特判），无需处理。
幂等：重复运行零改动。运行：cd backend && python -X utf8 scripts/refresh_permission_catalog_20260916.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.startup import ensure_permission_catalog  # noqa: E402
from app.repository.role_repo import RoleRepository  # noqa: E402
from app.core.startup import _REMOVED_PERMISSION_KEYS  # noqa: E402

OFFICE_KEY = "page.office"


def main() -> int:
    ensure_permission_catalog()

    repo = RoleRepository()
    try:
        for role in repo.list_all():
            key = role.get("role_key")
            perms = list(role.get("permissions") or [])
            if key == "admin":
                continue
            dropped = [p for p in perms if p in _REMOVED_PERMISSION_KEYS]
            perms = [p for p in perms if p not in _REMOVED_PERMISSION_KEYS]
            added = OFFICE_KEY not in perms
            if added:
                perms.append(OFFICE_KEY)
            if dropped or added:
                repo.update(key, permissions=perms)
                print(f"role {key}: +{[OFFICE_KEY] if added else []} -{dropped}")
            else:
                print(f"role {key}: 已正确，零改动")
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
