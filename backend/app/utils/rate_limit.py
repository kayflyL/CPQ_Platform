"""进程内存滑动窗口限流（无新依赖）——公开端点防滥用。

适用假设：单 uvicorn worker（本项目部署跑法）。多 worker 时各进程独立计数，
超限口径按 worker 数倍增可接受；未来多实例部署时换 Redis，check() 接口形状不变。
"""
import threading
import time
from collections import deque

from fastapi import Request


class SlidingWindowLimiter:
    """每键一个时间戳队列：check() 原子「清理过期 → 判容 → 记录（仅记录放行）」。

    内存防膨：全局键数超 _MAX_KEYS 时按最后活跃时间清最旧一批（匿名流量打不平它）。
    """

    _MAX_KEYS = 10000
    _EVICT_BATCH = 2000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> [deque[monotonic_ts], last_seen_monotonic]
        self._buckets: dict[str, tuple] = {}

    def check(self, key: str, limit: int, window_seconds: int) -> bool:
        """放行返回 True（并记录本次）；超限返回 False（不记录，不惩罚）。"""
        now = time.monotonic()
        with self._lock:
            self._evict_if_bloated(now)
            entry = self._buckets.get(key)
            if entry is None:
                entry = (deque(), now)
                self._buckets[key] = entry
            hits, _ = entry
            window_start = now - window_seconds
            while hits and hits[0] <= window_start:
                hits.popleft()
            entry = (hits, now)
            self._buckets[key] = entry
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def _evict_if_bloated(self, now: float) -> None:
        if len(self._buckets) <= self._MAX_KEYS:
            return
        oldest = sorted(self._buckets.items(), key=lambda kv: kv[1][1])[: self._EVICT_BATCH]
        for key, (_, last_seen) in oldest:
            # 刚活跃过的键不误删（按最旧 last_seen 排序，天然不会命中）
            if now - last_seen > 60:
                self._buckets.pop(key, None)


def client_ip(request: Request) -> str:
    """取客户端 IP：X-Forwarded-For 首段（nginx 反代写入）→ 回退直连地址。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else ""
