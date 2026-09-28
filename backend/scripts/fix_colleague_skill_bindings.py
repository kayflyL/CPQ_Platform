# -*- coding: utf-8 -*-
"""一次性迁移：把同事 skills 数组里错位的 workflow 类型 key 归位到 workflows。

存量症状（2026-09-13 用户报告）：需求分析（type=workflow）被绑在 assistant/
support_engineer/data_analyst 的 skills 数组里，员工页 Skill 下拉选项不含
workflow → 前端显示裸 key「requirement_analysis」。

保存路径已加 _reclassify_skill_bindings 自动归位（api/ai_colleagues.py），
本脚本只负责把存量行一次修完，不用挨个员工点保存。

用法：cd backend && ./.venv/Scripts/python.exe -X utf8 scripts/fix_colleague_skill_bindings.py [--dry-run]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.ai_colleagues import (  # noqa: E402
    _load_skill_catalog_map, _read_config, _reclassify_skill_bindings, _write_config,
)
from app.repository.system_config_repo import SystemConfigRepository  # noqa: E402


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    repo = SystemConfigRepository()
    try:
        cfg = _read_config(repo)
        catalog = _load_skill_catalog_map()
        changed = []
        for colleague in cfg.get("colleagues") or []:
            before = (list(colleague.get("skills") or []), list(colleague.get("workflows") or []))
            _reclassify_skill_bindings(colleague, catalog)
            after = (list(colleague.get("skills") or []), list(colleague.get("workflows") or []))
            if before != after:
                changed.append((colleague.get("role_key"), before, after))
        if not changed:
            print("无需迁移：所有绑定位已是正确数组。")
            return
        for role_key, before, after in changed:
            print(f"{role_key}: skills {before[0]} -> {after[0]} | workflows {before[1]} -> {after[1]}")
        if dry_run:
            print("(dry-run，未写库)")
            return
        _write_config(repo, cfg)
        print(f"已写回 {len(changed)} 位同事的绑定。")
    finally:
        repo.close()


if __name__ == "__main__":
    main()
