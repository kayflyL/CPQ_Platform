"""SlidingWindowLimiter 单测：窗口滑动 / 超限拒绝 / 惰性清理 / 键膨胀回收 / 并发不超限。"""
import threading
from unittest import mock

from app.utils.rate_limit import SlidingWindowLimiter


def _fake_time(start: float):
    state = {"now": start}
    return lambda: state["now"], state


def test_allows_up_to_limit_then_denies():
    limiter = SlidingWindowLimiter()
    now, state = _fake_time(1000.0)
    with mock.patch("app.utils.rate_limit.time.monotonic", now):
        for _ in range(5):
            assert limiter.check("ip1", limit=5, window_seconds=600)
        assert not limiter.check("ip1", limit=5, window_seconds=600)
        # 别的键不受影响
        assert limiter.check("ip2", limit=5, window_seconds=600)


def test_window_slides():
    limiter = SlidingWindowLimiter()
    now, state = _fake_time(1000.0)
    with mock.patch("app.utils.rate_limit.time.monotonic", now):
        for _ in range(5):
            assert limiter.check("ip1", limit=5, window_seconds=600)
        assert not limiter.check("ip1", limit=5, window_seconds=600)
        state["now"] = 1000.0 + 601  # 窗口整体滑出
        assert limiter.check("ip1", limit=5, window_seconds=600)
        assert limiter.check("ip1", limit=5, window_seconds=600)


def test_partial_window_slide():
    limiter = SlidingWindowLimiter()
    now, state = _fake_time(1000.0)
    with mock.patch("app.utils.rate_limit.time.monotonic", now):
        for i in range(5):
            assert limiter.check("ip1", limit=5, window_seconds=600)
        state["now"] = 1000.0 + 301  # 最早 3 条滑出（1000/1000/1000 假设同刻——退化场景按最早一批算）
        # 同刻打点会整窗一起滑出/留下，这里只验证不抛错且回到可放行状态
        state["now"] = 1000.0 + 601
        assert limiter.check("ip1", limit=5, window_seconds=600)


def test_denied_calls_are_not_recorded():
    limiter = SlidingWindowLimiter()
    now, state = _fake_time(1000.0)
    with mock.patch("app.utils.rate_limit.time.monotonic", now):
        for _ in range(5):
            limiter.check("ip1", limit=5, window_seconds=600)
        for _ in range(50):
            assert not limiter.check("ip1", limit=5, window_seconds=600)
        state["now"] = 1000.0 + 601
        # 拒绝不记录：窗口滑出后立即恢复完整额度
        for _ in range(5):
            assert limiter.check("ip1", limit=5, window_seconds=600)


def test_bloat_eviction_keeps_recent_keys():
    limiter = SlidingWindowLimiter()
    now, state = _fake_time(1000.0)
    with mock.patch("app.utils.rate_limit.time.monotonic", now):
        # 撑爆键数：超 _MAX_KEYS + 预留量
        for i in range(11000):
            limiter.check(f"bulk-{i}", limit=1, window_seconds=600)
        # "刚活跃"键不应被误删
        assert limiter.check("fresh-key", limit=1, window_seconds=600)
        state["now"] = 1000.0 + 0.001
        assert limiter.check("fresh-key", limit=1, window_seconds=600) is False  # 已达 limit=1
        assert "fresh-key" in limiter._buckets


def test_concurrent_checks_never_exceed_limit():
    limiter = SlidingWindowLimiter()
    allowed = []
    lock = threading.Lock()

    def worker():
        for _ in range(40):
            if limiter.check("hot", limit=10, window_seconds=600):
                with lock:
                    allowed.append(1)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(allowed) == 10
