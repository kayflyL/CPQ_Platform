# -*- coding: utf-8 -*-
"""在售产品目录读取（数据源）。

只保留需求理解 / 智能反问 / 槽位校验共用的目录读取能力：
types = 启用且至少有一个在售机型的类型；models_by_type = 类型名 -> 在售机型。
"""

from app.repository.server_catalog_repo import ServerCatalogRepository


def _in_sale(model: dict) -> bool:
    return (model.get("lifecycle_status") or "active") not in ("discontinued", "eol")


def load_catalog() -> tuple:
    """返回 (types, models_by_type_name)。"""
    repo = ServerCatalogRepository()
    try:
        all_types = repo.list_types()
        models_by_type: dict = {}
        for t in all_types:
            ms = [m for m in repo.list_models(type_id=t.get("id")) if _in_sale(m)]
            if ms:
                models_by_type[t.get("name") or ""] = ms
        types = [t for t in all_types if (t.get("name") or "") in models_by_type]
    finally:
        pass
    return types, models_by_type
