"""商机四步流程 RBAC 矩阵 e2e — 权限审计修复(P1-P3)回归。

隔离跑法（别动用户在 8000 的实例）：
    cd backend
    python -X utf8 -m uvicorn app.main:app --port 8001
    python -X utf8 tests/perm_matrix_e2e.py            # 默认打 http://127.0.0.1:8001

覆盖：
- oppA 正流程 + 全程越权断言（角色 action key / 阶段 409 / 成本附件读写门控 / 洗白拦截 / 总监 A1 可见成本+只读
  / 商机状态门控 action.opportunity.result / 节点任务队列 /opps?node= 口径）
- oppB 乱序提交（成本先于方案 → 409；方案提交后回头再提 → 409）
- oppD 工程加固 + 审批门（第二轮）：指派角色校验 409 / 旧 tasks 端点 404·scope=pool 400 /
  草稿乐观锁 409（方案/成本/报价单三处）/ 退回空原因 422 /
  低毛利审批门全链路（拦 409→驳回→新单→批准→放行）/ 通知断言
- oppE 调度台（第五轮）：dispatch 快照 nodes/stuck/matrix / 无主 suggest /
  规则矩阵 PUT+DELETE / 定向 autofill（只补测试商机，生产共库不碰真实卡死流程）
清理：测试用户 is_active=False；测试商机连同流程/方案/成本/报价/卡片/通知硬删
（共享的是生产库，软删会留残留——2026-09-16 用户点进残留商机踩出 409）
"""
import os
import sys
import uuid

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:8001").rstrip("/")
PASSWORD = "PermTest#123"

USERS = {
    "admin": ("权限测试-管理员", "admin"),
    "biz": ("权限测试-业务", "business"),
    "te": ("权限测试-技术", "te"),
    "cost": ("权限测试-成本", "cost"),
    "quote": ("权限测试-报价", "quote"),
    "director": ("权限测试-总监", "director"),
}

RESULTS = []

_SESSIONS = {}  # token -> requests.Session（连接池复用，防临时端口耗尽）


def check(desc, resp, expect):
    ok = resp.status_code == expect
    RESULTS.append((ok, desc, expect, resp.status_code))
    mark = "PASS" if ok else "FAIL"
    detail = "" if ok else f"（期望 {expect} 实得 {resp.status_code}: {resp.text[:120]}）"
    print(f"  [{mark}] {desc} {detail}")
    return resp


def api(token, method, path, expect=None, desc=None, **kw):
    # 连接池复用（每 token 一个 Session）：Windows 临时端口耗尽会 10048
    sess = _SESSIONS.setdefault(token, requests.Session())
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = sess.request(method, BASE + path, headers=headers, timeout=30, **kw)
    if desc is not None:
        check(desc, r, expect)
    return r


def login(name):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": name, "password": PASSWORD}, timeout=15)
    r.raise_for_status()
    token = r.json()["token"]
    _SESSIONS[token] = s
    return token


# ── setup：直连 DB 建测试用户 + 商机 ──

def setup_fixtures():
    from app.core.security import hash_password
    from app.repository.feed_user_repo import FeedUserRepository
    from app.repository.opportunity_repo import OpportunityRepository

    urepo = FeedUserRepository()
    try:
        user_ids = {}
        for key, (name, role) in USERS.items():
            existing = urepo.get_by_name(name)
            if existing:
                uid = existing["user_id"]
                urepo.set_password(uid, hash_password(PASSWORD))
                urepo.update_role(uid, role)
                urepo.update_active(uid, True)
            else:
                uid = urepo.create_user(name=name, role=role,
                                        password_hash=hash_password(PASSWORD))["user_id"]
            user_ids[key] = uid
    finally:
        urepo.close()

    suffix = uuid.uuid4().hex[:6]
    opp_a = f"OPP-PERMTEST-A-{suffix}"
    opp_b = f"OPP-PERMTEST-B-{suffix}"
    opp_c = f"OPP-PERMTEST-C-{suffix}"
    orepo = OpportunityRepository()
    try:
        for opp_id, label in ((opp_a, "A角色矩阵"), (opp_b, "B乱序阶段"),
                              (opp_c, "C乱序依赖")):
            orepo.create_or_update_opportunity(opp_id, {
                "customer_name": f"[权限测试{label}]",
                "owner_user_id": user_ids["biz"],
                "fae": "",
            })
    finally:
        orepo.close()
    return user_ids, opp_a, opp_b, opp_c


def set_flow_assignees(opp_id, assignees):
    """直接改写流程指派（模拟管理员提前/改派指派的合法状态），
    以便让被指派人过访问层、真正打到阶段校验 409。无流程自动建。"""
    from app.repository.flow_repo import FlowRepository

    repo = FlowRepository()
    try:
        flow = repo.get_or_create_flow(opp_id)
        flow.assignees = dict(assignees)
        repo.session.commit()
    finally:
        repo.close()


def cleanup(*opp_ids):
    from app.models.base import Opportunity_SessionLocal
    from app.repository.feed_user_repo import FeedUserRepository

    urepo = FeedUserRepository()
    try:
        for name, _ in USERS.values():
            u = urepo.get_by_name(name)
            if u:
                urepo.update_active(u["user_id"], False)
    finally:
        urepo.close()

    s = Opportunity_SessionLocal()
    try:
        from sqlalchemy import text
        # 子表→父表硬删，与生产库共库不留残留（软删行仍可被直接打开）
        stmts = [
            "delete from opportunities.quotation_items where quotation_id in"
            " (select quotation_id from opportunities.quotations where opportunity_id = :o)",
            "delete from opportunities.opportunity_pricing_approvals where opportunity_id = :o",
            "delete from opportunities.notifications where opportunity_id = :o",
            "delete from opportunities.opportunity_messages where opportunity_id = :o",
            "delete from opportunities.opportunity_attachments where opportunity_id = :o",
            "delete from opportunities.opportunity_flow_card_links where opportunity_id = :o",
            "delete from opportunities.opportunity_flow_cards where opportunity_id = :o",
            "delete from opportunities.opportunity_cost_sheets where opportunity_id = :o",
            "delete from opportunities.opportunity_bom_schemes where opportunity_id = :o",
            "delete from opportunities.opportunity_requirements where opportunity_id = :o",
            "delete from opportunities.opportunity_flow_nodes where flow_id in"
            " (select flow_id from opportunities.opportunity_flows where opportunity_id = :o)",
            "delete from opportunities.quotations where opportunity_id = :o",
            "delete from opportunities.opportunity_flows where opportunity_id = :o",
            "delete from opportunities.opportunities where opportunity_id = :o",
        ]
        for opp_id in opp_ids:
            for sql in stmts:
                s.execute(text(sql), {"o": opp_id})
        s.commit()
    finally:
        s.close()


# ── oppA：正流程 + 越权矩阵 ──

def run_opp_a(tok, opp_a):
    biz, te, cost, quote, director = (tok[k] for k in
                                      ("biz", "te", "cost", "quote", "director"))
    TE, COST, QUOTE = USERS["te"][0], USERS["cost"][0], USERS["quote"][0]
    print(f"\n== oppA {opp_a} 正流程 + 越权矩阵 ==")

    print("-- 需求阶段 --")
    api(biz, "GET", f"/api/portal/opp/{opp_a}/board", 200, "业务(owner)看板 200")
    api(te, "GET", f"/api/portal/opp/{opp_a}/board", 403, "技术未指派无访问权 403")
    api(te, "POST", f"/api/portal/opp/{opp_a}/initiate", 403,
        "技术越权发起需求 403", json={"assignee_name": TE})
    api(biz, "POST", f"/api/portal/opp/{opp_a}/initiate", 409,
        "发起无下游人选 409", json={})
    api(biz, "POST", f"/api/portal/opp/{opp_a}/initiate", 200,
        "业务发起需求(指派技术) 200",
        json={"opportunity": {}, "slots": {"cpu": "测试"},
              "requirement_text": "权限矩阵测试", "assignee_name": TE})
    r = api(te, "GET", f"/api/portal/opp/{opp_a}/board", 200,
            "技术(已指派)看板 200")
    rendered = ((r.json().get("flow") or {}).get("assignees") or {}).get("boming")
    ok = rendered == TE
    RESULTS.append((ok, "看板 flow.assignees 出口渲染为姓名", "-", rendered))
    print(f"  [{'PASS' if ok else 'FAIL'}] 看板 flow.assignees 出口渲染为姓名（实得 {rendered!r}）")
    api(biz, "POST", f"/api/portal/opp/{opp_a}/requirements", 409,
        "流程已过需求再重提 409", json={"slots": {}, "requirement_text": "x"})

    print("-- 方案配置阶段 --")
    api(biz, "POST", f"/api/portal/opp/{opp_a}/bom-schemes/draft", 403,
        "业务越权存方案草稿 403", json={"name": "越权", "configs": []})
    r = api(te, "POST", f"/api/portal/opp/{opp_a}/bom-schemes/draft", 200,
            "技术存方案草稿 200",
            json={"name": "方案A", "configs": [
                {"name": "配置A", "server_model": "TEST-2U", "qty": 1}]})
    scheme_id = r.json()["scheme"]["id"]
    api(te, "POST", f"/api/portal/opp/{opp_a}/bom-schemes/{scheme_id}/submit", 409,
        "提交无下游人选 409", json={})
    api(biz, "POST", f"/api/portal/opp/{opp_a}/bom-schemes/{scheme_id}/submit", 403,
        "业务越权提方案 403", json={"assignee_name": COST})
    api(te, "POST", f"/api/portal/opp/{opp_a}/bom-schemes/{scheme_id}/submit", 200,
        "技术提交方案(指派成本) 200", json={"assignee_name": COST})

    print("-- 成本核算阶段 + 成本附件门控 --")
    api(cost, "GET", f"/api/portal/opp/{opp_a}/board", 200, "成本(已指派)看板 200")
    r = api(cost, "POST", f"/api/feed/{opp_a}/attachments", 200,
            "成本上传成本附件 200",
            files={"file": ("成本明细.xlsx", b"fake-xlsx-bytes",
                            "application/vnd.ms-excel")},
            data={"category": "requirement"})
    att_id = r.json()["attachment"]["attachment_id"]
    api(cost, "GET", f"/api/feed/attachments/{att_id}/download", 200,
        "成本下载成本附件 200")
    api(biz, "GET", f"/api/feed/attachments/{att_id}/download", 403,
        "业务(owner)下载成本附件 403（类别门控）")
    r = api(biz, "GET", f"/api/feed/{opp_a}/attachments", 200,
            "业务(owner)拉附件列表 200（用于断言过滤）")
    biz_cats = {a["category"] for a in r.json().get("attachments", [])}
    ok = "requirement" not in biz_cats
    RESULTS.append((ok, "业务附件列表不含成本附件", "-", biz_cats))
    print(f"  [{'PASS' if ok else 'FAIL'}] 业务附件列表不含成本附件（实得 {biz_cats}）")
    api(te, "GET", f"/api/portal/opp/{opp_a}/board", 200,
        "技术(阶段已过)回看看板 200（历史指派人保留访问权）")
    r = api(te, "GET", f"/api/portal/opp/{opp_a}/board", 200, None)
    te_sheets = r.json().get("cost_sheets")
    ok = te_sheets == []
    RESULTS.append((ok, "技术回看成本表仍被裁剪", "-", te_sheets))
    print(f"  [{'PASS' if ok else 'FAIL'}] 技术回看成本表仍被裁剪（实得 {te_sheets}）")
    api(te, "POST", f"/api/portal/opp/{opp_a}/cost-sheets/draft", 403,
        "技术回看期越权存成本草稿 403", json={"name": "越权", "configs": []})
    api(biz, "PATCH", f"/api/feed/attachments/{att_id}/category", 403,
        "业务挪成本附件到方案桶(洗白) 403", json={"category": "technical"})

    api(biz, "POST", f"/api/portal/opp/{opp_a}/cost-sheets/draft", 403,
        "业务越权存成本草稿 403", json={"name": "越权", "configs": []})
    r = api(cost, "POST", f"/api/portal/opp/{opp_a}/cost-sheets/draft", 200,
            "成本存成本草稿 200",
            json={"name": "成本A", "configs": [
                {"name": "配置A", "qty": 1, "l6_cost": 100}]})
    sheet_id = r.json()["sheet"]["id"]
    api(biz, "POST", f"/api/portal/opp/{opp_a}/cost-sheets/{sheet_id}/submit", 403,
        "业务越权提成本 403", json={"assignee_name": QUOTE})
    r = api(cost, "POST", f"/api/portal/opp/{opp_a}/cost-sheets/{sheet_id}/submit",
            200, "成本提交(指派报价) 200", json={"assignee_name": QUOTE})
    quotation_id = r.json().get("quotation_id", "")

    print("-- 报价单阶段 --")
    api(quote, "GET", f"/api/portal/opp/{opp_a}/board", 200, "报价(已指派)看板 200")
    api(biz, "POST", f"/api/portal/opp/{opp_a}/convert-to-quotation", 403,
        "业务越权转报价 403", json={"quotation_id": quotation_id})
    api(cost, "POST", f"/api/portal/opp/{opp_a}/convert-to-quotation", 403,
        "成本越权转报价 403", json={"quotation_id": quotation_id})
    api(quote, "POST", f"/api/portal/opp/{opp_a}/convert-to-quotation", 200,
        "报价转报价草稿 200", json={"quotation_id": quotation_id})

    print("-- 总监 A1 可见性 + 只读裁剪 --")
    r = api(director, "GET", f"/api/portal/opp/{opp_a}/board", 200, "总监看板 200")
    sheets = r.json().get("cost_sheets")
    ok = isinstance(sheets, list) and len(sheets) >= 1
    RESULTS.append((ok, "总监(A1)可看成本表", ">=1", len(sheets or [])))
    print(f"  [{'PASS' if ok else 'FAIL'}] 总监(A1)可看成本表（实得 {len(sheets or [])} 张）")
    r = api(director, "GET", f"/api/feed/{opp_a}/attachments", 200,
            "总监附件列表 200（用于断言可见性）")
    d_cats = {a["category"] for a in r.json().get("attachments", [])}
    ok = "requirement" in d_cats
    RESULTS.append((ok, "总监(A1)可见成本附件", "in", d_cats))
    print(f"  [{'PASS' if ok else 'FAIL'}] 总监(A1)可见成本附件（实得 {d_cats}）")
    api(director, "POST", f"/api/portal/opp/{opp_a}/cost-sheets/{sheet_id}/submit",
        403, "总监越权提成本 403", json={"assignee_name": QUOTE})

    print("-- 商机状态权限门控 + 节点任务队列(/opps?node=) --")
    api(te, "PUT", f"/api/opportunities/{opp_a}/meta", 403,
        "技术改商机状态 403", json={"result": "won"})
    api(cost, "PUT", f"/api/opportunities/{opp_a}/meta", 403,
        "成本改商机状态 403", json={"result": "won"})
    api(quote, "PUT", f"/api/opportunities/{opp_a}/meta", 200,
        "报价员改商机状态 200", json={"result": "won"})
    api(biz, "PUT", f"/api/opportunities/{opp_a}/meta", 200,
        "业务改回商机状态 200", json={"result": "pending"})
    r = api(quote, "GET", "/api/portal/opps?node=quoting&scope=mine", 200,
            "报价员节点任务队列 200")
    cards = r.json().get("cards", [])
    ok = any(c.get("opportunity_id") == opp_a for c in cards)
    RESULTS.append((ok, "报价队列含 oppA（node=quoting&scope=mine）", "in", len(cards)))
    print(f"  [{'PASS' if ok else 'FAIL'}] 报价队列含 oppA（实得 {len(cards)} 条）")
    card = next((c for c in cards if c.get("opportunity_id") == opp_a), {})
    ok = card.get("current_node") == "quoting" and "quotation_count" in card
    RESULTS.append((ok, "任务卡片口径=商机卡片（流程节点+报价份数）", "-", card.get("current_node")))
    print(f"  [{'PASS' if ok else 'FAIL'}] 任务卡片口径=商机卡片（实得 {card.get('current_node')}）")
    api(te, "GET", "/api/portal/opps?node=boming&scope=all", 403,
        "非管理员看全部任务队列 403")
    r = api(quote, "GET", f"/api/portal/opps?node=quoting&scope=mine&search={opp_a}",
            200, "节点队列按商机号搜索 200")
    ids = [c.get("opportunity_id") for c in r.json().get("cards", [])]
    ok = ids == [opp_a]
    RESULTS.append((ok, "节点队列搜索命中 oppA（同商机列表口径）", "==", ids))
    print(f"  [{'PASS' if ok else 'FAIL'}] 节点队列搜索命中 oppA（实得 {ids}）")
    r = api(quote, "GET", "/api/portal/opps?node=quoting&scope=mine&search=不存在的搜索词XYZ",
            200, "节点队列空结果搜索 200")
    ok = not r.json().get("cards")
    RESULTS.append((ok, "节点队列搜索无命中返回空", "0", len(r.json().get("cards") or [])))
    print(f"  [{'PASS' if ok else 'FAIL'}] 节点队列搜索无命中返回空（实得 {len(r.json().get('cards') or [])} 条）")
    return quotation_id


# ── oppB：乱序提交 ──

def run_opp_b(tok, opp_b, opp_c):
    biz, te, cost = tok["biz"], tok["te"], tok["cost"]
    TE, COST = USERS["te"][0], USERS["cost"][0]
    print(f"\n== oppB {opp_b} 乱序提交 ==")

    # 需求单仅存草稿（未提交）：门户卡片 slots 与线索页同口径（current 优先、draft 回退）
    api(biz, "POST", f"/api/portal/opp/{opp_b}/requirements/draft", 200,
        "业务先存需求草稿 200",
        json={"slots": {"platform_type": "测试平台", "purchase_qty": 3},
              "requirement_text": "草稿口径测试"})
    r = api(biz, "GET", f"/api/portal/opps?search={opp_b}", 200,
            "商机卡片按商机号搜索 200")
    cards = r.json().get("cards", [])
    card = next((c for c in cards if c.get("opportunity_id") == opp_b), {})
    ok = card.get("platform_type") == "测试平台" and card.get("purchase_qty") == 3
    RESULTS.append((ok, "草稿需求单 slots 回退（平台/数量不空）", "-",
                    f"{card.get('platform_type')}/{card.get('purchase_qty')}"))
    print(f"  [{'PASS' if ok else 'FAIL'}] 草稿需求单 slots 回退（实得 "
          f"{card.get('platform_type')}/{card.get('purchase_qty')}）")

    api(biz, "POST", f"/api/portal/opp/{opp_b}/initiate", 200,
        "业务发起需求(指派技术) 200",
        json={"slots": {}, "requirement_text": "乱序测试", "assignee_name": TE})
    # 乱序#1：管理员把成本用户改派为当前(boming)节点处理人 → 过访问层，
    # 但成本阶段未开（方案未提交）→ 提交成本必须 409
    set_flow_assignees(opp_b, {"boming": COST})
    api(cost, "GET", f"/api/portal/opp/{opp_b}/board", 200,
        "成本(被改派为当前处理人)看板 200")
    r = api(cost, "POST", f"/api/portal/opp/{opp_b}/cost-sheets/draft", 200,
            "成本先存草稿 200",
            json={"name": "乱序成本", "configs": [{"name": "配置B", "qty": 1}]})
    sheet_id = r.json()["sheet"]["id"]
    api(cost, "POST", f"/api/portal/opp/{opp_b}/cost-sheets/{sheet_id}/submit", 409,
        "方案未提交时提成本 409（阶段校验）", json={"assignee_name": USERS["quote"][0]})

    # 乱序#2：oppC 需求尚未发起、管理员提前把技术指派为需求节点处理人 →
    # 技术过访问层，但方案阶段未开 → 提交方案必须 409
    set_flow_assignees(opp_c, {"requirement": TE})
    r = api(te, "POST", f"/api/portal/opp/{opp_c}/bom-schemes/draft", 200,
            "技术(需求未提)存方案草稿 200",
            json={"name": "方案C", "configs": [{"name": "配置C", "qty": 1}]})
    scheme_id = r.json()["scheme"]["id"]
    api(te, "POST", f"/api/portal/opp/{opp_c}/bom-schemes/{scheme_id}/submit", 409,
        "需求未提交时提方案 409（阶段校验）", json={"assignee_name": COST})


def verify_uid_storage(opp_a, user_ids):
    """指派存储断言：assignees 落库必须是 user_id 而非姓名。"""
    from app.models.flow import OpportunityFlow
    from app.models.base import Opportunity_SessionLocal

    s = Opportunity_SessionLocal()
    try:
        flow = s.query(OpportunityFlow).filter(
            OpportunityFlow.opportunity_id == opp_a).first()
        stored = dict(flow.assignees or {}) if flow else {}
    finally:
        s.close()
    expect = {"boming": user_ids["te"], "costing": user_ids["cost"],
              "quoting": user_ids["quote"]}
    for node, uid in expect.items():
        ok = stored.get(node) == uid
        RESULTS.append((ok, f"assignees.{node} 落库为 user_id", uid, stored.get(node)))
        print(f"  [{'PASS' if ok else 'FAIL'}] assignees.{node} 落库为 user_id"
              f"（期望 {uid} 实得 {stored.get(node)}）")


# ── 工程加固 + 审批门（第二轮：P4/P5/P6/P7/P1/P2）──

def with_margin_gate(threshold=50.0):
    """临时把 margin_alert 审批红线抬到 threshold（任何毛利都低于线）；返回恢复句柄。"""
    from app.repository.strategy_repo import StrategyRepository

    body = {"enabled": True, "threshold": threshold,
            "approval_threshold": threshold, "title": "e2e", "content": "e2e"}
    repo = StrategyRepository()
    try:
        rows = repo.list(domain="pricing", status="active", type="margin_alert")
        if rows:
            repo.update(rows[0]["id"], {"body": body}, operator="e2e")
            return ("update", rows[0]["id"], rows[0].get("body"))
        created = repo.create({"domain": "pricing", "type": "margin_alert",
                               "name": "利润率告警", "scope": None,
                               "body": body, "status": "active"}, operator="e2e")
        return ("create", created["id"], None)
    finally:
        repo.close()


def restore_margin_gate(handle):
    if not handle:
        return
    from app.repository.strategy_repo import StrategyRepository

    kind, sid, backup = handle
    repo = StrategyRepository()
    try:
        if kind == "update":
            repo.update(sid, {"body": backup}, operator="e2e")
        else:
            repo.delete(sid)
    finally:
        repo.close()


def stamp_exported_low_margin(quotation_id, margin=5.0):
    """绕过导出 UI：直接盖 exported_at + 低毛利成本快照（后端权威口径）。"""
    from datetime import datetime as dt
    from app.repository.quotation_repo import QuotationRepository

    repo = QuotationRepository()
    try:
        repo.update(
            quotation_id,
            exported_at=dt.now().isoformat(),
            cost_snapshot={"totals": {"marginPct": margin, "totalSales": 1000},
                           "configs": {}},
        )
    finally:
        repo.close()


def add_sent_quote_attachment(opp_id, quotation_id, uploader_uid):
    from app.repository.feed_repo import FeedRepository

    repo = FeedRepository()
    try:
        return repo.add_attachment(
            opportunity_id=opp_id, uploader_user_id=uploader_uid,
            original_filename="e2e-报价.xlsx", storage_key="e2e/fake.xlsx",
            file_size=12, mime_type="application/vnd.ms-excel",
            kind="export", quotation_id=quotation_id, category="sent_quote",
        )
    finally:
        repo.close()


def run_hardening(tok, opp_d, user_ids):
    biz, te, cost, quote, director = (tok[k] for k in
                                      ("biz", "te", "cost", "quote", "director"))
    BIZ, TE, COST, QUOTE = (USERS[k][0] for k in ("biz", "te", "cost", "quote"))
    print(f"\n== oppD {opp_d} 加固 + 审批门 ==")

    # P4 指派角色校验：非系统用户 / 角色不匹配
    api(biz, "POST", f"/api/portal/opp/{opp_d}/initiate", 200,
        "业务发起需求(指派技术) 200",
        json={"slots": {}, "requirement_text": "加固测试", "assignee_name": TE})
    api(te, "POST", f"/api/portal/opp/{opp_d}/assign", 409,
        "指派非系统用户 409",
        json={"node_key": "boming", "assignee_name": "路人甲"})
    api(te, "POST", f"/api/portal/opp/{opp_d}/assign", 409,
        "指派角色不匹配(cost 角色进 boming) 409",
        json={"node_key": "boming", "assignee_name": COST})
    api(cost, "POST", f"/api/portal/opp/{opp_d}/assign", 403,
        "非当前处理人越权指派 403",
        json={"node_key": "boming", "assignee_name": TE})

    # P5 任务队列已并入 /api/portal/opps?node=…：旧端点 404，scope=pool 400
    api(te, "GET", "/api/portal/tasks?scope=pool", 404, "旧 /api/portal/tasks 已删除 404")
    api(te, "GET", "/api/portal/opps?node=boming&scope=pool", 400, "scope=pool 已退役 400")

    # P6 乐观锁：BOM 草稿带过期基线
    r = api(te, "POST", f"/api/portal/opp/{opp_d}/bom-schemes/draft", 200,
            "技术存方案草稿 200",
            json={"name": "方案D", "configs": [{"name": "配置D", "qty": 1}]})
    scheme = r.json()["scheme"]
    api(te, "POST", f"/api/portal/opp/{opp_d}/bom-schemes/draft", 409,
        "方案草稿乐观锁冲突 409",
        json={"scheme_id": scheme["id"], "name": "方案D",
              "configs": scheme.get("configs") or [],
              "expected_updated_at": "2000-01-01T00:00:00"})
    api(te, "POST", f"/api/portal/opp/{opp_d}/bom-schemes/{scheme['id']}/submit", 200,
        "技术提交方案(指派成本) 200", json={"assignee_name": COST})

    r = api(cost, "POST", f"/api/portal/opp/{opp_d}/cost-sheets/draft", 200,
            "成本存成本草稿 200",
            json={"name": "成本D", "configs": [{"name": "配置D", "qty": 1}]})
    sheet = r.json()["sheet"]
    api(cost, "POST", f"/api/portal/opp/{opp_d}/cost-sheets/draft", 409,
        "成本草稿乐观锁冲突 409",
        json={"sheet_id": sheet["id"], "name": "成本D",
              "configs": sheet.get("configs") or [],
              "expected_updated_at": "2000-01-01T00:00:00"})
    r = api(cost, "POST", f"/api/portal/opp/{opp_d}/cost-sheets/{sheet['id']}/submit",
            200, "成本提交(指派报价) 200", json={"assignee_name": QUOTE})
    quotation_id = r.json().get("quotation_id", "")
    api(quote, "POST", f"/api/portal/opp/{opp_d}/convert-to-quotation", 200,
        "报价转报价草稿 200", json={"quotation_id": quotation_id})

    # P7 退回原因必填：空原因 422
    r = api(quote, "GET", f"/api/portal/opp/{opp_d}/cards", 200, "报价拉流转卡 200")
    cards = r.json().get("cards", [])
    card = next((c for c in cards if c.get("current_node") == "quoting"), None)
    if card:
        api(quote, "POST",
            f"/api/portal/opp/{opp_d}/cards/{card['id']}/return", 422,
            "退回空原因 422", json={"comment": "   "})
    else:
        RESULTS.append((False, "找到 quoting 节点流转卡", "card", None))
        print("  [FAIL] 找到 quoting 节点流转卡")

    # P6 报价单乐观锁
    api(quote, "PUT", f"/api/quotations/{quotation_id}", 409,
        "报价单乐观锁冲突 409",
        json={"expected_updated_at": "2000-01-01T00:00:00",
              "config_descriptions": {"配置D": "e2e"}})

    # P2 审批门全链路
    stamp_exported_low_margin(quotation_id)
    att = add_sent_quote_attachment(opp_d, quotation_id, user_ids["quote"])
    r = api(quote, "POST",
            f"/api/portal/opp/{opp_d}/quotes/{quotation_id}/submit", 409,
            "低毛利发送被拦 409", json={"attachment_id": att["attachment_id"]})
    r = api(director, "GET",
            f"/api/portal/opp/{opp_d}/pricing-approvals", 200,
            "总监拉商机内审批单列表 200")
    approvals = r.json().get("approvals", [])
    ok = any(a["quotation_id"] == quotation_id and a["status"] == "pending"
             for a in approvals)
    RESULTS.append((ok, "审批单已自动创建且 pending", True, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] 审批单已自动创建且 pending")
    approval_id = next((a["id"] for a in approvals
                        if a["quotation_id"] == quotation_id
                        and a["status"] == "pending"), None)
    api(quote, "POST",
        f"/api/portal/opp/{opp_d}/pricing-approvals/{approval_id}/decide", 403,
        "报价员无审批裁决权 403", json={"decision": "approve"})

    api(director, "POST",
        f"/api/portal/opp/{opp_d}/pricing-approvals/{approval_id}/decide", 422,
        "驳回无意见 422", json={"decision": "reject"})
    api(director, "POST",
        f"/api/portal/opp/{opp_d}/pricing-approvals/{approval_id}/decide", 200,
        "总监驳回(带意见) 200",
        json={"decision": "reject", "comment": "毛利太低，重新核价"})
    api(quote, "POST",
        f"/api/portal/opp/{opp_d}/quotes/{quotation_id}/submit", 409,
        "驳回后再发送仍拦并建新单 409",
        json={"attachment_id": att["attachment_id"]})
    r = api(director, "GET",
            f"/api/portal/opp/{opp_d}/pricing-approvals", 200, None)
    approval2 = next((a["id"] for a in r.json().get("approvals", [])
                      if a["quotation_id"] == quotation_id
                      and a["status"] == "pending"), None)
    ok = approval2 is not None and approval2 != approval_id
    RESULTS.append((ok, "驳回后重发创建新审批单", True, approval2))
    print(f"  [{'PASS' if ok else 'FAIL'}] 驳回后重发创建新审批单（#{approval_id} → #{approval2}）")
    api(director, "POST",
        f"/api/portal/opp/{opp_d}/pricing-approvals/{approval2}/decide", 200,
        "总监批准 200", json={"decision": "approve"})
    api(quote, "POST",
        f"/api/portal/opp/{opp_d}/quotes/{quotation_id}/submit", 200,
        "批准后发送 200", json={"attachment_id": att["attachment_id"]})

    # P1 通知：报价员应收到 task_assigned + 审批结果；总监应收到审批请求
    r = api(quote, "GET", "/api/notifications/unread-count", 200, None)
    n_quote = r.json().get("count", 0)
    ok = n_quote >= 2
    RESULTS.append((ok, "报价员通知≥2（任务+审批结果）", ">=2", n_quote))
    print(f"  [{'PASS' if ok else 'FAIL'}] 报价员通知≥2（实得 {n_quote}）")
    r = api(director, "GET", "/api/notifications/unread-count", 200, None)
    n_dir = r.json().get("count", 0)
    ok = n_dir >= 1
    RESULTS.append((ok, "总监收到审批请求通知", ">=1", n_dir))
    print(f"  [{'PASS' if ok else 'FAIL'}] 总监收到审批请求通知（实得 {n_dir}）")
    # 通知中心：未读分组 + 单条删除 + 清空已读
    r = api(director, "GET", "/api/notifications/unread-count", 200, None)
    by_type = r.json().get("by_type") or {}
    ok = by_type.get("pricing_approval_requested", 0) >= 1
    RESULTS.append((ok, "未读按类型分组含审批请求", ">=1",
                    by_type.get("pricing_approval_requested")))
    print(f"  [{'PASS' if ok else 'FAIL'}] 未读按类型分组含审批请求")
    r = api(director, "GET", "/api/notifications?unread_only=true&page_size=50",
            200, "总监拉未读列表 200")
    one = next((n["notification_id"] for n in r.json().get("notifications", [])
                if not n.get("read_at")), None)
    api(director, "DELETE", f"/api/notifications/{one}", 200, "单条删除 200")
    api(director, "DELETE", "/api/notifications/nonexistent", 404,
        "删不存在的通知 404")
    api(director, "POST", "/api/notifications/read-all", 200, "全部已读 200")
    r = api(director, "POST", "/api/notifications/clear-read", 200,
            "清空已读 200")
    ok = r.json().get("deleted", 0) >= 1
    RESULTS.append((ok, "清空已读删除条数≥1", ">=1", r.json().get("deleted")))
    print(f"  [{'PASS' if ok else 'FAIL'}] 清空已读删除条数≥1")
    api(quote, "POST", "/api/notifications/read-all", 200, None)
    r = api(quote, "GET", "/api/notifications/unread-count", 200, None)
    ok = r.json().get("count") == 0
    RESULTS.append((ok, "全部已读后未读归零", 0, r.json().get("count")))
    print(f"  [{'PASS' if ok else 'FAIL'}] 全部已读后未读归零")


# ── 调度台（第五轮：任务调度页重设计 —— 快照/无主/规则矩阵/一键补齐）──

def run_dispatch(tok, opp_e, user_ids):
    admin, biz, te = tok["admin"], tok["biz"], tok["te"]
    TE = USERS["te"][0]
    biz_uid = user_ids["biz"]
    print(f"\n== oppE {opp_e} 调度台 ==")

    api(biz, "POST", f"/api/portal/opp/{opp_e}/initiate", 200,
        "业务发起需求(指派技术) 200",
        json={"slots": {}, "requirement_text": "调度台测试", "assignee_name": TE})

    api(te, "GET", "/api/portal/dispatch", 403, "非管理员看调度台 403")
    api(te, "POST", "/api/portal/dispatch/autofill", 403,
        "非管理员一键补齐 403", json={"opportunity_ids": [opp_e]})

    # 规则矩阵 PUT（该端点首次有覆盖）
    api(admin, "PUT", "/api/portal/assignment-rules", 200,
        "管理员设默认规则(biz×boming→技术) 200",
        json={"business_user_id": biz_uid, "node_key": "boming",
              "assignee_name": TE})

    # 清空当前节点处理人 → 制造「无主」
    set_flow_assignees(opp_e, {})

    r = api(admin, "GET", "/api/portal/dispatch", 200, "管理员调度快照 200")
    data = r.json()
    node_keys = sorted(n.get("key") for n in data.get("nodes", []))
    ok = node_keys == ["boming", "costing", "quoting"]
    RESULTS.append((ok, "快照 nodes 含三条任务节点", "-", node_keys))
    print(f"  [{'PASS' if ok else 'FAIL'}] 快照 nodes 含三条任务节点（实得 {node_keys}）")
    stuck = data.get("stuck", [])
    item = next((s for s in stuck if s.get("opportunity_id") == opp_e), None)
    ok = item is not None and item.get("current_node") == "boming"
    RESULTS.append((ok, "无主清单含 oppE（节点=boming）", "in",
                    item and item.get("current_node")))
    print(f"  [{'PASS' if ok else 'FAIL'}] 无主清单含 oppE（实得节点 {item and item.get('current_node')}）")
    ok = bool(item) and item.get("suggest") == TE
    RESULTS.append((ok, "无主 suggest=默认规则(技术)", TE,
                    bool(item) and item.get("suggest")))
    print(f"  [{'PASS' if ok else 'FAIL'}] 无主 suggest=默认规则（实得 {bool(item) and item.get('suggest')!r}）")
    ok = data.get("matrix", {}).get(biz_uid, {}).get("boming", 0) >= 1
    RESULTS.append((ok, "matrix[biz][boming] 计入 oppE 活跃数", ">=1",
                    data.get("matrix", {}).get(biz_uid, {}).get("boming")))
    print(f"  [{'PASS' if ok else 'FAIL'}] matrix[biz][boming] 计入 oppE（实得 "
          f"{data.get('matrix', {}).get(biz_uid, {}).get('boming')}）")

    # 一键补齐：定向只补 oppE（生产共库，禁止连带改真实卡死流程）
    r = api(admin, "POST", "/api/portal/dispatch/autofill", 200,
            "定向一键补齐 200", json={"opportunity_ids": [opp_e]})
    ok = r.json().get("filled") == 1 and r.json().get("failed") == 0
    RESULTS.append((ok, "补齐恰好 1 条且无失败", "1/0",
                    f"{r.json().get('filled')}/{r.json().get('failed')}"))
    print(f"  [{'PASS' if ok else 'FAIL'}] 补齐恰好 1 条且无失败（实得 "
          f"{r.json().get('filled')}/{r.json().get('failed')}）")
    r = api(admin, "GET", "/api/portal/dispatch", 200, None)
    data = r.json()
    ok = not any(s.get("opportunity_id") == opp_e for s in data.get("stuck", []))
    RESULTS.append((ok, "补齐后 oppE 不再无主", "out", ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] 补齐后 oppE 不再无主")
    boming = next((n for n in data.get("nodes", [])
                   if n.get("key") == "boming"), {})
    ok = any(w.get("name") == TE and w.get("count", 0) >= 1
             for w in boming.get("workload", []))
    RESULTS.append((ok, "boming 负载含技术且计数≥1（姓名渲染）", ">=1",
                    boming.get("workload")))
    print(f"  [{'PASS' if ok else 'FAIL'}] boming 负载含技术且计数≥1（实得 {boming.get('workload')}）")
    ok = any(t.get("opportunity_id") == opp_e and t.get("to_assignee") == TE
             for t in data.get("transfers", []))
    RESULTS.append((ok, "转交记录含 oppE→技术（审计事件）", "in", ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] 转交记录含 oppE→技术（审计事件）")

    # 规则矩阵 DELETE（roundtrip 收尾，同步清掉测试规则）
    api(admin, "DELETE", "/api/portal/assignment-rules", 200,
        "管理员删默认规则 200",
        json={"business_user_id": biz_uid, "node_key": "boming",
              "assignee_name": ""})


def main():
    user_ids, opp_a, opp_b, opp_c = setup_fixtures()
    suffix = opp_a.rsplit("-", 1)[-1]
    opp_d = f"OPP-PERMTEST-D-{suffix}"
    opp_e = f"OPP-PERMTEST-E-{suffix}"
    tok = {k: login(name) for k, (name, _) in USERS.items()}
    gate = None
    try:
        run_opp_a(tok, opp_a)
        verify_uid_storage(opp_a, user_ids)
        run_opp_b(tok, opp_b, opp_c)
        from app.repository.opportunity_repo import OpportunityRepository
        orepo = OpportunityRepository()
        try:
            orepo.create_or_update_opportunity(opp_d, {
                "customer_name": "[权限测试D加固审批]",
                "owner_user_id": user_ids["biz"], "fae": ""})
            orepo.create_or_update_opportunity(opp_e, {
                "customer_name": "[权限测试E调度台]",
                "owner_user_id": user_ids["biz"], "fae": ""})
        finally:
            orepo.close()
        gate = with_margin_gate()
        run_hardening(tok, opp_d, user_ids)
        run_dispatch(tok, opp_e, user_ids)
    finally:
        restore_margin_gate(gate)
        cleanup(opp_a, opp_b, opp_c, opp_d, opp_e)
        # 规则兜底清理（roundtrip 中途失败也不给测试 biz 留规则）
        from app.repository.flow_repo import FlowRepository
        frepo = FlowRepository()
        try:
            frepo.delete_assignment_rule(user_ids["biz"], "boming")
        finally:
            frepo.close()

    fails = [r for r in RESULTS if not r[0]]
    print(f"\n== 结果：{len(RESULTS) - len(fails)}/{len(RESULTS)} 通过 ==")
    for _, desc, exp, got in fails:
        print(f"  FAIL {desc}（期望 {exp} 实得 {got}）")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
