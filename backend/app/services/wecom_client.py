"""企业微信推送 — 通知中心的外推通道(第三条腿),双通道:

- 自建应用 message/send:定向到个人,需企微后台配可信域名/回调后放行可信IP;
  配置 notify.wecom = {enabled, corpid, agentid, secret}(secret write-only 掩码)。
- 群机器人 webhook:广播到群,零门槛;配置 notify.wecom.webhook_url(整 URL 含 key,同样掩码)。

正常通知走 enqueue_*(独立守护线程 + 队列,业务端点只入队);
send_text 同步直发,仅供联调/测试端点。失败只打日志,通知永不阻断流程。
"""
import json
import logging
import queue
import threading
import time

import requests

from app.repository.system_config_repo import SystemConfigRepository

logger = logging.getLogger(__name__)

_CONFIG_KEY = "notify.wecom"
_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"

_token_cache: dict = {"token": "", "expires_at": 0.0}
_lock = threading.Lock()
_queue: "queue.Queue" = queue.Queue()
_worker_started = False


def load_config() -> dict:
    repo = SystemConfigRepository()
    try:
        cfg = repo.get_value(_CONFIG_KEY, {}) or {}
    finally:
        repo.close()
    return cfg if isinstance(cfg, dict) else {}


def _enabled(cfg: dict = None) -> bool:
    cfg = cfg or load_config()
    return bool(cfg.get("enabled")) and bool(cfg.get("corpid")) and bool(cfg.get("secret"))


def _get_token(cfg: dict) -> str:
    now = time.time()
    with _lock:
        if _token_cache["token"] and _token_cache["expires_at"] > now:
            return _token_cache["token"]
        resp = requests.get(
            f"{_API_BASE}/gettoken",
            params={"corpid": cfg.get("corpid"), "corpsecret": cfg.get("secret")},
            timeout=8,
        )
        data = resp.json()
        if data.get("errcode"):
            raise RuntimeError(f"wecom gettoken failed: {data.get('errcode')} {data.get('errmsg')}")
        _token_cache["token"] = data["access_token"]
        _token_cache["expires_at"] = now + int(data.get("expires_in", 7200)) - 300
        return _token_cache["token"]


def _post_message(payload: dict, cfg: dict) -> dict:
    resp = requests.post(
        f"{_API_BASE}/message/send",
        params={"access_token": _get_token(cfg)},
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=8,
    )
    data = resp.json()
    if data.get("errcode") in (40014, 42001):  # token 失效:清缓存重试一次
        with _lock:
            _token_cache["token"] = ""
            _token_cache["expires_at"] = 0.0
        resp = requests.post(
            f"{_API_BASE}/message/send",
            params={"access_token": _get_token(cfg)},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=8,
        )
        data = resp.json()
    return data


def send_text(touser: str, content: str, agentid=None) -> dict:
    """同步直发一条应用文本(联调/测试用)。touser=企微 userid,@all=可见范围全员。"""
    cfg = load_config()
    if not _enabled(cfg):
        return {"ok": False, "skipped": True, "message": "notify.wecom 未启用"}
    payload = {
        "touser": touser or "@all",
        "msgtype": "text",
        "agentid": int(agentid or cfg.get("agentid") or 0),
        "text": {"content": (content or "")[:2000]},
    }
    data = _post_message(payload, cfg)
    return {"ok": not data.get("errcode"), **data}


def _post_webhook(webhook_url: str, content: str, mentioned=None) -> dict:
    text = {"content": (content or "")[:2000]}
    if mentioned:
        text["mentioned_list"] = [m for m in mentioned if m]
    resp = requests.post(webhook_url, json={"msgtype": "text", "text": text}, timeout=8)
    data = resp.json()
    return {"ok": data.get("errcode") == 0, **data}


def _worker() -> None:
    while True:
        try:
            kind, a, b = _queue.get()
            if kind == "webhook":
                result = _post_webhook(a, b.get("content", ""), b.get("mentioned"))
            else:
                result = send_text(a, b)
            if not result.get("ok") and not result.get("skipped"):
                logger.warning("wecom push failed: %s", result)
        except Exception as exc:
            logger.warning("wecom push error: %s", exc)
        finally:
            _queue.task_done()


def _ensure_worker() -> None:
    global _worker_started
    if _worker_started:
        return
    with _lock:
        if _worker_started:
            return
        threading.Thread(target=_worker, name="wecom-push", daemon=True).start()
        _worker_started = True


def enqueue_text(tousers, content: str) -> None:
    """异步入队推应用文本;tousers=企微 userid 列表(| 分隔)。应用通道未启用时静默跳过。"""
    targets = [t for t in (tousers or []) if t]
    if not targets or not _enabled():
        return
    _ensure_worker()
    _queue.put(("app", "|".join(targets), content))


def enqueue_webhook(content: str, mentioned=None) -> None:
    """异步入队广播到群机器人(notify.wecom.webhook_url 配了才发)。
    mentioned=要真 @ 的企微 userid 列表(不在群里时企微自动忽略)。"""
    url = str(load_config().get("webhook_url") or "")
    if not url:
        return
    _ensure_worker()
    _queue.put(("webhook", url, {"content": content, "mentioned": mentioned}))
