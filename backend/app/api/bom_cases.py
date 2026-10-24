# -*- coding: utf-8 -*-
"""BOM案例库 API（/api/bom-cases）—— 选型配置 · BOM案例库。

- 无数字 id：case_key 为时间戳型业务键（BC-YYYYMMDD-HHMMSS-ffffff）；
- kp_lines 只存 [{part_id, qty, hint?}] 引用 kp_parts，详情返回解析后的 name/category/最新价；
- version 每次编辑 +1（golden 版本指纹引用）。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from app.repository.bom_case_repo import BomCaseRepository
from app.api.deps import get_current_user, require_perms, field_visible
from app.utils.price_mask import mask_part_price_fields

logger = logging.getLogger(__name__)
# 默认登录门槛；案例写操作收「解决方案」页权限（选型配置·BOM案例库所在域）。
# 价格：案例的 kp_lines 最新价 / price_snapshot / bom_excel_rows 底价按 field.parts.price 遮罩。
_PRICE_VIEW = "field.parts.price"
router = APIRouter(prefix="/api/bom-cases", tags=["bom-cases"],
                   dependencies=[Depends(get_current_user)])


def _mask_case(d, user):
    if d is not None and not field_visible(user, _PRICE_VIEW):
        return mask_part_price_fields(d)
    return d


@router.get("")
def list_cases(tag: Optional[str] = None, q: Optional[str] = None,
               enabled: Optional[bool] = None, with_parts: bool = False,
               server_type: Optional[str] = None, series: Optional[str] = None,
               model_id: Optional[int] = None,
               user: dict = Depends(get_current_user)):
    """分类过滤：系列(server_type: AI/通用…) / 平台(series: Orion/Polaris) / 机型(model_id)。"""
    repo = BomCaseRepository()
    try:
        cases = repo.list_cases(tag=tag, q=q, enabled=enabled, with_parts=with_parts,
                                server_type=server_type, series=series, model_id=model_id)
        if not field_visible(user, _PRICE_VIEW):
            cases = mask_part_price_fields(cases)
        return {"cases": cases}
    finally:
        repo.close()


@router.post("/l6-preview")
def l6_preview(data: dict):
    """按 BOM 模板求值 L6 配置单行（编辑器选基准配置/模板时调用；算不出的行留空手填）。"""
    from app.services.bom_template_eval import eval_l6_rows
    template_id = data.get("bom_template_id")
    base_config_id = data.get("base_config_id")
    if not template_id or not base_config_id:
        raise HTTPException(400, "需要 bom_template_id + base_config_id")
    rows = eval_l6_rows(int(template_id), int(base_config_id),
                        data.get("kp_lines") or [], data.get("chassis_signals") or {})
    return {"rows": rows}


@router.get("/{case_key}")
def get_case(case_key: str, user: dict = Depends(get_current_user)):
    repo = BomCaseRepository()
    try:
        d = repo.get_case(case_key)
        if not d:
            raise HTTPException(404, f"未找到 BOM案例 {case_key}")
        return _mask_case(d, user)
    finally:
        repo.close()


@router.post("", dependencies=[Depends(require_perms("page.strategies"))])
def create_case(data: dict):
    repo = BomCaseRepository()
    try:
        try:
            return repo.create_case(data)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except IntegrityError:
            raise HTTPException(409, "案例键冲突，请重试")
    finally:
        repo.close()


@router.put("/{case_key}", dependencies=[Depends(require_perms("page.strategies"))])
def update_case(case_key: str, data: dict):
    repo = BomCaseRepository()
    try:
        try:
            d = repo.update_case(case_key, data)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if not d:
            raise HTTPException(404, f"未找到 BOM案例 {case_key}")
        return d
    finally:
        repo.close()


@router.delete("/{case_key}", dependencies=[Depends(require_perms("page.strategies"))])
def delete_case(case_key: str):
    repo = BomCaseRepository()
    try:
        if not repo.delete_case(case_key):
            raise HTTPException(404, f"未找到 BOM案例 {case_key}")
        return {"success": True}
    finally:
        repo.close()
