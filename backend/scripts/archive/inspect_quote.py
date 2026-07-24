"""
诊断脚本：导出模板预览时，CFG1/CFG2 的占位符 {{L6维保描述}}/{{KP维保描述}} 未被填充
=========================================================================
背景：预览后只有 CFG3 正确显示数据，CFG1/CFG2 仍保留 {{...}} 原文。
代码层面已确认——只要 binding 作用到某页，占位符必被改写；
所以问题出在「binding 为什么没作用到 CFG1/CFG2」，需要看模板的 bindings 实际数据。

用法（在 backend 目录下执行）:
    python scripts/inspect_quote.py QUO-20260707211813663420

然后把关心的那个模板（你测试用的）对应的那段输出贴回来即可。
"""
import sys
import json
from pathlib import Path

# 无论从哪里运行，都回到 backend 根，以便 import app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.models.base import Opportunity_SessionLocal

QUO_ID = sys.argv[1] if len(sys.argv) > 1 else "QUO-20260707211813663420"


def norm(v):
    """JSON 列可能是 dict/list/str，统一成可序列化结构"""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return v
    return v


db = Opportunity_SessionLocal()
try:
    print("########## 1) 报价单的配置字段（决定拆页与取值）##########")
    q = db.execute(text("""
        SELECT quotation_id, config_count,
               config_descriptions, config_server_models,
               config_quantities, config_warranty_info
        FROM opportunities.quotations
        WHERE quotation_id = :qid
    """), {"qid": QUO_ID}).mappings().first()
    if not q:
        print(f"!! 未找到报价单 {QUO_ID}")
    else:
        print(json.dumps({k: norm(q[k]) for k in q}, ensure_ascii=False, indent=2))

    print("\n########## 2) 报价单项（补充 config 来源；表名若不对可忽略报错）##########")
    try:
        items = db.execute(text("""
            SELECT config_name, category, part_name, qty, final_price
            FROM opportunities.opportunity_items
            WHERE quotation_id = :qid
            ORDER BY config_name, category
        """), {"qid": QUO_ID}).mappings().all()
        print(f"共 {len(items)} 项")
        for it in items:
            print(json.dumps({k: it[k] for k in it}, ensure_ascii=False))
    except Exception as e:
        print(f"(opportunity_items 查询失败，可忽略：{e})")

    print("\n########## 3) 所有导出模板（重点看：bindings / sheet_config / 每页结构）##########")
    tpls = db.execute(text("""
        SELECT id, name, display_name, is_default,
               bindings, sheet_config, workbook_snapshot
        FROM opportunities.univer_templates
        ORDER BY id
    """)).mappings().all()
    print(f"共 {len(tpls)} 个模板")
    for t in tpls:
        snap = norm(t["workbook_snapshot"]) or {}
        sheets = snap.get("sheets", {}) if isinstance(snap, dict) else {}
        print(json.dumps({
            "id": t["id"],
            "name": t["name"],
            "display_name": t["display_name"],
            "is_default": t["is_default"],
            "sheet_config": norm(t["sheet_config"]),
            "workbook_sheetOrder": snap.get("sheetOrder") if isinstance(snap, dict) else None,
            "workbook_sheets": {
                sid: {"name": (s or {}).get("name"),
                      "_config_name": (s or {}).get("_config_name")}
                for sid, s in sheets.items()
            },
            "bindings": norm(t["bindings"]),
        }, ensure_ascii=False, indent=2))

finally:
    db.close()

print("\n完成。请把【你测试用的那个模板】对应的那段，以及第 1 节，整段贴回。")
