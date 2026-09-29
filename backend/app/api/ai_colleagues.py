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
from app.services.data_boundary import normalize_colleague
from app.services.office_access import allowed_chat_role_keys

router = APIRouter(prefix="/api/ai-colleagues", tags=["ai-colleagues"])

require_ai_office_manage = require_perms("ai.office.manage")

_CONFIG_KEY = "ai_colleagues"

# 桌宠虚拟形象白名单：与 frontend/public/live2d/<key> 一一对应
PET_MODEL_KEYS = {"koharu", "hibiki", "shizuku", "nico", "izumi", "haru", "wanko"}
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
    "floor": {"width": 22, "depth": 24},
    "workspace": {"width": 24, "depth": 26},
    "zones": [
        {"id": "desk_zone", "type": "desk", "label": "开放办公区", "aliases": ["办公区", "工位", "座位", "自己的座位"], "walk_target": "home", "position": {"x": 2.5, "z": -1.4}, "width": 17, "depth": 11.2},
        {"id": "meeting_room", "type": "meeting", "label": "会议室", "aliases": ["会议室", "会议区"], "walk_target": "meeting", "position": {"x": 6, "z": 8.1}, "radius": 4.2, "capacity": 8, "width": 10, "depth": 7.8, "room": True, "glass": True, "door_to_wall": False, "door": {"side": "back", "offset": 0, "width": 1.6}},
        {"id": "public_zone", "type": "public", "label": "接待区", "aliases": ["接待区", "前台", "公共区", "办公区"], "walk_target": "center", "shape": "rect", "position": {"x": -5, "z": 8.1}, "width": 12, "depth": 7.8, "room": True},
        {"id": "tea", "type": "lounge", "label": "茶水间", "aliases": ["茶水间"], "walk_target": "center", "position": {"x": -8, "z": -10.2}, "width": 6, "depth": 3.6, "room": True},
        {"id": "rest", "type": "lounge", "label": "休息区", "aliases": ["休息区"], "walk_target": "center", "position": {"x": 3, "z": -10.2}, "width": 16, "depth": 3.6, "room": True},
        {"id": "off1", "type": "office", "label": "办公室1", "aliases": ["办公室1"], "walk_target": "center", "position": {"x": -8.5, "z": -5.2}, "width": 5, "depth": 3.6, "room": True, "door": {"side": "right", "offset": 0, "width": 1.2}},
        {"id": "off2", "type": "office", "label": "办公室2", "aliases": ["办公室2"], "walk_target": "center", "position": {"x": -8.5, "z": -1.6}, "width": 5, "depth": 3.6, "room": True, "door": {"side": "right", "offset": 0, "width": 1.2}},
        {"id": "off3", "type": "office", "label": "办公室3", "aliases": ["办公室3"], "walk_target": "center", "position": {"x": -8.5, "z": 2.2}, "width": 5, "depth": 4.0, "room": True, "door": {"side": "right", "offset": 0, "width": 1.2}}
    ],
    "furniture_catalog": [
    {"type":"desk","label":"办公桌","category":"desk","width":1.75,"depth":0.95,"height":1.45,"rotatable":True},
    {"type":"office_chair","label":"办公椅","category":"chair","width":0.6,"depth":0.62,"height":1.1,"rotatable":True},
    {"type":"meeting_table","label":"会议长桌","category":"meeting","width":4,"depth":1.2,"height":0.72,"rotatable":True},
    {"type":"meeting_chair","label":"会议椅","category":"chair","width":0.55,"depth":0.55,"height":0.95,"rotatable":True},
    {"type":"plant","label":"绿植","category":"plant","width":0.55,"depth":0.55,"height":1.4,"rotatable":False},
    {"type":"bookshelf","label":"书架","category":"storage","width":1.4,"depth":0.5,"height":2.1,"rotatable":True},
    {"type":"coffee_bar","label":"茶水吧台","category":"storage","width":1.6,"depth":0.72,"height":1.3,"rotatable":True},
    {"type":"lounge_sofa","label":"休息沙发","category":"lounge","width":2,"depth":0.9,"height":0.9,"rotatable":True},
    {"type":"whiteboard","label":"白板","category":"meeting","width":2.1,"depth":0.08,"height":1.25,"rotatable":True},
    {"type":"art","label":"装饰画","category":"decor","width":0.95,"depth":0.06,"height":0.7,"rotatable":True},
    {"type":"rug","label":"地毯","category":"decor","width":2.4,"depth":1.8,"height":0.02,"rotatable":True},
    {"type":"partition","label":"工位隔断","category":"desk","width":0.9,"depth":0.12,"height":1.4,"rotatable":True},
    {"type":"fridge","label":"冰箱","category":"storage","width":0.9,"depth":0.9,"height":1.9,"rotatable":True},
    {"type":"coffee_table","label":"茶几","category":"lounge","width":0.8,"depth":0.8,"height":0.45,"rotatable":True},
    {"type":"round_table","label":"圆桌","category":"lounge","width":1.1,"depth":1.1,"height":0.75,"rotatable":True},
    {"type":"stool","label":"高脚凳","category":"chair","width":0.4,"depth":0.4,"height":0.7,"rotatable":True},
    {"type":"reception_desk","label":"前台","category":"furniture","width":2.2,"depth":0.9,"height":1.1,"rotatable":True},
    {"type":"coat_rack","label":"衣帽架","category":"decor","width":0.5,"depth":0.5,"height":1.8,"rotatable":True},
    {"type":"tv","label":"电视","category":"decor","width":1.4,"depth":0.12,"height":0.9,"rotatable":True},
    {"type":"file_cabinet","label":"文件柜","category":"storage","width":0.6,"depth":0.6,"height":1.1,"rotatable":True}
    ],
    "furniture": [
    {"id": "desk_o1", "type": "desk", "position": {"x": -3, "z": -5}, "rotation_y": 0, "zoneId": "desk_zone", "seat": True, "role_key": None},
    {"id": "desk_o2", "type": "desk", "position": {"x": 0.5, "z": -5}, "rotation_y": 0, "zoneId": "desk_zone", "seat": True, "role_key": None},
    {"id": "desk_o3", "type": "desk", "position": {"x": 4, "z": -5}, "rotation_y": 0, "zoneId": "desk_zone", "seat": True, "role_key": None},
    {"id": "desk_o4", "type": "desk", "position": {"x": 7.5, "z": -5}, "rotation_y": 0, "zoneId": "desk_zone", "seat": True, "role_key": None},
    {"id": "desk_o5", "type": "desk", "position": {"x": -3, "z": -1.5}, "rotation_y": 0, "zoneId": "desk_zone", "seat": True, "role_key": None},
    {"id": "desk_o6", "type": "desk", "position": {"x": 0.5, "z": -1.5}, "rotation_y": 0, "zoneId": "desk_zone", "seat": True, "role_key": None},
    {"id": "desk_o7", "type": "desk", "position": {"x": 4, "z": -1.5}, "rotation_y": 0, "zoneId": "desk_zone", "seat": True, "role_key": None},
    {"id": "desk_o8", "type": "desk", "position": {"x": 7.5, "z": -1.5}, "rotation_y": 0, "zoneId": "desk_zone", "seat": True, "role_key": None},
    {"id": "desk_o9", "type": "desk", "position": {"x": -3, "z": 2}, "rotation_y": 0, "zoneId": "desk_zone", "seat": True, "role_key": None},
    {"id": "desk_o10", "type": "desk", "position": {"x": 0.5, "z": 2}, "rotation_y": 0, "zoneId": "desk_zone", "seat": True, "role_key": None},
    {"id": "desk_o11", "type": "desk", "position": {"x": 4, "z": 2}, "rotation_y": 0, "zoneId": "desk_zone", "seat": True, "role_key": None},
    {"id": "desk_o12", "type": "desk", "position": {"x": 7.5, "z": 2}, "rotation_y": 0, "zoneId": "desk_zone", "seat": True, "role_key": None},
    {"id": "wb_o1", "type": "whiteboard", "position": {"x": 10.6, "z": -5}, "rotation_y": -1.5708, "zoneId": "desk_zone"},
    {"id": "wb_o2", "type": "whiteboard", "position": {"x": 10.6, "z": -1.5}, "rotation_y": -1.5708, "zoneId": "desk_zone"},
    {"id": "wb_o3", "type": "whiteboard", "position": {"x": 10.6, "z": 2}, "rotation_y": -1.5708, "zoneId": "desk_zone"},
    {"id": "plant_o1", "type": "plant", "position": {"x": -5.5, "z": -6.5}, "rotation_y": 0, "zoneId": "desk_zone"},
    {"id": "plant_o2", "type": "plant", "position": {"x": 10.5, "z": -6.5}, "rotation_y": 0, "zoneId": "desk_zone"},
    {"id": "plant_o3", "type": "plant", "position": {"x": -5.5, "z": 3.6}, "rotation_y": 0, "zoneId": "desk_zone"},
    {"id": "plant_o4", "type": "plant", "position": {"x": 10.5, "z": 3.6}, "rotation_y": 0, "zoneId": "desk_zone"},
    {"id": "meeting_table", "type": "meeting_table", "position": {"x": 6, "z": 8.1}, "rotation_y": 0, "zoneId": "meeting_room", "seat": False},
    {"id": "meeting_chair_1", "type": "meeting_chair", "position": {"x": 4.8, "z": 7.1}, "rotation_y": 0, "zoneId": "meeting_room", "seat": True, "role_key": None},
    {"id": "meeting_chair_2", "type": "meeting_chair", "position": {"x": 6, "z": 7.1}, "rotation_y": 0, "zoneId": "meeting_room", "seat": True, "role_key": None},
    {"id": "meeting_chair_3", "type": "meeting_chair", "position": {"x": 7.2, "z": 7.1}, "rotation_y": 0, "zoneId": "meeting_room", "seat": True, "role_key": None},
    {"id": "meeting_chair_4", "type": "meeting_chair", "position": {"x": 4.8, "z": 9.1}, "rotation_y": 0, "zoneId": "meeting_room", "seat": True, "role_key": None},
    {"id": "meeting_chair_5", "type": "meeting_chair", "position": {"x": 6, "z": 9.1}, "rotation_y": 0, "zoneId": "meeting_room", "seat": True, "role_key": None},
    {"id": "meeting_chair_6", "type": "meeting_chair", "position": {"x": 7.2, "z": 9.1}, "rotation_y": 0, "zoneId": "meeting_room", "seat": True, "role_key": None},
    {"id": "meeting_chair_7", "type": "meeting_chair", "position": {"x": 3.3, "z": 8.1}, "rotation_y": 0, "zoneId": "meeting_room", "seat": True, "role_key": None},
    {"id": "meeting_chair_8", "type": "meeting_chair", "position": {"x": 8.7, "z": 8.1}, "rotation_y": 0, "zoneId": "meeting_room", "seat": True, "role_key": None},
    {"id": "whiteboard_meeting", "type": "whiteboard", "position": {"x": 10.6, "z": 8.1}, "rotation_y": -1.5708, "zoneId": "meeting_room"},
    {"id": "coffee_bar_tea", "type": "coffee_bar", "position": {"x": -9.9, "z": -9.4}, "rotation_y": 0, "zoneId": "tea"},
    {"id": "fridge_tea", "type": "fridge", "position": {"x": -10.3, "z": -11.2}, "rotation_y": 0, "zoneId": "tea"},
    {"id": "round_table_tea", "type": "round_table", "position": {"x": -7.2, "z": -10.0}, "rotation_y": 0, "zoneId": "tea"},
    {"id": "stool_tea_1", "type": "stool", "position": {"x": -6.55, "z": -9.35}, "rotation_y": 0, "zoneId": "tea"},
    {"id": "stool_tea_2", "type": "stool", "position": {"x": -7.85, "z": -9.35}, "rotation_y": 0, "zoneId": "tea"},
    {"id": "stool_tea_3", "type": "stool", "position": {"x": -6.55, "z": -10.65}, "rotation_y": 0, "zoneId": "tea"},
    {"id": "stool_tea_4", "type": "stool", "position": {"x": -7.85, "z": -10.65}, "rotation_y": 0, "zoneId": "tea"},
    {"id": "plant_tea", "type": "plant", "position": {"x": -10.4, "z": -11.4}, "rotation_y": 0, "zoneId": "tea"},
    {"id": "lounge_sofa_rest_1", "type": "lounge_sofa", "position": {"x": -2.5, "z": -9.8}, "rotation_y": 0, "zoneId": "rest"},
    {"id": "coffee_table_rest_1", "type": "coffee_table", "position": {"x": -2.5, "z": -9.0}, "rotation_y": 0, "zoneId": "rest"},
    {"id": "lounge_sofa_rest_2", "type": "lounge_sofa", "position": {"x": 5.5, "z": -9.8}, "rotation_y": 0, "zoneId": "rest"},
    {"id": "coffee_table_rest_2", "type": "coffee_table", "position": {"x": 5.5, "z": -9.0}, "rotation_y": 0, "zoneId": "rest"},
    {"id": "round_table_rest", "type": "round_table", "position": {"x": 3, "z": -9.6}, "rotation_y": 0, "zoneId": "rest"},
    {"id": "stool_rest_1", "type": "stool", "position": {"x": 3.65, "z": -9.0}, "rotation_y": 0, "zoneId": "rest"},
    {"id": "stool_rest_2", "type": "stool", "position": {"x": 2.35, "z": -9.0}, "rotation_y": 0, "zoneId": "rest"},
    {"id": "stool_rest_3", "type": "stool", "position": {"x": 3.65, "z": -10.2}, "rotation_y": 0, "zoneId": "rest"},
    {"id": "stool_rest_4", "type": "stool", "position": {"x": 2.35, "z": -10.2}, "rotation_y": 0, "zoneId": "rest"},
    {"id": "tv_rest", "type": "tv", "position": {"x": 10.7, "z": -10.2}, "rotation_y": -1.5708, "zoneId": "rest"},
    {"id": "plant_rest_1", "type": "plant", "position": {"x": -4.6, "z": -11.6}, "rotation_y": 0, "zoneId": "rest"},
    {"id": "plant_rest_2", "type": "plant", "position": {"x": 1.0, "z": -11.6}, "rotation_y": 0, "zoneId": "rest"},
    {"id": "plant_rest_3", "type": "plant", "position": {"x": 7.5, "z": -11.5}, "rotation_y": 0, "zoneId": "rest"},
    {"id": "plant_rest_4", "type": "plant", "position": {"x": 10.6, "z": -8.9}, "rotation_y": 0, "zoneId": "rest"},
    {"id": "desk_off1", "type": "desk", "position": {"x": -8.5, "z": -6.2}, "rotation_y": 0, "zoneId": "off1", "seat": True, "role_key": None},
    {"id": "whiteboard_off1", "type": "whiteboard", "position": {"x": -8.5, "z": -3.55}, "rotation_y": 3.1416, "zoneId": "off1"},
    {"id": "desk_off2", "type": "desk", "position": {"x": -8.5, "z": -2.55}, "rotation_y": 0, "zoneId": "off2", "seat": True, "role_key": None},
    {"id": "whiteboard_off2", "type": "whiteboard", "position": {"x": -8.5, "z": 0.05}, "rotation_y": 3.1416, "zoneId": "off2"},
    {"id": "desk_off3", "type": "desk", "position": {"x": -8.5, "z": 1.25}, "rotation_y": 0, "zoneId": "off3", "seat": True, "role_key": None},
    {"id": "whiteboard_off3", "type": "whiteboard", "position": {"x": -8.5, "z": 4.05}, "rotation_y": 3.1416, "zoneId": "off3"},
    {"id": "reception_desk", "type": "reception_desk", "position": {"x": -4.0, "z": 9.4}, "rotation_y": 0, "zoneId": "public_zone"},
    {"id": "chair_reception", "type": "office_chair", "position": {"x": -4.0, "z": 8.4}, "rotation_y": 0, "zoneId": "public_zone", "seat": True, "role_key": None},
    {"id": "brand_wall", "type": "tv", "position": {"x": -4.0, "z": 6.6}, "rotation_y": 0, "zoneId": "public_zone"},
    {"id": "rug_reception", "type": "rug", "position": {"x": -7.6, "z": 9.4}, "rotation_y": 0, "zoneId": "public_zone"},
    {"id": "lounge_sofa_reception", "type": "lounge_sofa", "position": {"x": -8.7, "z": 9.4}, "rotation_y": 0, "zoneId": "public_zone"},
    {"id": "coffee_table_reception", "type": "coffee_table", "position": {"x": -7.1, "z": 9.4}, "rotation_y": 0, "zoneId": "public_zone"},
    {"id": "coat_rack_reception", "type": "coat_rack", "position": {"x": -10.6, "z": 11.3}, "rotation_y": 0, "zoneId": "public_zone"},
    {"id": "plant_rec_1", "type": "plant", "position": {"x": -10.5, "z": 4.7}, "rotation_y": 0, "zoneId": "public_zone"},
    {"id": "plant_rec_2", "type": "plant", "position": {"x": 0.6, "z": 4.7}, "rotation_y": 0, "zoneId": "public_zone"},
    {"id": "plant_rec_3", "type": "plant", "position": {"x": 0.6, "z": 11.4}, "rotation_y": 0, "zoneId": "public_zone"},
    ],
    "status_zone_map": {
        "working": "desk_zone", "thinking": "desk_zone", "waiting_input": "desk_zone", "done": "desk_zone", "idle": "desk_zone",
        "meeting": "meeting_room", "public": "public_zone", "error": "desk_zone"
    },
    "character_models": [
        "/models/ai-colleagues/kenney-mini/character-male-a.glb",
        "/models/ai-colleagues/kenney-mini/character-female-a.glb",
        "/models/ai-colleagues/kenney-mini/character-male-b.glb",
        "/models/ai-colleagues/kenney-mini/character-female-b.glb",
        "/models/ai-colleagues/kenney-mini/character-male-c.glb",
        "/models/ai-colleagues/kenney-mini/character-female-c.glb"
    ]
}
_DEFAULT_MEETING_ZONE = copy.deepcopy(_DEFAULT_OFFICE["zones"][1])
_DEFAULT_PUBLIC_ZONE = copy.deepcopy(_DEFAULT_OFFICE["zones"][2])

# 一日作息（区间化日程，替代旧 schedule_rules/idle/fallback_actions 三套点状规则）：
# roles=[] 表示全员适用；weekdays 用 ISO 编号（1=周一）；段活动文案支持 {name}/{role}/{zone} 变量。
_DEFAULT_DAILY_PLANS = [
    {
        "id": "weekday_common",
        "label": "全员 · 工作日",
        "roles": [],
        "weekdays": [1, 2, 3, 4, 5],
        "segments": [
            {"start": "09:00", "end": "09:30", "status": "meeting", "intent": "morning_sync", "zone": "meeting_room", "activity": "参加晨会同步"},
            {"start": "09:30", "end": "12:00", "status": "working", "intent": "work", "zone": "desk_zone", "activity": "{name} 进入上午工作块"},
            {"start": "12:00", "end": "13:30", "status": "idle", "intent": "lunch_break", "zone": "rest", "activity": "午休时间"},
            {"start": "13:30", "end": "15:00", "status": "working", "intent": "work", "zone": "desk_zone", "activity": "{name} 进入下午工作块"},
            {"start": "15:00", "end": "15:20", "status": "waiting_input", "intent": "tea_break", "zone": "tea", "activity": "{name} 去茶水间歇口气"},
            {"start": "15:20", "end": "18:00", "status": "working", "intent": "work", "zone": "desk_zone", "activity": "{name} 继续推进手头任务"},
            {"start": "18:00", "end": "18:30", "status": "thinking", "intent": "daily_review", "zone": "desk_zone", "activity": "{name} 复盘今日进展与待办"},
        ],
    }
]

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
        "status_meta": {
            "queued": {"label": "排队中", "color": "#9aa4b2"},
            "running": {"label": "进行中", "color": "#1677ff"},
            "done": {"label": "已完成", "color": "#52c9a0"},
            "failed": {"label": "失败", "color": "#ff4d4f"},
            "cancelled": {"label": "已取消", "color": "#8c8c8c"},
        },
        "assignment_status_meta": {
            "queued": {"label": "排队", "color": "#9aa4b2"},
            "routed": {"label": "已派发", "color": "#1677ff"},
            "active": {"label": "进行中", "color": "#1677ff"},
            "blocked": {"label": "受阻", "color": "#fa8c16"},
            "done": {"label": "完成", "color": "#52c9a0"},
            "failed": {"label": "失败", "color": "#ff4d4f"},
            "cancelled": {"label": "已取消", "color": "#8c8c8c"},
        },
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
            "interaction_action": {
                "status": "meeting",
                "intent": "discuss",
                "zone": "meeting_room",
                "activity": "找同事简短沟通",
                "message": "一起去会议室碰一下。"
            }
        },
        "daily_plans": copy.deepcopy(_DEFAULT_DAILY_PLANS),
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
    dispatchable: Optional[bool] = None
    price_access: Optional[bool] = None
    capabilities: Optional[list] = None
    behavior_profile: Optional[dict] = None
    relations: Optional[dict] = None
    skills: Optional[list] = None
    workflows: Optional[list] = None
    memory_policy: Optional[dict] = None
    pet_model: Optional[str] = None
    model_url: Optional[str] = None


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
    type: Optional[str] = "skill"
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

    _migrate_meeting_room_furniture(office)



def _migrate_meeting_room_furniture(office: dict) -> None:
    """把旧的超大会议桌布局（6m 桌 + 椅子在 x=4/8 桌头）收敛为 4m 桌布局。

    只在检测到与旧默认完全一致的椅子摆法时迁移，避免覆盖用户后续的自定义编辑。
    """
    furniture = office.get("furniture")
    if not isinstance(furniture, list):
        return
    meeting = [item for item in furniture if isinstance(item, dict) and item.get("zoneId") == "meeting_room"]
    chairs = [item for item in meeting if item.get("type") == "meeting_chair"]
    if len(chairs) < 6:
        return
    # 旧默认：两排椅子分别位于 z=-7 / z=-4，x 取 4/6/8
    xs = {(round(c.get("position", {}).get("x") or 0), round(c.get("position", {}).get("z") or 0)) for c in chairs}
    legacy_near = {(4, -7), (6, -7), (8, -7)}
    legacy_far = {(4, -4), (6, -4), (8, -4)}
    if not (legacy_near.issubset(xs) and legacy_far.issubset(xs)):
        return
    # 新默认：端头椅子内收到 5/7，与 4m 桌长边对齐
    xmap = {4: 5, 8: 7}
    for chair in chairs:
        pos = chair.get("position")
        if not isinstance(pos, dict):
            continue
        x = round(pos.get("x") or 0)
        if x in xmap and round(pos.get("z") or 0) in (-7, -4):
            pos["x"] = xmap[x]


# 独立办公室白板：旧默认挂在桌后墙（人正对面、被显示器遮挡），迁移到对面墙（门侧）。
# 仅当摆位与旧默认完全一致时才搬，避免覆盖用户自定义布局。
_OFFICE_WHITEBOARD_MIGRATIONS = {
    "whiteboard_off1": {"from_z": -6.85, "to_z": -3.55},
    "whiteboard_off2": {"from_z": -3.25, "to_z": 0.05},
    "whiteboard_off3": {"from_z": 0.35, "to_z": 4.05},
}


def _migrate_office_whiteboards(office: dict) -> bool:
    furniture = office.get("furniture")
    if not isinstance(furniture, list):
        return False
    changed = False
    for item in furniture:
        if not isinstance(item, dict):
            continue
        plan = _OFFICE_WHITEBOARD_MIGRATIONS.get(item.get("id"))
        if not plan:
            continue
        pos = item.get("position")
        if not isinstance(pos, dict):
            continue
        try:
            x = round(float(pos.get("x") or 0), 2)
            z = round(float(pos.get("z") or 0), 2)
            rot = float(item.get("rotation_y") or 0)
        except (TypeError, ValueError):
            continue
        if x == -8.5 and z == plan["from_z"] and abs(rot) < 0.01:
            pos["z"] = plan["to_z"]
            item["rotation_y"] = 3.1416
            changed = True
    return changed


def _hhmm_add_minutes(hhmm: str, minutes: int) -> str:
    try:
        parts = str(hhmm).strip().split(":")
        total = (int(parts[0]) * 60 + int(parts[1]) + int(minutes)) % (24 * 60)
        return f"{total // 60:02d}:{total % 60:02d}"
    except (ValueError, IndexError):
        return str(hhmm).strip()


def _migrate_behavior_daily_plans(behavior: dict) -> bool:
    """旧 schedule_rules / idle / life.fallback_actions → daily_plans 区间日程。

    - schedule_rules 逐条转成「旧定时规则（迁移）」计划的段（start=原时刻，时长 30 分钟，每天生效）
    - idle / fallback_actions 的固定文案职责由日程段承担，直接退役
    """
    autonomous = behavior.get("autonomous")
    if not isinstance(autonomous, dict):
        return False
    changed = False
    legacy_rules = autonomous.pop("schedule_rules", None)
    if legacy_rules is not None:
        changed = True
    if autonomous.pop("idle", None) is not None:
        changed = True
    life = autonomous.get("life")
    if isinstance(life, dict) and life.pop("fallback_actions", None) is not None:
        changed = True

    plans = autonomous.get("daily_plans")
    if not isinstance(plans, list):
        plans = copy.deepcopy(_DEFAULT_DAILY_PLANS)
        autonomous["daily_plans"] = plans
        changed = True

    if isinstance(legacy_rules, list):
        legacy_segments = []
        for rule in legacy_rules:
            if not isinstance(rule, dict):
                continue
            start = str(rule.get("time") or "").strip()
            if not start:
                continue
            legacy_segments.append({
                "start": start,
                "end": _hhmm_add_minutes(start, 30),
                "status": str(rule.get("status") or "meeting"),
                "intent": str(rule.get("intent") or "schedule"),
                "zone": str(rule.get("zone") or "meeting_room"),
                "activity": str(rule.get("activity") or ""),
            })
        if legacy_segments:
            plans.append({
                "id": "legacy_schedule",
                "label": "旧定时规则（迁移）",
                "roles": [],
                "weekdays": [1, 2, 3, 4, 5, 6, 7],
                "segments": legacy_segments,
            })
            changed = True

    for index, plan in enumerate(plans):
        if not isinstance(plan, dict):
            continue
        plan.setdefault("id", f"daily_plan_{index}")
        plan.setdefault("label", "")
        roles = plan.get("roles")
        plan["roles"] = [str(r).strip() for r in roles if str(r).strip()] if isinstance(roles, list) else []
        weekdays = plan.get("weekdays")
        if isinstance(weekdays, list):
            plan["weekdays"] = sorted({int(d) for d in weekdays if isinstance(d, (int, float)) and 1 <= int(d) <= 7})
        else:
            plan["weekdays"] = [1, 2, 3, 4, 5, 6, 7]
        segments = [s for s in plan.get("segments") or [] if isinstance(s, dict) and s.get("start") and s.get("end")]
        segments.sort(key=lambda s: str(s.get("start")))
        plan["segments"] = segments
    return changed


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
    for colleague in cfg.get("colleagues", []):
        if isinstance(colleague, dict):
            if _migrate_colleague_legacy(colleague):
                config_changed = True
            for key, default_value in _default_colleague(colleague.get("role_key", "")).items():
                if key not in colleague:
                    colleague[key] = copy.deepcopy(default_value)
                    config_changed = True
            # 读侧归一化：剥离已退役键（data_boundary/data_sources），price_access 布尔直存
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
    if _migrate_office_whiteboards(office):
        config_changed = True
    # 家具 catalog 以代码内默认值为单一事实源：读取时始终刷新，避免 DB 遗留旧尺寸导致前后端渲染/编辑/寻路不一致。
    default_catalog = copy.deepcopy(_DEFAULT_OFFICE.get("furniture_catalog") or [])
    if office.get("furniture_catalog") != default_catalog:
        office["furniture_catalog"] = default_catalog
        config_changed = True
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
    default_mission = _DEFAULT_BEHAVIOR.get("mission") or {}
    mission = behavior.get("mission")
    if not isinstance(mission, dict):
        behavior["mission"] = copy.deepcopy(default_mission)
        config_changed = True
    else:
        for key, default_value in default_mission.items():
            if key not in mission:
                mission[key] = copy.deepcopy(default_value)
                config_changed = True
    if _migrate_behavior_daily_plans(behavior):
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
        "dispatchable": True,
        "capabilities": [],
        "behavior_profile": copy.deepcopy(_DEFAULT_BEHAVIOR_PROFILE),
        "memory_policy": {
            "enabled": True,
            "short_term_max_turns": 12,
            "query_recent": 6,
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
        colleague = _default_colleague(role_key)
        colleague.update({k: v for k, v in patch.items() if v is not None})
        # 价格可见性：同事级布尔，唯一事实源（默认拒绝）
        if "price_access" in patch and patch["price_access"] is not None:
            colleague["price_access"] = bool(patch["price_access"])
        else:
            colleague["price_access"] = False
        catalog = _load_skill_catalog_map()
        colleague = _reclassify_skill_bindings(colleague, catalog)
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


@router.get("/layout/office-sample")
def get_layout_office_sample(manager: dict = Depends(require_ai_office_manage)):
    # 只读样板：编辑器用它替换工作副本，落库仍走 PUT /layout（唯一写路径）
    return {"office": copy.deepcopy(_DEFAULT_OFFICE)}

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
        "type": str(payload.get("type") or "skill").strip() or "skill",
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


def _load_skill_catalog_map() -> dict:
    try:
        repo = SkillCatalogRepository()
        try:
            return {str(s.get("key") or "").strip(): s for s in repo.list()}
        finally:
            repo.close()
    except Exception:
        return {}


def _reclassify_skill_bindings(colleague: dict, catalog: dict) -> dict:
    """workflow 类型的 key 只住 workflows 数组、skill 类型只住 skills（存量错位归位）。

    员工页两个下拉按 type 分列选项，错位数组里的 key 匹配不到选项 → 前端显示裸
    key（如 requirement_analysis 出现在 Skill 栏）。目录外的 key 保持原位（可能是
    尚未入库的自定义项，不丢数据）；同 key 出现在两个数组只留一份。
    """
    def _key(ref):
        return ref if isinstance(ref, str) else str((ref or {}).get("key") or "").strip()

    out: dict = {"skills": [], "workflows": []}
    seen: set = set()
    for field in ("skills", "workflows"):
        for ref in (colleague.get(field) or []):
            key = _key(ref)
            if not key or key in seen:
                continue
            skill = catalog.get(key)
            if skill is not None:
                dest = "workflows" if str(skill.get("type") or "").strip() == "workflow" else "skills"
            else:
                dest = field
            out[dest].append(ref)
            seen.add(key)
    colleague["skills"] = out["skills"]
    colleague["workflows"] = out["workflows"]
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
    include_retired: bool = False,
    user_id: Optional[str] = None,
    manager: dict = Depends(require_ai_office_manage),
):
    """治理面记忆列表。默认只看公共域（治理面维护对象）；
    传 user_id 查看该用户的私有域（排查/治理用）。"""
    from app.repository.colleague_memory_repo import ColleagueMemoryRepository
    uid = str(user_id or "").strip()
    items = ColleagueMemoryRepository().list_by_role(
        role_key, keyword=str(keyword or ""), limit=max(1, min(int(limit or 100), 500)),
        include_retired=bool(include_retired),
        visible_to=uid or None, public_only=not uid)
    return {"memories": items, "total": len(items)}


@router.post("/{role_key}/memories/consolidate")
async def consolidate_colleague_memories(role_key: str, manager: dict = Depends(require_ai_office_manage)):
    from app.services.colleague_memory_service import consolidate_role
    result = await consolidate_role(role_key)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=str(result.get("error") or "整理失败"))
    return result


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
    """管理面删除=强制失效打戳（双时间轴：历史可追溯），不物理删。"""
    from app.repository.colleague_memory_repo import ColleagueMemoryRepository
    repo = ColleagueMemoryRepository()
    existing = repo.get(memory_id)
    if not existing or existing.get("role_key") != role_key:
        raise HTTPException(status_code=404, detail="记忆不存在")
    repo.retire(memory_id, force=True)
    return {"retired": memory_id}


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
                # 价格可见性：同事级布尔直存，唯一事实源
                if patch.get("price_access") is not None:
                    patch["price_access"] = bool(patch["price_access"])
                merged = {**colleague, **patch, "role_key": role_key}
                catalog = _load_skill_catalog_map()
                merged = _reclassify_skill_bindings(merged, catalog)
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
