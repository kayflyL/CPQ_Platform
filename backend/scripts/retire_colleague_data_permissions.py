# -*- coding: utf-8 -*-
"""一次性迁移：同事数据权限退役为「工具即权限」。

背景（2026-09-13 定调）：能力面 = tool_ids，价格可见性 = 同事级 price_access 布尔，
query_data 可读表 = 工具自有白名单（system_config.query_data_tables_allow，代码有默认 8 表兜底）。
按同事编辑的 data_boundary / data_sources 两个配置键退役。

注意：必须直接改 raw JSON（repo.get_value），不能走 _read_config——读侧归一化
normalize_colleague 已剥离 data_boundary，看不到旧值。

本脚本做的事：
1. 每位同事：缺 price_access 时按旧边界语义推导（mode=allow_read 且 price 不在
   masked_fields），然后从存量 JSON 里 pop data_boundary / data_sources。
2. 若 query_data_tables_allow 配置键不存在且方案助手旧边界有白名单表，则种成配置
   （当前库两者一致=默认 8 表，预期不写）。

用法：cd backend && ./.venv/Scripts/python.exe -X utf8 scripts/retire_colleague_data_permissions.py [--dry-run]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.repository.system_config_repo import SystemConfigRepository  # noqa: E402

_CONFIG_KEY = "ai_colleagues"
_TABLES_KEY = "query_data_tables_allow"


def _legacy_price_ok(colleague: dict) -> bool:
    boundary = colleague.get("data_boundary")
    if not isinstance(boundary, dict):
        return False
    if str(boundary.get("mode") or "") != "allow_read":
        return False
    return "price" not in {str(x) for x in (boundary.get("masked_fields") or [])}


def _legacy_tables(colleague: dict) -> list | None:
    boundary = colleague.get("data_boundary")
    if isinstance(boundary, dict) and boundary.get("mode") == "allow_read":
        tables = [str(x) for x in (boundary.get("tables_allow") or []) if str(x).strip()]
        if tables:
            return tables
    return None


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    repo = SystemConfigRepository()
    try:
        cfg = repo.get_value(_CONFIG_KEY, {}) or {}
        colleagues = cfg.get("colleagues") or []
        assistant_tables: list | None = None
        for colleague in colleagues:
            if not isinstance(colleague, dict):
                continue
            if "price_access" not in colleague:
                colleague["price_access"] = _legacy_price_ok(colleague)
            if colleague.get("role_key") == "assistant":
                assistant_tables = _legacy_tables(colleague)
            colleague.pop("data_boundary", None)
            colleague.pop("data_sources", None)
            print(f"{colleague.get('role_key')}: price_access={colleague.get('price_access')}")

        tables_row = repo.get(_TABLES_KEY)
        plan = "配置已存在，未动" if tables_row is not None else (
            f"将种入方案助手旧白名单 {assistant_tables}" if assistant_tables else "不种：用代码默认 8 表兜底")
        print(f"query_data_tables_allow: {plan}")
        if dry_run:
            print("(dry-run，未写库)")
            return
        repo.set(_CONFIG_KEY, cfg, "json",
                 "AI 同事配置（角色/人设/工具/入口/权限/团队/布局）", "admin")
        if tables_row is None and assistant_tables:
            repo.set(_TABLES_KEY, assistant_tables, "json",
                     "query_data 工具可读表白名单（工具自有权限）", "admin")
        print(f"已写回 {len(colleagues)} 位同事。")
    finally:
        repo.close()


if __name__ == "__main__":
    main()
