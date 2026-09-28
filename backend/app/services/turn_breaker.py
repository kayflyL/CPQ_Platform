# -*- coding: utf-8 -*-
"""turn_breaker —— 回合级熔断阶梯（munder-difflin 断路器借鉴，P0-②）。

阶梯：healthy → steering(180s) → constrained(360s)；stop 仍是既有 900s 硬上限（不动）。
信号三类：
  - 墙钟：回合跑了多久（steer/constrain 档位依据）
  - 无进展：距上一条事件超过 no_progress_after（事件全静默——内层 LLM 超时早已该触发，
    还静默说明卡在非 LLM 代码或事件循环本身，09-12 _cap_tool_context 死循环即此类）
  - 同节点重入：同一 step 第 3 次进入 running（回合内绕圈）
observe_only=True（默认）：只记日志，不执行任何动作；线上跑一段验证误报率后再武装。
武装时 steer=广播收口提示、constrain=提前走 900s 同款优雅暂停（reason_code 区分）。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

HEALTHY = "healthy"
STEERING = "steering"
CONSTRAINED = "constrained"

# 同参重复工具调用守卫（agent_react 源头执行，非 observe-only）：
# 连续 N 次同名同参调用 = 模型在原地打转，立刻止损（munder 用 ≥8，我们单循环
# max_iterations≤6，取 6=「每轮都在重复同一个调用」的极限情形）。
REPEAT_TOOL_LIMIT = 6


class ToolRepeatGuard:
    """同参重复工具调用守卫：连续同名同参调用计数，超限判死循环。"""

    def __init__(self, limit: int = REPEAT_TOOL_LIMIT) -> None:
        self.limit = max(2, int(limit))
        self._sig: Optional[tuple] = None
        self._streak = 0

    def record(self, name: str, args: dict) -> bool:
        """记一次调用；返回 True = 连续重复超限，应中止本步。"""
        try:
            import json
            canonical = json.dumps(args or {}, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            canonical = str(args or {})
        sig = (str(name or ""), canonical)
        if sig == self._sig:
            self._streak += 1
        else:
            self._sig = sig
            self._streak = 1
        return self._streak >= self.limit


class TurnBreaker:
    """回合熔断器：吃事件流（observe），supervise() 取代裸 asyncio.wait 做分层看护。

    纯策略+日志，不做网络/落库；时钟可注入便于测试。armed=False 时 constrain 不动作。
    """

    def __init__(
        self,
        *,
        thread_id: str = "",
        clock: Callable[[], float] = time.monotonic,
        steer_after: float = 180.0,
        constrain_after: float = 360.0,
        no_progress_after: float = 150.0,
        node_reentry_limit: int = 3,
        poll_interval: float = 15.0,
        hard_stop_after: float = 900.0,
        armed: bool = False,
    ) -> None:
        self.thread_id = thread_id
        self._clock = clock
        self.steer_after = steer_after
        self.constrain_after = constrain_after
        self.no_progress_after = no_progress_after
        self.node_reentry_limit = node_reentry_limit
        self.poll_interval = poll_interval
        self.hard_stop_after = hard_stop_after
        self.armed = armed
        self._turn_start = clock()
        self._last_event_ts = clock()
        self._level = HEALTHY
        self._node_entries: dict[str, int] = {}
        self.observations: list[dict] = []

    # ── 事件观察（wrap_sink 喂进来的每个事件；绝不抛错） ──
    def observe(self, payload: Any) -> None:
        try:
            self._last_event_ts = self._clock()
            if not isinstance(payload, dict):
                return
            etype = str(payload.get("type") or "")
            step = str(payload.get("step") or "")
            if etype in ("step_start", "step_done") and step:
                if etype == "step_start":
                    count = self._node_entries.get(step, 0) + 1
                    self._node_entries[step] = count
                    if count >= self.node_reentry_limit:
                        self._record("node_reentry", step=step, count=count)
            elif etype == "node_trace" and step and str(payload.get("status") or "") == "running":
                count = self._node_entries.get(step, 0) + 1
                self._node_entries[step] = count
                if count >= self.node_reentry_limit:
                    self._record("node_reentry", step=step, count=count)
        except Exception:
            logger.exception("turn_breaker.observe 失败（观察器自身不能影响回合）")

    def wrap_sink(self, sink: Optional[Any]) -> Any:
        """包一层 event_sink：先喂观察器，再原样转发（无 sink 也能观察）。"""
        breaker = self

        async def _wrapped(payload: dict) -> None:
            breaker.observe(payload)
            if sink is not None:
                await sink(payload)

        return _wrapped

    # ── 档位评估（supervise 轮询时调用；返回是否发生升档） ──
    def evaluate(self) -> bool:
        now = self._clock()
        elapsed = now - self._turn_start
        idle = now - self._last_event_ts
        new_level = HEALTHY
        if elapsed >= self.constrain_after:
            new_level = CONSTRAINED
        elif elapsed >= self.steer_after:
            new_level = STEERING
        # 无进展独立于墙钟：哪怕只跑了 60s，事件静默超阈值也是强异常
        if idle >= self.no_progress_after and new_level == HEALTHY:
            new_level = STEERING
            self._record("no_progress", idle_s=round(idle, 1), elapsed_s=round(elapsed, 1))
        if _level_rank(new_level) > _level_rank(self._level):
            self._level = new_level
            self._record(
                "escalate", level=new_level, elapsed_s=round(elapsed, 1),
                idle_s=round(idle, 1), armed=self.armed)
            return True
        return False

    @property
    def level(self) -> str:
        return self._level

    # ── 看护循环：取代裸 asyncio.wait(task, timeout=900) ──
    async def supervise(self, task: "asyncio.Future") -> tuple[set, set, str]:
        """返回 (done, pending, reason)；reason ∈ completed / hard_stop / constrained。

        hard_stop 语义与旧 asyncio.wait(timeout=900) 完全一致（含 pending 传导），
        调用方走既有的放弃式暂停分支即可。
        """
        while True:
            now = self._clock()
            hard_deadline = self._turn_start + self.hard_stop_after
            wait_s = min(self.poll_interval, max(0.05, hard_deadline - now))
            done, pending = await asyncio.wait({task}, timeout=wait_s)
            if done:
                return done, set(), "completed"
            now = self._clock()
            if now >= hard_deadline:
                return set(), {task}, "hard_stop"
            if task.done():  # wait 返回空集的极端竞态兜底
                return {task}, set(), "completed"
            self.evaluate()
            if (self._level == CONSTRAINED and self.armed
                    and not task.done()):
                task.cancel()
                self._record("constrained_cancel", elapsed_s=round(now - self._turn_start, 1))
                # 给取消留最多 30s 回收；无论是否回收完都按 pending 交回，
                # 调用方必须走暂停分支（cancelled 任务的 .result() 会抛 CancelledError）
                await asyncio.wait({task}, timeout=30.0)
                return set(), {task}, "constrained"

    def _record(self, kind: str, **fields: Any) -> None:
        entry = {"kind": kind, "thread_id": self.thread_id, **fields}
        self.observations.append(entry)
        logger.warning("turn_breaker %s %s", kind, entry)


_LEVEL_RANK = {HEALTHY: 0, STEERING: 1, CONSTRAINED: 2}


def _level_rank(level: str) -> int:
    return _LEVEL_RANK.get(level, 0)
