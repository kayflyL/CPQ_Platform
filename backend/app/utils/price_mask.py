"""价格字段掩码（RBAC 字段级权限）—— 报价/报价单/配件等价格字段统一置空。

用法：API 层按 field_visible() 判断，不可见时对返回 dict/list 调用 mask_price_fields()
（返回新结构，不改原对象），保证"看不到价格"是后端强制，不是前端隐藏。
"""
from typing import Any

_PRICE_KEYS = {
    "total_price", "base_price", "final_price", "profit_margin", "db_price",
    "l6_price", "l6_custom_price", "l6_profit_margin", "kp_profit_margin",
    "total_cost", "total_sales", "profit", "margin_pct",
    "cost", "price", "amount", "unit_price", "sales_price", "cost_price",
    "total",
}


def mask_price_fields(obj: Any) -> Any:
    """递归把 dict/list 中的价格字段置为 None。"""
    if isinstance(obj, list):
        return [mask_price_fields(x) for x in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in _PRICE_KEYS:
                out[k] = None
            elif isinstance(v, (dict, list)):
                out[k] = mask_price_fields(v)
            else:
                out[k] = v
        return out
    return obj


# 配件域价格键（库价/价格历史/价格快照）—— field.parts.price 门控用。
# 与报价域 _PRICE_KEYS 分开维护：刻意不含 total/amount 等通用键，
# 避免误伤分页信封的 total（配件列表接口的响应就是 {parts/items, total} 形状）。
_PART_PRICE_KEYS = {
    "price", "latest_price", "unit_price", "unit_currency", "latest_currency",
    "latest_price_date", "latest_date", "price_history", "price_snapshot",
    "base_price", "final_price", "total_price",
}


def mask_part_price_fields(obj: Any) -> Any:
    """递归把配件结构（料号行/KP行/案例/价格历史）中的库价字段置为 None。"""
    if isinstance(obj, list):
        return [mask_part_price_fields(x) for x in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in _PART_PRICE_KEYS:
                out[k] = None
            elif isinstance(v, (dict, list)):
                out[k] = mask_part_price_fields(v)
            else:
                out[k] = v
        return out
    return obj
