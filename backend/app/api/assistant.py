"""Assistant API — global AI assistant chat.

Identity resolved from X-User-Id (same as Feed). POST /threads/{id}/messages stores
the user turn and kicks off a background LLM stream; tokens are pushed over the WS
endpoint (/ws/{thread_id}) via assistant_hub. If the call fails, the real error
(HTTP/auth/model name) is surfaced in-chat so the user can diagnose; AI 设置页的
「测试连接」按钮做更结构化的排障。
"""
import asyncio
import logging
import json
from typing import Optional, Union

from fastapi import (
    APIRouter, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect,
)
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_user as current_user, require_perms, resolve_ws_user, user_has_permission
from app.core.config import get_settings
from app.repository.assistant_repo import AssistantRepository
from app.services import llm_client
from app.services.assistant_hub import assistant_hub
from app.services.office_events import publish_office_event
from app.services.office_intent import resolve_office_spatial_intent
from app.services.office_memory import office_memory
from app.services.agent_tools import tool_catalog
from app.services.office_access import allowed_chat_role_keys
from app.services.colleague_turn_service import run_colleague_turn
from app.services.ai_colleague_service import (
    get_colleague,
    resolve_assistant_message_dispatch,
    resolve_assistant_message_target,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


def _user_can_chat_with_role(user: dict, role_key: Optional[str]) -> bool:
    """Check whether the current account may open or continue this AI role chat."""
    key = str(role_key or "").strip()
    if not key or key == "unknown":
        return True
    allowed = allowed_chat_role_keys(user)
    if allowed is None:
        return True
    return key in allowed


def _authorize_thread_access(thread: dict, user: dict) -> None:
    """Owner/admin access plus role-level chat authorization."""
    if str(thread.get("created_by") or "") != str(user.get("user_id") or "") and not user_has_permission(user, "ai.office.admin"):
        raise HTTPException(status_code=403, detail="无权访问该会话")
    role_key = str(thread.get("colleague_role_key") or "").strip()
    if role_key and not _user_can_chat_with_role(user, role_key):
        raise HTTPException(status_code=403, detail="无权与该 AI 角色聊天")


def _thread_for_user(repo: AssistantRepository, thread_id: str, user: dict) -> dict:
    """读取会话并校验所有者；管理员/有 AI 运行管理权限者可跨用户管理。"""
    thread = repo.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="会话不存在")
    _authorize_thread_access(thread, user)
    return thread


def _decorate_assistant_threads(threads: list) -> list:
    """给会话记录补登录用户姓名与 AI 同事显示名，前端列表直接可用。"""
    if not threads:
        return threads
    user_ids = [str(t.get("created_by") or "") for t in threads if t.get("created_by")]
    role_keys = [str(t.get("colleague_role_key") or "") for t in threads if t.get("colleague_role_key")]
    user_name_map: dict = {}
    colleague_name_map: dict = {}
    if user_ids:
        from app.repository.feed_user_repo import FeedUserRepository
        user_repo = FeedUserRepository()
        try:
            user_name_map = user_repo.name_map(user_ids)
        finally:
            user_repo.close()
    if role_keys:
        from app.repository.system_config_repo import SystemConfigRepository
        config_repo = SystemConfigRepository()
        try:
            cfg = config_repo.get_value("ai_colleagues", {}) or {}
            colleagues = cfg.get("colleagues") or []
            colleague_name_map = {
                str(c.get("role_key") or ""): (c.get("name") or c.get("role_key") or "")
                for c in colleagues if isinstance(c, dict)
            }
        finally:
            config_repo.close()
    for t in threads:
        created_by = str(t.get("created_by") or "")
        role_key = str(t.get("colleague_role_key") or "")
        t["created_by_name"] = user_name_map.get(created_by, created_by)
        t["colleague_name"] = colleague_name_map.get(role_key, "")
    return threads


class CreateThreadBody(BaseModel):
    title: Optional[str] = None
    opportunity_id: Optional[str] = None
    quotation_id: Optional[str] = None
    opening_role_key: Optional[str] = None
    thread_kind: Optional[str] = "assistant"  # assistant=方案助手；office_colleague=AI Office 同事
    entry_point: Optional[str] = None  # portal / floating_assistant / ai_office / settings


class RenameThreadBody(BaseModel):
    title: str


class PostMessageBody(BaseModel):
    content: str
    opportunity_id: Optional[str] = None
    quotation_id: Optional[str] = None
    context_summary: Optional[str] = None  # 前端多域 provider 拼的当前上下文摘要
    role_key: Optional[str] = None  # 可选：直接指定某位 AI 同事（不传则按分派规则自动决定）
    entry_point: Optional[str] = None


class SelfConfigBody(BaseModel):
    model_id: Optional[Union[str, int]] = None


class DispatchPreviewBody(BaseModel):
    content: str
    context_summary: Optional[str] = None


class ResolveThreadBody(BaseModel):
    role_key: str
    opportunity_id: Optional[str] = None
    quotation_id: Optional[str] = None
    entry_point: Optional[str] = None


@router.post("/threads/resolve")
def resolve_employee_thread(body: ResolveThreadBody, user: dict = Depends(current_user)):
    """Resolve the canonical non-deleted AI employee thread for user + role_key.

    All chat entry points call this first, so Portal, floating assistant and
    AI Office open the same conversation history.
    """
    role_key = (body.role_key or "").strip()
    if not role_key:
        raise HTTPException(status_code=400, detail="role_key 不能为空")
    if not _user_can_chat_with_role(user, role_key):
        raise HTTPException(status_code=403, detail="无权与该 AI 角色聊天")

    is_preview = (body.entry_point or "").strip() == "skill_studio_preview"
    repo = AssistantRepository()
    try:
        # 预览会话（Skill 编辑器测试）：每次进入都新建独立线程，不复用正式会话；退出/刷新由前端清理。
        if is_preview:
            colleague = get_colleague(role_key)
            title = "需求分析预览 · " + str((colleague or {}).get("name") or role_key).strip()
            thread = repo.create_thread(
                created_by=user["user_id"],
                title=title,
                thread_kind="office_colleague",
                colleague_role_key=role_key,
                entry_point="skill_studio_preview",
            )
            opening = str((colleague or {}).get("opening_message") or "").strip()
            if opening:
                repo.add_message(
                    thread_id=thread["thread_id"],
                    role="assistant",
                    content=opening,
                    kind="opening",
                    colleague_role_key=role_key,
                )
            return {"thread": thread}
        existing = repo.list_threads(
            user["user_id"],
            thread_kind="office_colleague",
            colleague_role_key=role_key,
            limit=1,
        )
        if existing:
            thread = existing[0]
            if body.entry_point:
                updated = repo.update_thread_entry_point(thread["thread_id"], body.entry_point)
                if updated:
                    thread = updated
            return {"thread": thread}

        colleague = get_colleague(role_key)
        title = str((colleague or {}).get("name") or role_key).strip() or role_key
        try:
            thread = repo.create_thread(
                created_by=user["user_id"],
                title=title,
                opportunity_id=body.opportunity_id,
                quotation_id=body.quotation_id,
                thread_kind="office_colleague",
                colleague_role_key=role_key,
                entry_point=body.entry_point,
            )
        except IntegrityError:
            repo.session.rollback()
            existing = repo.list_threads(
                user["user_id"],
                thread_kind="office_colleague",
                colleague_role_key=role_key,
                limit=1,
            )
            if existing:
                return {"thread": existing[0]}
            raise
        opening = str((colleague or {}).get("opening_message") or "").strip()
        if opening:
            repo.add_message(
                thread_id=thread["thread_id"],
                role="assistant",
                content=opening,
                kind="opening",
                colleague_role_key=role_key,
            )
        return {"thread": thread}
    finally:
        repo.close()


@router.post("/threads")
def create_thread(body: CreateThreadBody, user: dict = Depends(current_user)):
    opening_role_key = (body.opening_role_key or "").strip() or None
    if opening_role_key and not _user_can_chat_with_role(user, opening_role_key):
        raise HTTPException(status_code=403, detail="无权与该 AI 角色聊天")
    if body.thread_kind == "office_colleague" and not opening_role_key:
        raise HTTPException(status_code=400, detail="员工会话必须指定 role_key")

    repo = AssistantRepository()
    try:
        thread = repo.create_thread(
            created_by=user["user_id"],
            title=body.title,
            opportunity_id=body.opportunity_id,
            quotation_id=body.quotation_id,
            thread_kind=body.thread_kind or "assistant",
            colleague_role_key=opening_role_key,
            entry_point=body.entry_point,
        )
        # 指定 AI 同事开场时使用该同事配置的开场白；否则沿用全局方案助手开场白。
        opening_role_key = "assistant"
        opening = _opening_message()
        if body.opening_role_key:
            colleague = get_colleague(body.opening_role_key)
            opening_role_key = body.opening_role_key
            opening = str((colleague or {}).get("opening_message") or "").strip()
        if opening:
            repo.add_message(
                thread_id=thread["thread_id"], role="assistant", content=opening, kind="opening",
                colleague_role_key=opening_role_key,
            )
        return {"thread": thread}
    finally:
        repo.close()


@router.get("/threads")
def list_threads(
    scope: str = "mine",
    thread_kind: Optional[str] = None,
    role_key: Optional[str] = None,
    created_by: Optional[str] = None,
    keyword: Optional[str] = None,
    include_deleted: bool = False,
    include_preview: bool = False,
    user: dict = Depends(current_user),
):
    """会话列表：scope=mine（默认，当前用户，可含回收站/预览）/ scope=all（AI 设置管理页，含回收站+消息数）。"""
    role_filter = (role_key or "").strip() or None
    if role_filter and not _user_can_chat_with_role(user, role_filter):
        return {"threads": []}
    repo = AssistantRepository()
    try:
        if scope == "all":
            if not user_has_permission(user, "ai.office.admin"):
                raise HTTPException(status_code=403, detail="无权限查看全部会话")
            return {"threads": _decorate_assistant_threads(repo.list_all_threads(
                thread_kind=thread_kind,
                colleague_role_key=role_key,
                created_by=created_by,
                keyword=keyword,
            ))}
        return {"threads": repo.list_threads(
            user["user_id"],
            thread_kind=thread_kind or "assistant",
            colleague_role_key=role_filter,
            include_deleted=include_deleted,
            with_meta=include_preview,
            include_preview=include_preview,
        )}
    finally:
        repo.close()


@router.get("/threads/{thread_id}/messages")
def list_messages(thread_id: str, limit: int = 50, user: dict = Depends(current_user)):
    repo = AssistantRepository()
    try:
        _thread_for_user(repo, thread_id, user)
        return {"messages": repo.list_messages(thread_id, limit=limit)}
    finally:
        repo.close()


async def _run_office_turn(
    thread_id: str,
    content: str,
    context_summary: Optional[str],
    history: list,
    colleague: Optional[dict],
    user_id: Optional[str] = None,
    user: Optional[dict] = None,
    opportunity_id: Optional[str] = None,
) -> None:
    """后台处理 AI Office 会话：空间指令优先，其余走普通聊天/LLM 意图识别。"""
    try:
        colleague_role_key = (colleague or {}).get("role_key") or "assistant"
        await office_memory.remember(
            colleague_role_key,
            f"用户消息：{content}",
            kind="episodic",
            importance=0.4,
        )

        spatial = await resolve_office_spatial_intent(content, colleague_role_key, colleague=colleague)

        if spatial:
            await _reply_spatial_action(thread_id, content, colleague, spatial)
            return

        await publish_office_event(
            colleague_role_key,
            "working",
            "接收新任务",
            message=content or "",
            thread_id=thread_id,
        )
        asyncio.create_task(run_colleague_turn(
            thread_id, content, context_summary, history, colleague,
            trace_sink=lambda **kw: _record_assistant_tool_trace(user_id=user_id, **kw),
            user=user,
            opportunity_id=opportunity_id,
        ))
    except Exception:
        logger.exception("AI Office 消息后台处理失败")
        try:
            await assistant_hub.broadcast(thread_id, {"type": "error", "message": "回复处理失败，请稍后重试"})
        except Exception:
            pass
@router.post("/threads/{thread_id}/messages")
async def post_message(thread_id: str, body: PostMessageBody, user: dict = Depends(current_user)):
    """Append a user turn, then stream an assistant reply via WS.

    立即返回 user_message;LLM token 流通过 /ws/{thread_id} 推送(chunk → done)。
    首条用户消息自动作为会话标题。LLM 失败时回退占位回复。
    """
    requested_role_key = (body.role_key or "").strip() or None
    if requested_role_key and not _user_can_chat_with_role(user, requested_role_key):
        raise HTTPException(status_code=403, detail="无权与该 AI 角色聊天")

    repo = AssistantRepository()
    try:
        thread = _thread_for_user(repo, thread_id, user)
        if body.entry_point:
            updated_thread = repo.update_thread_entry_point(thread_id, body.entry_point)
            if updated_thread:
                thread = updated_thread
        if requested_role_key:
            colleague = get_colleague(requested_role_key)
        else:
            colleague = resolve_assistant_message_target(body.content, body.context_summary)

        if colleague and not _user_can_chat_with_role(user, str(colleague.get("role_key") or "")):
            raise HTTPException(status_code=403, detail="无权与该 AI 角色聊天")
        if not requested_role_key and not colleague:
            allowed = allowed_chat_role_keys(user)
            if allowed is not None:
                raise HTTPException(status_code=403, detail="请选择可用的 AI 角色")

        user_msg = repo.add_message(
            thread_id=thread_id, role="user", content=body.content,
            opportunity_id=body.opportunity_id, quotation_id=body.quotation_id,
        )
        # auto-title: 首条用户消息前 24 字作为标题
        if not thread.get("title") or thread["title"] == "新会话":
            snippet = (body.content or "").strip().replace("\n", " ")[:24]
            if snippet:
                updated = repo.update_thread_title(thread_id, snippet)
                if updated:
                    thread = updated
        history = repo.list_messages(thread_id)
    finally:
        repo.close()

    asyncio.create_task(_run_office_turn(
        thread_id, body.content, body.context_summary, history, colleague,
        user_id=user["user_id"],
        user=user,
        opportunity_id=body.opportunity_id or thread.get("opportunity_id"),
    ))
    return {"user_message": user_msg, "thread": thread, "colleague": colleague}


@router.post("/threads/{thread_id}/self-config")
async def mark_self_config(thread_id: str, body: SelfConfigBody, user: dict = Depends(current_user)):
    """候选卡“去配置这台服务器”点击后，把当前待机型的 workflow 置为 self_config 并跳过下游 BOM。

    纯确定性状态迁移，不启动 LLM 回合；无待机型流程时返回 409。
    """
    repo = AssistantRepository()
    try:
        thread = _thread_for_user(repo, thread_id, user)
    finally:
        repo.close()
    role_key = str(thread.get("colleague_role_key") or "").strip()
    colleague = get_colleague(role_key) if role_key else None
    if colleague and not _user_can_chat_with_role(user, str(colleague.get("role_key") or "")):
        raise HTTPException(status_code=403, detail="无权与该 AI 角色聊天")
    from app.services.colleague_turn_service import mark_self_config_flow
    done = await mark_self_config_flow(thread_id, colleague)
    if not done:
        raise HTTPException(status_code=409, detail="当前没有等待机型的流程")
    return {"ok": True, "model_id": body.model_id}


@router.post("/threads/{thread_id}/dispatch-preview")
def dispatch_preview(thread_id: str, body: DispatchPreviewBody, user: dict = Depends(current_user)):
    """发送前预览推荐同事：不落库、不启动任务，只返回命中的同事与规则。"""
    repo = AssistantRepository()
    try:
        _thread_for_user(repo, thread_id, user)
    finally:
        repo.close()
    result = resolve_assistant_message_dispatch(body.content, body.context_summary)
    colleague = result.get("colleague")
    if colleague and not _user_can_chat_with_role(user, str(colleague.get("role_key") or "")):
        colleague = None
    return {
        "colleague": colleague,
        "matched_rule": result.get("matched_rule") if colleague else None,
    }


_DEFAULT_OPENING = (
    "Hi！我是你的服务器配置顾问 🎉\n\n"
    "请告诉我你的工作负载，我来推荐合适的平台，再陪你一步步配置：\n\n"
    "- 🖥️ 虚拟化 / 云主机（运行多少台虚拟机？）\n"
    "- 🗄️ 数据库（SQL/NoSQL？数据量多大？）\n"
    "- 🤖 AI / 机器学习（训练还是推理？需要几块 GPU？）\n"
    "- 🌐 Web / 应用服务器\n"
    "- 💾 文件 / 备份存储\n"
    "- 🏢 边缘 / 分支机构\n\n"
    "也可以直接描述你的需求。"
)


def _opening_message() -> str:
    """新会话开场引导文案（system_config.assistant_opening 可配，默认内置）。"""
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            v = repo.get_value("assistant_opening")
        finally:
            repo.close()
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception:
        pass
    return _DEFAULT_OPENING


def _record_assistant_tool_trace(tool_name: str, status: str, duration_ms: int, thread_id: Optional[str],
                                 response_chars: int = 0, error: Optional[str] = None,
                                 model: Optional[str] = None, prompt_chars: int = 0,
                                 node_type: Optional[str] = None,
                                 user_id: Optional[str] = None,
                                 role_key: Optional[str] = None) -> None:
    """把方案助手/AI 同事的工具调用写入 rules.llm_trace（审计数据源），失败不阻塞主流程。"""
    try:
        from app.services.llm_trace import record_llm_trace
        record_llm_trace(
            node_type=node_type or f"assistant_tool:{tool_name}",
            opportunity_id=thread_id or "",
            pipeline_id=thread_id or "",
            status=status,
            duration_ms=duration_ms,
            response_chars=response_chars,
            model=model or "",
            prompt_chars=prompt_chars,
            error=error,
            user_id=user_id or "",
            role_key=role_key or "",
            tool_name=tool_name or "",
        )
    except Exception as e:
        logger.warning("写助手工具审计 trace 失败: %s", e)


async def _reply_spatial_action(thread_id: str, user_text: str, colleague: Optional[dict], spatial: dict) -> None:
    """Persist a short spatial confirmation and publish the office event immediately."""
    colleague_role_key = (colleague or {}).get("role_key") or "assistant"
    reply = str(spatial.get("reply") or "好的。").strip()
    repo = AssistantRepository()
    try:
        asst = repo.add_message(
            thread_id=thread_id, role="assistant", content=reply,
            colleague_role_key=(colleague or {}).get("role_key"),
        )
    except Exception:
        logger.exception("space instruction reply persistence failed")
        asst = None
    finally:
        repo.close()

    try:
        await publish_office_event(
            spatial.get("role_key") or colleague_role_key,
            spatial.get("status") or "meeting",
            spatial.get("activity") or "前往目标区域",
            message=reply,
            zone=spatial.get("zone"),
            intent=spatial.get("intent"),
            thread_id=thread_id,
            priority="user",
            source="assistant_chat",
        )
    except Exception:
        logger.exception("办公室空间指令事件发布失败")

    await assistant_hub.broadcast(thread_id, {"type": "chunk", "delta": reply})
    await assistant_hub.broadcast(thread_id, {"type": "done", "message": asst})
@router.get("/tools")
def list_tools():
    """AI 工具目录（只读）：全系统已注册 LLM 工具（名称/分类/描述/参数/默认启用）。

    数据来源：agent_tools._TOOL_SPECS（唯一注册表）；AI 设置页「方案助手」tab 底部只读表格展示。
    """
    return {"tools": tool_catalog()}


@router.patch("/threads/{thread_id}")
def rename_thread(thread_id: str, body: RenameThreadBody, user: dict = Depends(current_user)):
    """重命名当前用户拥有的会话。"""
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="会话标题不能为空")
    repo = AssistantRepository()
    try:
        _thread_for_user(repo, thread_id, user)
        updated = repo.update_thread_title(thread_id, title)
        if not updated:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {"thread": updated}
    finally:
        repo.close()


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: str, hard: bool = False, user: dict = Depends(current_user)):
    """删除会话：默认软删（进回收站）；hard=1 彻底删除（消息+状态一起物理清）。"""
    repo = AssistantRepository()
    try:
        _thread_for_user(repo, thread_id, user)
        if hard:
            ok = repo.hard_delete_thread(thread_id)
        else:
            ok = repo.soft_delete_thread(thread_id)
        if not ok:
            raise HTTPException(status_code=404, detail="会话不存在")
    finally:
        repo.close()
    return {"status": "ok"}


@router.post("/threads/{thread_id}/restore")
def restore_thread(thread_id: str, user: dict = Depends(current_user)):
    """回收站恢复：清空 deleted_at，会话回到正常列表。"""
    repo = AssistantRepository()
    try:
        _thread_for_user(repo, thread_id, user)
        if not repo.restore_thread(thread_id):
            raise HTTPException(status_code=404, detail="会话不存在")
    finally:
        repo.close()
    return {"status": "ok"}


@router.post("/admin/cleanup/empty-threads")
def cleanup_empty_threads(admin: dict = Depends(require_perms("ai.office.admin"))):
    """一键清理空会话：物理删除所有 0 消息的会话（含消息+状态），不可恢复。"""
    repo = AssistantRepository()
    try:
        deleted = repo.hard_delete_empty_threads()
    finally:
        repo.close()
    return {"deleted": deleted}


@router.get("/admin/audit")
def admin_audit(admin: dict = Depends(require_perms("ai.office.admin"))):
    """AI 同事审计/绩效面板：方案助手 LLM 调用 + 工具调用 trace 指标。"""
    from app.services.llm_trace import assistant_metrics
    return assistant_metrics(limit=100)


@router.post("/admin/cleanup/trace")
def cleanup_trace(body: dict, admin: dict = Depends(require_perms("ai.office.admin"))):
    """LLM 调用痕迹清理：只保留最近 keep_days 天（<=0 全清）。"""
    try:
        keep_days = int((body or {}).get("keep_days") or 30)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="keep_days 需为数字")
    repo = AssistantRepository()
    try:
        deleted = repo.purge_llm_trace(keep_days)
    finally:
        repo.close()
    return {"deleted": deleted}


@router.post("/admin/cleanup/samples")
def cleanup_samples(body: dict, admin: dict = Depends(require_perms("ai.office.admin"))):
    """需求反馈样本清理：保留最近 keep_n 条（0=全清）。"""
    try:
        keep_n = int((body or {}).get("keep_n") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="keep_n 需为数字")
    repo = AssistantRepository()
    try:
        deleted = repo.prune_requirement_samples(keep_n)
    finally:
        repo.close()
    return {"deleted": deleted}


# ── WS: subscribe to a thread's LLM token stream ──

@router.websocket("/ws/{thread_id}")
async def assistant_ws(ws: WebSocket, thread_id: str, token: Optional[str] = Query(None)):
    """Subscribe to the thread's token stream (chunk / done broadcast by colleague_turn_service).

    Frontend connects on panel open + currentThreadId. Inbound text is ignored
    (user messages go via REST POST which triggers the stream).
    """
    user = resolve_ws_user(token)
    if get_settings().AUTH_ENABLED and not user:
        await ws.close(code=4401)
        return

    repo = AssistantRepository()
    try:
        thread = repo.get_thread(thread_id)
    finally:
        repo.close()
    if not thread:
        await ws.close(code=4404)
        return
    try:
        _authorize_thread_access(thread, user or {})
    except HTTPException:
        await ws.close(code=4403)
        return

    await assistant_hub.connect(ws, thread_id)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await assistant_hub.disconnect(ws)
