# -*- coding: utf-8 -*-
"""AI office mission planner and runner.

P0: turn a user instruction into a small mission/steps plan, persist it under
system_config.office_missions, then drive office-visible assignment events.

All roles, capabilities, dispatch rules, delays and action mappings are read
from ai_colleagues config; no colleague or route is hardcoded here.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.repository.system_config_repo import SystemConfigRepository
from app.services import ai_colleague_service
from app.services import llm_client
from app.services.agent_react import run_react_loop
from app.services.office_events import publish_office_event

logger = logging.getLogger(__name__)

_MISSION_KEY = "office_missions"
_CANCELLED_MISSIONS: set[str] = set()
_DELETED_MISSIONS: set[str] = set()
_MISSION_TASKS: Dict[str, asyncio.Task] = {}

VALID_ASSIGNMENT_STATUSES = {
    "queued", "routed", "active", "blocked", "done", "failed", "cancelled",
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_missions() -> List[dict]:
    try:
        repo = SystemConfigRepository()
        try:
            value = repo.get_value(_MISSION_KEY, {"missions": []})
        finally:
            repo.close()
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            missions = value.get("missions")
            return missions if isinstance(missions, list) else []
        return []
    except Exception:
        logger.exception("读取 office missions 失败")
        return []


def _save_missions(missions: List[dict]) -> None:
    try:
        repo = SystemConfigRepository()
        try:
            repo.set(
                _MISSION_KEY,
                {"missions": missions},
                "json",
                "AI 办公室任务编排（mission/steps）",
                "system",
            )
        finally:
            repo.close()
    except Exception:
        logger.exception("保存 office missions 失败")


def _save_mission(mission: dict) -> None:
    missions = _load_missions()
    replaced = False
    for index, item in enumerate(missions):
        if item.get("mission_id") == mission.get("mission_id"):
            missions[index] = mission
            replaced = True
            break
    if not replaced:
        missions.append(mission)
    max_missions = int((mission.get("_max_missions") or 100))
    _save_missions(missions[-max_missions:])

def _cancel_mission_task(mission_id: str) -> None:
    task = _MISSION_TASKS.pop(mission_id, None)
    if task and not task.done():
        task.cancel()

def _remove_mission_runtime(mission_id: str) -> None:
    _CANCELLED_MISSIONS.add(mission_id)
    _DELETED_MISSIONS.add(mission_id)
    _cancel_mission_task(mission_id)


def _config() -> dict:
    return ai_colleague_service.get_ai_colleague_config()


def _enabled_colleagues(config: dict) -> List[dict]:
    colleagues = config.get("colleagues") or []
    return [c for c in colleagues if isinstance(c, dict) and c.get("enabled", True)]


def _mission_settings(config: dict) -> dict:
    behavior = config.get("behavior") or {}
    mission = behavior.get("mission") or {}
    collaboration = mission.get("collaboration") or {
        "enabled": True,
        "zone": "meeting_room",
        "status": "meeting",
        "intent": "collaborate",
        "activity": "与协作对象讨论任务",
        "keywords": ["找", "和", "跟", "与", "核对", "讨论", "确认", "对齐"],
        "max_participants": 4,
    }
    return {
        "enabled": bool(mission.get("enabled", True)),
        "owner_role_key": mission.get("owner_role_key") or "",
        "max_steps": max(1, int(mission.get("max_steps") or 8)),
        "max_iterations": max(1, int(mission.get("max_iterations") or 4)),
        "route_delay_seconds": float(mission.get("route_delay_seconds") or 1.2),
        "work_delay_seconds": float(mission.get("work_delay_seconds") or 2.5),
        "done_delay_seconds": float(mission.get("done_delay_seconds") or 0.8),
        "default_intent": mission.get("default_intent") or "work",
        "clear_statuses": [
            str(item).strip().lower()
            for item in (mission.get("clear_statuses") or ["queued", "done", "failed", "cancelled"])
            if str(item).strip()
        ],
        "default_deliverable_type": mission.get("default_deliverable_type") or "text",
        "collaboration_deliverable_type": mission.get("collaboration_deliverable_type") or "meeting",
        "deliverable_types": mission.get("deliverable_types") or {},
        "collaboration_enabled": bool(collaboration.get("enabled", True)),
        "collaboration_zone": collaboration.get("zone") or "meeting_room",
        "collaboration_status": collaboration.get("status") or "meeting",
        "collaboration_intent": collaboration.get("intent") or "collaborate",
        "collaboration_activity": collaboration.get("activity") or "与协作对象讨论任务",
        "collaboration_keywords": [
            str(item).strip().lower()
            for item in (collaboration.get("keywords") or [])
            if str(item).strip()
        ],
        "collaboration_max_participants": max(2, int(collaboration.get("max_participants") or 4)),
    }

def _zone_for_role(role_key: str, colleague: Optional[dict], config: dict) -> str:
    if colleague:
        profile = colleague.get("behavior_profile") or {}
        preferred = profile.get("preferred_zones")
        if isinstance(preferred, list):
            for item in preferred:
                if isinstance(item, dict) and item.get("zone"):
                    return str(item["zone"]).strip()
    office = ((config.get("layout") or {}).get("office") or {})
    for zone in office.get("zones") or []:
        if not isinstance(zone, dict):
            continue
        for slot in zone.get("slots") or []:
            if isinstance(slot, dict) and slot.get("role_key") == role_key:
                return zone.get("id") or "desk_zone"
    return "desk_zone"


def _team_graph(config: dict) -> dict:
    layout = config.get("layout") or {}
    graph = layout.get("team_graph")
    return graph if isinstance(graph, dict) else {}


def _lead_role_key(config: dict) -> Optional[str]:
    colleagues = _enabled_colleagues(config)
    enabled_keys = {str(c.get("role_key") or "") for c in colleagues}
    if not enabled_keys:
        return None
    graph_lead = _team_graph(config).get("lead_role_key")
    if graph_lead in enabled_keys:
        return str(graph_lead)
    for colleague in colleagues:
        relations = colleague.get("relations") or {}
        if relations.get("team_role") == "lead":
            role_key = str(colleague.get("role_key") or "")
            if role_key in enabled_keys:
                return role_key
    return str(colleagues[0].get("role_key") or "")


def _make_step(
    mission_id: str,
    role_key: str,
    task: str,
    config: dict,
    step_index: int,
) -> dict:
    colleague = next(
        (c for c in _enabled_colleagues(config) if c.get("role_key") == role_key),
        None,
    )
    assignment_id = f"a_{mission_id}_{step_index}"
    return {
        "step_id": f"s{step_index}",
        "assignment_id": assignment_id,
        "role_key": role_key,
        "task": task,
        "intent": ((config.get("behavior") or {}).get("mission") or {}).get("default_intent") or "work",
        "zone": _zone_for_role(role_key, colleague, config),
        "assignment_status": "queued",
        "result_summary": "",
        "collaboration": False,
        "assigned_at": _now_iso(),
        "completed_by": "",
        "deliverables": [],
    }


def _role_key_mentions(prompt: str, colleagues: List[dict]) -> List[str]:
    haystack = (prompt or "").lower()
    ordered: List[tuple] = []
    for colleague in colleagues:
        role_key = colleague.get("role_key")
        if not role_key:
            continue
        positions = []
        for field in ("name", "role_key"):
            value = colleague.get(field)
            if value and str(value).strip().lower() in haystack:
                positions.append(haystack.find(str(value).strip().lower()))
        if positions:
            ordered.append((min(positions), role_key))
    ordered.sort(key=lambda item: item[0])
    return [role for _, role in ordered]


def _rule_roles(prompt: str, config: dict) -> List[str]:
    if not prompt:
        return []
    haystack = prompt.lower()
    rules = config.get("dispatch_rules")
    if not isinstance(rules, list):
        return []
    roles: List[str] = []
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("enabled", True) is False:
            continue
        keywords = rule.get("keywords")
        if not isinstance(keywords, list):
            continue
        if any(str(k).strip().lower() in haystack for k in keywords if str(k).strip()):
            role_key = rule.get("role_key")
            if role_key and role_key not in roles:
                roles.append(role_key)
    return roles


def plan_mission(
    prompt: str,
    config: Optional[dict] = None,
    owner_role_key: Optional[str] = None,
    priority: str = "medium",
    *,
    opportunity_id: Optional[str] = None,
    flow_node: Optional[str] = None,
    skill_key: Optional[str] = None,
    artifacts: Optional[List[dict]] = None,
) -> dict:
    config = config or _config()
    colleagues = _enabled_colleagues(config)
    if not colleagues:
        return {
            "ok": False,
            "error": "没有可用的 AI 同事",
            "mission_id": "",
            "steps": [],
        }
    prompt = (prompt or "").strip()
    if not prompt:
        return {
            "ok": False,
            "error": "任务内容不能为空",
            "mission_id": "",
            "steps": [],
        }
    lead_role_key = _lead_role_key(config) or str(colleagues[0].get("role_key") or "")
    if owner_role_key and any(c.get("role_key") == owner_role_key for c in colleagues):
        lead_role_key = owner_role_key
    now = datetime.now()
    mission_id = f"m_{now:%Y%m%d%H%M%S}_{uuid.uuid4().hex[:6]}"

    return {
        "ok": True,
        "mission_id": mission_id,
        "owner_role_key": lead_role_key,
        "lead_role_key": lead_role_key,
        "prompt": prompt,
        "status": "queued",
        "source": "lead",
        "priority": priority,
        "planning": True,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "completed_at": "",
        "completed_by": "",
        "opportunity_id": opportunity_id or "",
        "flow_node": flow_node or "",
        "skill_key": skill_key or "",
        "artifacts": [dict(item) for item in (artifacts or []) if isinstance(item, dict)],
        "deliverables": [],
        "steps": [],
    }


_LEAD_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role_key": {"type": "string"},
                    "task": {"type": "string"},
                },
                "required": ["role_key", "task"],
            },
        },
    },
    "required": ["assignments"],
}


def _lead_roster(config: dict) -> List[dict]:
    roster: List[dict] = []
    for colleague in _enabled_colleagues(config):
        role_key = str(colleague.get("role_key") or "")
        if not role_key:
            continue
        roster.append({
            "role_key": role_key,
            "name": colleague.get("name") or role_key,
            "capabilities": colleague.get("capabilities") or [],
            "tool_ids": colleague.get("tool_ids") or [],
            "dispatchable": colleague.get("dispatchable", True),
        })
    return roster


def _lead_fallback_steps(mission: dict, config: dict) -> List[dict]:
    lead_role_key = str(mission.get("lead_role_key") or _lead_role_key(config) or "")
    if not lead_role_key:
        return []
    prompt = str(mission.get("prompt") or "").strip()
    return [_make_step(mission.get("mission_id") or "", lead_role_key, prompt, config, 1)]


async def _plan_lead_steps(mission: dict, settings: dict) -> List[dict]:
    config = _config()
    lead_role_key = str(mission.get("lead_role_key") or _lead_role_key(config) or "")
    colleagues = _enabled_colleagues(config)
    enabled_keys = {str(c.get("role_key") or "") for c in colleagues if c.get("enabled", True)}
    prompt = str(mission.get("prompt") or "").strip()
    if not lead_role_key or not prompt or not enabled_keys:
        return _lead_fallback_steps(mission, config)

    lead = next((c for c in colleagues if c.get("role_key") == lead_role_key), None) or {}
    roster = _lead_roster(config)
    dispatch_rules = config.get("dispatch_rules") if isinstance(config.get("dispatch_rules"), list) else []
    messages = [
        {"role": "system", "content": str((lead or {}).get("system_prompt") or "")},
        {
            "role": "user",
            "content": (
                "任务目标：\n" + prompt +
                "\n\n团队列表：\n" + repr(roster) +
                "\n\n参考派发规则：\n" + repr(dispatch_rules) +
                "\n\n输出 JSON：{\"assignments\":[{\"role_key\":\"...\",\"task\":\"...\"}]}"
            ),
        },
    ]

    try:
        data = await llm_client.chat_json(
            messages,
            schema=_LEAD_PLAN_SCHEMA,
            model=lead.get("model_override") or None,
            timeout=20.0,
            max_attempts=1,
        )
    except Exception:
        logger.debug("lead mission planning failed; falling back to lead self execution", exc_info=True)
        return _lead_fallback_steps(mission, config)

    raw_assignments = data.get("assignments") if isinstance(data, dict) else None
    if not isinstance(raw_assignments, list):
        return _lead_fallback_steps(mission, config)

    valid: List[dict] = []
    seen: set = set()
    max_steps = max(1, int(settings.get("max_steps") or 8))
    for item in raw_assignments:
        if not isinstance(item, dict):
            continue
        role_key = str(item.get("role_key") or "").strip()
        task = str(item.get("task") or "").strip()
        if role_key not in enabled_keys or not task:
            continue
        dedupe_key = (role_key, task.casefold())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        valid.append({"role_key": role_key, "task": task})
        if len(valid) >= max_steps:
            break

    if not valid:
        return _lead_fallback_steps(mission, config)

    return [
        _make_step(
            mission.get("mission_id") or "",
            item["role_key"],
            item["task"],
            config,
            index + 1,
        )
        for index, item in enumerate(valid)
    ]


async def _emit_assignment(
    mission: dict,
    step: dict,
    status: str,
    assignment_status: str,
    activity: str,
    message: str = "",
    *,
    tool: Optional[str] = None,
    participants: Optional[list] = None,
    result_summary: str = "",
) -> None:
    await publish_office_event(
        step.get("role_key"),
        status,
        activity,
        message=message or step.get("task") or "",
        tool=tool,
        intent=step.get("intent"),
        zone=step.get("zone"),
        participants=participants,
        source="office_mission",
        mission_id=mission.get("mission_id"),
        assignment_id=step.get("assignment_id"),
        assignment_status=assignment_status,
        step_id=step.get("step_id"),
        task_id=step.get("assignment_id"),
        result_summary=result_summary,
    )


def _make_step_deliverables(step: dict, result_summary: str, settings: dict) -> List[dict]:
    role_key = step.get("role_key") or ""
    deliverable_type = (
        settings["collaboration_deliverable_type"]
        if step.get("collaboration")
        else settings["default_deliverable_type"]
    )
    return [{
        "type": deliverable_type,
        "title": step.get("task") or "任务产出",
        "content": result_summary or "",
        "created_at": _now_iso(),
        "created_by": role_key,
    }]


def _complete_step(step: dict, result_summary: str, settings: dict) -> None:
    step["assignment_status"] = "done"
    step["result_summary"] = result_summary or "步骤已完成"
    step["completed_at"] = _now_iso()
    step["completed_by"] = step.get("role_key") or ""
    step["deliverables"] = _make_step_deliverables(step, step["result_summary"], settings)


async def _run_step(mission: dict, step: dict, settings: dict) -> None:
    role_key = step.get("role_key") or ""
    participants = [str(item) for item in (step.get("participants") or []) if str(item)]
    event_status = str(step.get("status") or ("working" if not step.get("collaboration") else "meeting"))
    collaboration = bool(step.get("collaboration"))
    step["started_at"] = _now_iso()

    if collaboration and participants:
        for participant_key in participants:
            await _emit_assignment(
                mission,
                {**step, "role_key": participant_key},
                event_status,
                "routed",
                settings["collaboration_activity"],
                step.get("task") or "",
                participants=[role_key, *participants],
            )

    await _emit_assignment(
        mission,
        step,
        event_status,
        "routed",
        settings["collaboration_activity"] if collaboration else f"前往任务区域：{step.get('zone') or '工位'}",
        step.get("task") or "",
        participants=participants,
    )
    await asyncio.sleep(max(0.0, float(settings["route_delay_seconds"])))

    await _emit_assignment(
        mission,
        step,
        event_status,
        "active",
        settings["collaboration_activity"] if collaboration else "开始处理任务",
        step.get("task") or "",
        participants=participants,
    )
    if collaboration and participants:
        for participant_key in participants:
            await _emit_assignment(
                mission,
                {**step, "role_key": participant_key},
                event_status,
                "active",
                settings["collaboration_activity"],
                step.get("task") or "",
                participants=[role_key, *participants],
            )

    if collaboration:
        await asyncio.sleep(max(0.0, float(settings["work_delay_seconds"]) * 2))
        await _emit_assignment(
            mission,
            step,
            "done",
            "done",
            "协作讨论完成",
            step.get("task") or "",
            participants=participants,
            result_summary="已完成协作讨论",
        )
        for participant_key in participants:
            await _emit_assignment(
                mission,
                {**step, "role_key": participant_key},
                "done",
                "done",
                "协作讨论完成",
                step.get("task") or "",
                participants=[role_key, *participants],
                result_summary="已完成协作讨论",
            )
        _complete_step(step, "已完成协作讨论", settings)
        await asyncio.sleep(max(0.0, float(settings["done_delay_seconds"])))
        return

    async def _react_event_sink(payload: dict) -> None:
        sub = (payload or {}).get("sub") or {}
        await _emit_assignment(
            mission,
            step,
            "working",
            "active",
            sub.get("text") or "工具调用中",
            sub.get("text") or "",
            tool=sub.get("tool"),
        )

    result_summary = ""
    allowed = ai_colleague_service.colleague_tool_ids(role_key)
    try:
        if allowed is None or allowed:
            react = await run_react_loop(
                step.get("task") or "",
                {"enabled_tools": allowed} if allowed is not None else {},
                max_iterations=int(settings["max_iterations"]),
                system_prompt=str((ai_colleague_service.get_colleague(role_key) or {}).get("system_prompt") or ""),
                allowed_tool_ids=allowed,
                event_sink=_react_event_sink,
            )
            result_summary = (react.get("answer") or "").strip()[:240]
    except Exception:
        logger.exception("office mission step ReAct 执行失败: %s", role_key)
        result_summary = "任务编排已推进，业务工具执行失败"
    await asyncio.sleep(max(0.0, float(settings["work_delay_seconds"])))

    await _emit_assignment(
        mission,
        step,
        "done",
        "done",
        "任务步骤完成",
        result_summary or "步骤已完成",
        result_summary=result_summary,
    )
    _complete_step(step, result_summary or "步骤已完成", settings)
    await asyncio.sleep(max(0.0, float(settings["done_delay_seconds"])))

async def _run_mission(mission: dict, settings: dict) -> None:
    mission_id = mission.get("mission_id") or ""
    if mission_id in _DELETED_MISSIONS:
        return
    _CANCELLED_MISSIONS.discard(mission_id)
    mission["status"] = "running"
    mission["updated_at"] = _now_iso()
    _save_mission(mission)
    try:
        if mission.get("planning") and not mission.get("steps"):
            if mission_id in _DELETED_MISSIONS:
                return
            if mission_id in _CANCELLED_MISSIONS:
                mission["status"] = "cancelled"
                mission["planning"] = False
                mission["updated_at"] = _now_iso()
                _save_mission(mission)
                return
            lead_key = mission.get("lead_role_key") or mission.get("owner_role_key") or ""
            await publish_office_event(
                lead_key,
                "working",
                "Lead 正在拆解任务并分配",
                message=str(mission.get("prompt") or ""),
                source="office_mission",
                mission_id=mission_id,
            )
            mission["steps"] = await _plan_lead_steps(mission, settings)
            mission["planning"] = False
            mission["updated_at"] = _now_iso()
            _save_mission(mission)

        for step in mission.get("steps") or []:
            if mission_id in _DELETED_MISSIONS:
                return
            if mission_id in _CANCELLED_MISSIONS:
                step["assignment_status"] = "cancelled"
                step["result_summary"] = step.get("result_summary") or "任务已取消"
                continue
            step["assignment_status"] = "routed"
            await _run_step(mission, step, settings)
            if mission_id in _DELETED_MISSIONS:
                return
            step["assignment_status"] = "done"
            step["result_summary"] = step.get("result_summary") or "步骤已完成"
            mission["updated_at"] = _now_iso()
            _save_mission(mission)

        if mission_id in _DELETED_MISSIONS:
            return
        if mission_id in _CANCELLED_MISSIONS:
            mission["status"] = "cancelled"
        else:
            mission["status"] = "done"
            mission["completed_at"] = _now_iso()
            mission["completed_by"] = mission.get("owner_role_key") or ""
            raw_deliverables = [
                deliverable
                for step in mission.get("steps") or []
                for deliverable in (step.get("deliverables") or [])
            ]
            seen_deliverables: set = set()
            deduped_deliverables: List[dict] = []
            for deliverable in raw_deliverables:
                key = (
                    deliverable.get("type"),
                    deliverable.get("title"),
                    deliverable.get("content"),
                )
                if key in seen_deliverables:
                    continue
                seen_deliverables.add(key)
                deduped_deliverables.append(deliverable)
            mission["deliverables"] = deduped_deliverables
        mission["updated_at"] = _now_iso()
        _save_mission(mission)
    except asyncio.CancelledError:
        if mission_id in _DELETED_MISSIONS:
            raise
        mission["status"] = "cancelled"
        mission["updated_at"] = _now_iso()
        _save_mission(mission)
        raise
    except Exception:
        logger.exception("office mission runner 失败")
        mission["status"] = "failed"
        mission["updated_at"] = _now_iso()
        _save_mission(mission)

def create_mission(
    prompt: str,
    created_by: str = "user",
    owner_role_key: Optional[str] = None,
    priority: str = "medium",
    *,
    opportunity_id: Optional[str] = None,
    flow_node: Optional[str] = None,
    skill_key: Optional[str] = None,
    artifacts: Optional[List[dict]] = None,
) -> dict:
    config = _config()
    settings = _mission_settings(config)
    if not settings["enabled"]:
        return {"ok": False, "error": "任务指挥台未启用", "mission_id": "", "steps": []}
    planned = plan_mission(
        prompt,
        config,
        owner_role_key,
        priority,
        opportunity_id=opportunity_id,
        flow_node=flow_node,
        skill_key=skill_key,
        artifacts=artifacts,
    )
    if not planned.get("ok"):
        return planned
    planned["created_by"] = created_by or "user"
    planned["_max_missions"] = 100
    _save_mission(planned)
    task = asyncio.create_task(_run_mission(planned, settings))
    mission_id = str(planned.get("mission_id") or "")
    _MISSION_TASKS[mission_id] = task

    def _cleanup_mission_task(done_task: asyncio.Task) -> None:
        if _MISSION_TASKS.get(mission_id) is done_task:
            _MISSION_TASKS.pop(mission_id, None)

    task.add_done_callback(_cleanup_mission_task)
    return planned


def record_mission(
    prompt: str,
    created_by: str = "user",
    owner_role_key: Optional[str] = None,
    *,
    opportunity_id: Optional[str] = None,
    flow_node: Optional[str] = None,
    skill_key: Optional[str] = None,
    artifacts: Optional[List[dict]] = None,
    status: str = "done",
) -> dict:
    """写入一条已完成的 AI 产出任务记录，不启动后台执行器。

    用于 Skill 对话产出物直接落到 AI 办公室任务看板；业务数据仍存真实业务节点，
    这里只保存草稿视图所需的最小关联信息。
    """
    planned = plan_mission(
        prompt,
        _config(),
        owner_role_key,
        "medium",
        opportunity_id=opportunity_id,
        flow_node=flow_node,
        skill_key=skill_key,
        artifacts=artifacts,
    )
    planned["created_by"] = created_by or "user"
    planned["planning"] = False
    planned["status"] = status or "done"
    planned["completed_at"] = _now_iso()
    planned["completed_by"] = owner_role_key or ""
    planned["_max_missions"] = 100
    _save_mission(planned)
    return planned


def cancel_mission(mission_id: str) -> Optional[dict]:
    mission = get_mission(mission_id)
    if not mission:
        return None
    if mission.get("status") in ("done", "failed", "cancelled"):
        return {"ok": False, "error": "当前任务状态不可取消"}
    _CANCELLED_MISSIONS.add(mission_id)
    _cancel_mission_task(mission_id)
    mission["status"] = "cancelled"
    mission["updated_at"] = _now_iso()
    for step in mission.get("steps") or []:
        if step.get("assignment_status") not in ("done", "failed", "cancelled"):
            step["assignment_status"] = "cancelled"
            step["result_summary"] = step.get("result_summary") or "任务已取消"
    _save_mission(mission)
    return mission

def retry_mission(mission_id: str, created_by: str = "user") -> Optional[dict]:
    mission = get_mission(mission_id)
    if not mission:
        return None
    if mission.get("status") in ("queued", "running", "done", "cancelled"):
        return {"ok": False, "error": "仅失败任务可重试"}
    _CANCELLED_MISSIONS.discard(mission_id)
    prompt = str(mission.get("prompt") or "").strip()
    if not prompt:
        return None
    return create_mission(
        prompt,
        created_by or "user",
        mission.get("owner_role_key"),
        mission.get("priority") or "medium",
        opportunity_id=mission.get("opportunity_id") or None,
        flow_node=mission.get("flow_node") or None,
        skill_key=mission.get("skill_key") or None,
        artifacts=mission.get("artifacts") or [],
    )

def get_mission(mission_id: str) -> Optional[dict]:
    for mission in _load_missions():
        if mission.get("mission_id") == mission_id:
            return mission
    return None


def list_missions(limit: int = 50) -> List[dict]:
    missions = _load_missions()
    return missions[-max(1, min(int(limit or 50), 200)):]
def delete_mission(mission_id: str) -> bool:
    missions = _load_missions()
    next_missions = [m for m in missions if m.get("mission_id") != mission_id]
    if len(next_missions) == len(missions):
        return False
    _remove_mission_runtime(mission_id)
    _save_missions(next_missions)
    return True


def clear_missions(statuses: Optional[list] = None) -> int:
    if not statuses:
        statuses = _mission_settings(_config()).get("clear_statuses") or [
            "queued", "done", "failed", "cancelled"
        ]
    allowed = set(statuses)
    missions = _load_missions()
    next_missions: List[dict] = []
    for mission in missions:
        mission_id = mission.get("mission_id")
        if mission.get("status") in allowed:
            if mission_id:
                _remove_mission_runtime(str(mission_id))
            continue
        next_missions.append(mission)
    removed = len(missions) - len(next_missions)
    if removed:
        _save_missions(next_missions)
    return removed
