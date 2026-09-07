# -*- coding: utf-8 -*-
"""线索登记表唯一视图：配置 + kp_rows 一套，不再暴露扁平键。"""


def test_requirement_slots_from_ext_only_kp_rows():
    """登记表唯一视图：配置 + kp_rows（part_category/description/qty）一套。"""
    from app.services.portal_flow_adapter import requirement_slots_from_ext
    ext = {
        "server_type": "AI训练", "series": "Orion", "form": "4U", "purchase_qty": 1,
        "warranty_years": 3,
        # ext 里仍可能有旧窄字段（历史数据/下游信号），但登记表视图不得再暴露它们。
        "cpu": {"model": "兆芯50000", "qty": 2, "cores": 96},
        "memory": {"total_gb": 768},
        "storage": [{"capacity": "1.92T", "qty": 2, "type": "SSD"}],
        "gpu": [{"tokens": ["L20"], "qty": 4}],
        "nic": {"NIC": [{"qty": 1}]},
        "raid": [{"model": "9460-8i", "qty": 1}],
        "kp_rows": [
            {"part_category": "CPU", "description": "兆芯50000 处理器（2.2GHz/96C）", "qty": 2},
            {"part_category": "Memory", "description": "768GB DDR5", "qty": 12},
        ],
    }
    slots = requirement_slots_from_ext(ext)
    assert slots["server_type"] == "AI训练"
    assert slots["platform_type"] == "Orion"
    assert slots["chassis_form"] == "4U"
    assert slots["purchase_qty"] == 1
    assert slots["warranty_years"] == "3"
    # 扁平键不再进登记表视图
    for k in ("cpu", "memory", "storage", "gpu", "nic", "raid", "psu"):
        assert k not in slots, f"登记表视图不应再暴露扁平键 {k}"
    assert slots["kp_rows"][0]["part_category"] == "CPU"
    assert slots["kp_rows"][0]["description"] == "兆芯50000 处理器（2.2GHz/96C）"
    assert slots["kp_rows"][0]["qty"] == 2
    assert slots["kp_rows"][1]["description"] == "768GB DDR5"
