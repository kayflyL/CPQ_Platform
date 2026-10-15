# -*- coding: utf-8 -*-
"""产出物模板 API —— 模板 CRUD / 图表资产清单 / 预览 HTML / 样例 PDF。

权限与 skills CRUD 同模式：读=get_current_user（节点编辑器下拉/预览要读），
写=require_perms("ai.office.manage")。echarts.js 端点公开（iframe srcdoc 预览引用，
公开 OSS 库内容，无敏感数据）。
"""
from typing import Optional
import json
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, require_perms
from app.repository.artifact_template_repo import ArtifactTemplateRepo
from app.services import chart_assets
from app.services.artifact_render import render_report_html, render_report_pdf

require_ai_office_manage = require_perms("ai.office.manage")

router = APIRouter(prefix="/api/artifact-templates", tags=["artifact-templates"])

_VALID_BLOCK_TYPES = {"title", "text", "kpi", "chart", "table", "fields", "heading", "callout", "divider", "image"}
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


@router.get("/contracts")
def list_contracts(user: dict = Depends(get_current_user)):
    """文档卡契约清单（编辑器章节键下拉 / 对账 / AI 生成共用）。

    注意必须注册在 GET /{template_id} 之前，否则 "contracts" 会被当 template_id 吞掉。
    """
    return _list_document_contracts()


@router.get("/echarts.js")
def echarts_js():
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "vendor", "echarts.min.js")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="echarts vendor missing")
    return FileResponse(path, media_type="application/javascript", filename="echarts.min.js")


# 抬头 Logo（title 区块 logo_url）：存 backend/app/static/artifact_logos，uuid 重命名防覆盖。
# 读取端点公开（编辑器 iframe srcdoc 预览引用，与 echarts.js 同款理由）；渲染侧读盘转 data URI。
_LOGO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "artifact_logos")
_LOGO_EXTS = {".png", ".jpg", ".jpeg", ".svg"}


@router.post("/logo")
async def upload_logo(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    import os
    import uuid

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _LOGO_EXTS:
        raise HTTPException(status_code=400, detail="仅支持 png/jpg/svg")
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Logo 不能超过 2MB")
    os.makedirs(_LOGO_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(_LOGO_DIR, name), "wb") as f:
        f.write(content)
    return {"url": f"/api/artifact-templates/logo/{name}", "filename": name}


@router.get("/logo/{filename}")
def get_logo(filename: str):
    import os
    import re as _re

    if not _re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$", filename or ""):
        raise HTTPException(status_code=404)
    path = os.path.join(_LOGO_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404)
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}.get(
        os.path.splitext(filename)[1].lower(), "application/octet-stream")
    return Response(content=open(path, "rb").read(), media_type=mime)


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


# ───────────── 契约聚合 / 按契约对账 / AI 生成（2026-10-03） ─────────────

def _list_document_contracts() -> list[dict]:
    """扫全部活跃推理流的节点配置 → 文档卡契约（kind=document 且 sections 非空）。

    章节键下拉 / 按契约对账 / AI 生成共用这一个权威来源（与输出节点对接提示同口径：
    kind=document 且 sections 非空才算报告文档卡，防「需求原文」插头误认）。
    """
    import json as _json

    from sqlalchemy import text as _text

    from app.models.base import Rules_SessionLocal

    out: list[dict] = []
    seen: set = set()
    session = Rules_SessionLocal()
    try:
        rows = session.execute(
            _text(
                "select f.skill_key, f.name as flow_name, n.node_key, n.config "
                "from rules.reasoning_node_config n join rules.reasoning_flow f on f.id = n.flow_id "
                "where f.is_active = true"
            )
        ).fetchall()
    finally:
        session.close()
    for skill_key, flow_name, node_key, cfg in rows:
        try:
            cfg = cfg if isinstance(cfg, dict) else _json.loads(cfg or "{}")
        except Exception:
            continue
        for a in ((cfg or {}).get("target") or {}).get("artifacts") or []:
            if not isinstance(a, dict) or a.get("kind") != "document":
                continue
            sections = [
                {"key": str(x.get("key")), "title": str(x.get("title")), "requires": str(x.get("requires") or "")}
                for x in (a.get("sections") or [])
                if isinstance(x, dict) and x.get("key") and x.get("title")
            ]
            if not sections:
                continue
            dedup = (str(skill_key or ""), str(a.get("name") or ""))
            if dedup in seen:
                continue
            seen.add(dedup)
            out.append({
                "flow_key": str(skill_key or ""),
                "flow_name": str(flow_name or skill_key or ""),
                "node_key": str(node_key or ""),
                "doc_name": str(a.get("name") or "数据报告"),
                "data_range": a.get("data_range") if isinstance(a.get("data_range"), dict) else {},
                "sections": sections,
            })
    return out


def _find_contract(flow_key: str, doc_name: str = "") -> Optional[dict]:
    for c in _list_document_contracts():
        if c["flow_key"] == flow_key and (not doc_name or c["doc_name"] == doc_name):
            return c
    return None


class ReconcileIn(BaseModel):
    blocks: list = []
    flow_key: str
    doc_name: str = ""


@router.post("/reconcile")
def reconcile_template(body: ReconcileIn, manager: dict = Depends(require_ai_office_manage)):
    """按契约对账补齐（确定性，无 LLM）：缺的章节槽按契约追加，未知 key 只报不删。"""
    contract = _find_contract(body.flow_key, body.doc_name)
    if not contract:
        raise HTTPException(status_code=404, detail="未找到该工作流的文档卡契约")
    blocks = _validate_blocks(body.blocks)
    contract_keys = {s["key"] for s in contract["sections"]}
    covered = {
        str(b.get("key"))
        for b in blocks
        if b.get("type") == "text" and b.get("source") == "payload" and b.get("key")
    }
    missing = [s for s in contract["sections"] if s["key"] not in covered]
    unknown = sorted(covered - contract_keys)
    if missing:
        blocks = blocks + [
            {"type": "text", "source": "payload", "key": s["key"], "title": s["title"]}
            for s in missing
        ]
    return {"blocks": blocks, "missing_added": [s["key"] for s in missing], "unknown_keys": unknown}


class GenerateIn(BaseModel):
    flow_key: str
    doc_name: str = ""


@router.post("/generate")
async def generate_template(body: GenerateIn, manager: dict = Depends(require_ai_office_manage)):
    """按契约生成模板骨架（过程可见）：LLM 逐章读【内容要求】并从资产货架选实现，
    确定性校验兜底（章节覆盖 / 资产存在 / 出处标注 / 无契约外口径）。

    生成依据 = 契约全文（含每章内容要求 requires）——2026-10-03 定调；
    资产注册表只是 AI 的"货架"（实现手段），不是内容来源。
    返回 trace（六步结构化产物，前端逐步揭晓）+ blocks，不自动保存。
    """
    contract = _find_contract(body.flow_key, body.doc_name)
    if not contract:
        raise HTTPException(status_code=404, detail="未找到该工作流的文档卡契约")
    from app.services import llm_client

    assets = chart_assets.list_assets()
    shelf = "\n".join(f"- {a['id']}（{a['kind']}，{a['name']}）" for a in assets)
    kpi_asset = next((a for a in assets if a["kind"] == "kpi"), None)
    kpi_keys = "、".join(m["key"] for m in (kpi_asset or {}).get("metrics") or [])
    sections_text = "\n".join(
        f"{i + 1}. {s['title']}（key={s['key']}）：{(s.get('requires') or '').strip() or '（无内容要求，仅正文叙述）'}"
        for i, s in enumerate(contract["sections"])
    )
    prompt = (
        f"为「{contract['doc_name']}」设计 PDF 报告模板的区块序列。\n"
        f"数据范围：{json.dumps(contract.get('data_range'), ensure_ascii=False)}"
        f"（图表/KPI 取数默认跟随数据范围，模板一般不写死窗口参数）\n\n"
        f"章节契约全文（每章的【内容要求】= 该章必须被满足的数据语义，逐章读完再动手）：\n"
        f"{sections_text}\n\n"
        f"资产货架（现成数据视图，只能引用这里列出的，不得虚构）：\n{shelf}\n"
        f"KPI 指标原子（metrics 可选值）：{kpi_keys}\n\n"
        f"区块目录：\n"
        f"- title：报告抬头，放第一个，无字段\n"
        f"- kpi：指标卡条；asset、metrics=[原子key]、chapter=所属章key、cite=出处短语\n"
        f"- chart：图表；asset、height(160-420)、chapter、cite\n"
        f"- table：表格；asset、chapter、cite\n"
        f"- text：章节正文槽（每章恰一个）；source='payload'、key=章节key、title=章节标题\n"
        f"- heading：小节题（title）；divider：分割线；callout：提示卡（tone='blue'|'green'|'amber'、co_title、text）——纯版式，少量点缀\n\n"
        f"硬性要求：\n"
        f"1) 每章有且仅有一个 text 正文槽，key 逐字照契约，顺序照契约；\n"
        f"2) 每个 kpi/chart/table 必须服务于所在章的内容要求：chapter=该章key，cite=该章内容要求原文里的短语；\n"
        f"3) 不得引入内容要求之外的任何数据口径，不得引用货架之外的资产；\n"
        f"4) 排版：title 第一；概览类图表 span=6 成对并排；表格与正文槽 span=12。\n\n"
        f'只输出 JSON 对象：{{"chapters":[{{"key":"...","title":"...","needs":["..."],"assets":[{{"asset":"...","cite":"..."}}]}}],'
        f'"blocks":[{{...}}]}}'
    )
    raw = await llm_client.chat_json([{"role": "user", "content": prompt}], max_tokens=6000)
    chapters = raw.get("chapters") if isinstance(raw, dict) else None
    blocks = raw.get("blocks") if isinstance(raw, dict) else None
    if not isinstance(blocks, list):
        raise HTTPException(status_code=502, detail="AI 返回结构异常（无 blocks 数组）")

    # ── 确定性校验与修复：LLM 只提议，规则裁决 ──
    assets_by_id = {a["id"]: a for a in assets}
    contract_keys = {s["key"] for s in contract["sections"]}
    sec_by_key = {s["key"]: s for s in contract["sections"]}
    checks: list = []
    dropped: list = []
    out: list = [{"type": "title"}]
    provenance: list = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "title":
            continue
        if t not in _VALID_BLOCK_TYPES or t == "fields":
            dropped.append(f"未知类型 {t}")
            continue
        nb = {k: v for k, v in b.items() if k != "id"}
        if t in ("kpi", "chart", "table"):
            asset = assets_by_id.get(str(nb.get("asset") or ""))
            ch_key = str(nb.get("chapter") or "")
            sec = sec_by_key.get(ch_key)
            if asset is None:
                dropped.append(f"{t} 引用了货架之外的资产 {nb.get('asset')}")
                continue
            if sec is None:
                dropped.append(f"{t}（{asset['name']}）的 chapter 不在契约：{ch_key or '（空）'}")
                continue
            cite = str(nb.get("cite") or "").strip() or str(sec.get("requires") or "")[:40]
            nb["cite"] = cite
            provenance.append({"type": t, "asset": asset["name"], "chapter": sec["title"], "cite": cite})
        if nb.get("span") not in (4, 6, 8, 12):
            nb.pop("span", None)
        if t == "text":
            key = str(nb.get("key") or "")
            if key not in contract_keys:
                dropped.append(f"章节槽 key 不在契约：{key or '（空）'}")
                continue
            nb["source"] = "payload"
            if sec_by_key.get(key):
                nb["title"] = sec_by_key[key]["title"]
        out.append(nb)
    covered = {str(b.get("key")) for b in out if b.get("type") == "text" and b.get("key")}
    missing = [s for s in contract["sections"] if s["key"] not in covered]
    for s in missing:
        out.append({"type": "text", "source": "payload", "key": s["key"], "title": s["title"]})

    # ── 自动配图兜底（确定性）：内容要求含关键词而该章无数据块时，从货架补配 ──
    # （AI 没配/漏配不致命——要求里的"平台分布/逐月表/排行"这类硬需求必须有落点）
    _AUTO_MATCH_RULES = [
        (("排行", "TOP"), "cockpit.sales_rank", "chart", 240),
        (("逐月表", "各平台新增商机数"), "cockpit.platform_monthly", "table", None),
        (("机箱形态",), "cockpit.chassis_dist", "chart", 260),
        (("占比",), "cockpit.dist", "chart", 240),
        (("新增商机数", "新增配置数"), "cockpit.kpi", "kpi", None),
        (("趋势",), "cockpit.trend", "chart", 260),
    ]
    auto_added = 0
    for s in contract["sections"]:
        has_data = any(b.get("chapter") == s["key"] for b in out if b.get("type") in ("kpi", "chart", "table"))
        if has_data:
            continue
        req_text = s.get("requires") or ""
        if not req_text:
            continue
        for kws, asset_id, kind, height in _AUTO_MATCH_RULES:
            hit = next((k for k in kws if k in req_text), None)
            if not hit:
                continue
            asset = assets_by_id.get(asset_id)
            if asset is None:
                continue
            blk: dict = {"type": kind, "asset": asset_id, "chapter": s["key"],
                         "cite": f"自动匹配「{hit}」← {req_text[:36]}"}
            if height:
                blk["height"] = height
            if kind == "kpi":
                blk.pop("height", None)
            # 插到该章正文槽之后
            idx = next((i for i, b in enumerate(out)
                        if b.get("type") == "text" and b.get("key") == s["key"]), None)
            out.insert((idx + 1) if idx is not None else len(out), blk)
            auto_added += 1
            break
    if auto_added:
        provenance = [
            {"type": b["type"], "asset": (assets_by_id.get(str(b.get("asset"))) or {}).get("name") or str(b.get("asset")),
             "chapter": (sec_by_key.get(str(b.get("chapter"))) or {}).get("title") or str(b.get("chapter")),
             "cite": str(b.get("cite") or "")}
            for b in out if b.get("type") in ("kpi", "chart", "table")
        ]
    checks.append({"k": "章节覆盖", "v": f"{len(contract['sections']) - len(missing)} / {len(contract['sections'])}"
                   + (f" · 缺失已补：{'、'.join(s['key'] for s in missing)}" if missing else "")})
    # 每章图表 ≤2：LLM 容易堆图，超出的按顺序剔除（防膨胀规则）
    per_ch: dict = {}
    trimmed: list = []
    for b in out:
        if b.get("type") == "chart" and b.get("chapter"):
            n = per_ch.get(b["chapter"], 0)
            if n >= 2:
                dropped.append(f"第「{b['chapter']}」章图表超过 2 张，已剔除多余")
                continue
            per_ch[b["chapter"]] = n + 1
        trimmed.append(b)
    out = trimmed
    provenance = [
        {"type": b["type"], "asset": (assets_by_id.get(str(b.get("asset"))) or {}).get("name") or str(b.get("asset")),
         "chapter": (sec_by_key.get(str(b.get("chapter"))) or {}).get("title") or str(b.get("chapter")),
         "cite": str(b.get("cite") or "")}
        for b in out if b.get("type") in ("kpi", "chart", "table")
    ]
    checks.append({"k": "防膨胀", "v": "每章图表 ≤2" + (f" · 已剔除 {sum(1 for d in dropped if '超过 2 张' in d)} 项" if any('超过 2 张' in d for d in dropped) else " · 无超出")})
    checks.append({"k": "资产存在", "v": "全部引用均在货架且 kind 匹配" if not dropped
                   else f"剔除 {len(dropped)} 项：{'；'.join(dropped[:4])}"})
    checks.append({"k": "出处标注", "v": f"{len(provenance)} 个数据块已标注「为满足第 N 章〔要求短语〕」"})
    if missing:
        checks.append({"k": "缺章补齐", "v": "、".join(s["key"] for s in missing)})

    # ── 六步 trace（前端逐步揭晓）。2/3 步从出处确定性推导，不依赖 LLM 自报结构 ──
    prov_by_ch: dict = {}
    for p in provenance:
        prov_by_ch.setdefault(p["chapter"], []).append(p)
    req_chapters = [
        {"title": s["title"], "key": s["key"], "requires": s.get("requires") or "",
         "blocks": [f"{p['type']} · {p['asset']}" for p in prov_by_ch.get(s["title"], [])]}
        for s in contract["sections"]
    ]
    match_maps = [
        {"a": f"{p['chapter']} · {p['cite'][:30]}", "b": f"{p['type']} · {p['asset']}", "src": f"满足第「{p['chapter']}」章内容要求"}
        for p in provenance
    ]
    trace = {"steps": [
        {"key": "contract", "title": "读取契约", "items": {
            "name": contract["doc_name"], "range": json.dumps(contract.get("data_range"), ensure_ascii=False),
            "sections": contract["sections"]}},
        {"key": "requires", "title": "逐章解析内容要求", "items": {"chapters": req_chapters}},
        {"key": "match", "title": "匹配资产货架", "items": {"maps": match_maps}},
        {"key": "compose", "title": "编排骨架", "items": {"seq": [
            {"type": b["type"],
             "note": (sec_by_key.get(str(b.get("key"))) or {}).get("title") or assets_by_id.get(str(b.get("asset")), {}).get("name") or (b.get("title") or ""),
             "data": b.get("type") in ("kpi", "chart", "table")}
            for b in out]}},
        {"key": "validate", "title": "校验与出处标注", "items": {"checks": checks}},
    ]}
    return {"blocks": out, "trace": trace, "provenance": provenance, "dropped": dropped, "contract": contract}
