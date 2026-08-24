"""Config-driven office access policy.

Admin users see every office room and every AI colleague. Other users are
scoped by ``ai_colleagues.access_policy``.

New policy shape is direct and human-readable:
  - enabled=False means unrestricted;
  - user_chat_role_keys > role_chat_role_keys > default_chat_role_keys;
  - legacy room mappings are only used as a fallback when the direct fields
    have never been configured.
"""
from typing import Any, Dict, List, Optional

from app.repository.system_config_repo import SystemConfigRepository

_CONFIG_KEY = "ai_colleagues"


def _policy(config: Dict[str, Any]) -> Dict[str, Any]:
    policy = config.get("access_policy")
    return policy if isinstance(policy, dict) else {}


def _room_map(policy: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = policy.get(key)
    return value if isinstance(value, dict) else {}


def _normalise_role_keys(value: Any) -> List[str]:
    if isinstance(value, list):
        return sorted({str(item) for item in value if str(item).strip()})
    if value is None:
        return []
    return [str(value)]


def _direct_access_role_keys(user: Optional[dict], policy: Dict[str, Any]) -> Optional[List[str]]:
    """Resolve direct role access. Returns None when no direct policy exists."""
    direct_keys = ("default_chat_role_keys", "role_chat_role_keys", "user_chat_role_keys")
    if not any(key in policy for key in direct_keys):
        return None

    user_map = _room_map(policy, "user_chat_role_keys")
    for identifier in (user.get("id"), user.get("user_id"), user.get("name")):
        if not identifier:
            continue
        if identifier in user_map:
            return _normalise_role_keys(user_map.get(identifier))

    role_map = _room_map(policy, "role_chat_role_keys")
    role_key = user.get("role") or "member"
    if role_key in role_map:
        return _normalise_role_keys(role_map.get(role_key))

    defaults = policy.get("default_chat_role_keys")
    if defaults is not None:
        return _normalise_role_keys(defaults)

    return []


def _room_access_role_keys(user: Optional[dict], config: Dict[str, Any], policy: Dict[str, Any]) -> Optional[List[str]]:
    """Legacy room-based fallback for old configurations."""
    rooms = config.get("rooms") or []
    if not rooms:
        return None
    user_room_map = _room_map(policy, "user_room_map")
    role_room_map = _room_map(policy, "role_room_map")

    room_ids: Optional[List[str]] = None
    for identifier in (user.get("id"), user.get("user_id"), user.get("name")):
        if not identifier:
            continue
        mapped = user_room_map.get(identifier)
        if isinstance(mapped, list):
            room_ids = [str(item) for item in mapped]
            break
        if mapped is not None:
            room_ids = [str(mapped)]
            break

    if room_ids is None:
        role_ids = role_room_map.get(user.get("role") or "member")
        if isinstance(role_ids, list):
            room_ids = [str(item) for item in role_ids]
        elif role_ids is not None:
            room_ids = [str(role_ids)]

    if room_ids is None:
        defaults = policy.get("default_room_ids")
        if isinstance(defaults, list):
            room_ids = [str(item) for item in defaults]
        else:
            room_ids = ["default"]

    if not room_ids or "*" in room_ids:
        return None

    allowed: set = set()
    unrestricted = False
    resolved_any = False
    for room_id in room_ids:
        room = next((item for item in rooms if isinstance(item, dict) and item.get("id") == room_id), None)
        if not room:
            continue
        resolved_any = True
        role_keys = room.get("role_keys") or []
        if not role_keys:
            unrestricted = True
            break
        allowed.update(str(key) for key in role_keys if key)

    if unrestricted or not resolved_any:
        return None
    allowed.add("unknown")
    return sorted(allowed) if allowed else []


def allowed_office_role_keys(user: Optional[dict]) -> Optional[List[str]]:
    """Return allowed role_keys, or None when the user can see all roles."""
    if not user:
        return []
    if (user.get("role") or "") == "admin":
        return None

    repo = SystemConfigRepository()
    try:
        config = repo.get_value(_CONFIG_KEY, {}) or {}
    finally:
        repo.close()

    if not isinstance(config, dict):
        return []
    policy = _policy(config)
    if policy.get("enabled") is False:
        return None
    direct = _direct_access_role_keys(user, policy)
    if direct is not None:
        return direct or []
    return _room_access_role_keys(user, config, policy)


def allowed_chat_role_keys(user: Optional[dict]) -> Optional[List[str]]:
    """Return role_keys the user is allowed to chat with.

    Uses the same direct AI-role policy as office visibility; falls back to
    the legacy room policy for installations that have not been migrated.
    """
    return allowed_office_role_keys(user)
