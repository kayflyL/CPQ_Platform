"""Config-driven AI office spatial-intent resolver.

This module asks the configured LLM to decide whether a chat message should
produce a spatial office action. It never hardcodes role keys, coordinates,
zone ids or activity copy; everything comes from system_config.ai_colleagues.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.services import ai_colleague_service, llm_client

logger = logging.getLogger(__name__)


_INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["chat", "spatial"]},
        "zone": {"type": "string"},
        "status": {"type": "string"},
        "intent": {"type": "string"},
        "reply": {"type": "string"},
    },
}


def _as_dict_list(value: Any) -> list:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _office(config: dict) -> dict:
    layout = config.get("layout")
    if not isinstance(layout, dict):
        return {}
    office = layout.get("office")
    return office if isinstance(office, dict) else {}


def _zone_label(zone: dict, zone_id: str) -> str:
    return str(zone.get("label") or zone_id or "目标区域").strip()


def _status_zone_map(office: dict) -> dict:
    value = office.get("status_zone_map")
    return value if isinstance(value, dict) else {}


def _allowed_statuses(zones: list, status_zone_map: dict) -> list:
    statuses = {"idle", "working", "meeting"}
    statuses.update(str(status) for status in status_zone_map.keys() if str(status).strip())
    for zone in zones:
        if str(zone.get("type") or "").lower() == "meeting":
            statuses.add("meeting")
    return sorted(status for status in statuses if status)


def _zone_aliases(zone: dict) -> list:
    value = zone.get("aliases")
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _zone_spec(zones: list) -> str:
    lines = []
    for zone in zones:
        zone_id = str(zone.get("id") or "").strip()
        if not zone_id:
            continue
        zone_type = str(zone.get("type") or "").strip()
        label = _zone_label(zone, zone_id)
        aliases = _zone_aliases(zone)
        walk_target = str(zone.get("walk_target") or "").strip()
        line = f"- id={zone_id}, type={zone_type}, label={label}"
        if aliases:
            line += f", aliases={','.join(aliases)}"
        if walk_target:
            line += f", walk_target={walk_target}"
        lines.append(line)
    return "\n".join(lines) or "无可用区域"


def _build_classifier_prompt(
    role_key: str,
    colleague: Optional[dict],
    zones: list,
    status_zone_map: dict,
) -> str:
    persona = str((colleague or {}).get("system_prompt") or "").strip()
    if not persona:
        persona = f"CPQ 平台的 AI 同事 {role_key}"
    zone_lines = _zone_spec(zones)
    status_lines = "\n".join(
        f"- {status} -> {zone}"
        for status, zone in status_zone_map.items()
        if str(status).strip() and str(zone).strip()
    )
    allowed = " / ".join(_allowed_statuses(zones, status_zone_map))
    return (
        "你是 CPQ AI 办公室的动作理解器。请判断用户消息是否明确要求当前 AI 同事改变位置或工作状态。\n"
        f"当前同事 role_key：{role_key}\n"
        f"当前同事人设：{persona}\n\n"
        "可用区域：\n" + zone_lines + "\n\n"
        "状态-区域映射：\n" + (status_lines or "无") + "\n\n"
        "输出规则：\n"
        "1. 每次必须返回 kind 字段，值为 \"chat\" 或 \"spatial\"。只要句子表达明确的办公空间动作：位移到可用区域（去/回/前往/到/坐到/走到），或状态切换（开始工作/开始会议/休息一下）且能映射到可用状态，就返回 spatial，即使后面还跟着业务目的；普通业务问题、闲聊、反问一律返回 chat。\n"
        "2. spatial.zone 必须从可用区域 id 中选择，spatial.status 只能是：" + allowed + "。\n"
        "3. spatial.reply 是该同事对用户的简短确认，一句中文即可，不要输出业务解释或长篇自我介绍。\n"
        "4. chat 时 zone/status/intent/reply 都留空。\n"
        "5. 示例：去会议室应返回 {\"kind\":\"spatial\",\"zone\":\"meeting_room\",\"status\":\"meeting\",\"intent\":\"meeting\",\"reply\":\"好的，我这就去会议室。\"}。\n"
        "只输出 JSON，不要输出 Markdown。"
    )


def _zone_status(zone: dict, status_zone_map: dict) -> str:
    zone_id = str(zone.get("id") or "").strip()
    zone_type = str(zone.get("type") or "").lower()
    if zone_type == "meeting":
        return "meeting"
    for status in ("working", "public", "idle"):
        if str(status_zone_map.get(status) or "").strip() == zone_id:
            return status
    for status, mapped_zone in status_zone_map.items():
        if str(mapped_zone).strip() == zone_id:
            if status in ("working", "idle", "meeting", "public"):
                return status
    return "working" if zone_type != "meeting" else "meeting"


async def resolve_office_spatial_intent(
    text: Optional[str],
    role_key: Optional[str] = None,
    config: Optional[dict] = None,
    colleague: Optional[dict] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve a spatial office command with the configured LLM, if any."""
    message = (text or "").strip()
    if not message:
        return None

    config = config or ai_colleague_service.get_ai_colleague_config()
    office = _office(config)
    zones = _as_dict_list(office.get("zones"))
    if not zones:
        return None
    status_zone_map = _status_zone_map(office)
    role_key = str(role_key or (colleague or {}).get("role_key") or "assistant").strip()

    try:
        data = await llm_client.chat_json(
            [
                {"role": "system", "content": _build_classifier_prompt(role_key, colleague, zones, status_zone_map)},
                {"role": "user", "content": message},
            ],
            schema=_INTENT_SCHEMA,
            model=(colleague or {}).get("model_override") or None,
            temperature=0.0,
            timeout=60.0,
            max_attempts=1,
        )
    except Exception as exc:
        logger.debug("office spatial intent LLM classification failed: %s", exc)
        return None

    if not isinstance(data, dict):
        return None

    zone_id = str(data.get("zone") or "").strip()
    zone = next((item for item in zones if str(item.get("id") or "").strip() == zone_id), None)
    kind = str(data.get("kind") or "").strip().lower()

    if kind == "chat":
        return None

    if kind != "spatial":
        if not zone:
            return None

    if not zone:
        return None

    zone_type = str(zone.get("type") or "").lower()
    label = _zone_label(zone, zone_id)
    allowed = set(_allowed_statuses(zones, status_zone_map))
    status = str(data.get("status") or "").strip()
    if status not in allowed:
        if zone_type == "meeting":
            status = "meeting"
        else:
            status = _zone_status(zone, status_zone_map)

    intent = str(data.get("intent") or "").strip()
    if not intent:
        if zone_type == "meeting":
            intent = "meeting"
        elif status == "working":
            intent = "work"
        else:
            intent = "move"

    reply = str(data.get("reply") or "").strip()
    if not reply:
        reply = f"好的，我这就去{label}。"

    return {
        "role_key": role_key,
        "status": status,
        "intent": intent,
        "zone": zone_id,
        "activity": f"前往{label}",
        "message": message,
        "reply": reply,
    }
