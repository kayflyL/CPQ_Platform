"""Config-driven LLM brain for AI office natural interactions.

The brain only runs when enabled in `behavior.brain`. It reads colleague
persona/memory from `system_config.ai_colleagues` and asks the configured LLM
to produce meeting summaries, task assignments and conclusions. No role names,
prompts or output copy are hardcoded in this module.
"""
from __future__ import annotations

import copy
import logging
import random
import time
from typing import Any, Dict, List, Optional

from app.api.ai_colleagues import _DEFAULT_BEHAVIOR_PROFILE
from app.services import llm_client
from app.services.office_memory import office_memory

logger = logging.getLogger(__name__)

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
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
        "conclusion": {"type": "string"},
    },
    "required": ["summary", "conclusion"],
}


async def generate_meeting_output(
    participants: List[str],
    context: Optional[Dict[str, Any]] = None,
    colleagues: Optional[List[dict]] = None,
    brain_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a structured meeting output, best-effort."""
    config = brain_config or {}
    if not config.get("enabled", False):
        return {}

    participant_keys = [str(item).strip() for item in participants if str(item).strip()]
    colleague_list = colleagues or []
    participant_colleagues = [
        colleague for colleague in colleague_list
        if (colleague or {}).get("role_key") in participant_keys
    ]
    if not participant_colleagues:
        return {}

    persona_lines: List[str] = []
    for colleague in participant_colleagues:
        role_key = colleague.get("role_key")
        persona = colleague.get("system_prompt") or "未配置"
        memory = office_memory.snapshot(role_key)
        facts = memory.get("facts") or {}
        last_status = facts.get("last_status") or "无"
        last_activity = facts.get("last_activity") or "无"
        persona_lines.append(
            f"- {role_key}：人设={persona}；最近状态={last_status}；最近活动={last_activity}"
        )

    context_lines: List[str] = []
    if context:
        if context.get("thread_id"):
            context_lines.append(f"线程：{context.get('thread_id')}")
        if context.get("opportunity_id"):
            context_lines.append(f"商机：{context.get('opportunity_id')}")
        if context.get("activity"):
            context_lines.append(f"触发活动：{context.get('activity')}")
    if not context_lines:
        context_lines.append("上下文：办公室协作事件")

    prompt = (
        "你是 CPQ 平台 AI 办公室的协作记录员。请根据以下 AI 同事的人设和最近状态，"
        "生成一次协作会议的简短记录。不要虚构业务数据；信息不足时保持概括。"
        "\n\n参与者：\n"
        + "\n".join(persona_lines)
        + "\n\n背景：\n"
        + "\n".join(context_lines)
        + "\n\n输出 JSON：summary、assignments、conclusion。assignments 只分配给参与者。"
    )

    messages = [{"role": "user", "content": prompt}]
    model_override = config.get("model_override") or None
    max_attempts = int(config.get("max_attempts") or 1)
    try:
        data = await llm_client.chat_json(
            messages,
            schema=_OUTPUT_SCHEMA,
            model=model_override,
            timeout=60.0,
            max_attempts=max_attempts,
        )
    except Exception:
        logger.debug("office brain LLM call failed", exc_info=True)
        return {}

    if not isinstance(data, dict):
        return {}
    assignments = data.get("assignments")
    if not isinstance(assignments, list):
        assignments = []
    cleaned_assignments: List[Dict[str, Any]] = []
    for item in assignments:
        if not isinstance(item, dict):
            continue
        role_key = str(item.get("role_key") or "").strip()
        task = str(item.get("task") or "").strip()
        if role_key and role_key in participant_keys and task:
            cleaned_assignments.append({"role_key": role_key, "task": task})

    return {
        "summary": str(data.get("summary") or "").strip(),
        "assignments": cleaned_assignments,
        "conclusion": str(data.get("conclusion") or "").strip(),
    }

_ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "intent": {"type": "string"},
        "zone": {"type": "string"},
        "activity": {"type": "string"},
        "message": {"type": "string"},
        "target_role_key": {"type": ["string", "null"]},
    },
    "required": ["status", "intent", "zone", "activity"],
}

_ALLOWED_ACTION_STATUSES = {"idle", "thinking", "working", "meeting", "public"}
_ALLOWED_ACTION_ZONES = {"desk_zone", "meeting_room", "public_zone"}
_ALLOWED_ACTION_INTENTS = {"work", "review", "move", "discuss", "meeting", "public", "wait"}

_DEFAULT_FALLBACK_ACTIONS = [
    {"status": "working", "intent": "work", "zone": "desk_zone", "activity": "整理方案资料", "message": ""},
    {"status": "thinking", "intent": "review", "zone": "desk_zone", "activity": "复盘近期商机", "message": ""},
    {"status": "working", "intent": "work", "zone": "desk_zone", "activity": "检查待办任务", "message": ""},
    {"status": "public", "intent": "move", "zone": "public_zone", "activity": "去公共区稍作休息", "message": ""},
]


def _autonomous_stable_hash(value: Any) -> int:
    import hashlib
    return int(hashlib.md5(str(value).encode("utf-8")).hexdigest(), 16)


def _autonomous_current_clock(timezone: str) -> str:
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        now = datetime.now(ZoneInfo(timezone or "Asia/Shanghai"))
    except (ZoneInfoNotFoundError, ValueError):
        from datetime import datetime
        now = datetime.now()
    return now.strftime("%H:%M")


def _autonomous_peer_keys(role_key: str, colleagues: List[dict]) -> List[str]:
    role_key = (role_key or "").strip()
    peers: List[str] = []
    for colleague in colleagues or []:
        if not isinstance(colleague, dict):
            continue
        peer = str(colleague.get("role_key") or "").strip()
        if peer and peer != role_key and peer not in peers:
            peers.append(peer)
    return peers


def _autonomous_allowed_zones(life_config: Dict[str, Any]) -> set:
    configured = life_config.get("allowed_zones")
    if isinstance(configured, list):
        zones = {str(zone).strip() for zone in configured if str(zone).strip()}
        if zones:
            return zones
    return set(_ALLOWED_ACTION_ZONES)


def _normalized_behavior_profile(colleague: Optional[dict]) -> Dict[str, Any]:
    default_profile = copy.deepcopy(_DEFAULT_BEHAVIOR_PROFILE)
    source = (colleague or {}).get("behavior_profile")
    if not isinstance(source, dict):
        return default_profile
    normalized = copy.deepcopy(default_profile)
    for key, value in source.items():
        if key in {"preferred_zones", "preferred_idle_actions"}:
            normalized[key] = copy.deepcopy(value) if isinstance(value, list) else copy.deepcopy(default_profile[key])
        elif key == "window_activity":
            normalized[key] = copy.deepcopy(value) if isinstance(value, dict) else copy.deepcopy(default_profile[key])
        else:
            normalized[key] = value
    return normalized


def _profile_fallback_action(
    role_key: str,
    colleague: Optional[dict],
    allowed_zones: set,
) -> Optional[Dict[str, Any]]:
    profile = _normalized_behavior_profile(colleague)
    if not profile.get("wander_enabled", True):
        return {
            "status": "working",
            "intent": "work",
            "zone": "desk_zone",
            "activity": "在工位处理工作",
            "message": "",
            "target_role_key": None,
        }
    preferred = [
        item for item in profile.get("preferred_zones") or []
        if isinstance(item, dict) and item.get("zone") in allowed_zones
    ]
    if not preferred:
        return None
    weights = []
    for item in preferred:
        try:
            weight = max(0, float(item.get("weight") or 0))
        except (TypeError, ValueError):
            weight = 0
        weights.append(weight)
    if sum(weights) <= 0:
        return None
    seed = _autonomous_stable_hash(role_key) + int(time.time() // 60)
    rng = random.Random(seed)
    chosen = rng.choices(preferred, weights=weights, k=1)[0]
    zone = str(chosen.get("zone") or "desk_zone").strip()
    activity = str(chosen.get("activity") or "").strip()
    if zone == "meeting_room":
        return {"status": "meeting", "intent": "meeting", "zone": zone, "activity": activity or "去会议室整理资料", "message": "", "target_role_key": None}
    if zone == "public_zone":
        return {"status": "public", "intent": "move", "zone": zone, "activity": activity or "去公共区看看", "message": "", "target_role_key": None}
    if zone == "desk_zone":
        return {"status": "working", "intent": "work", "zone": zone, "activity": activity or "在工位处理工作", "message": "", "target_role_key": None}
    return {"status": "thinking", "intent": "review", "zone": zone, "activity": activity or "去偏好区域", "message": "", "target_role_key": None}


def _autonomous_rule_action(
    role_key: str,
    colleague: Optional[dict],
    colleagues: List[dict],
    life_config: Dict[str, Any],
    office_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    import time as _time
    now = _time.time()
    latest = office_snapshot or {}
    current = latest.get(role_key) or {}
    current_zone = current.get("zone")
    peer_keys = _autonomous_peer_keys(role_key, colleagues)
    allowed_zones = _autonomous_allowed_zones(life_config)

    if current_zone in allowed_zones and current_zone != "desk_zone":
        return {
            "status": "thinking",
            "intent": "review",
            "zone": "desk_zone",
            "activity": "回到工位继续工作",
            "message": "",
            "target_role_key": None,
        }

    profile_action = _profile_fallback_action(role_key, colleague, allowed_zones)

    interaction_enabled = bool(life_config.get("interaction_enabled", True))
    if interaction_enabled and peer_keys:
        interaction_cooldown = max(60, int(life_config.get("interaction_cooldown_seconds") or 300))
        bucket = int(now // interaction_cooldown)
        seed = _autonomous_stable_hash(f"{role_key}:{bucket}")
        if seed % 4 == 0:
            target_role_key = peer_keys[seed % len(peer_keys)]
            interaction_action = life_config.get("interaction_action") or {}
            if not isinstance(interaction_action, dict):
                interaction_action = {}
            return {
                "status": interaction_action.get("status") or "meeting",
                "intent": interaction_action.get("intent") or "discuss",
                "zone": interaction_action.get("zone") or "meeting_room",
                "activity": interaction_action.get("activity") or "找同事简短沟通",
                "message": interaction_action.get("message") or "一起去会议室碰一下。",
                "target_role_key": target_role_key,
            }

    fallback = life_config.get("fallback_actions")
    if not isinstance(fallback, list) or not fallback:
        fallback = _DEFAULT_FALLBACK_ACTIONS
    valid_actions = [item for item in fallback if isinstance(item, dict)]
    if not valid_actions:
        valid_actions = _DEFAULT_FALLBACK_ACTIONS
    if profile_action:
        return profile_action
    index = (_autonomous_stable_hash(role_key) + int(now // 60)) % len(valid_actions)
    action = dict(valid_actions[index])
    action["target_role_key"] = None
    return action


def _autonomous_clean_action(
    data: Any,
    role_key: str,
    peer_keys: List[str],
    allowed_zones=None,
) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    status = str(data.get("status") or "thinking").strip().lower()
    if status not in _ALLOWED_ACTION_STATUSES:
        status = "thinking"
    intent = str(data.get("intent") or "work").strip().lower()
    if intent not in _ALLOWED_ACTION_INTENTS:
        intent = "work"
    zone_set = set(allowed_zones or _ALLOWED_ACTION_ZONES)
    default_zone = "desk_zone" if "desk_zone" in zone_set else next(iter(sorted(zone_set)), "desk_zone")
    zone = str(data.get("zone") or default_zone).strip()
    if zone not in zone_set:
        zone = default_zone
    activity = str(data.get("activity") or "").strip()
    if len(activity) > 80:
        activity = activity[:80]
    if not activity:
        activity = "自主处理工作"
    message = str(data.get("message") or "").strip()
    if len(message) > 240:
        message = message[:240]
    target_role_key = str(data.get("target_role_key") or "").strip()
    if target_role_key == role_key or target_role_key not in peer_keys:
        target_role_key = None
    if status == "meeting":
        zone = "meeting_room" if "meeting_room" in zone_set else default_zone
    if status == "public":
        zone = "public_zone" if "public_zone" in zone_set else default_zone
    return {
        "status": status,
        "intent": intent,
        "zone": zone,
        "activity": activity,
        "message": message,
        "target_role_key": target_role_key,
    }


async def generate_autonomous_action(
    role_key: str,
    colleagues: List[dict],
    *,
    brain_config: Optional[Dict[str, Any]] = None,
    life_config: Optional[Dict[str, Any]] = None,
    timezone: str = "Asia/Shanghai",
    office_snapshot: Optional[Dict[str, Any]] = None,
    use_llm: bool = False,
    raise_on_llm_error: bool = False,
) -> Dict[str, Any]:
    """Generate one config-driven autonomous action, best-effort."""
    life_config = life_config or {}
    peer_keys = _autonomous_peer_keys(role_key, colleagues)
    allowed_zones = _autonomous_allowed_zones(life_config)
    colleague = next(
        (item for item in (colleagues or []) if isinstance(item, dict) and item.get("role_key") == role_key),
        {},
    )
    if not use_llm:
        return _autonomous_clean_action(
            _autonomous_rule_action(role_key, colleague, colleagues, life_config, office_snapshot or {}),
            role_key,
            peer_keys,
            allowed_zones,
        )

    name = str(colleague.get("name") or role_key or "").strip() or role_key
    persona = str(colleague.get("system_prompt") or "未配置").strip()
    memory = office_memory.snapshot(role_key)
    facts = memory.get("facts") or {}
    recent_events = memory.get("recent_events") or []
    recent_all = office_memory.recent_all(20)

    recent_lines: List[str] = []
    for event in recent_events[-5:]:
        recent_lines.append(
            f"- {event.get('activity') or event.get('status') or ''} / {event.get('zone') or ''}"
        )
    recent_all_lines: List[str] = []
    for event in recent_all[-12:]:
        recent_all_lines.append(
            f"- {event.get('role_key')} {event.get('activity') or event.get('status') or ''} @ {event.get('zone') or ''}"
        )

    zones = sorted(allowed_zones)
    profile = _normalized_behavior_profile(colleague)
    profile_lines = [
        f"允许走动：{'是' if profile.get('wander_enabled', True) else '否'}",
        "偏好区域：" + "、".join(
            f"{item.get('zone')}(权重{item.get('weight')})" for item in profile.get("preferred_zones") or [] if isinstance(item, dict)
        ),
        "偏好空闲动作：" + "、".join(str(item) for item in profile.get("preferred_idle_actions") or []),
    ]

    prompt_lines = [
        "你是 CPQ 平台 AI 办公室中的一位数字同事。现在要决定你接下来很短时间内的自然行为。",
        "不要处理真实业务，也不要虚构业务数据；只给出一个简短的下一步动作。",
        f"当前时间：{_autonomous_current_clock(timezone)}",
        f"你的角色：{name}",
        f"人设：{persona}",
        f"最近状态：{facts.get('last_status') or '无'}",
        f"最近活动：{facts.get('last_activity') or '无'}",
        f"当前区域：{facts.get('last_zone') or '无'}",
        "可选区域：" + "、".join(str(zone) for zone in zones),
        "行为偏好：",
        *profile_lines,
        "最近个人事件：",
        *recent_lines,
        "办公室最近事件：",
        *recent_all_lines,
        "请输出 JSON：status（idle/thinking/working/meeting/public）、intent（work/review/move/discuss/meeting/public/wait）、zone、activity、message、target_role_key（可为 null）。",
    ]
    prompt = "\n".join(prompt_lines)

    messages = [
        {
            "role": "system",
            "content": (
                "你是 AI 办公室的自主行动决策器。输出必须保持简短、自然、安全；"
                "不要频繁发起会议，优先待在工位工作，偶尔去公共区或会议室。"
            ),
        },
        {"role": "user", "content": prompt},
    ]

    config = brain_config or {}
    model_override = config.get("model_override") or None
    max_attempts = int(config.get("max_attempts") or 1)
    try:
        data = await llm_client.chat_json(
            messages,
            schema=_ACTION_SCHEMA,
            model=model_override,
            temperature=0.7,
            timeout=30.0,
            max_attempts=max_attempts,
        )
    except Exception:
        logger.debug("office autonomous brain LLM call failed", exc_info=True)
        if raise_on_llm_error:
            raise
        return _autonomous_clean_action(
            _autonomous_rule_action(role_key, colleague, colleagues, life_config, office_snapshot or {}),
            role_key,
            peer_keys,
            allowed_zones,
        )

    return _autonomous_clean_action(data, role_key, peer_keys, allowed_zones)
