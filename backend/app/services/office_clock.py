"""Autonomous office clock.

Reads the AI-colleague runtime configuration and produces config-driven
office events. The clock never contains role names, desk coordinates or
activity copy; it only interprets the rules stored in
`system_config.ai_colleagues`.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.api.ai_colleagues import _read_config
from app.repository.system_config_repo import SystemConfigRepository
from app.services.office_brain import generate_autonomous_action, generate_meeting_output
from app.services.office_events import publish_office_event
from app.services.office_hub import office_hub

logger = logging.getLogger(__name__)

_FALLBACK_TICK_SECONDS = 10


def _as_list(value: Any) -> List[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _select_role_keys(rule: Dict[str, Any], colleagues: List[dict]) -> List[str]:
    roles = rule.get("roles")
    if roles == "*" or roles == "" or roles is None:
        return [c.get("role_key") for c in colleagues if c.get("role_key")]
    if isinstance(roles, str):
        roles = [item.strip() for item in roles.split(",") if item.strip()]
    allowed = {str(item).strip() for item in roles} if isinstance(roles, (list, tuple)) else set()
    if not allowed or "*" in allowed:
        return [c.get("role_key") for c in colleagues if c.get("role_key")]
    return [c.get("role_key") for c in colleagues if c.get("role_key") in allowed]


def _hhmm_and_date(timezone: str) -> tuple[str, str]:
    try:
        now = datetime.now(ZoneInfo(timezone or "Asia/Shanghai"))
    except (ZoneInfoNotFoundError, ValueError):
        now = datetime.now()
    return now.strftime("%H:%M"), now.strftime("%Y-%m-%d")


class OfficeClock:
    """Long-running, best-effort scheduler for autonomous office intents."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stopped = False
        self._last_schedule_fired: Dict[str, float] = {}
        self._meeting_last_fired: Dict[str, float] = {}
        self._life_last_fired: Dict[str, float] = {}
        self._life_llm_last_fired: Dict[str, float] = {}
        self._life_llm_hour_key: int = 0
        self._life_llm_calls_this_hour: int = 0
        self._life_llm_backoff_until: Dict[str, float] = {}

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopped = False
        self._task = asyncio.create_task(self._run(), name="office-clock")

    async def stop(self) -> None:
        self._stopped = True
        task = self._task
        if not task:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("office clock stopped with error", exc_info=True)
        self._task = None

    async def _run(self) -> None:
        while not self._stopped:
            tick_seconds = _FALLBACK_TICK_SECONDS
            try:
                tick_seconds = await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("office clock tick failed", exc_info=True)
            await asyncio.sleep(max(5, tick_seconds))

    async def _tick(self) -> int:
        config = self._load_config()
        behavior = config.get("behavior") or {}
        autonomous = behavior.get("autonomous") or {}
        tick_seconds = int(autonomous.get("tick_seconds") or _FALLBACK_TICK_SECONDS)
        if not autonomous.get("enabled", True):
            return tick_seconds

        colleagues = [
            colleague for colleague in _as_list(config.get("colleagues"))
            if colleague.get("role_key") and colleague.get("enabled", True)
        ]
        if not colleagues:
            return tick_seconds

        await self._tick_schedule(autonomous, colleagues)
        await self._tick_idle(autonomous, colleagues)
        await self._tick_life(behavior, autonomous, colleagues)
        await self._tick_collaboration(behavior, colleagues)
        return tick_seconds

    def _load_config(self) -> Dict[str, Any]:
        repo = SystemConfigRepository()
        try:
            return _read_config(repo)
        except Exception:
            logger.debug("failed to load ai colleagues config", exc_info=True)
            return {}
        finally:
            repo.close()


    async def _tick_life(self, behavior: Dict[str, Any], autonomous: Dict[str, Any], colleagues: List[dict]) -> None:
        life = autonomous.get("life") or {}
        if not isinstance(life, dict) or not life.get("enabled", True):
            return
        now = time.time()
        latest = office_hub.snapshot()
        colleague_keys = {str(colleague.get("role_key") or "").strip() for colleague in colleagues if colleague.get("role_key")}
        max_actions = max(1, min(int(life.get("max_actions_per_tick") or 1), max(1, len(colleagues))))
        cooldown_seconds = max(10, int(life.get("cooldown_seconds") or 45))

        configured_active = life.get("active_statuses")
        if isinstance(configured_active, list):
            active_statuses = {str(item).strip().lower() for item in configured_active if str(item).strip()}
        elif isinstance(configured_active, str):
            active_statuses = {item.strip().lower() for item in configured_active.split(",") if item.strip()}
        else:
            active_statuses = {"working", "meeting", "waiting_input", "error"}

        eligible: List[dict] = []
        for colleague in colleagues:
            role_key = str(colleague.get("role_key") or "").strip()
            if not role_key:
                continue
            event = latest.get(role_key) or {}
            status = str(event.get("status") or "idle").lower()
            source = event.get("source")
            if source in {"user", "chat", "assistant", "pipeline"}:
                continue
            if source != "autonomous" and status in active_statuses:
                continue
            last_fired = float(self._life_last_fired.get(role_key) or 0.0)
            if now - last_fired < cooldown_seconds:
                continue
            eligible.append(colleague)
        if not eligible:
            return

        tick_seconds = max(5, int(autonomous.get("tick_seconds") or _FALLBACK_TICK_SECONDS))
        rng = random.Random(f"office-life:{int(now // tick_seconds)}")
        selected = rng.sample(eligible, min(max_actions, len(eligible)))

        for colleague in selected:
            role_key = str(colleague.get("role_key") or "").strip()
            if not role_key:
                continue
            self._life_last_fired[role_key] = now

            use_llm = bool(life.get("llm_enabled", False))
            llm_min_interval = int(life.get("llm_min_interval_seconds") or 180)
            llm_backoff_seconds = max(30, int(life.get("llm_backoff_seconds") or 300))
            hour_key = int(now // 3600)
            if hour_key != self._life_llm_hour_key:
                self._life_llm_hour_key = hour_key
                self._life_llm_calls_this_hour = 0
            llm_budget = max(0, int(life.get("llm_budget_per_hour") or 0))
            if use_llm and llm_budget <= 0:
                use_llm = False
            if use_llm and now < float(self._life_llm_backoff_until.get(role_key) or 0.0):
                use_llm = False
            if use_llm and now - float(self._life_llm_last_fired.get(role_key) or 0.0) < llm_min_interval:
                use_llm = False
            if use_llm and self._life_llm_calls_this_hour >= llm_budget:
                use_llm = False
            if use_llm:
                self._life_llm_calls_this_hour += 1
                self._life_llm_last_fired[role_key] = now

            llm_timeout = max(3.0, min(15.0, float(life.get("llm_timeout_seconds") or 12.0)))
            try:
                action = await asyncio.wait_for(
                    generate_autonomous_action(
                        role_key,
                        colleagues,
                        brain_config=(behavior or {}).get("brain") or {},
                        life_config=life,
                        timezone=autonomous.get("timezone") or "Asia/Shanghai",
                        office_snapshot=latest,
                        use_llm=use_llm,
                        raise_on_llm_error=use_llm,
                    ),
                    timeout=llm_timeout,
                )
            except asyncio.TimeoutError:
                if use_llm:
                    self._life_llm_backoff_until[role_key] = now + llm_backoff_seconds
                action = await generate_autonomous_action(
                    role_key,
                    colleagues,
                    brain_config={},
                    life_config=life,
                    timezone=autonomous.get("timezone") or "Asia/Shanghai",
                    office_snapshot=latest,
                    use_llm=False,
                )
            except Exception:
                if use_llm:
                    self._life_llm_backoff_until[role_key] = now + llm_backoff_seconds
                logger.debug("office life action failed", exc_info=True)
                action = await generate_autonomous_action(
                    role_key,
                    colleagues,
                    brain_config={},
                    life_config=life,
                    timezone=autonomous.get("timezone") or "Asia/Shanghai",
                    office_snapshot=latest,
                    use_llm=False,
                )
            else:
                if use_llm:
                    self._life_llm_backoff_until.pop(role_key, None)
            if not action or not action.get("status"):
                continue

            latest_for_role = latest.get(role_key) or {}
            if (
                latest_for_role.get("source") == "autonomous"
                and latest_for_role.get("status") == action.get("status")
                and latest_for_role.get("zone") == action.get("zone")
                and latest_for_role.get("intent") == action.get("intent")
                and latest_for_role.get("activity") == action.get("activity")
                and float(latest_for_role.get("ts") or 0) > now - 3600
            ):
                continue

            target_role_key = action.get("target_role_key")
            participants = [role_key]
            conversation_id = None
            actor = None
            if target_role_key and target_role_key in colleague_keys and target_role_key != role_key:
                target_event = latest.get(target_role_key) or {}
                target_status = str(target_event.get("status") or "idle").lower()
                target_source = target_event.get("source")
                target_busy = target_source != "autonomous" and target_status in active_statuses
                if target_source not in {"user", "chat", "assistant", "pipeline"} and not target_busy:
                    participants = [role_key, target_role_key]
                    conversation_id = f"office_life_{abs(hash((role_key, target_role_key, int(now)))) % 100000000}"
                    actor = role_key

            if len(participants) > 1 and conversation_id:
                for participant in participants:
                    await self._publish_life_event(participant, action, participants, conversation_id, actor)
            else:
                await self._publish_life_event(role_key, action, [role_key], None, None)

    async def _publish_life_event(
        self,
        role_key: str,
        action: Dict[str, Any],
        participants: List[str],
        conversation_id: Optional[str],
        actor: Optional[str],
    ) -> None:
        await publish_office_event(
            role_key,
            action.get("status") or "thinking",
            action.get("activity") or "自主活动",
            message=action.get("message") or "",
            zone=action.get("zone"),
            intent=action.get("intent"),
            participants=list(participants),
            conversation_id=conversation_id,
            priority="low",
            source="autonomous",
            actor=actor,
        )


    async def _tick_schedule(self, autonomous: Dict[str, Any], colleagues: List[dict]) -> None:
        rules = _as_list(autonomous.get("schedule_rules"))
        if not rules:
            return
        timezone = autonomous.get("timezone") or "Asia/Shanghai"
        current_hhmm, current_date = _hhmm_and_date(timezone)
        now = time.time()
        for index, rule in enumerate(rules):
            rule_time = str(rule.get("time") or "").strip()
            if not rule_time or rule_time != current_hhmm:
                continue
            rule_id = str(rule.get("id") or f"schedule_{index}")
            fire_key = f"{rule_id}:{current_date}:{rule_time}"
            if fire_key in self._last_schedule_fired:
                continue
            self._last_schedule_fired[fire_key] = now
            role_keys = _select_role_keys(rule, colleagues)
            participants = list(role_keys)
            intent = rule.get("intent") or rule_id
            conversation_id = rule.get("conversation_id") or f"office_schedule_{rule_id}"
            for role_key in role_keys:
                await publish_office_event(
                    role_key,
                    rule.get("status") or "meeting",
                    rule.get("activity") or "",
                    message=rule.get("message") or "",
                    zone=rule.get("zone"),
                    intent=intent,
                    participants=participants,
                    conversation_id=conversation_id,
                    priority=rule.get("priority") or "normal",
                )

    async def _tick_idle(self, autonomous: Dict[str, Any], colleagues: List[dict]) -> None:
        idle = autonomous.get("idle") or {}
        if not isinstance(idle, dict) or not idle.get("enabled", True):
            return
        after_seconds = int(idle.get("after_seconds") or 600)
        latest = office_hub.snapshot()
        now = time.time()
        for colleague in colleagues:
            role_key = colleague.get("role_key")
            if not role_key:
                continue
            event = latest.get(role_key)
            if not event or event.get("status") != "idle":
                continue
            last_ts = float(event.get("ts") or 0)
            if last_ts and now - last_ts < after_seconds:
                continue
            await publish_office_event(
                role_key,
                idle.get("status") or "thinking",
                idle.get("activity") or "自主检查待办",
                message=idle.get("message") or "",
                zone=idle.get("zone") or "desk_zone",
                intent=idle.get("intent") or "review_pending_tasks",
                priority="low",
            )

    async def _tick_collaboration(self, behavior: Dict[str, Any], colleagues: List[dict]) -> None:
        rules = _as_list(behavior.get("collaboration_rules"))
        if not rules:
            return
        latest = office_hub.snapshot()
        colleague_keys = {c.get("role_key") for c in colleagues if c.get("role_key")}

        groups: Dict[str, List[str]] = {}
        for role_key, event in latest.items():
            if role_key not in colleague_keys:
                continue
            thread_id = event.get("thread_id")
            opportunity_id = event.get("opportunity_id")
            if thread_id:
                key = f"thread:{thread_id}"
            elif opportunity_id:
                key = f"opportunity:{opportunity_id}"
            else:
                continue
            groups.setdefault(key, [])
            if role_key not in groups[key]:
                groups[key].append(role_key)

        for rule in rules:
            if rule.get("when") != "same_thread_id":
                continue
            min_members = int(rule.get("min_members") or 2)
            cooldown_seconds = int(rule.get("cooldown_seconds") or 300)
            for group_key, role_keys in groups.items():
                if len(role_keys) < min_members:
                    continue
                signature = tuple(sorted(role_keys) + [group_key, rule.get("zone") or "meeting_room"])
                now = time.time()
                last_fired = self._meeting_last_fired.get(signature)
                if last_fired and now - last_fired < cooldown_seconds:
                    continue
                already_meeting = any(
                    latest.get(role, {}).get("status") == "meeting"
                    for role in role_keys
                )
                if already_meeting:
                    continue
                self._meeting_last_fired[signature] = now
                participants = list(role_keys)
                conversation_id = f"office_meeting_{group_key.replace(':', '_')}"
                for role_key in role_keys:
                    await publish_office_event(
                        role_key,
                        rule.get("status") or "meeting",
                        rule.get("activity") or "进入协作讨论",
                        message=rule.get("message") or "",
                        zone=rule.get("zone") or "meeting_room",
                        intent=rule.get("intent") or "meeting",
                        participants=participants,
                        conversation_id=conversation_id,
                        thread_id=event_key_thread_id(group_key),
                        opportunity_id=event_key_opportunity_id(group_key),
                        priority="normal",
                    )

                await self._publish_brain_output(
                    participants=participants,
                    conversation_id=conversation_id,
                    group_key=group_key,
                    behavior=behavior,
                    colleagues=colleagues,
                    zone=rule.get("zone") or "meeting_room",
                )


    async def _publish_brain_output(
        self,
        *,
        participants: List[str],
        conversation_id: str,
        group_key: str,
        behavior: Dict[str, Any],
        colleagues: List[dict],
        zone: str,
    ) -> None:
        brain_config = behavior.get("brain") or {}
        if not brain_config.get("enabled", False):
            return
        output = await generate_meeting_output(
            participants,
            context={
                "thread_id": event_key_thread_id(group_key),
                "opportunity_id": event_key_opportunity_id(group_key),
                "activity": "office_meeting",
            },
            colleagues=colleagues,
            brain_config=brain_config,
        )
        if not output:
            return
        for role_key in participants:
            await publish_office_event(
                role_key,
                "meeting",
                "会议结论已生成",
                message=output.get("summary") or output.get("conclusion") or "",
                zone=zone,
                intent="meeting_conclusion",
                participants=list(participants),
                conversation_id=conversation_id,
                thread_id=event_key_thread_id(group_key),
                opportunity_id=event_key_opportunity_id(group_key),
                summary=output.get("summary"),
                assignments=output.get("assignments"),
                conclusion=output.get("conclusion"),
                priority="normal",
            )


def event_key_thread_id(group_key: str) -> Optional[str]:
    if group_key.startswith("thread:"):
        return group_key[len("thread:"):]
    return None


def event_key_opportunity_id(group_key: str) -> Optional[str]:
    if group_key.startswith("opportunity:"):
        return group_key[len("opportunity:"):]
    return None


office_clock = OfficeClock()
