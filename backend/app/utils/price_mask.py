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
