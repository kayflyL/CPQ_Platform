"""工具内容 API —— 工具中心/工具页展示文案的读写。

读：登录即可（工具页人人可看，文案跟着页面走）。
写：action.tools.content.manage（默认仅 admin；admin 可在「用户与权限」开放）。
content 为前端不透明 JSONB blob（结构归前端 toolsRegistry 定义的 TS 类型）。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user, require_perms
from app.repository.tool_content_repo import DEFAULT_TOOL_CONTENTS, ToolContentRepository

router = APIRouter(tags=["tools"])


@router.get("/api/tools/content", dependencies=[Depends(get_current_user)])
def list_tool_contents():
    repo = ToolContentRepository()
    try:
        return {"contents": repo.list_all(), "defaults": DEFAULT_TOOL_CONTENTS}
    finally:
        repo.close()


class ToolContentBody(BaseModel):
    content: dict


@router.put("/api/tools/content/{key}")
def save_tool_content(key: str, body: ToolContentBody, user: dict = Depends(require_perms("action.tools.content.manage"))):
    key = (key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="工具 key 不能为空")
    if not isinstance(body.content, dict):
        raise HTTPException(status_code=400, detail="content 必须是对象")
    repo = ToolContentRepository()
    try:
        if repo.get(key) is None and key not in DEFAULT_TOOL_CONTENTS:
            raise HTTPException(status_code=404, detail=f"未知工具 {key}（新工具需先在注册表登记）")
        repo.upsert(key, body.content, updated_by=user.get("name") or "")
        return {"success": True}
    finally:
        repo.close()
