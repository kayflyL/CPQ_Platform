# -*- coding: utf-8 -*-
"""商机统计口径工具（opportunity_stats）测试（2026-09-16）。

趋势报告数字随机漂移的根治：统计数字唯一来源=与商机线索页同一份实现的确定性工具。
本文件锁三件事：
1. 口径实现单点：dashboard / opportunity_repo / 工具全部指向 opp_caliber_repo + opp_stats
2. 工具注册：spec 在册、registry 按 enabled_tools 启用、坏日期参数不炸
3. compute 的全量数字口径由生产库人工核验（本月 18/Polaris 7 与线索页一致），
   这里只测离线可测的部分。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch


def test_caliber_impls_are_shared_not_copied():
    """口径实现单点：dashboard 的别名与线索页 repo 的委托都指向同一份函数。"""
    import app.api.dashboard as dash
    import app.repository.opp_caliber_repo as core

    assert dash._current_slot_map is core.current_slot_map
    assert dash._current_config_subquery is core.current_config_subquery
    import app.services.opp_stats as svc
    assert svc.current_slot_map is core.current_slot_map
    assert svc.current_config_subquery is core.current_config_subquery


def test_repo_slot_map_delegates_to_core():
    """线索页 repo 的 _current_slot_map 只是会话适配，实现委托给口径核心。"""
    from app.repository.opportunity_repo import OpportunityRepository

    sent = {}

    def _capture(session, opp_ids=None):
        sent["session"] = session
        return {"OPP-1": {"platform_type": "Polaris"}}

    repo = OpportunityRepository()
    repo._session = MagicMock(name="session")
    with patch("app.repository.opp_caliber_repo.current_slot_map", _capture):
        out = repo._current_slot_map(["OPP-1"])
    assert out == {"OPP-1": {"platform_type": "Polaris"}}
    assert sent["session"] is repo.session


def test_opportunity_stats_tool_registered():
    from app.services.agent_tool_specs import _TOOL_SPECS, build_tool_registry

    assert "opportunity_stats" in _TOOL_SPECS
    reg = build_tool_registry({"enabled_tools": ["opportunity_stats"]})
    assert "opportunity_stats" in reg.names()
    # 默认不进全集（default_enabled=False，同 query_data：按节点显式启用）
    reg_default = build_tool_registry({})
    assert "opportunity_stats" not in reg_default.names()


def test_compute_bad_dates_returns_error_without_db():
    from app.services.opp_stats import compute_opp_stats

    out = compute_opp_stats("not-a-date", "2026-09-16")
    assert out.get("ok") is False and "YYYY-MM-DD" in out.get("error", "")


def test_tool_handler_passes_window_args():
    from app.services.agent_tool_handlers import _tool_opportunity_stats

    with patch("app.services.opp_stats.compute_opp_stats", return_value={"ok": True}) as fake:
        out = asyncio.run(_tool_opportunity_stats({"start": "2026-01-01", "end": "2026-09-16"}))
    assert out == {"ok": True}
    fake.assert_called_once_with("2026-01-01", "2026-09-16")


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  OK {fn.__name__}"); passed += 1
        except Exception:
            print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
