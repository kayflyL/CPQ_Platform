"""探查商机库：看有没有持久化的「客户需求文本」可拿来批量验证推理流。
用法：python -X utf8 backend/scripts/inspect_opportunity_requirements.py
只读、不改库。"""
import sys, json
sys.path.insert(0, r'D:\CPQ_Platform_V1\backend')

from sqlalchemy import create_engine, text
from app.core.config import get_settings

# config.py 默认 postgres/961216（见 memory cpq-db-direct-query，别用 .env stale URL）
url = get_settings().DATABASE_URL
engine = create_engine(url, connect_args={"client_encoding": "UTF8"})

with engine.connect() as c:
    # 1. 总量 + 有 extra_fields 的
    total = c.execute(text("SELECT count(*) FROM opportunities.opportunities WHERE status='active'")).scalar()
    with_extra = c.execute(text(
        "SELECT count(*) FROM opportunities.opportunities "
        "WHERE status='active' AND extra_fields IS NOT NULL AND extra_fields::text NOT IN ('','null','{}')"
    )).scalar()
    print(f"[商机] active 总数={total}  有 extra_fields={with_extra}\n")

    # 2. 扫 extra_fields 全部出现过的 key（找需求文本候选字段）
    rows = c.execute(text(
        "SELECT opportunity_id, customer_name, extra_fields "
        "FROM opportunities.opportunities "
        "WHERE status='active' AND extra_fields IS NOT NULL AND extra_fields::text NOT IN ('','null','{}') "
        "LIMIT 200"
    )).fetchall()
    key_counter = {}
    for oid, cust, ef in rows:
        try:
            d = json.loads(ef) if isinstance(ef, str) else (ef or {})
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        for k in d:
            key_counter[k] = key_counter.get(k, 0) + 1
    print("[extra_fields key 出现频次 Top]")
    for k, n in sorted(key_counter.items(), key=lambda x: -x[1])[:25]:
        print(f"  {n:4d}  {k}")

    # 3. 找疑似需求文本的字段（key 含 requirement/需求/desc/note/brief，且 value 是较长文本）
    print("\n[疑似需求文本字段（key 含 requirement/需求/desc/note/brief/comment/text 且值较长）]")
    CAND_KEYS = ("requirement", "需求", "desc", "note", "brief", "comment", "text", "remark", "备注", "说明")
    shown = 0
    for oid, cust, ef in rows:
        try:
            d = json.loads(ef) if isinstance(ef, str) else (ef or {})
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            if not isinstance(v, str) or len(v) < 12:
                continue
            if any(c.lower() in k.lower() for c in CAND_KEYS):
                print(f"\n  ● {oid} | {cust or '-'} | key={k!r} len={len(v)}")
                print(f"    {v[:160]}{'…' if len(v)>160 else ''}")
                shown += 1
                if shown >= 12:
                    break
        if shown >= 12:
            break
    if not shown:
        print("  （没找到持久化的需求文本字段）")

    # 4. quotations 里有没有需求来源（Feed 附件 category=requirement）
    print("\n[需求附件 Feed（category=requirement）]")
    try:
        feed_cnt = c.execute(text(
            "SELECT count(*) FROM attachments.attachments WHERE category='requirement'"
        )).scalar()
        print(f"  category=requirement 附件数={feed_cnt}")
    except Exception as e:
        print(f"  附件表不可查: {e}")
