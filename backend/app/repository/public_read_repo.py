"""公开目录只读仓库 — 公开端点专用（cpq_public_ro 受限连接，回退主连接+警告）。

与 ServerCatalogRepository 的区别：
1. 列级白名单 SELECT（与 migrations/20261031_create_public_readonly_role.sql 的 GRANT 一一对应，
   两边必须同步改——角色没授权的列查了会炸，等于第二道闸）；
2. 只出 is_published 机型；
3. 绝不 JOIN/SELECT 任何可能带价的列或表。
"""
import json
import logging
from typing import List, Optional

from sqlalchemy import text

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_warned = False


def _public_engine():
    """公开链路引擎：PUBLIC_DB_URL（cpq_public_ro）优先；未配置回退主 l6_engine（打警告，不阻断）。"""
    global _engine, _warned
    if _engine is None:
        url = get_settings().PUBLIC_DB_URL
        if url:
            import sqlalchemy as sa
            _engine = sa.create_engine(url, pool_pre_ping=True)
        else:
            from app.models.base import l6_engine
            if not _warned:
                logger.warning("PUBLIC_DB_URL 未配置：公开端点回退主连接（建议建 cpq_public_ro 角色并配置，见迁移 SQL）")
                _warned = True
            _engine = l6_engine
    return _engine


def _json(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (TypeError, ValueError):
            return None
    return v


class PublicReadRepository:
    """列清单与角色 GRANT 对齐——两边一起改。"""

    _TYPE_COLS = "id, name, description, sort_order, showcase_config"
    _MODEL_COLS = ("m.id, m.name, m.server_type_id, m.use, m.base_config_id, m.sort_order, "
                   "m.description, m.image_url, m.lifecycle_status, m.product_content, m.is_published")
    _BC_JOIN_COLS = "bc.form AS bc_form, bc.bays AS bc_bays, bc.series AS bc_series, bc.name AS bc_name"

    @staticmethod
    def _attach_base_config(row: dict) -> dict:
        bc = None
        if row.get("base_config_id") is not None:
            bc = {
                "form": row.get("bc_form"),
                "bays": row.get("bc_bays"),
                "series": row.get("bc_series"),
                "name": row.get("bc_name"),
            }
        for k in ("bc_form", "bc_bays", "bc_series", "bc_name"):
            row.pop(k, None)
        row["base_config"] = bc
        row["product_content"] = _json(row.get("product_content"))
        # 公开面只留安全键；drawing_config/showcase 相关内部配置不出（与白名单 DTO 一致）
        row.pop("is_published", None)
        return row

    def list_types(self) -> List[dict]:
        with _public_engine().connect() as c:
            return [dict(r) for r in c.execute(
                text(f"SELECT {self._TYPE_COLS} FROM l6.server_types ORDER BY sort_order")
            ).mappings().all()]

    def list_published_models(self, type_id: Optional[int] = None) -> List[dict]:
        q = (f"SELECT {self._MODEL_COLS}, {self._BC_JOIN_COLS} "
             "FROM l6.server_models m LEFT JOIN l6.base_configs bc ON bc.id = m.base_config_id "
             "WHERE m.is_published")
        p: dict = {}
        if type_id:
            q += " AND m.server_type_id = :t"
            p["t"] = type_id
        q += " ORDER BY m.sort_order, m.id"
        with _public_engine().connect() as c:
            return [self._attach_base_config(dict(r))
                    for r in c.execute(text(q), p).mappings().all()]

    def get_published_model(self, model_id: int) -> Optional[dict]:
        q = (f"SELECT {self._MODEL_COLS}, {self._BC_JOIN_COLS} "
             "FROM l6.server_models m LEFT JOIN l6.base_configs bc ON bc.id = m.base_config_id "
             "WHERE m.id = :id AND m.is_published")
        with _public_engine().connect() as c:
            r = c.execute(text(q), {"id": model_id}).mappings().first()
            if not r:
                return None
            row = self._attach_base_config(dict(r))
            cfg_rows = c.execute(text("""
                SELECT id, name, form, bays, series, config_content
                FROM l6.base_configs WHERE model_id = :mid ORDER BY sort_order, id
            """), {"mid": model_id}).mappings().all()
        row["configs"] = []
        for cr in cfg_rows:
            cd = dict(cr)
            cd["config_content"] = _json(cd.get("config_content"))
            row["configs"].append(cd)
        return row
