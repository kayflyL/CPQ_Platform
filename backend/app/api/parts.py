"""料号库 API（parts_master 统一 L6+KP 料号）"""
from fastapi import APIRouter, HTTPException
from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse
from typing import Optional
import pandas as pd
import io
from app.repository.parts_master_repo import PartsMasterRepository

router = APIRouter(prefix="/api/parts", tags=["parts"])


@router.get("")
def list_parts(
    category: Optional[str] = None,
    major_category: Optional[str] = None,
    section: Optional[str] = None,
    search: Optional[str] = None,
    chassis: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    sort_by: Optional[str] = None,   # name / unit_price
    sort_order: Optional[str] = None, # asc / desc
):
    """分页查询料号列表。page 从 1 开始。"""
    repo = PartsMasterRepository()
    all_parts = repo.list(category, search, section, major_category=major_category)
    if chassis:
        all_parts = [
            p for p in all_parts
            if chassis in (p.get("specs") or {}).get("chassis", [])
        ]
    # 排序
    if sort_by in ("name", "unit_price"):
        reverse = sort_order == "desc"
        all_parts.sort(key=lambda p: (p.get(sort_by) or "" if sort_by == "name" else p.get(sort_by) or 0), reverse=reverse)
    total = len(all_parts)
    start = (page - 1) * page_size
    end = start + page_size
    return {"parts": all_parts[start:end], "total": total}


@router.get("/sections")
def list_sections():
    return {"sections": PartsMasterRepository().sections()}

@router.get("/major-categories")
def list_major_categories():
    """大类汇总（一级主导航用）：[{major_category, count, categories:[子类...]}]。"""
    return {"major_categories": PartsMasterRepository().major_categories()}


# ---- 分类管理（大类/STEP 的增/改名/删，改名删除批量传播到 parts_master）----
@router.get("/taxonomy")
def list_taxonomy(kind: str = "major"):
    """分类列表：[{name, count, categories}]，顺序由 part_taxonomy 决定。kind=major|step。"""
    return {"items": PartsMasterRepository().list_taxonomy(kind)}

@router.post("/taxonomy")
def add_taxonomy(body: dict):
    """新增分类。body: {kind:'major'|'step', name}。"""
    try:
        return PartsMasterRepository().add_taxonomy(body.get("kind", ""), body.get("name", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.put("/taxonomy/rename")
def rename_taxonomy(body: dict):
    """重命名分类（批量传播到所有用了它的料号）。body: {kind, old_name, new_name}。"""
    try:
        updated = PartsMasterRepository().rename_taxonomy(
            body.get("kind", ""), body.get("old_name", ""), body.get("new_name", ""))
        return {"updated": updated}
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.delete("/taxonomy")
def delete_taxonomy(kind: str, name: str):
    """删除分类。被料号使用时拒绝（先把它们迁到别的分类）。"""
    try:
        return PartsMasterRepository().delete_taxonomy(kind, name)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/categories")
def list_categories():
    return {"categories": PartsMasterRepository().categories()}


@router.get("/spec-keys")
def get_spec_keys():
    """返回每个 category 下的 spec_key 列表，供策略编辑器下拉使用。"""
    return PartsMasterRepository().spec_keys()


@router.get("/spec-values")
def get_spec_values(category: str, spec_key: str):
    """返回指定 category + spec_key 下的所有不同值，供策略编辑器下拉使用。"""
    return {"values": PartsMasterRepository().spec_values(category, spec_key)}


@router.get("/export")
def export_parts(section: Optional[str] = None):
    """导出料号库为 Excel。"""
    repo = PartsMasterRepository()
    parts = repo.list(section=section)
    # 展平 specs 为多列
    rows = []
    for p in parts:
        row = {
            "料号PN": p.get("pn"),
            "名称": p.get("name"),
            "部段": p.get("section"),
            "类别": p.get("category"),
            "单价": p.get("unit_price"),
            "规格文本": p.get("spec_text"),
            "说明": p.get("description"),
        }
        # 扩展属性展开到列
        specs = p.get("specs") or {}
        for k, v in specs.items():
            if isinstance(v, list):
                row[k] = ",".join(str(x) for x in v)
            else:
                row[k] = v
        rows.append(row)

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=parts_{section or 'all'}.xlsx"}
    )


@router.get("/import-template")
def download_import_template():
    """下载导入模板。"""
    # 示例数据
    example = [
        {
            "料号PN": "S.E.M.0000351",
            "名称": "3.5寸背板 PCBA",
            "部段": "基准件",
            "类别": "背板",
            "单价": 850.00,
            "规格文本": "PCBA_3.5''_Triple-mode",
            "说明": "适用于 Orion/Polaris 3.5寸背板",
            "io_slot": "IO1,IO2",  # 扩展属性示例
            "chassis": "Orion,Polaris",
        }
    ]
    df = pd.DataFrame(example)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=parts_import_template.xlsx"}
    )


@router.post("/import")
async def import_parts(file: UploadFile = File(...), dry_run: bool = True):
    """批量导入料号。dry_run=True 只预览不写入。返回 {preview, summary}。"""
    repo = PartsMasterRepository()
    content = await file.read()
    df = pd.read_excel(io.BytesIO(content), engine="openpyxl")

    # 列名映射（中文 → 字段名）
    col_map = {
        "料号PN": "pn", "料号": "pn", "PN": "pn",
        "名称": "name",
        "大类": "major_category",
        "部段": "section",
        "类别": "category",
        "单价": "unit_price",
        "规格文本": "spec_text",
        "说明": "description",
    }

    # 识别扩展属性列（不在 col_map 中的列）
    known_cols = set(col_map.keys())
    spec_cols = [c for c in df.columns if c not in known_cols and not c.startswith("_")]

    preview = []
    summary = {"total": len(df), "new": 0, "update": 0, "invalid": 0}

    existing_pns = set(p.get("pn") for p in repo.list())

    for idx, row in df.iterrows():
        r: dict = {"_row_index": idx + 2}  # Excel 行号从 2 开始（1 是表头）

        # 提取基础字段
        data = {}
        for cn, val in row.items():
            fn = col_map.get(cn)
            if fn:
                data[fn] = val if pd.notna(val) else None

        pn = data.get("pn")
        if not pn or str(pn).strip() == "":
            r["action"] = "invalid"
            r["message"] = "料号PN 为空"
            summary["invalid"] += 1
            preview.append(r)
            continue

        pn = str(pn).strip()
        data["pn"] = pn

        # 提取扩展属性
        specs = {}
        for cn in spec_cols:
            val = row.get(cn)
            if pd.notna(val):
                # 尝试解析为数组（逗号分隔）
                if isinstance(val, str) and "," in val:
                    specs[cn] = [v.strip() for v in val.split(",") if v.strip()]
                else:
                    specs[cn] = val
        if specs:
            data["specs"] = specs

        # 判断新增/更新
        if pn in existing_pns:
            r["action"] = "update"
            summary["update"] += 1
        else:
            r["action"] = "new"
            summary["new"] += 1

        r["pn"] = pn
        r["name"] = data.get("name", "")
        r["category"] = data.get("category", "")
        r["message"] = "ok"
        preview.append(r)

        # 非预览模式才真正写入
        if not dry_run and r["action"] in ("new", "update"):
            try:
                repo.upsert(data)
            except Exception as e:
                r["message"] = str(e)

    return {"preview": preview, "summary": summary}


@router.get("/{pn}")
def get_part(pn: str):
    p = PartsMasterRepository().get(pn)
    if not p:
        raise HTTPException(404, "料号不存在")
    return p


@router.post("")
def create_part(data: dict):
    try:
        return {"pn": PartsMasterRepository().insert(data)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{pn}")
def update_part(pn: str, updates: dict):
    PartsMasterRepository().update(pn, updates)
    return {"ok": True}


@router.delete("/{pn}")
def delete_part(pn: str):
    PartsMasterRepository().delete(pn)
    return {"ok": True}