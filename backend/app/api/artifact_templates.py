# -*- coding: utf-8 -*-
"""产出物模板 API —— 模板 CRUD / 图表资产清单 / 预览 HTML / 样例 PDF。

权限与 skills CRUD 同模式：读=get_current_user（节点编辑器下拉/预览要读），
写=require_perms("ai.office.manage")。echarts.js 端点公开（iframe srcdoc 预览引用，
公开 OSS 库内容，无敏感数据）。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, require_perms
from app.repository.artifact_template_repo import ArtifactTemplateRepo
from app.services import chart_assets
from app.services.artifact_render import render_report_html, render_report_pdf

require_ai_office_manage = require_perms("ai.office.manage")

router = APIRouter(prefix="/api/artifact-templates", tags=["artifact-templates"])

_VALID_BLOCK_TYPES = {"title", "text", "kpi", "chart", "table"}
_VALID_FORMATS = {"pdf"}  # xlsx/pptx 走文件模板路线，下期开放


class TemplateIn(BaseModel):
    key: str = Field(min_length=2, max_length=80)
    name: str = ""
    format: str = "pdf"
    description: str = ""
    blocks: list = []


def _validate_blocks(blocks: list) -> list:
    out = []
    for b in blocks or []:
        if not isinstance(b, dict) or b.get("type") not in _VALID_BLOCK_TYPES:
            raise HTTPException(status_code=400, detail=f"非法区块类型：{b if isinstance(b, str) else (b or {}).get('type')}")
        out.append(b)
    return out


def _sample_payload() -> dict:
    return {
        "meta": {"title": "商机经营周报", "subtitle": "模板预览 · 示例内容（真实库数据）"},
        "answer": (
            "## 本周概览\n"
            "近 8 周新增商机整体保持平稳，**Orion 平台**贡献主要增量；"
            "以下图表均实时取自商机库，与商机线索页驾驶舱同源。\n\n"
            "- 平台结构：Orion 占比领先，Polaris 与 Intel 保持稳定节奏\n"
            "- 赢单率：近 8 周赢单率保持在健康区间\n\n"
            "## 风险与建议\n"
            "1. 关注工作站类需求的跟进节奏\n"
            "2. 建议对近 7 天新增商机优先安排方案配置"
        ),
    }


@router.get("")
def list_templates(user: dict = Depends(get_current_user)):
    repo = ArtifactTemplateRepo()
    try:
        return repo.list()
    finally:
        repo.close()


@router.get("/chart-assets")
def list_chart_assets(user: dict = Depends(get_current_user)):
    return chart_assets.list_assets()


@router.get("/echarts.js")
def echarts_js():
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "vendor", "echarts.min.js")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="echarts vendor missing")
    return FileResponse(path, media_type="application/javascript", filename="echarts.min.js")


@router.post("/preview")
def preview_template(body: TemplateIn, user: dict = Depends(get_current_user)):
    """编辑器实时预览：返回完整 HTML（iframe srcdoc 用）。数据真实取库。"""
    blocks = _validate_blocks(body.blocks)
    html = render_report_html(
        blocks,
        _sample_payload(),
        template_name=body.name,
        echarts_url="/api/artifact-templates/echarts.js",
        interactive=True,
    )
    return Response(content=html, media_type="text/html; charset=utf-8")


@router.post("/render-sample-pdf")
async def render_sample_pdf(body: TemplateIn, user: dict = Depends(get_current_user)):
    blocks = _validate_blocks(body.blocks)
    try:
        pdf = await render_report_pdf(blocks, _sample_payload(), template_name=body.name)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        import logging
        logging.getLogger(__name__).exception("sample pdf render failed")
        raise HTTPException(status_code=500, detail="PDF 渲染失败")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="sample.pdf"'},
    )


@router.post("")
def create_template(body: TemplateIn, manager: dict = Depends(require_ai_office_manage)):
    key = (body.key or "").strip()
    if not key or not key.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="key 仅限字母/数字/-/_")
    if body.format.lower() not in _VALID_FORMATS:
        raise HTTPException(status_code=400, detail=f"暂不支持的格式：{body.format}（当前仅 pdf）")
    blocks = _validate_blocks(body.blocks)
    repo = ArtifactTemplateRepo()
    try:
        if repo.key_exists(key):
            raise HTTPException(status_code=409, detail=f"模板 key 已存在：{key}")
        return repo.create(
            {"key": key, "name": body.name, "format": body.format.lower(),
             "description": body.description, "blocks": blocks},
            operator=(manager or {}).get("username") or "system",
        )
    finally:
        repo.close()


@router.get("/{template_id}")
def get_template(template_id: int, user: dict = Depends(get_current_user)):
    repo = ArtifactTemplateRepo()
    try:
        row = repo.get(template_id)
        if row is None:
            raise HTTPException(status_code=404, detail="模板不存在")
        return row
    finally:
        repo.close()


@router.put("/{template_id}")
def update_template(template_id: int, body: TemplateIn, manager: dict = Depends(require_ai_office_manage)):
    if body.format.lower() not in _VALID_FORMATS:
        raise HTTPException(status_code=400, detail=f"暂不支持的格式：{body.format}")
    blocks = _validate_blocks(body.blocks)
    repo = ArtifactTemplateRepo()
    try:
        row = repo.update(
            template_id,
            {"name": body.name, "format": body.format.lower(),
             "description": body.description, "blocks": blocks},
            operator=(manager or {}).get("username") or "system",
        )
        if row is None:
            raise HTTPException(status_code=404, detail="模板不存在")
        return row
    finally:
        repo.close()


@router.delete("/{template_id}")
def delete_template(template_id: int, manager: dict = Depends(require_ai_office_manage)):
    repo = ArtifactTemplateRepo()
    try:
        if not repo.soft_delete(template_id):
            raise HTTPException(status_code=404, detail="模板不存在")
        return {"ok": True}
    finally:
        repo.close()
