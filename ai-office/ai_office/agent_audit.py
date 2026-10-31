# -*- coding: utf-8 -*-
"""agent_audit —— 写操作审计落账（P4）。fire-and-forget：失败仅日志，绝不挡业务。

写入点：registry.execute 对写语义工具（contract.effects="write"）成功执行后统一调用——
那是所有大脑工具调用的唯一入口；事务直达重放（_execute_pending）的审计列 P4 尾巴补。
"""
import logging

logger = logging.getLogger(__name__)


def audit_write(*, thread_id: str = "", agent_role_key: str = "", user_id: str = "",
                tool: str = "", args_digest: str = "", result_ok: bool = False,
                target_entity: str = "", entity_id: str = "", readback: str = "",
                note: str = "") -> None:
    """落一行审计账（自建会话，独立短事务；任何异常只记日志）。"""
    try:
        from datetime import datetime
        from app.models.base import Rules_SessionLocal
        from app.models.agent_audit import AgentAuditLog
        session = Rules_SessionLocal()
        try:
            session.add(AgentAuditLog(
                created_at=datetime.now().isoformat(timespec="seconds"),
                thread_id=str(thread_id or "")[:80],
                agent_role_key=str(agent_role_key or "")[:80],
                user_id=str(user_id or "")[:80],
                tool=str(tool or "")[:80],
                args_digest=str(args_digest or "")[:400],
                result_ok=bool(result_ok),
                target_entity=str(target_entity or "")[:80],
                entity_id=str(entity_id or "")[:80],
                readback=str(readback or "")[:2000],
                note=str(note or "")[:500],
            ))
            session.commit()
        finally:
            session.close()
    except Exception:
        logger.exception("审计落账失败（不挡业务）tool=%s", tool)
