# -*- coding: utf-8 -*-
"""需求分析公共辅助函数（仅保留仍被图执行器复用的系列权威源读取）。"""

# 产品系列权威源 = 设置-服务器管理-产品系列（l6.server_types，用户可增删）。
# 系列识别词只读活目录，不做代码兜底；目录为空则返回 []。


def _load_series_values() -> list:
    """全平台产品系列权威源（l6.server_types，[{name/description/sort_order},...]）→ 系列名列表。

    读库失败或为空返回 []，绝不回退代码常量；增删产品系列即全站生效。
    """
    try:
        from app.repository.server_catalog_repo import ServerCatalogRepository
        types = ServerCatalogRepository().list_types()
        vals = [str(t.get("name")).strip() for t in types if t.get("name")]
        return [v for v in vals if v]
    except Exception:
        return []
