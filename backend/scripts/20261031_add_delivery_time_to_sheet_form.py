"""一次性幂等脚本：requirement_sheet_form 增加「期望交期」字段（公开线索表与商机详情页同字段）。

跑法：cd backend && ./.venv/Scripts/python.exe -X utf8 scripts/20261031_add_delivery_time_to_sheet_form.py
- config_fields 中已存在 key=expected_delivery 时跳过（可重跑）
- 字段渲染走 RequirementForm 的通用 a-input 分支（control=text），随表单定义驱动，无需改组件
- slots 契约不扩（_BASIC_KEYS 不加 key）——AI 反问不问交期，表单与 slots 回传经 config 动态键往返
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.repository.system_config_repo import SystemConfigRepository

DELIVERY_FIELD = {
    "key": "expected_delivery",
    "label": "期望交期",
    "control": "text",
    "placeholder": "如 2026-12-31 / Q1 内（选填）",
}


def main() -> None:
    repo = SystemConfigRepository()
    try:
        form = repo.get_value("requirement_sheet_form", {}) or {}
        fields = form.get("config_fields") or []
        if any(f.get("key") == DELIVERY_FIELD["key"] for f in fields if isinstance(f, dict)):
            print("skip: expected_delivery already in requirement_sheet_form")
            return
        # 插到「数量」之后（与原型一致：形态/数量/维保 → 期望交期）
        insert_at = len(fields)
        for i, f in enumerate(fields):
            if isinstance(f, dict) and f.get("key") == "purchase_qty":
                insert_at = i + 1
                break
        fields.insert(insert_at, dict(DELIVERY_FIELD))
        form["config_fields"] = fields
        repo.set("requirement_sheet_form", form, type="json",
                 description="线索登记表单定义（字段/中文名/顺序/控件的唯一权威）")
        print(f"ok: expected_delivery inserted at position {insert_at}")
    finally:
        repo.close()


if __name__ == "__main__":
    main()
