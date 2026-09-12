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
from app.services.agent_tool_specs import tool_catalog
from app.services.office_access import allowed_chat_role_keys
from app.services.colleague_turn_service import run_colleague_turn
from app.services.ai_colleague_service import (
    get_colleague,
    get_team_lead_role_key,
    resolve_assistant_message_target_async,
    resolve_chat_target,
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


class CardSelectionBody(BaseModel):
    slot: str
    value: str
    label: Optional[str] = None  # 仅审计展示用；落槽以服务端留底的 (slot,value) 匹配为准
    qty: Optional[int] = None    # stepper 数量参数（服务端按机箱能力 clamp 后克隆 signal）


class PostMessageBody(BaseModel):
    content: str
    opportunity_id: Optional[str] = None
    quotation_id: Optional[str] = None
    context_summary: Optional[str] = None  # 前端多域 provider 拼的当前上下文摘要
    role_key: Optional[str] = None  # 可选：直接指定某位 AI 同事（不传则按分派规则自动决定）
    entry_point: Optional[str] = None
    option_slot: Optional[str] = None  # 用户点击结构化选项时，明确该选项对应的槽位
    card_selections: Optional[list[CardSelectionBody]] = None  # 表单模式：一次提交多组缺口选择
    workflow_key: Optional[str] = None  # 方案助手「+」显式唤醒的工作流 key（直接 ACTIVE）


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


class GroupResolveBody(BaseModel):
    entry_point: Optional[str] = None


@router.post("/threads/group-resolve")
def group_thread_resolve(body: GroupResolveBody, user: dict = Depends(current_user)):
    """团队群会话（未绑定同事的总助线程）get-or-create。

    群聊是 leader 调度与 @ 点名的唯一场所；与方案助手 1:1（office_colleague 绑定线程）是两个窗口。
    """
    if not _user_can_chat_with_role(user, "assistant"):
        raise HTTPException(status_code=403, detail="无权访问团队群")
    repo = AssistantRepository()
    try:
        existing = [
            t for t in repo.list_threads(user["user_id"], thread_kind="assistant", limit=5)
            if not str(t.get("colleague_role_key") or "").strip()
        ]
        if existing:
            thread = existing[0]
            if body.entry_point:
                updated = repo.update_thread_entry_point(thread["thread_id"], body.entry_point)
                if updated:
                    thread = updated
            return {"thread": thread}
        thread = repo.create_thread(
            created_by=user["user_id"],
            title="配置团队",
            thread_kind="assistant",
            entry_point=body.entry_point,
        )
        opening = str((get_colleague("assistant") or {}).get("opening_message") or "").strip()
        if opening:
            repo.add_message(
                thread_id=thread["thread_id"], role="assistant", content=opening,
                kind="opening", colleague_role_key="assistant",
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
        # 开场白唯一出处 = 员工配置（Manage Teams · 员工 · 开场白）；未点名同事即方案助手本人。
        opening_role_key = opening_role_key or "assistant"
        opening = str((get_colleague(opening_role_key) or {}).get("opening_message") or "").strip()
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
        msgs = repo.list_messages(thread_id, limit=limit)
        # 上下文水位：估算送入 LLM 的历史规模（中文约 0.6 token/字符；上限按 64k 保守显示）
        chars = sum(len(str(m.get("content") or "")) for m in msgs)
        est_tokens = int(chars * 0.6)
        limit_tokens = 65536
        return {
            "messages": msgs,
            "context_usage": {
                "chars": chars,
                "est_tokens": est_tokens,
                "limit_tokens": limit_tokens,
                "ratio": round(min(1.0, est_tokens / limit_tokens), 3),
            },
        }
    finally:
        repo.close()


@router.post("/threads/{thread_id}/restore")
def restore_thread(thread_id: str, user: dict = Depends(current_user)):
    """从归档恢复会话：同（类型，角色）的当前活跃会话先归档换位（每角色仅一个活跃会话）。"""
    repo = AssistantRepository()
    try:
        thread = _thread_for_user(repo, thread_id, user)
        if not str(thread.get("deleted_at") or "").strip():
            return {"thread": thread}
        role_key = str(thread.get("colleague_role_key") or "").strip() or None
        kind = thread.get("thread_kind") or "assistant"
        for t in repo.list_threads(user["user_id"], thread_kind=kind, colleague_role_key=role_key, limit=1):
            if t.get("thread_id") != thread_id:
                repo.soft_delete_thread(t["thread_id"], created_by=user["user_id"])
        restored = repo.restore_thread(thread_id, created_by=user["user_id"])
        if not restored:
            raise HTTPException(status_code=404, detail="会话不存在")
        fresh = repo.list_threads(user["user_id"], thread_kind=kind, colleague_role_key=role_key, limit=5)
        target = next((t for t in fresh if t.get("thread_id") == thread_id), None)
        return {"thread": target or thread}
    finally:
        repo.close()


# 每线程在跑的后台任务注册表：stop 端点据此真正取消任务（旧 stop 事件无消费者=安慰剂，已废）。
_ACTIVE_TURN_TASKS: dict[str, "asyncio.Task"] = {}


async def _run_office_turn(
    thread_id: str,
    content: str,
    context_summary: Optional[str],
    history: list,
    colleague: Optional[dict],
    user_id: Optional[str] = None,
    user: Optional[dict] = None,
    opportunity_id: Optional[str] = None,
    option_slot: Optional[str] = None,
    card_selections: Optional[list] = None,
    entry_point: Optional[str] = None,
    workflow_key: Optional[str] = None,
) -> None:
    """后台处理 AI Office 会话：空间指令优先，其余走普通聊天/LLM 意图识别。"""
    try:
        colleague_role_key = (colleague or {}).get("role_key") or "assistant"

        await publish_office_event(
            colleague_role_key,
            "working",
            "接收新任务",
            message=content or "",
            thread_id=thread_id,
        )
        task = asyncio.create_task(run_colleague_turn(
            thread_id, content, context_summary, history, colleague,
            trace_sink=lambda **kw: _record_assistant_tool_trace(user_id=user_id, **kw),
            user=user,
            opportunity_id=opportunity_id,
            option_slot=option_slot,
            card_selections=card_selections,
            entry_point=entry_point,
            workflow_key=workflow_key,
        ))
        _ACTIVE_TURN_TASKS[thread_id] = task
        task.add_done_callback(lambda _t: _ACTIVE_TURN_TASKS.pop(thread_id, None))
    except Exception:
        logger.exception("AI Office 消息后台处理失败")
        # 必达终态：失败必须落一条持久化消息——只广播的话，无 WS 客户端时用户看到的就是石沉大海。
        try:
            repo = AssistantRepository()
            try:
                repo.add_message(
                    thread_id=thread_id, role="assistant",
                    content="这一条处理失败了，请重新发送一次。", kind="error",
                )
            finally:
                repo.close()
        except Exception:
            logger.exception("落库终态错误消息失败")
        try:
            await assistant_hub.broadcast(thread_id, {"type": "error", "message": "这一条处理失败了，请重新发送一次。"})
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
        if body.entry_point and (body.entry_point or "").strip() != "workflow_launcher":
            updated_thread = repo.update_thread_entry_point(thread_id, body.entry_point)
            if updated_thread:
                thread = updated_thread
        # 绑定会话（1:1，含方案助手自己）永不转接；只有未绑定线程=团队群才 @点名/判官转接（2026-08-30 定调）
        bound_role = str(thread.get("colleague_role_key") or "").strip() or (requested_role_key or "").strip()
        colleague, dispatch_target = await resolve_chat_target(
            bound_role or None, body.content, body.context_summary,
        )

        if colleague and not _user_can_chat_with_role(user, str(colleague.get("role_key") or "")):
            raise HTTPException(status_code=403, detail="无权与该 AI 角色聊天")
        if not requested_role_key and not colleague:
            allowed = allowed_chat_role_keys(user)
            if allowed is not None:
                raise HTTPException(status_code=403, detail="请选择可用的 AI 角色")

        # history 必须先于本轮落库读取（history=之前的消息）：组 prompt/需求原文时当前消息
        # 由各消费方显式追加，混入会造成双发双写（2026-09-05 需求原文双 Polaris 实测）。
        history = repo.list_messages(thread_id)
        user_msg = repo.add_message(
            thread_id=thread_id, role="user", content=body.content,
            opportunity_id=body.opportunity_id, quotation_id=body.quotation_id,
        )
        if dispatch_target is not None:
            # 转接可见化：用户消息之后落一条转接标记（leader 名义），专家随后的回复带自己的头像身份
            name = str(dispatch_target.get("name") or dispatch_target.get("role_key") or "")
            reason = str(dispatch_target.get("_dispatch_reason") or "").strip()
            marker = repo.add_message(
                thread_id=thread_id, role="assistant",
                content=f"转给 {name}" + (f"（{reason}）" if reason else ""),
                kind="handoff", colleague_role_key="assistant",
            )
            await assistant_hub.broadcast(thread_id, {"type": "done", "message": marker})
        # auto-title: 首条用户消息前 24 字作为标题
        if not thread.get("title") or thread["title"] == "新会话":
            snippet = (body.content or "").strip().replace("\n", " ")[:24]
            if snippet:
                updated = repo.update_thread_title(thread_id, snippet)
                if updated:
                    thread = updated
    finally:
        repo.close()

    asyncio.create_task(_run_office_turn(
        thread_id, body.content, body.context_summary, history, colleague,
        user_id=user["user_id"],
        user=user,
        opportunity_id=body.opportunity_id or thread.get("opportunity_id"),
        option_slot=body.option_slot,
        card_selections=[s.model_dump() for s in body.card_selections] if body.card_selections else None,
        entry_point=body.entry_point or thread.get("entry_point"),
        workflow_key=body.workflow_key,
    ))
    return {"user_message": user_msg, "thread": thread, "colleague": colleague}


@router.post("/threads/{thread_id}/stop")
async def stop_workflow(thread_id: str, user: dict = Depends(current_user)):
    """停止当前线程正在运行的后台任务：直接取消任务并把取消事件广播给前端。"""
    repo = AssistantRepository()
    try:
        _thread_for_user(repo, thread_id, user)
    finally:
        repo.close()
    task = _ACTIVE_TURN_TASKS.pop(thread_id, None)
    if task is not None and not task.done():
        task.cancel()
    # 排队中的引导消息一并作废（用户按停=不要了；原话仍在会话历史里）
    from app.services.colleague_turn_service import _clear_thread_queue
    _clear_thread_queue(thread_id)
    await assistant_hub.broadcast(thread_id, {"type": "analysis_cancelled", "message": "已取消当前任务。"})
    return {"status": "cancelled" if task is not None else "idle"}


@router.post("/threads/{thread_id}/dispatch-preview")
async def dispatch_preview(thread_id: str, body: DispatchPreviewBody, user: dict = Depends(current_user)):
    """发送前预览转接对象：不落库、不启动任务，由 AI 按员工名册判断（leader 专属）。"""
    repo = AssistantRepository()
    try:
        thread = _thread_for_user(repo, thread_id, user)
    finally:
        repo.close()
    # 与 post_message 同一套门控：绑定会话永不转接；总助会话仅 leader=方案助手时转接
    colleague = None
    if not str(thread.get("colleague_role_key") or "").strip() and get_team_lead_role_key() == "assistant":
        colleague = await resolve_assistant_message_target_async(body.content, body.context_summary)
    if colleague and not _user_can_chat_with_role(user, str(colleague.get("role_key") or "")):
        colleague = None
    return {
        "colleague": colleague,
        "reason": str(colleague.get("_dispatch_reason") or "") if colleague else "",
    }


@router.get("/threads/{thread_id}/card-pick")
def card_pick(thread_id: str, slot: str = Query(..., min_length=1),
              role_key: Optional[str] = Query(None), user: dict = Depends(current_user)):
    """配件库自选候选：按当前留底卡的 pick_meta 生成与发卡同格式的选项（含 signal），
    并登记进 last_card.options——后续点击仍走 (slot,value) 服务端留底匹配，
    客户端回传不携带 signal，服务端留底原则不破。"""
    from app.services.skill_memory import _load_mem, _save_mem
    from app.services.part_selector import manual_pick_options
    from app.services.data_boundary import colleague_price_ok
    from app.services.ai_colleague_service import get_colleague

    repo = AssistantRepository()
    try:
        thread = _thread_for_user(repo, thread_id, user)
    finally:
        repo.close()
    rk = (role_key or "").strip() or str(thread.get("colleague_role_key") or "").strip() or "assistant"
    mem = _load_mem(thread_id, rk)
    last_card = mem.get("last_card") or {}
    meta = last_card.get("pick_meta") or {}
    if not meta:
        raise HTTPException(status_code=409, detail="当前选项卡不支持自选（任务进行中的配件推荐卡才可）")

    # 行绑定卡（kp_reason 确认卡，2026-09-06 插头化）：自选候选=该行数据源重跑
    # （注册表解析，放宽 limit），选项带 kp_manual_pick 信号（价格服务端留底，
    # 客户端不携带）；登记进 last_card 供后续 (slot,value) 留底匹配。
    if meta.get("row"):
        from app.services.skill_memory import _load_mem as _lm, _save_mem as _sm  # noqa: F401
        from app.services.part_selector import resolve_kp_pools
        from app.services.data_boundary import colleague_price_ok
        from app.services.ai_colleague_service import get_colleague
        binding = {}
        try:
            from app.repository.reasoning_flow_repo import ReasoningFlowRepository
            fr = ReasoningFlowRepository()
            try:
                flow = fr.get_active_flow("requirement_analysis")
                kcfg = (flow.get("node_configs") or {}).get("kp_reason") or {}
                binding = (kcfg.get("data_bindings") or {}).get("kp_pool") or {}
            finally:
                fr.close()
        except Exception:
            binding = {}
        series = str(meta.get("series") or "")
        row_qty = int(meta.get("row_qty") or 1)
        pools, _src = resolve_kp_pools(
            binding,
            [{"category": str(meta.get("category") or ""), "request_spec": str(meta.get("request_spec") or ""),
              "qty": row_qty, "unmatched": True}],
            series=series, default_limit=50)
        pool = next(iter(pools.values()), {}) if pools else {}
        cands = [c for c in (pool.get("candidates") or [])
                 if isinstance(c, dict) and str(c.get("name") or "").strip()]
        recalled = bool(cands)
        if not recalled:
            # 行描述零召回（库内无对应词）：自选下拉回落类目全量，但如实标注「未按行
            # 规格过滤」，与发卡兜底组「宁缺毋滥」不同——客户主动要全库就该给全库。
            from app.services.data_tools import part_query
            _q = part_query(str(meta.get("category") or ""), series=series, limit=50)
            cands = (_q.get("rows") or []) if _q.get("ok") else []
        price_ok = colleague_price_ok(get_colleague(rk) or {})
        opts = []
        for c in cands:
            if not isinstance(c, dict) or not str(c.get("name") or "").strip():
                continue
            desc = " · ".join(f"{k}:{v}" for k, v in (c.get("specs") or {}).items())[:80]
            o = {"label": str(c.get("name") or ""), "value": str(c.get("name") or ""),
                 "desc": desc, "slot": slot,
                 "group": "配件库候选" if recalled else "配件库全部·未按行规格过滤",
                 "qty": row_qty, "qty_max": max(row_qty, 24),
                 "signal": {"kp_manual_pick": {"row": str(meta.get("row")),
                                               "part_id": str(c.get("part_id") or ""),
                                               "name": str(c.get("name") or ""),
                                               **({"price": c.get("price")} if price_ok else {}),
                                               "currency": str(c.get("currency") or "RMB")}}}
            opts.append(o)
        if not opts:
            raise HTTPException(status_code=404, detail="该行数据源暂无候选")
        keep = [o for o in (last_card.get("options") or [])
                if not (str(o.get("slot") or "") == slot and o.get("_manual"))]
        merged = keep + [{**o, "_manual": True} for o in opts]
        _save_mem(thread_id, rk, {**mem, "last_card": {**last_card, "options": merged}})
        return {"slot": slot, "options": [{k: v for k, v in o.items() if k != "signal"} for o in opts]}

    opts = manual_pick_options(
        slot, str(meta.get("server_type_name") or ""),
        baseline={"series": meta.get("series"), "gpu_slots": meta.get("gpu_slots"),
                  "max_cpu": meta.get("max_cpu"), "max_dimm": meta.get("max_dimm")},
        include_price=colleague_price_ok(get_colleague(rk) or {}))
    if not opts:
        raise HTTPException(status_code=404, detail="配件库该类别没有平台适配候选")
    keep = [o for o in (last_card.get("options") or [])
            if not (str(o.get("slot") or "") == slot and o.get("_manual"))]
    merged = keep + [{**o, "_manual": True} for o in opts]
    _save_mem(thread_id, rk, {**mem, "last_card": {**last_card, "options": merged}})
    return {"slot": slot, "options": [{k: v for k, v in o.items() if k != "signal"} for o in opts]}


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
