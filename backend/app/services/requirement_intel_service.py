# -*- coding: utf-8 -*-
"""需求分析公共辅助函数（仅保留仍被图执行器复用的系列权威源读取）。"""

# 平台系列权威源（本地定义；series 权威源 = system_config.server_series）。
_SERIES_KEYWORDS = ["Orion", "Polaris", "Intel", "工作站"]


def _load_series_values() -> list:
    """全平台系列权威源（system_config.server_series，[{value,label},...]）→ 值列表；读失败回退常量。"""
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            raw = repo.get_value("server_series", [])
        finally:
            repo.close()
        if isinstance(raw, list):
            vals = [str(it["value"]) for it in raw
                    if isinstance(it, dict) and it.get("value")]
            if vals:
                return vals
    except Exception:
        pass
    return list(_SERIES_KEYWORDS)
