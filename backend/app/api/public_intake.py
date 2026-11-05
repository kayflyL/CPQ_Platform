"""公开线索汇聚 API —— 免登录端点（价格物理不出网的三层防线之一）。

安全面（规格 = docs/prototypes/公开目录与线索提交-原型.html 标注）：
1. 数据层：目录读走 PublicReadRepository（cpq_public_ro 受限连接 + 列级白名单）；
2. 代码层：公开 DTO 白名单子集 + product_content.specs 价格词黑名单（fail-closed 整行剔除）；
3. 行为层：蜜罐 + 双桶限流 + 字段白名单重建 + 同手机号未结线索并入。
端点一律不挂鉴权依赖（先例 /api/share/*）；带价 API 不在本模块，也不得迁入。
"""
import logging
import re
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.api.server_catalog import _normalize_portal_banner
from app.repository.lead_repo import LeadRepository
from app.repository.public_read_repo import PublicReadRepository
from app.repository.system_config_repo import SystemConfigRepository
from app.models.lead import generate_lead_id
from app.utils.file_storage import FileStorage
from app.utils.rate_limit import SlidingWindowLimiter, client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["public-intake"])

_catalog_limiter = SlidingWindowLimiter()
_submit_ip_limiter = SlidingWindowLimiter()
_submit_global_limiter = SlidingWindowLimiter()

_CATALOG_IP_LIMIT = (120, 60)        # 目录 GET：120 次/分/IP
_SUBMIT_IP_LIMIT = (5, 600)          # 提交：5 次/10 分钟/IP
_SUBMIT_GLOBAL_LIMIT = (200, 3600)   # 提交：200 次/小时/全站

_PHONE_RE = re.compile(r"^1\d{10}$")
_UPLOAD_EXT_ALLOWED = {
    ".xlsx", ".xls", ".csv", ".pdf", ".docx", ".doc",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".txt",
}
_UPLOAD_MAX_SIZE = 20 * 1024 * 1024
_UPLOAD_MAX_COUNT = 5
_MAX_LEAD_FILES_BYTES = _UPLOAD_MAX_SIZE * _UPLOAD_MAX_COUNT

# specs 自由文本价格词黑名单：key/value 命中即整行剔除（fail-closed，运营手填内容不可信）
_PRICE_WORD_RE = re.compile(r"(价格|报价|单价|总价|含税|元\s*/|￥|¥|\bprice\b|\bcost\b|\bbudget\b)", re.I)

# 平台字段对外用芯片品牌（用户口径：AMD 就是 Orion，兆芯就是 Polaris）；
# 公开表单提交品牌，落库时翻译回内部代号，下游需求草稿词汇不变。运营增系列时同步维护。
_CHIP_TO_SERIES = {"AMD": "Orion", "兆芯": "Polaris"}


def _guard(request: Request, limiter: SlidingWindowLimiter, limit: int, window: int) -> None:
    if not limiter.check(client_ip(request), limit=limit, window_seconds=window):
        raise HTTPException(429, "请求太频繁，请稍后再试")


# ---------- 公开目录 DTO（白名单子集，价格物理不出网） ----------

def _safe_specs(specs) -> list:
    """specs 行级价格词过滤：key 或 value 命中黑名单 → 整行丢弃。"""
    if not isinstance(specs, list):
        return []
    out = []
    for row in specs:
        if not isinstance(row, dict):
            continue
        k = str(row.get("key") or "")
        v = str(row.get("value") or "")
        if not k or _PRICE_WORD_RE.search(k) or _PRICE_WORD_RE.search(v):
            continue
        out.append({"key": k[:80], "value": v[:200]})
    return out


def _docs_enabled() -> bool:
    """产品资料公开总闸（system_config.lead.public_docs_enabled，默认开）。含价资料一键全线下架。"""
    repo = SystemConfigRepository()
    try:
        v = repo.get_value("lead.public_docs_enabled", True)
        return bool(v)
    finally:
        repo.close()


def _pc_dto(pc: dict) -> dict:
    pc = pc if isinstance(pc, dict) else {}
    return {
        "tagline": pc.get("tagline"),
        "overview": pc.get("overview"),
        "stage_theme": pc.get("stage_theme"),
        "highlight_image": pc.get("highlight_image"),
        "highlights": pc.get("highlights"),
        "capabilities": pc.get("capabilities"),
        "scenarios": pc.get("scenarios"),
        "features": pc.get("features"),
        "specs": _safe_specs(pc.get("specs")),
        "docs": pc.get("docs") if _docs_enabled() else [],
    }


def _config_content_dto(cc) -> dict:
    """base_configs.config_content 只透传 description/spec_diff 两个键（其余内部参数不给）。"""
    cc = cc if isinstance(cc, dict) else {}
    return {
        "description": str(cc.get("description") or "")[:500],
        "spec_diff": str(cc.get("spec_diff") or "")[:500],
    }


def _base_config_dto(bc: Optional[dict]) -> Optional[dict]:
    if not bc:
        return None
    return {k: bc.get(k) for k in ("form", "bays", "series", "name")}


def _model_list_dto(m: dict) -> dict:
    return {
        "id": m["id"],
        "name": m.get("name"),
        "server_type_id": m.get("server_type_id"),
        "use": m.get("use"),
        "sort_order": m.get("sort_order"),
        "image_url": m.get("image_url"),
        "description": m.get("description"),
        "lifecycle_status": m.get("lifecycle_status"),
        "base_config": _base_config_dto(m.get("base_config")),
        "product_content": {k: _pc_dto(m.get("product_content") or {}).get(k) for k in ("tagline",)},
    }


def _model_detail_dto(m: dict) -> dict:
    return {
        "id": m["id"],
        "name": m.get("name"),
        "server_type_id": m.get("server_type_id"),
        "use": m.get("use"),
        "sort_order": m.get("sort_order"),
        "image_url": m.get("image_url"),
        "description": m.get("description"),
        "lifecycle_status": m.get("lifecycle_status"),
        "base_config": _base_config_dto(m.get("base_config")),
        "product_content": _pc_dto(m.get("product_content") or {}),
        "configs": [
            {
                "id": c["id"],
                "name": c.get("name"),
                "form": c.get("form"),
                "bays": c.get("bays"),
                "series": c.get("series"),
                "config_content": _config_content_dto(c.get("config_content")),
            }
            for c in m.get("configs") or []
        ],
    }


def _showcase_config_dto(t: dict) -> dict:
    sc = t.get("showcase_config")
    if isinstance(sc, str):
        import json
        try:
            sc = json.loads(sc)
        except (TypeError, ValueError):
            sc = None
    return {"id": t["id"], "name": t.get("name"), "description": t.get("description"),
            "sort_order": t.get("sort_order"), "showcase_config": sc}


# ---------- GET：公开目录（无鉴权 + 限流） ----------

@router.get("/catalog/types")
def public_types(request: Request):
    _guard(request, _catalog_limiter, *_CATALOG_IP_LIMIT)
    return {"types": [_showcase_config_dto(t) for t in PublicReadRepository().list_types()]}


@router.get("/catalog/models")
def public_models(request: Request, type_id: Optional[int] = None):
    _guard(request, _catalog_limiter, *_CATALOG_IP_LIMIT)
    return {"models": [_model_list_dto(m) for m in PublicReadRepository().list_published_models(type_id)]}


@router.get("/catalog/models/{model_id}")
def public_model_detail(request: Request, model_id: int):
    _guard(request, _catalog_limiter, *_CATALOG_IP_LIMIT)
    m = PublicReadRepository().get_published_model(model_id)
    if not m:
        raise HTTPException(404, "机型不存在")
    return _model_detail_dto(m)


@router.get("/catalog/banner")
def public_banner(request: Request):
    _guard(request, _catalog_limiter, *_CATALOG_IP_LIMIT)
    repo = SystemConfigRepository()
    try:
        raw = repo.get_value("server_portal_banner", {})
        try:
            return _normalize_portal_banner(raw if isinstance(raw, dict) else {})
        except HTTPException:
            return {}
    finally:
        repo.close()


@router.get("/requirement-sheet-form")
def public_sheet_form(request: Request):
    """线索登记表字段定义（requirement_sheet_form）—— 公开登记表渲染用。

    纯表单结构（字段 key/label/控件），无任何业务数据；专项放行而非开放整个 system-config。"""
    _guard(request, _catalog_limiter, *_CATALOG_IP_LIMIT)
    repo = SystemConfigRepository()
    try:
        v = repo.get_value("requirement_sheet_form", {})
        return v if isinstance(v, dict) else {}
    finally:
        repo.close()


# ---------- POST：线索提交（蜜罐 → 限流 → 校验 → 去重 → 落库） ----------

def _clean_str(v: Optional[str], cap: int) -> str:
    return (v or "").strip()[:cap]


def _rebuild_config_slots(raw: dict) -> Optional[dict]:
    """配置区白名单键重建（不信客户端原样 JSON）。无有效内容返回 None。"""
    if not isinstance(raw, dict):
        return None
    relation = raw.get("config_relation") if raw.get("config_relation") in ("compose", "alternative") else "compose"

    configs_out = []
    for cfg in (raw.get("configs") or [])[:5]:
        if not isinstance(cfg, dict):
            continue
        def _int(v, lo, hi, dflt=None):
            try:
                n = int(v)
            except (TypeError, ValueError):
                return dflt
            return n if lo <= n <= hi else dflt

        kp_rows = []
        for r in (cfg.get("kp_rows") or [])[:20]:
            if not isinstance(r, dict):
                continue
            row = {
                "category": _clean_str(r.get("category"), 40) or "Key Parts",
                "part_category": _clean_str(r.get("part_category"), 40),
                "catalogue": _clean_str(r.get("catalogue"), 120),
                "description": _clean_str(r.get("description"), 300),
                "qty": _int(r.get("qty"), 1, 9999, 1),
                "note": _clean_str(r.get("note"), 200),
            }
            if row["catalogue"] or row["description"]:
                kp_rows.append(row)
        item = {
            "name": _clean_str(cfg.get("name"), 40) or f"CFG{len(configs_out) + 1}",
            "server_model": _clean_str(cfg.get("server_model"), 80),
            "platform_type": _CHIP_TO_SERIES.get(_clean_str(cfg.get("platform_type"), 40),
                                                 _clean_str(cfg.get("platform_type"), 40)),
            "server_type": _clean_str(cfg.get("server_type"), 40),
            "chassis_form": _clean_str(cfg.get("chassis_form"), 20),
            "qty": _int(cfg.get("qty"), 1, 999, 1),
            "warranty_years": str(_int(cfg.get("warranty_years"), 1, 10, 1)),
            "kp_rows": kp_rows,
        }
        if item["server_model"] or item["platform_type"] or item["server_type"] or item["chassis_form"] or kp_rows:
            configs_out.append(item)
    if not configs_out:
        return None
    out = {"configs": configs_out, "config_relation": relation}
    if relation == "alternative":
        out["purchase_qty"] = _int(raw.get("purchase_qty"), 1, 999, None)
        if configs_out:
            out["primary_config"] = _clean_str(raw.get("primary_config"), 40) or configs_out[0]["name"]
    else:
        total = sum(c["qty"] for c in configs_out)
        if total:
            out["purchase_qty"] = total
    return out


def _read_attachments(files: List[UploadFile]) -> list:
    if not files:
        return []
    if len(files) > _UPLOAD_MAX_COUNT:
        raise HTTPException(400, f"附件最多 {_UPLOAD_MAX_COUNT} 个")
    saved = []
    total = 0
    for f in files:
        ext = "." + (f.filename or "").rsplit(".", 1)[-1].lower() if "." in (f.filename or "") else ""
        if ext not in _UPLOAD_EXT_ALLOWED:
            raise HTTPException(400, f"附件格式不支持：{f.filename}")
        content = f.file.read()
        total += len(content)
        if total > _MAX_LEAD_FILES_BYTES:
            raise HTTPException(400, "附件总大小超限")
        if len(content) > _UPLOAD_MAX_SIZE:
            raise HTTPException(400, f"单个附件过大（>20MB）：{f.filename}")
        saved.append({"content": content, "name": f.filename or "file"})
    return saved


@router.post("/leads")
async def submit_lead(
    request: Request,
    requirement_text: str = Form(""),
    company: str = Form(""),
    contact_name: str = Form(""),
    contact_phone: str = Form(""),
    contact_email: str = Form(""),
    delivery_region: str = Form(""),
    expected_delivery: str = Form(""),
    source: str = Form("catalog_general"),
    config_slots: str = Form(""),
    website: str = Form(""),  # 蜜罐：真实用户不可见必为空
    files: List[UploadFile] = File(default=[]),
):
    # 蜜罐：机器人填了 → 与成功完全一致的响应，静默丢弃（不落库、不计限流失败）
    if website.strip():
        logger.info("honeypot triggered: ip=%s", client_ip(request))
        return {"ok": True, "lead_id": None, "merged": False}

    _guard(request, _submit_ip_limiter, *_SUBMIT_IP_LIMIT)
    if not _submit_global_limiter.check("global", limit=_SUBMIT_GLOBAL_LIMIT[0],
                                        window_seconds=_SUBMIT_GLOBAL_LIMIT[1]):
        raise HTTPException(429, "当前提交量过大，请稍后再试")

    phone = (contact_phone or "").strip()
    if not _PHONE_RE.fullmatch(phone):
        raise HTTPException(400, "请填写 11 位大陆手机号")
    text_clean = (requirement_text or "").strip()
    if len(text_clean) < 5 or len(text_clean) > 2000:
        raise HTTPException(400, "需求描述请填 5~2000 字")
    company_c = _clean_str(company, 80)
    if not company_c:
        raise HTTPException(400, "请填写公司名称")
    email_c = _clean_str(contact_email, 100)
    if email_c and "@" not in email_c:
        raise HTTPException(400, "邮箱格式不正确")
    if source not in ("catalog_model", "catalog_general"):
        source = "catalog_general"

    import json
    try:
        slots_raw = json.loads(config_slots) if config_slots else None
    except (TypeError, ValueError):
        slots_raw = None
    slots = _rebuild_config_slots(slots_raw)

    lead_id = generate_lead_id()
    saved_files = _read_attachments(files)
    storage = FileStorage()
    attachments_meta = []
    for f in saved_files:
        try:
            info = storage.save_lead_attachment(f["content"], f["name"], lead_id)
            attachments_meta.append({"storage_key": info["stored_path"], "name": info["name"],
                                     "size": info["file_size"]})
        except OSError as e:
            logger.exception("lead attachment save failed: %s", e)
            raise HTTPException(500, "附件保存失败，请重试")

    lead = {
        "lead_id": lead_id,
        "source": source,
        "company": company_c,
        "contact_name": _clean_str(contact_name, 50),
        "contact_phone": phone,
        "contact_email": email_c,
        "delivery_region": _clean_str(delivery_region, 40),
        "requirement_text": text_clean,
        "config_slots": slots,
        "expected_delivery": _clean_str(expected_delivery, 40),
        "attachments": attachments_meta or None,
        "client_ip": client_ip(request),
        "user_agent": (request.headers.get("user-agent") or "")[:200],
    }

    repo = LeadRepository()
    try:
        open_hit = repo.find_open_by_phone(phone)
        if open_hit:
            repo.merge_submission(open_hit["lead_id"], text_clean,
                                  attachments_append=attachments_meta,
                                  config_slots=slots,
                                  expected_delivery=lead["expected_delivery"],
                                  delivery_region=lead["delivery_region"])
            logger.info("lead merged into %s from %s", open_hit["lead_id"], lead_id)
            return {"ok": True, "lead_id": open_hit["lead_id"], "merged": True}
        repo.insert(lead)
        logger.info("lead created %s source=%s slots=%s att=%s",
                    lead_id, source, bool(slots), len(attachments_meta))
        return {"ok": True, "lead_id": lead_id, "merged": False}
    finally:
        repo.close()
