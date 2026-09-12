"""API endpoints for system configuration"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from fastapi.responses import FileResponse

from typing import Any, Optional

from pydantic import BaseModel

from app.api.deps import require_admin

from app.repository.system_config_repo import SystemConfigRepository

from app.services import llm_client

from app.utils.file_storage import FileStorage



router = APIRouter(prefix="/api/system-config", tags=["system-config"])



_BRANDING_KEY = "branding"

_BRANDING_LOGO_EXTS = {".png", ".jpg", ".jpeg", ".svg"}

_BRANDING_LOGO_URL = "/api/system-config/branding/logo"





@router.get("/")

def list_configs():

    """Get all system configs (excluding branding, which is now managed via spec templates)"""

    repo = SystemConfigRepository()

    try:

        all_configs = repo.get_all()

        # 过滤掉 branding 参数（已迁移至规格书模板管理）

        return [c for c in all_configs if c.get("key") != _BRANDING_KEY]

    finally:

        repo.close()





@router.get("/requirement_slots_spec")
def get_requirement_slots_spec():
    """返回线索登记表完整字段契约 = 基本信息(requirement_slots 配置) + 部件(KP 大类动态合成)。

    前端进度卡 / 编辑器统一按此清单对齐，避免前端自行拼接两处来源。
    """
    from app.services.requirement_slots import combined_slot_spec, slot_map_options
    spec = combined_slot_spec()
    return {"slots": spec, "slot_map_options": slot_map_options(), "version": 1, "ask_threshold": 2}


@router.post("/kp_slot_group_map/reset")
def reset_kp_slot_group_map(admin: dict = Depends(require_admin)):
    """重置 KP 大类→归一部件槽位映射为规范种子。"""
    repo = SystemConfigRepository()
    try:
        value = repo.reset_kp_slot_group_map()
        return {"success": True, "value": value}
    finally:
        repo.close()


@router.get("/{key}")

def get_config(key: str):

    """Get config by key"""

    repo = SystemConfigRepository()

    try:

        config = repo.get(key)

        if not config:

            raise HTTPException(status_code=404, detail=f"Config '{key}' not found")

        return config

    finally:

        repo.close()





@router.get("/{key}/value")

def get_config_value(key: str, default: Any = None):

    """Get config value only"""

    repo = SystemConfigRepository()

    try:

        value = repo.get_value(key, default)

        return {"key": key, "value": value}

    finally:

        repo.close()





@router.put("/{key}")

def set_config(key: str, data: dict, admin: dict = Depends(require_admin)):

    """Set config value"""

    repo = SystemConfigRepository()

    try:

        value = data.get("value")

        if value is None:

            raise HTTPException(status_code=400, detail="Missing 'value' field")

        

        type = data.get("type", "string")

        description = data.get("description")

        operator = data.get("operator", "system")

        

        return repo.set(key, value, type, description, operator)

    finally:

        repo.close()





@router.delete("/{key}")

def delete_config(key: str, admin: dict = Depends(require_admin)):

    """Delete config"""

    repo = SystemConfigRepository()

    try:

        success = repo.delete(key)

        if not success:

            raise HTTPException(status_code=404, detail=f"Config '{key}' not found")

        return {"success": True}

    finally:

        repo.close()





@router.post("/requirement_slots/reset")

def reset_requirement_slots(admin: dict = Depends(require_admin)):

    """重置需求期望槽位清单为规范种子（基本信息 6 项），供编辑器「恢复默认」使用。"""

    repo = SystemConfigRepository()

    try:

        value = repo.reset_requirement_slots()

        return {"success": True, "value": value}

    finally:

        repo.close()







# ── LLM 配置排障：测试连接 + 拉取模型列表（AI 设置页用）──────────────

# 用表单当前值（未保存也行）实测，缺省字段回落 system_config.llm_config / .env。

class LlmTestBody(BaseModel):

    base_url: Optional[str] = None

    api_key: Optional[str] = None

    model: Optional[str] = None





@router.post("/llm_config/test")

def test_llm(body: LlmTestBody):

    """用给定配置实测一次 chat，返回真实结果/错误（供「测试连接」按钮）。"""

    return llm_client.test_connection(body.model_dump(exclude_none=True))





@router.post("/llm_config/models")

def list_llm_models(body: LlmTestBody):

    """拉取 provider 可用模型 id 列表（供「拉取模型列表」按钮）。"""

    try:

        ids = llm_client.list_models(body.model_dump(exclude_none=True))

        return {"success": True, "models": ids}

    except llm_client.LLMError as e:

        return {"success": False, "models": [], "message": str(e)}





@router.get("/llm_config/capabilities")

def get_llm_capabilities(model: Optional[str] = None):

    """读取当前/指定模型的能力档案（内置 + 覆盖 + 生效），供「模型能力档案」页展示。"""

    try:

        return {"success": True, **llm_client.describe_model_capabilities(model)}

    except Exception as e:

        return {"success": False, "message": str(e)}





@router.post("/llm_config/probe")

def probe_llm_capabilities(body: LlmTestBody):

    """实测当前端点的 JSON mode / 原生 tools 支持情况，供「能力探测」按钮使用。"""

    return llm_client.probe_model_capabilities(body.model_dump(exclude_none=True))





@router.post("/branding/logo")

async def upload_branding_logo(file: UploadFile = File(...), admin: dict = Depends(require_admin)):

    """上传品牌 logo（覆盖式，落盘到 storage/branding/logo<ext>，并写回 branding.logo_path）。"""

    ext = Path(file.filename or "").suffix.lower()

    if ext not in _BRANDING_LOGO_EXTS:

        raise HTTPException(

            status_code=400,

            detail=f"不支持的图片格式 {ext or '(无)'}，仅支持 {'/'.join(sorted(_BRANDING_LOGO_EXTS))}",

        )

    content = await file.read()

    storage = FileStorage()

    try:

        info = storage.save_branding_logo(content, file.filename or "logo.png")

    except Exception as e:

        raise HTTPException(status_code=500, detail=f"logo 保存失败：{e}")

    repo = SystemConfigRepository()

    try:

        branding = repo.get_value(_BRANDING_KEY, {}) or {}

        if not isinstance(branding, dict):

            branding = {}

        branding["logo_path"] = info["stored_path"]

        branding["logo_url"] = _BRANDING_LOGO_URL

        repo.set(_BRANDING_KEY, branding, type="json")

    finally:

        repo.close()

    return {

        "logo_path": info["stored_path"],

        "logo_url": _BRANDING_LOGO_URL,

        "file_size": info["file_size"],

    }





@router.get("/branding/logo")

def get_branding_logo():

    """读取品牌 logo（FileResponse，供 <img :src> 直接用）。"""

    repo = SystemConfigRepository()

    try:

        branding = repo.get_value(_BRANDING_KEY, {}) or {}

    finally:

        repo.close()

    logo_path = branding.get("logo_path") if isinstance(branding, dict) else None

    if not logo_path:

        raise HTTPException(status_code=404, detail="未设置 logo")

    abs_path = FileStorage().base_path / logo_path

    if not abs_path.exists():

        raise HTTPException(status_code=404, detail="logo 文件不存在")

    return FileResponse(

        str(abs_path),

        headers={"Cache-Control": "no-cache, must-revalidate"},

    )
