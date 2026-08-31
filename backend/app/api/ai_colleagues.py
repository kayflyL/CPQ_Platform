"""AI 同事配置 API。

AI 同事是角色化 AI 能力：总助 + 专业同事。
角色列表、人设、工具、入口、权限全部来自 system_config.ai_colleagues，
本 API 只负责读取和更新，不在代码中硬编码角色清单。
"""
from typing import Any, Optional
import copy

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user, require_perms, resolve_ws_user
from app.core.config import get_settings
from app.repository.feed_user_repo import FeedUserRepository
from app.repository.role_repo import RoleRepository
from app.repository.system_config_repo import SystemConfigRepository
from app.repository.skill_catalog_repo import SkillCatalogRepository
from app.services.agent_tool_specs import tool_required_data_sources
from app.services.ai_colleague_service import _canonical_data_source
from app.services.data_boundary import (
    apply_price_access,
    normalize_boundary,
    normalize_colleague,
)
from app.services.skill_registry import (
    DEFAULT_SKILL_BINDINGS as _DEFAULT_SKILL_BINDINGS,
)
from app.services.office_access import allowed_chat_role_keys

router = APIRouter(prefix="/api/ai-colleagues", tags=["ai-colleagues"])

require_ai_office_manage = require_perms("ai.office.manage")

_CONFIG_KEY = "ai_colleagues"

# 桌宠虚拟形象白名单：与 frontend/public/live2d/<key> 一一对应
PET_MODEL_KEYS = {"koharu", "hibiki", "shizuku", "nico", "izumi"}
DEFAULT_PET_MODEL = "koharu"


def _clamp_pet_model(colleague: dict) -> None:
    """形象 key 必须落在白名单；非法/缺省一律回落到默认形象，避免任意路径拼进 L2D 加载。"""
    if (colleague.get("pet_model") or "") not in PET_MODEL_KEYS:
        colleague["pet_model"] = DEFAULT_PET_MODEL


_DEFAULT_TEAM_META = {
    "name": "CPQ AI 团队",
    "description": "负责商机、选型、成本与报价的 AI 团队",
    "color": "#1677ff",
}

_DEFAULT_ACCESS_POLICY = {
    "enabled": True,
    "default_room_ids": ["default"],
    "role_room_map": {"member": ["default"]},
    "user_room_map": {},
    "default_chat_role_keys": ["assistant"],
    "role_chat_role_keys": {
        "business": ["assistant"],
        "te": ["support_engineer"],
        "cost": ["cost_analyst"],
        "quote": ["quote_specialist"],
        "member": ["assistant"],
    },
    "user_chat_role_keys": {},
}

_DEFAULT_ROOMS = [
    {
        "id": "default",
        "name": "全局办公室",
        "description": "所有 AI 同事",
        "color": "#1677ff",
        "role_keys": [],
    }
]

_DEFAULT_OFFICE = {
    "floor": {"width": 24, "depth": 16},
    "workspace": {"width": 44, "depth": 26},
    "zones": [
        {
            "id": "desk_zone",
            "type": "desk",
            "label": "工位区",
            "aliases": ["工位", "座位", "自己的座位"],
            "walk_target": "home",
            "slots": [
                {"id": "desk_1", "role_key": None, "position": {"x": -4.6, "z": -2.4}, "rotation_y": 0},
                {"id": "desk_2", "role_key": None, "position": {"x": 0.0, "z": -2.4}, "rotation_y": 0},
                {"id": "desk_3", "role_key": None, "position": {"x": 4.6, "z": -2.4}, "rotation_y": 0},
                {"id": "desk_4", "role_key": None, "position": {"x": -4.6, "z": 2.4}, "rotation_y": 0},
                {"id": "desk_5", "role_key": None, "position": {"x": 0.0, "z": 2.4}, "rotation_y": 0},
                {"id": "desk_6", "role_key": None, "position": {"x": 4.6, "z": 2.4}, "rotation_y": 0},
            ],
        },
        {
            "id": "meeting_room",
            "type": "meeting",
            "label": "会议室",
            "aliases": ["会议室", "会议区"],
            "walk_target": "meeting",
            "position": {"x": 18.5, "z": 0},
            "radius": 4.2,
            "capacity": 8,
            "width": 10.5,
            "depth": 6.2,
            "room": True,
            "door": {"side": "left", "offset": 0, "width": 1.4},
            "slots": [
                {"id": "meeting_1", "role_key": None, "position": {"x": 16.0, "z": 1.5}},
                {"id": "meeting_2", "role_key": None, "position": {"x": 17.6, "z": 1.5}},
                {"id": "meeting_3", "role_key": None, "position": {"x": 19.2, "z": 1.5}},
                {"id": "meeting_4", "role_key": None, "position": {"x": 20.8, "z": 1.5}},
                {"id": "meeting_5", "role_key": None, "position": {"x": 16.0, "z": -1.5}},
                {"id": "meeting_6", "role_key": None, "position": {"x": 17.6, "z": -1.5}},
                {"id": "meeting_7", "role_key": None, "position": {"x": 19.2, "z": -1.5}},
                {"id": "meeting_8", "role_key": None, "position": {"x": 20.8, "z": -1.5}},
            ],
        },
        {
            "id": "public_zone",
            "type": "public",
            "label": "办公室公共区",
            "aliases": ["办公室", "公共区", "办公区"],
            "walk_target": "center",
            "shape": "circle",
            "position": {"x": 0, "z": 0},
            "radius": 3.2,
            "slots": [],
        },
    ],
    "furniture_catalog": [
        {"type": "desk", "label": "办公桌", "category": "desk", "width": 1.75, "depth": 0.95, "height": 1.45, "rotatable": True},
        {"type": "office_chair", "label": "办公椅", "category": "chair", "width": 0.6, "depth": 0.62, "height": 1.1, "rotatable": True},
        {"type": "meeting_table", "label": "会议长桌", "category": "meeting", "width": 6.0, "depth": 1.4, "height": 0.72, "rotatable": True},
        {"type": "meeting_chair", "label": "会议椅", "category": "chair", "width": 0.55, "depth": 0.55, "height": 0.95, "rotatable": True},
        {"type": "plant", "label": "绿植", "category": "plant", "width": 0.55, "depth": 0.55, "height": 1.4, "rotatable": False},
        {"type": "bookshelf", "label": "书架", "category": "storage", "width": 1.4, "depth": 0.5, "height": 2.1, "rotatable": True},
        {"type": "coffee_bar", "label": "茶水吧台", "category": "storage", "width": 1.6, "depth": 0.72, "height": 1.3, "rotatable": True},
        {"type": "lounge_sofa", "label": "休息沙发", "category": "lounge", "width": 2.0, "depth": 0.9, "height": 0.9, "rotatable": True},
        {"type": "whiteboard", "label": "白板", "category": "meeting", "width": 2.1, "depth": 0.08, "height": 1.25, "rotatable": True},
        {"type": "art", "label": "装饰画", "category": "decor", "width": 0.95, "depth": 0.06, "height": 0.7, "rotatable": True}
    ],
    "furniture": [
        {"id": "plant_corner_bl", "type": "plant", "position": {"x": -10.8, "z": -6.8}, "rotation_y": 0},
        {"id": "plant_corner_br", "type": "plant", "position": {"x": 10.8, "z": -6.8}, "rotation_y": 0},
        {"id": "plant_corner_tl", "type": "plant", "position": {"x": -10.8, "z": 6.8}, "rotation_y": 0},
        {"id": "plant_corner_tr", "type": "plant", "position": {"x": 10.8, "z": 6.8}, "rotation_y": 0},
        {"id": "bookshelf_left_back", "type": "bookshelf", "position": {"x": -11.0, "z": -2.6}, "rotation_y": 0},
        {"id": "bookshelf_left_front", "type": "bookshelf", "position": {"x": -11.0, "z": 2.6}, "rotation_y": 0},
        {"id": "coffee_bar_right", "type": "coffee_bar", "position": {"x": 11.0, "z": 3.1}, "rotation_y": -1.57079632679},
        {"id": "lounge_sofa_right", "type": "lounge_sofa", "position": {"x": 10.5, "z": -4.2}, "rotation_y": -1.57079632679},
        {"id": "whiteboard_meeting", "type": "whiteboard", "position": {"x": 18.5, "z": -2.85}, "rotation_y": 0},
        {"id": "art_meeting", "type": "art", "position": {"x": 23.4, "z": 0}, "rotation_y": 1.57079632679}
    ],
    "status_zone_map": {
        "working": "desk_zone",
        "thinking": "desk_zone",
        "waiting_input": "desk_zone",
        "done": "desk_zone",
        "idle": "desk_zone",
        "meeting": "meeting_room",
    "public": "public_zone",
        "error": "desk_zone",
    },
    "character_models": [
        "/models/ai-colleagues/kenney-mini/character-male-a.glb",
        "/models/ai-colleagues/kenney-mini/character-female-a.glb",
        "/models/ai-colleagues/kenney-mini/character-male-b.glb",
        "/models/ai-colleagues/kenney-mini/character-female-b.glb",
        "/models/ai-colleagues/kenney-mini/character-male-c.glb",
        "/models/ai-colleagues/kenney-mini/character-female-c.glb",
    ],
}

_DEFAULT_MEETING_ZONE = copy.deepcopy(_DEFAULT_OFFICE["zones"][1])
_DEFAULT_PUBLIC_ZONE = copy.deepcopy(_DEFAULT_OFFICE["zones"][2])

_DEFAULT_BEHAVIOR = {
    "status_meta": {
        "idle": {"label": "空闲", "color": "#9aa4b2", "monitor_active": False, "indicator_opacity": 0.9, "animation": "idle"},
        "thinking": {"label": "思考中", "color": "#1677ff", "monitor_active": True, "indicator_opacity": 0.9, "animation": "working"},
        "working": {"label": "工作中", "color": "#1677ff", "monitor_active": True, "indicator_opacity": 0.9, "animation": "working"},
        "waiting_input": {"label": "等待输入", "color": "#fa8c16", "monitor_active": False, "indicator_opacity": 0.9, "animation": "waiting"},
        "done": {"label": "已完成", "color": "#52c9a0", "monitor_active": False, "indicator_opacity": 0.9, "animation": "done"},
        "error": {"label": "异常", "color": "#ff4d4f", "monitor_active": False, "indicator_opacity": 0.95, "animation": "error"},
        "meeting": {"label": "协作中", "color": "#9254de", "monitor_active": False, "indicator_opacity": 0.9, "animation": "meeting"},
        "public": {"label": "公共区", "color": "#13c2c2", "monitor_active": False, "indicator_opacity": 0.9, "animation": "idle"},
    },
    "mission": {
        "enabled": True,
        "owner_role_key": "assistant",
        "max_steps": 8,
        "max_iterations": 4,
        "route_delay_seconds": 1.2,
        "work_delay_seconds": 2.5,
        "done_delay_seconds": 0.8,
        "default_intent": "work",
        "assignment_action_map": {
            "queued": "sit_idle",
            "routed": "walk_to_target",
            "active": "work_at_target",
            "blocked": "walk_to_helper",
            "done": "return_to_desk",
            "failed": "show_error",
            "cancelled": "return_to_desk"
        }
    },
    "collaboration_rules": [
        {"when": "same_thread_id", "min_members": 2, "zone": "meeting_room", "status": "meeting", "intent": "meeting", "activity": "进入协作讨论", "cooldown_seconds": 300}
    ],
    "brain": {
        "enabled": False,
        "model_override": None,
        "max_attempts": 1,
        "generate_summary": True,
        "generate_assignments": True,
        "generate_conclusion": True
    },
    "autonomous": {
        "enabled": True,
        "tick_seconds": 10,
        "timezone": "Asia/Shanghai",
        "life": {
            "enabled": True,
            "max_actions_per_tick": 1,
            "cooldown_seconds": 20,
            "llm_enabled": False,
            "llm_budget_per_hour": 0,
            "llm_min_interval_seconds": 180,
            "llm_timeout_seconds": 12.0,
            "llm_backoff_seconds": 300,
            "interaction_enabled": True,
            "interaction_cooldown_seconds": 300,
            "allowed_zones": ["desk_zone", "meeting_room", "public_zone"],
            "active_statuses": ["working", "meeting", "waiting_input", "error"],
            "fallback_actions": [
                {"status": "working", "intent": "work", "zone": "desk_zone", "activity": "整理方案资料", "message": ""},
                {"status": "thinking", "intent": "review", "zone": "desk_zone", "activity": "复盘近期商机", "message": ""},
                {"status": "working", "intent": "work", "zone": "desk_zone", "activity": "检查待办任务", "message": ""},
                {"status": "public", "intent": "move", "zone": "public_zone", "activity": "去公共区稍作休息", "message": ""}
            ],
            "interaction_action": {
                "status": "meeting",
                "intent": "discuss",
                "zone": "meeting_room",
                "activity": "找同事简短沟通",
                "message": "一起去会议室碰一下。"
            }
        },
        "idle": {
            "enabled": True,
            "after_seconds": 600,
            "status": "thinking",
            "intent": "review_pending_tasks",
            "activity": "自主检查待办",
            "zone": "desk_zone"
        },
        "schedule_rules": [
            {
                "id": "morning_sync",
                "time": "09:00",
                "status": "meeting",
                "intent": "morning_sync",
                "activity": "参加晨会同步",
                "zone": "meeting_room",
                "roles": []
            },
            {
                "id": "wrap_up",
                "time": "18:00",
                "status": "done",
                "intent": "wrap_up",
                "activity": "整理今日工作",
                "zone": "desk_zone",
                "roles": []
            }
        ]
    },
}

_DEFAULT_BEHAVIOR_PROFILE = {
    "wander_enabled": True,
    "min_idle_seconds": 8,
    "max_idle_seconds": 20,
    "preferred_zones": [
        {"zone": "desk_zone", "weight": 55, "activity": "在工位整理工作"},
        {"zone": "public_zone", "weight": 30, "activity": "去公共区看看"},
        {"zone": "meeting_room", "weight": 15, "activity": "去会议室整理资料"},
    ],
    "preferred_idle_actions": ["sit_idle", "look_around", "check_notes"],
    "window_activity": {"enabled": False, "zone": "public_zone", "activity": "看看窗外"},
}

_DEFAULT_LAYOUT = {
    "nodes": [],
    "edges": [],
    "office": copy.deepcopy(_DEFAULT_OFFICE),
}



def _skill_runtime(skill: dict) -> Optional[dict]:
    if not isinstance(skill, dict):
        return None
    runtime = skill.get("runtime")
    if isinstance(runtime, dict) and runtime:
        return runtime
    skill_key = str(skill.get("key") or "").strip()
    skill_type = str(skill.get("type") or "").strip()
    workflow_key = str(skill.get("workflow_key") or "").strip()
    if skill_key and (skill_type == "workflow" or workflow_key):
        return {
            "name": str(skill.get("name") or skill_key).strip() or skill_key,
            "input_hint": str(skill.get("input_contract") or "").strip(),
        }
    return None


def _find_skill(skill_key: str) -> Optional[dict]:
    repo = SkillCatalogRepository()
    try:
        return repo.get(skill_key)
    except Exception:
        return None
    finally:
        repo.close()


class ColleagueUpdate(BaseModel):
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    color: Optional[str] = None
    enabled: Optional[bool] = None
    system_prompt: Optional[str] = None
    opening_message: Optional[str] = None
    response_style: Optional[str] = None
    response_profile: Optional[dict] = None
    model_override: Optional[str] = None
    tool_ids: Optional[list] = None
    data_sources: Optional[list] = None
    dispatchable: Optional[bool] = None
    price_access: Optional[bool] = None
    data_boundary: Optional[dict] = None
    capabilities: Optional[list] = None
    behavior_profile: Optional[dict] = None
    relations: Optional[dict] = None
    skills: Optional[list] = None
    memory_policy: Optional[dict] = None
    pet_model: Optional[str] = None


class ColleagueCreate(ColleagueUpdate):
    role_key: str


class DispatchConfigUpdate(BaseModel):
    dispatch_enabled: Optional[bool] = None
    dispatch_rules: Optional[list] = None


class TeamMetaUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None


class RoomUpdate(BaseModel):
    rooms: Optional[list] = None


class AccessPolicyUpdate(BaseModel):
    enabled: Optional[bool] = None
    default_room_ids: Optional[list] = None
    role_room_map: Optional[dict] = None
    user_room_map: Optional[dict] = None
    default_chat_role_keys: Optional[list] = None
    role_chat_role_keys: Optional[dict] = None
    user_chat_role_keys: Optional[dict] = None


class LayoutUpdate(BaseModel):
    nodes: Optional[list] = None
    edges: Optional[list] = None
    office: Optional[dict] = None
    lead_role_key: Optional[str] = None


class BehaviorUpdate(BaseModel):
    behavior: Optional[dict] = None


class SkillUpsert(BaseModel):
    key: str
    id: Optional[str] = None
    type: Optional[str] = "tool_prompt"
    workflow_key: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    tool_ids: Optional[list] = None
    hit_count: Optional[int] = None
    input_contract: Optional[str] = None
    output_contract: Optional[str] = None
    output_kind: Optional[str] = None


def _migrate_office_layout(office: dict) -> None:
    """Upgrade legacy office layout with configurable zone aliases and arrival targets."""
    zones = office.get("zones")
    if not isinstance(zones, list):
        zones = []
        office["zones"] = zones

    zone_defaults = {
        "desk_zone": {
            "aliases": ["工位", "座位", "自己的座位"],
            "walk_target": "home",
        },
        "meeting_room": {
            "aliases": ["会议室", "会议区"],
            "walk_target": "meeting",
        },
        "public_zone": {
            "aliases": ["办公室", "公共区", "办公区"],
            "walk_target": "center",
            "shape": "circle",
        },
    }

    for index, zone in enumerate(zones):
        if not isinstance(zone, dict):
            continue
        if zone.get("id") == "meeting_room":
            needs_upgrade = (
                not isinstance(zone.get("door"), dict)
                or float(zone.get("width") or 0) < 10
                or float(zone.get("depth") or 0) < 6
                or float(zone.get("radius") or 0) < 4
            )
            if needs_upgrade:
                zones[index] = copy.deepcopy(_DEFAULT_MEETING_ZONE)
        defaults = zone_defaults.get(zone.get("id"))
        if defaults:
            for key, value in defaults.items():
                zone.setdefault(key, copy.deepcopy(value))

    if not any(isinstance(zone, dict) and zone.get("id") == "public_zone" for zone in zones):
        zones.append(copy.deepcopy(_DEFAULT_PUBLIC_ZONE))

    status_zone_map = office.setdefault("status_zone_map", {})
    if isinstance(status_zone_map, dict):
        status_zone_map.setdefault("public", "public_zone")


def _normalize_behavior_profile(profile: Any) -> dict:
    default_profile = copy.deepcopy(_DEFAULT_BEHAVIOR_PROFILE)
    if not isinstance(profile, dict):
        return default_profile
    normalized = copy.deepcopy(default_profile)
    normalized.update(profile)
    preferred_zones = profile.get("preferred_zones")
    if not isinstance(preferred_zones, list):
        preferred_zones = copy.deepcopy(default_profile["preferred_zones"])
    normalized["preferred_zones"] = [
        {**item, "zone": str(item.get("zone") or "").strip()} if isinstance(item, dict) else item
        for item in preferred_zones
    ]
    if not isinstance(normalized.get("preferred_idle_actions"), list):
        normalized["preferred_idle_actions"] = copy.deepcopy(default_profile["preferred_idle_actions"])
    if not isinstance(normalized.get("window_activity"), dict):
        normalized["window_activity"] = copy.deepcopy(default_profile["window_activity"])
    return normalized


def _migrate_colleague_legacy(colleague: dict) -> bool:
    changed = False
    persona = colleague.get("persona")
    if isinstance(persona, str) and persona.strip():
        system_prompt = colleague.get("system_prompt")
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            colleague["system_prompt"] = persona.strip()
            changed = True
    if "persona" in colleague:
        colleague.pop("persona", None)
        changed = True

    profile = _normalize_behavior_profile(colleague.get("behavior_profile"))
    if not isinstance(colleague.get("behavior_profile"), dict):
        changed = True
    legacy_preferred_zone = str(colleague.get("preferred_zone") or "").strip()
    if legacy_preferred_zone:
        existing = next((item for item in profile["preferred_zones"] if isinstance(item, dict) and item.get("zone") == legacy_preferred_zone), None)
        if existing:
            profile["preferred_zones"].remove(existing)
            existing["weight"] = max(int(existing.get("weight") or 0), 70)
            profile["preferred_zones"].insert(0, existing)
        else:
            profile["preferred_zones"].insert(0, {"zone": legacy_preferred_zone, "weight": 70, "activity": "去偏好区域"})
    legacy_meeting_zone = str(colleague.get("meeting_zone") or "").strip()
    if legacy_meeting_zone:
        existing = next((item for item in profile["preferred_zones"] if isinstance(item, dict) and item.get("zone") == legacy_meeting_zone), None)
        if existing:
            existing["weight"] = max(int(existing.get("weight") or 0), 20)
        else:
            profile["preferred_zones"].append({"zone": legacy_meeting_zone, "weight": 20, "activity": "去会议室"})
    if "preferred_zone" in colleague or "meeting_zone" in colleague:
        changed = True
    colleague.pop("preferred_zone", None)
    colleague.pop("meeting_zone", None)
    colleague["behavior_profile"] = profile
    return changed


def _read_config(repo: SystemConfigRepository) -> dict:
    value = repo.get_value(_CONFIG_KEY, {}) or {}
    if isinstance(value, list):
        return {
            "version": 1,
            "colleagues": value,
            "team_meta": dict(_DEFAULT_TEAM_META),
            "layout": dict(_DEFAULT_LAYOUT),
        }
    if not isinstance(value, dict):
        return {
            "version": 1,
            "colleagues": [],
            "team_meta": dict(_DEFAULT_TEAM_META),
            "layout": dict(_DEFAULT_LAYOUT),
        }
    cfg = dict(value)
    if not isinstance(cfg.get("colleagues"), list):
        cfg["colleagues"] = []
    config_changed = False
    cfg_version = int(cfg.get("version") or 1)
    if cfg_version < 2:
        for colleague in cfg.get("colleagues", []):
            if not isinstance(colleague, dict):
                continue
            role_key = str(colleague.get("role_key") or "").strip()
            refs = colleague.get("skills")
            if isinstance(refs, list) and refs:
                continue
            defaults = _DEFAULT_SKILL_BINDINGS.get(role_key)
            if defaults:
                colleague["skills"] = list(defaults)
                config_changed = True
        cfg["version"] = 2
        config_changed = True
    for colleague in cfg.get("colleagues", []):
        if isinstance(colleague, dict):
            if _migrate_colleague_legacy(colleague):
                config_changed = True
            for key, default_value in _default_colleague(colleague.get("role_key", "")).items():
                if key not in colleague:
                    colleague[key] = copy.deepcopy(default_value)
                    config_changed = True
            # 数据边界读侧归一化：price_access 永远是派生值（单一事实源=masked_fields）
            normalize_colleague(colleague)
    if not isinstance(cfg.get("team_meta"), dict):
        cfg["team_meta"] = dict(_DEFAULT_TEAM_META)
    if not isinstance(cfg.get("protected_role_keys"), list):
        cfg["protected_role_keys"] = []
    if not isinstance(cfg.get("access_policy"), dict):
        cfg["access_policy"] = copy.deepcopy(_DEFAULT_ACCESS_POLICY)
    if not isinstance(cfg.get("rooms"), list) or not cfg.get("rooms"):
        cfg["rooms"] = copy.deepcopy(_DEFAULT_ROOMS)
    for room in cfg["rooms"]:
        if not isinstance(room, dict):
            continue
        room.setdefault("id", "default")
        room.setdefault("name", "全局办公室")
        room.setdefault("description", "")
        room.setdefault("color", "#1677ff")
        room.setdefault("role_keys", [])
    if not isinstance(cfg.get("layout"), dict):
        cfg["layout"] = copy.deepcopy(_DEFAULT_LAYOUT)
    if not isinstance(cfg["layout"].get("office"), dict):
        cfg["layout"]["office"] = copy.deepcopy(_DEFAULT_OFFICE)
    office = cfg["layout"]["office"]
    for key, default_value in _DEFAULT_OFFICE.items():
        if key not in office:
            office[key] = copy.deepcopy(default_value)
    _migrate_office_layout(office)
    colleague_keys = {c.get("role_key") for c in (cfg.get("colleagues") or []) if isinstance(c, dict) and c.get("role_key")}
    team_graph = cfg["layout"].get("team_graph")
    if not isinstance(team_graph, dict):
        team_graph = {}
        cfg["layout"]["team_graph"] = team_graph
    team_graph.setdefault("subagent_role_keys", [])
    if not team_graph.get("lead_role_key") and "assistant" in colleague_keys:
        team_graph["lead_role_key"] = "assistant"
    if not isinstance(cfg.get("behavior"), dict):
        cfg["behavior"] = copy.deepcopy(_DEFAULT_BEHAVIOR)
    behavior = cfg["behavior"]
    for key, default_value in _DEFAULT_BEHAVIOR.items():
        if key not in behavior:
            behavior[key] = copy.deepcopy(default_value)
            config_changed = True
    default_autonomous = _DEFAULT_BEHAVIOR.get("autonomous") or {}
    autonomous = behavior.get("autonomous")
    if not isinstance(autonomous, dict):
        behavior["autonomous"] = copy.deepcopy(default_autonomous)
    else:
        for key, default_value in default_autonomous.items():
            if key not in autonomous:
                autonomous[key] = copy.deepcopy(default_value)
                config_changed = True
        default_life = default_autonomous.get("life") or {}
        life = autonomous.get("life")
        if not isinstance(life, dict):
            autonomous["life"] = copy.deepcopy(default_life)
        else:
            if "llm_budget_per_hour" not in life and life.get("llm_enabled") is True:
                life["llm_enabled"] = False
                config_changed = True
            for key, default_value in default_life.items():
                if key not in life:
                    life[key] = copy.deepcopy(default_value)
                    config_changed = True
    if config_changed:
        _write_config(repo, cfg)
    return cfg


def _write_config(repo: SystemConfigRepository, config: dict) -> None:
    repo.set(_CONFIG_KEY, config, "json",
             "AI 同事配置（角色/人设/工具/入口/权限/团队/布局）", "admin")


def _default_colleague(role_key: str) -> dict:
    return {
        "role_key": role_key,
        "name": role_key,
        "color": "#1677ff",
        "avatar_url": "",
        "pet_model": DEFAULT_PET_MODEL,
        "enabled": True,
        "system_prompt": "",
        "opening_message": "",
        "response_style": "detailed",
        "response_profile": {
            "style": "detailed",
            "max_tokens": None,
            "temperature": None,
            "style_prompt": "",
        },
        "model_override": None,
        "tool_ids": [],
        "data_sources": [],
        "dispatchable": True,
        "capabilities": [],
        "behavior_profile": copy.deepcopy(_DEFAULT_BEHAVIOR_PROFILE),
        "memory_policy": {
            "enabled": True,
            "short_term_max_turns": 12,
            "query_recent": 6,
            "save_after_turn": True,
            "auto_memory": True,
        },
        "relations": {
            "team_role": "",
            "reports_to": "",
        },
        "skills": [],
    }


def _full_colleague_config(cfg: dict) -> dict:
    """Admin-only full AI colleague config, used by Manage Teams."""
    return {
        "colleagues": list(cfg.get("colleagues", []) or []),
        "dispatch_enabled": cfg.get("dispatch_enabled", True),
        "dispatch_rules": cfg.get("dispatch_rules", []),
        "team_meta": cfg.get("team_meta", dict(_DEFAULT_TEAM_META)),
        "protected_role_keys": cfg.get("protected_role_keys", []),
        "access_policy": cfg.get("access_policy", copy.deepcopy(_DEFAULT_ACCESS_POLICY)),
        "rooms": cfg.get("rooms", copy.deepcopy(_DEFAULT_ROOMS)),
        "layout": cfg.get("layout", copy.deepcopy(_DEFAULT_LAYOUT)),
        "behavior": cfg.get("behavior", copy.deepcopy(_DEFAULT_BEHAVIOR)),
    }


@router.get("/scope-options")
def scope_options(manager: dict = Depends(require_ai_office_manage)):
    """作用域注册表：数据来源 / 页面职责的中文预设。"""
    from app.services.ai_colleague_service import get_scope_catalog
    return get_scope_catalog()


@router.get("/admin-config")
def admin_config(manager: dict = Depends(require_ai_office_manage)):
    repo = SystemConfigRepository()
    try:
        cfg = _read_config(repo)
        return _full_colleague_config(cfg)
    finally:
        repo.close()


@router.get("/manage-roles")
def manage_roles(manager: dict = Depends(require_ai_office_manage)):
    """Scoped RBAC role list used by TeamManager's role -> AI role dropdown."""
    repo = RoleRepository()
    try:
        roles = [
            {
                "role_key": role.get("role_key") or "",
                "name": role.get("name") or role.get("role_key") or "",
            }
            for role in repo.list_all()
        ]
        return {"roles": roles}
    finally:
        repo.close()


@router.get("/manage-users")
def manage_users(manager: dict = Depends(require_ai_office_manage)):
    """Scoped user list for AI Office access-policy exceptions.

    Uses the same ai.office.manage permission as TeamManager, so delegated
    office managers do not need full user-management admin access.
    """
    repo = FeedUserRepository()
    try:
        users = [
            {
                "user_id": str(user.get("user_id") or ""),
                "name": user.get("name") or "",
                "role": user.get("role") or "member",
                "is_active": bool(user.get("is_active", True)),
            }
            for user in repo.list_all()
        ]
        return {"users": users}
    finally:
        repo.close()


@router.get("/")
def list_colleagues(user: dict = Depends(get_current_user)):
    repo = SystemConfigRepository()
    try:
        cfg = _read_config(repo)
        colleagues = list(cfg.get("colleagues", []) or [])
        allowed = allowed_chat_role_keys(user)
        if allowed is not None:
            allowed_set = set(allowed)
            colleagues = [
                colleague for colleague in colleagues
                if (colleague or {}).get("role_key") in allowed_set
                or (colleague or {}).get("role_key") == "unknown"
            ]
        return {
            "colleagues": colleagues,
            "team_meta": cfg.get("team_meta", dict(_DEFAULT_TEAM_META)),
            "rooms": cfg.get("rooms", copy.deepcopy(_DEFAULT_ROOMS)),
            "layout": cfg.get("layout", copy.deepcopy(_DEFAULT_LAYOUT)),
            "behavior": cfg.get("behavior", copy.deepcopy(_DEFAULT_BEHAVIOR)),
        }
    finally:
        repo.close()


@router.post("/")
def create_colleague(data: ColleagueCreate, manager: dict = Depends(require_ai_office_manage)):
    repo = SystemConfigRepository()
    try:
        cfg = _read_config(repo)
        role_key = (data.role_key or "").strip()
        if not role_key:
            raise HTTPException(status_code=400, detail="role_key 不能为空")
        colleagues = cfg.get("colleagues") or []
        if any((c or {}).get("role_key") == role_key for c in colleagues):
            raise HTTPException(status_code=409, detail=f"AI 同事 '{role_key}' 已存在")
        patch = data.model_dump(exclude_unset=True)
        patch.pop("role_key", None)
        bool_flag = patch.pop("price_access", None)
        raw_boundary = patch.pop("data_boundary", None)
        colleague = _default_colleague(role_key)
        colleague.update({k: v for k, v in patch.items() if v is not None})
        # 新同事默认拒绝（不能靠 _default_colleague 的默认回填——那会给存量同事
        # 抢先塞 deny_all，把旧 price_access=True 的懒迁移顶掉）
        colleague.setdefault("data_boundary", {"mode": "deny_all", "schemas": [],
                                               "tables_allow": [], "masked_fields": ["price"]})
        if isinstance(raw_boundary, dict):
            colleague["data_boundary"] = normalize_boundary({"data_boundary": raw_boundary})
        elif bool_flag is not None:
            colleague["data_boundary"] = apply_price_access(colleague.get("data_boundary") or {}, bool(bool_flag))
        if "skills" in patch or "tool_ids" in patch:
            colleague = _merge_skill_data_sources(colleague)
        _clamp_pet_model(colleague)
        normalize_colleague(colleague)
        cfg["colleagues"] = colleagues + [colleague]
        _write_config(repo, cfg)
        return colleague
    finally:
        repo.close()


@router.put("/dispatch")
def update_dispatch(data: DispatchConfigUpdate, manager: dict = Depends(require_ai_office_manage)):
    repo = SystemConfigRepository()
    try:
        cfg = _read_config(repo)
        patch = data.model_dump(exclude_unset=True)
        cfg.update(patch)
        _write_config(repo, cfg)
        return {
            "dispatch_enabled": cfg.get("dispatch_enabled", True),
            "dispatch_rules": cfg.get("dispatch_rules", []),
        }
    finally:
        repo.close()


@router.put("/team-meta")
def update_team_meta(data: TeamMetaUpdate, manager: dict = Depends(require_ai_office_manage)):
    repo = SystemConfigRepository()
    try:
        cfg = _read_config(repo)
        patch = data.model_dump(exclude_unset=True)
        team_meta = dict(cfg.get("team_meta") or {})
        team_meta.update({k: v for k, v in patch.items() if v is not None})
        cfg["team_meta"] = team_meta
        _write_config(repo, cfg)
        return {"team_meta": team_meta}
    finally:
        repo.close()


@router.put("/access-policy")
def update_access_policy(data: AccessPolicyUpdate, manager: dict = Depends(require_ai_office_manage)):
    repo = SystemConfigRepository()
    try:
        cfg = _read_config(repo)
        policy = dict(cfg.get("access_policy") or {})
        patch = data.model_dump(exclude_unset=True)
        for key, value in patch.items():
            if value is not None:
                policy[key] = value
        cfg["access_policy"] = policy
        _write_config(repo, cfg)
        return {"access_policy": policy}
    finally:
        repo.close()


@router.put("/rooms")
def update_rooms(data: RoomUpdate, manager: dict = Depends(require_ai_office_manage)):
    repo = SystemConfigRepository()
    try:
        if not isinstance(data.rooms, list) or not data.rooms:
            raise HTTPException(status_code=400, detail="rooms 不能为空")
        cfg = _read_config(repo)
        cfg["rooms"] = data.rooms
        _write_config(repo, cfg)
        return {"rooms": cfg["rooms"]}
    finally:
        repo.close()


def _sync_team_graph(cfg: dict, layout: dict, edges: list, lead_role_key_override: Optional[str] = None) -> None:
    """将画布连线映射为 team_graph 并同步到同事 relations 配置。

    不写死任何角色：只根据 user/agent 连线的拓扑推断 lead 与 subagent。
    """
    colleague_keys = {c.get("role_key") for c in (cfg.get("colleagues") or []) if isinstance(c, dict) and c.get("role_key")}
    clean_edges = [e for e in (edges or []) if isinstance(e, dict)]
    user_edges = [e for e in clean_edges if e.get("source") == "user"]
    lead_role_key = lead_role_key_override if lead_role_key_override in colleague_keys else None
    if not lead_role_key and "assistant" in colleague_keys:
        lead_role_key = "assistant"
    if not lead_role_key:
        lead_role_key = next((e.get("target") for e in user_edges if e.get("target") in colleague_keys), None)
    if not lead_role_key:
        sources = {e.get("source") for e in clean_edges if e.get("source") in colleague_keys}
        targets = {e.get("target") for e in clean_edges if e.get("target") in colleague_keys}
        candidates = sorted(sources - targets)
        lead_role_key = candidates[0] if candidates else (sorted(sources)[0] if sources else None)
    subagent_role_keys = [
        e.get("target")
        for e in clean_edges
        if e.get("source") == lead_role_key and e.get("target") in colleague_keys
    ]
    layout["team_graph"] = {
        "lead_role_key": lead_role_key,
        "subagent_role_keys": subagent_role_keys,
    }
    colleagues = cfg.get("colleagues") or []
    for colleague in colleagues:
        if not isinstance(colleague, dict):
            continue
        role_key = colleague.get("role_key")
        if role_key not in colleague_keys:
            continue
        relations = colleague.get("relations")
        if not isinstance(relations, dict):
            relations = {}
        if role_key == lead_role_key:
            relations["team_role"] = "lead"
            relations.pop("reports_to", None)
        elif role_key in subagent_role_keys:
            relations["team_role"] = "subagent"
            relations["reports_to"] = lead_role_key
        else:
            relations.setdefault("team_role", "member")
        colleague["relations"] = relations


@router.put("/layout")
def update_layout(data: LayoutUpdate, manager: dict = Depends(require_ai_office_manage)):
    repo = SystemConfigRepository()
    try:
        cfg = _read_config(repo)
        patch = data.model_dump(exclude_unset=True)
        layout = dict(cfg.get("layout") or {})
        if patch.get("nodes") is not None:
            layout["nodes"] = patch["nodes"]
        edges_changed = patch.get("edges") is not None
        lead_changed = patch.get("lead_role_key") is not None
        if edges_changed:
            layout["edges"] = patch["edges"]
        if edges_changed or lead_changed:
            _sync_team_graph(
                cfg,
                layout,
                patch.get("edges") if edges_changed else layout.get("edges") or [],
                patch.get("lead_role_key"),
            )
        if patch.get("office") is not None:
            office = dict(layout.get("office") or {})
            office.update(patch["office"])
            layout["office"] = office
        cfg["layout"] = layout
        _write_config(repo, cfg)
        return {"layout": layout}
    finally:
        repo.close()


@router.put("/behavior")
def update_behavior(data: BehaviorUpdate, manager: dict = Depends(require_ai_office_manage)):
    repo = SystemConfigRepository()
    try:
        if data.behavior is None:
            raise HTTPException(status_code=400, detail="behavior 不能为空")
        cfg = _read_config(repo)
        cfg["behavior"] = data.behavior
        _write_config(repo, cfg)
        return {"behavior": cfg["behavior"]}
    finally:
        repo.close()


def _normalize_skill(payload: dict) -> dict:
    key = str(payload.get("key") or "").strip()
    skill_id = str(payload.get("id") or "").strip() or key
    skill = {
        "key": key,
        "id": skill_id,
        "type": str(payload.get("type") or "tool_prompt").strip() or "tool_prompt",
        "workflow_key": str(payload.get("workflow_key") or "").strip() or None,
        "name": str(payload.get("name") or key).strip() or key,
        "description": str(payload.get("description") or "").strip(),
        "prompt": str(payload.get("prompt") or "").strip(),
        "tool_ids": payload.get("tool_ids") if isinstance(payload.get("tool_ids"), list) else [],
        "input_contract": str(payload.get("input_contract") or "").strip(),
        "output_contract": str(payload.get("output_contract") or "").strip(),
        "output_kind": str(payload.get("output_kind") or "").strip() or None,
    }
    return skill


@router.get("/skills")
def list_skills(user: dict = Depends(get_current_user)):
    repo = SkillCatalogRepository()
    try:
        skills = []
        for skill in repo.list():
            skill = dict(skill)
            for legacy_key in ("memory_rules", "office_action"):
                skill.pop(legacy_key, None)
            runtime = _skill_runtime(skill)
            skill["runnable"] = bool(runtime)
            skill["runtime_name"] = (runtime or {}).get("name")
            skill["input_hint"] = (runtime or {}).get("input_hint")
            skills.append(skill)
        return {"skills": skills}
    finally:
        repo.close()


@router.post("/skills")
def create_skill(data: SkillUpsert, manager: dict = Depends(require_ai_office_manage)):
    repo = SkillCatalogRepository()
    try:
        key = (data.key or "").strip()
        if not key:
            raise HTTPException(status_code=400, detail="skill key 不能为空")
        if repo.get(key):
            raise HTTPException(status_code=409, detail=f"技能 '{key}' 已存在")
        skill = _normalize_skill(data.model_dump())
        return repo.upsert(skill, operator=(manager or {}).get("username") or "system")
    finally:
        repo.close()


@router.put("/skills/{skill_key}")
def update_skill(skill_key: str, data: SkillUpsert, manager: dict = Depends(require_ai_office_manage)):
    repo = SkillCatalogRepository()
    try:
        existing = repo.get(skill_key)
        if not existing:
            raise HTTPException(status_code=404, detail=f"技能 '{skill_key}' 不存在")
        patch = data.model_dump(exclude_unset=True)
        patch.pop("key", None)
        merged = _normalize_skill({**existing, **patch, "key": skill_key})
        return repo.upsert(merged, operator=(manager or {}).get("username") or "system")
    finally:
        repo.close()


@router.delete("/skills/{skill_key}")
def delete_skill(skill_key: str, manager: dict = Depends(require_ai_office_manage)):
    skill_repo = SkillCatalogRepository()
    try:
        if not skill_repo.get(skill_key):
            raise HTTPException(status_code=404, detail=f"技能 '{skill_key}' 不存在")
        skill_repo.soft_delete(skill_key, operator=(manager or {}).get("username") or "system")
    finally:
        skill_repo.close()

    try:
        from app.repository.reasoning_flow_repo import ReasoningFlowRepository
        rf_repo = ReasoningFlowRepository()
        try:
            rf_repo.deactivate_skill_flows(skill_key, operator=(manager or {}).get("username") or "system")
        finally:
            rf_repo.close()
    except Exception:
        pass

    return {"deleted": skill_key}


def _merge_skill_data_sources(colleague: dict) -> dict:
    """给员工绑定 Skill 时自动落该 Skill 所需的数据域，运行时仍会再做一次兜底合并。"""
    refs = colleague.get("skills")
    if not isinstance(refs, list):
        return colleague
    try:
        repo = SkillCatalogRepository()
        try:
            catalog = {str(s.get("key") or "").strip(): s for s in repo.list()}
        finally:
            repo.close()
    except Exception:
        return colleague
    required: set = set()
    for ref in refs:
        key = ref if isinstance(ref, str) else (ref or {}).get("key")
        skill = catalog.get(str(key or "").strip())
        if not skill:
            continue
        tools = skill.get("tool_ids")
        if not isinstance(tools, list):
            continue
        required.update(_canonical_data_source(item) for item in tool_required_data_sources(tools))
    if not required:
        return colleague
    sources = {str(item).strip() for item in (colleague.get("data_sources") or []) if str(item or "").strip()}
    sources.update(required)
    colleague["data_sources"] = sorted(sources)
    return colleague


class MemoryCreate(BaseModel):
    type: str = "business_fact"
    content: str = ""
    pinned: bool = False


class MemoryUpdate(BaseModel):
    type: Optional[str] = None
    content: Optional[str] = None
    pinned: Optional[bool] = None


@router.get("/{role_key}/memories")
def list_colleague_memories(
    role_key: str,
    keyword: Optional[str] = None,
    limit: int = 100,
    manager: dict = Depends(require_ai_office_manage),
):
    from app.repository.colleague_memory_repo import ColleagueMemoryRepository
    items = ColleagueMemoryRepository().list_by_role(
        role_key, keyword=str(keyword or ""), limit=max(1, min(int(limit or 100), 500)))
    return {"memories": items, "total": len(items)}


@router.post("/{role_key}/memories")
def create_colleague_memory(role_key: str, data: MemoryCreate, manager: dict = Depends(require_ai_office_manage)):
    from app.repository.colleague_memory_repo import ColleagueMemoryRepository
    item = ColleagueMemoryRepository().add(
        role_key, data.type, data.content,
        source="manual", pinned=bool(data.pinned),
        created_by=str((manager or {}).get("name") or (manager or {}).get("id") or ""))
    if not item:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    return {"memory": item}


@router.put("/{role_key}/memories/{memory_id}")
def update_colleague_memory(
    role_key: str,
    memory_id: int,
    data: MemoryUpdate,
    manager: dict = Depends(require_ai_office_manage),
):
    from app.repository.colleague_memory_repo import ColleagueMemoryRepository
    repo = ColleagueMemoryRepository()
    existing = repo.get(memory_id)
    if not existing or existing.get("role_key") != role_key:
        raise HTTPException(status_code=404, detail="记忆不存在")
    patch = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    updated = repo.update(memory_id, patch)
    if not updated:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    return {"memory": updated}


@router.delete("/{role_key}/memories/{memory_id}")
def delete_colleague_memory(role_key: str, memory_id: int, manager: dict = Depends(require_ai_office_manage)):
    from app.repository.colleague_memory_repo import ColleagueMemoryRepository
    repo = ColleagueMemoryRepository()
    existing = repo.get(memory_id)
    if not existing or existing.get("role_key") != role_key:
        raise HTTPException(status_code=404, detail="记忆不存在")
    repo.delete(memory_id)
    return {"deleted": memory_id}


@router.delete("/{role_key}/memories")
def clear_colleague_memories(role_key: str, manager: dict = Depends(require_ai_office_manage)):
    from app.repository.colleague_memory_repo import ColleagueMemoryRepository
    deleted = ColleagueMemoryRepository().delete_by_role(role_key)
    return {"deleted": deleted, "role_key": role_key}


@router.put("/{role_key}")
def update_colleague(role_key: str, data: ColleagueUpdate, manager: dict = Depends(require_ai_office_manage)):
    repo = SystemConfigRepository()
    try:
        cfg = _read_config(repo)
        colleagues = cfg.get("colleagues") or []
        for i, colleague in enumerate(colleagues):
            if colleague.get("role_key") == role_key:
                patch = data.model_dump(exclude_unset=True)
                # 数据边界编辑糖：price_access 布尔/裸 data_boundary 一律折算进边界再落库
                bool_flag = patch.pop("price_access", None)
                raw_boundary = patch.pop("data_boundary", None)
                if isinstance(raw_boundary, dict):
                    patch["data_boundary"] = normalize_boundary({"data_boundary": raw_boundary})
                elif bool_flag is not None:
                    patch["data_boundary"] = apply_price_access(
                        colleague.get("data_boundary") if isinstance(colleague.get("data_boundary"), dict) else {},
                        bool(bool_flag))
                merged = {**colleague, **patch, "role_key": role_key}
                merged.pop("price_access", None)  # 派生值不落库（读侧归一化返回）
                if "skills" in patch or "tool_ids" in patch:
                    merged = _merge_skill_data_sources(merged)
                _clamp_pet_model(merged)
                normalize_colleague(merged)
                colleagues[i] = merged
                cfg["colleagues"] = colleagues
                _write_config(repo, cfg)
                return merged
        raise HTTPException(status_code=404, detail=f"AI 同事 '{role_key}' 不存在")
    finally:
        repo.close()


@router.delete("/{role_key}")
def delete_colleague(role_key: str, manager: dict = Depends(require_ai_office_manage)):
    repo = SystemConfigRepository()
    try:
        cfg = _read_config(repo)
        protected_role_keys = cfg.get("protected_role_keys") or []
        if role_key in protected_role_keys:
            raise HTTPException(status_code=400, detail=f"AI 同事 '{role_key}' 已被配置为受保护角色，不能删除")
        colleagues = cfg.get("colleagues") or []
        next_colleagues = [c for c in colleagues if (c or {}).get("role_key") != role_key]
        if len(next_colleagues) == len(colleagues):
            raise HTTPException(status_code=404, detail=f"AI 同事 '{role_key}' 不存在")
        cfg["colleagues"] = next_colleagues
        dispatch_rules = cfg.get("dispatch_rules")
        if isinstance(dispatch_rules, list):
            cfg["dispatch_rules"] = [r for r in dispatch_rules if (r or {}).get("role_key") != role_key]
        _write_config(repo, cfg)
        return {"deleted": role_key}
    finally:
        repo.close()
