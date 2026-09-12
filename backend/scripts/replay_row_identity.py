# -*- coding: utf-8 -*-
"""行身份回放（P3-4）：拿真实线程的 reasoning_state 在**新代码**下重跑 kp_reason 落地。

只读（零模型、零写库），量四件事：
  A 身份唯一性：同一份发布行里 row_id / origin 不得重复（一行不许有两份身份）→ 目标 0；
  B 同义重复行：同类目 + 同内容版本（row_content_rev）的行数 >1 → 目标 0
    （合法同类目多行——如「4个千兆网口」+「2个万兆网口」——内容版本不同，不计入）；
  C 旧数据兼容：picks / row_answers 的键形态（row_id / origin / 文本键）占比，
    证明升级不需要数据迁移，旧线程仍能解析；
  D 幂等：同一线程连跑两次，行身份逐项一致。

用法（backend 目录下）：
  .venv\\Scripts\\python.exe -X utf8 scripts\\replay_row_identity.py --limit 60
  .venv\\Scripts\\python.exe -X utf8 scripts\\replay_row_identity.py --json out.json
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
from psycopg2.extras import DictCursor

from app.core.config import get_settings
from app.services.part_selector import row_content_rev
from app.services.skill_phases import phase_kp_reason

SQL = """
SELECT thread_id, reasoning_state
FROM opportunities.assistant_threads
WHERE reasoning_state IS NOT NULL AND reasoning_state <> ''
ORDER BY updated_at DESC NULLS LAST
LIMIT %s
"""


def _key_shape(key: str) -> str:
    """键形态：引擎铸造的 row_id / 来源锚点 / 文本键（类目|描述）。"""
    k = str(key or "").strip()
    if k.startswith("kp-") and "|" not in k:
        return "row_id"
    if ":" in k and "|" not in k:
        return "origin"
    return "text"


def _build_ctx(state: dict) -> dict:
    """从存储的 skill_chat 状态重建 kp_reason 回合上下文（只取落地所需字段）。"""
    ext = state.get("ext") if isinstance(state.get("ext"), dict) else {}
    ns = state.get("node_state") if isinstance(state.get("node_state"), dict) else {}
    ctx: dict = {"ext": dict(ext), "node_state": ns,
                 "steps_done": state.get("steps_done") or []}
    base = state.get("locked_baseline")
    if isinstance(base, dict) and base:
        ctx["baselines"] = [base]
    elif ext.get("server_type_name") or ext.get("server_type"):
        ctx["baselines"] = [{"server_type_name": ext.get("server_type_name") or ext.get("server_type")}]
    return ctx


def _run(ctx: dict) -> list:
    asyncio.run(phase_kp_reason(ctx, {}, None))
    return [p for p in (ctx.get("kp_parts") or []) if isinstance(p, dict)]


def _dupes(parts: list) -> list:
    """BOM 里的同义重复行：同类目 + 同内容版本 + 同落地料（name）出现两次以上。

    组合件（一行需求由多颗料组成，如 NIC 一行 = 网卡+两口+光模块）料名不同，不算重复；
    客户登记了两条内容相同的行、或引擎重复铸行 → 算重复（P2 病象：11 行里有 2 行 RAID 卡）。
    """
    groups: dict = collections.defaultdict(list)
    for p in parts:
        cat = str(p.get("category") or "")
        desc = str(p.get("request_spec") or p.get("description") or "")
        groups[(cat, row_content_rev(cat, desc), str(p.get("name") or ""))].append(p)
    out = []
    for (cat, rev, name), rows in groups.items():
        if len(rows) > 1:
            out.append({"category": cat, "rev": rev, "name": name, "n": len(rows),
                        "origins": [str(r.get("origin") or "") for r in rows],
                        "descs": [str(r.get("request_spec") or "") for r in rows]})
    return out

def _published_rows(state: dict, parts: list) -> list:
    """按**发布口径**取行清单（bridge_ctx 的 kp_rows_all）——这是 AI 引用的权威表。"""
    from app.services.skill_node_plugins import plugin_for
    ext = state.get("ext") if isinstance(state.get("ext"), dict) else {}
    ns = state.get("node_state") if isinstance(state.get("node_state"), dict) else {}
    engine = {"ext": dict(ext), "kp_parts": parts, "node_state": ns,
              "flow_configs": {}}
    base = state.get("locked_baseline")
    if isinstance(base, dict) and base:
        engine["_locked_baseline"] = base
    ctx: dict = {}
    plugin_for("kp_reason").bridge_ctx(engine, ctx)
    return [r for r in (ctx.get("kp_rows_all") or []) if isinstance(r, dict)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    s = get_settings()
    conn = psycopg2.connect(host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
                            user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD,
                            client_encoding="UTF8")
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute(SQL, (args.limit,))
    threads = cur.fetchall()

    tot = {"threads": 0, "replayed": 0, "skipped": 0,
           "dup_row_id": 0, "dup_origin": 0, "synonym_rows": 0, "synonym_groups": 0,
           "idempotent_bad": 0, "rows": 0, "published_rows": 0,
           "landed": 0, "unmatched": 0, "legacy_pick_threads": 0, "legacy_pick_hit_threads": 0}
    key_shapes = collections.Counter()
    offenders: list = []
    skip_reasons = collections.Counter()

    for t in threads:
        tot["threads"] += 1
        raw = t["reasoning_state"]
        try:
            rs = json.loads(raw)
        except Exception:
            tot["skipped"] += 1
            skip_reasons["bad_json"] += 1
            continue
        state = None
        for _role, st in (rs or {}).items():
            if isinstance(st, dict) and (st.get("ext") or st.get("node_state")):
                state = st
                break
        if state is None:
            tot["skipped"] += 1
            skip_reasons["no_state"] += 1
            continue
        ext = state.get("ext") or {}
        if not (isinstance(ext.get("kp_rows"), list) and ext.get("kp_rows")):
            tot["skipped"] += 1
            skip_reasons["no_kp_rows"] += 1
            continue

        ctx = _build_ctx(state)
        parts = _run(ctx)
        again = [dict(p) for p in parts]
        ctx2 = _build_ctx(state)
        parts2 = _run(ctx2)
        tot["replayed"] += 1
        tot["rows"] += len(parts)
        if [(p.get("origin"), p.get("row_id")) for p in parts] != \
           [(p.get("origin"), p.get("row_id")) for p in parts2]:
            tot["idempotent_bad"] += 1
        pub = _published_rows(state, parts)
        ids = [str(r.get("row_id") or "") for r in pub]
        tot["published_rows"] += len(pub)
        tot["dup_row_id"] += len(ids) - len(set(ids))
        origins = [str(r.get("origin") or "") for r in pub]
        tot["dup_origin"] += len(origins) - len(set(origins))
        tot["landed"] += sum(1 for p in parts if not p.get("unmatched") and not p.get("waived"))
        tot["unmatched"] += sum(1 for p in parts if p.get("unmatched"))
        ds = _dupes(parts)
        tot["synonym_groups"] += len(ds)
        tot["synonym_rows"] += sum(d["n"] - 1 for d in ds)
        if ds:
            offenders.append({"thread_id": t["thread_id"], "dupes": ds})
        # 键形态（旧数据兼容性）
        for scope, store in (("node_state.picks", (state.get("node_state") or {}).get("kp_reason") or {}),
                             ("ext.kp_picks", ext)):
            picks = store.get("picks") if scope.startswith("node_state") else store.get("kp_picks")
            for k in (picks or {}):
                key_shapes[scope + ":" + _key_shape(k)] += 1
        _legacy = [k for k in (((state.get("node_state") or {}).get("kp_reason") or {}).get("picks") or {})
                   if _key_shape(k) == "text"] or [k for k in (ext.get("kp_picks") or {}) if _key_shape(k) == "text"]
        if _legacy:
            tot["legacy_pick_threads"] += 1
            if any(not p.get("unmatched") and not p.get("waived") for p in parts):
                tot["legacy_pick_hit_threads"] += 1
        for k in ((state.get("node_state") or {}).get("kp_reason") or {}).get("row_answers") or {}:
            key_shapes["row_answers:" + _key_shape(k)] += 1

    print("=" * 66)
    print("行身份回放（P3-4）：真实线程 reasoning_state → 新代码重跑 kp_reason")
    print("=" * 66)
    print(f"  取线程 {tot['threads']} / 回放 {tot['replayed']} / 跳过 {tot['skipped']} {dict(skip_reasons)}")
    print(f"  BOM 行合计 {tot['rows']} / 发布行合计（权威行清单）{tot['published_rows']}")
    print(f"  [A] 发布行身份唯一  重复 row_id = {tot['dup_row_id']}（目标 0）"
          f"，重复 origin = {tot['dup_origin']}（目标 0）")
    print(f"  [B] BOM 同义重复行  同类目+同内容+同料 的重复行数 = {tot['synonym_rows']}（目标 0）"
          f"，涉及 {tot['synonym_groups']} 组")
    print(f"  [D] 幂等        连跑两次身份不一致的线程 = {tot['idempotent_bad']}（目标 0）")
    print(f"  [E] 旧数据仍生效  文本键 pick 的线程 {tot['legacy_pick_threads']}，"
          f"其中回放后仍有落地行的 {tot['legacy_pick_hit_threads']}（升级无需迁移）")
    print(f"      落地行 {tot['landed']} / 未落地行 {tot['unmatched']}")
    print(f"  [C] 旧数据键形态 {dict(key_shapes)}")
    if offenders:
        print("\n  同义重复行明细（前 8 条）：")
        for o in offenders[:8]:
            for d in o["dupes"]:
                print(f"    - {o['thread_id'][:12]} {d['category']} ×{d['n']} "
                      f"{d['origins']} {d['descs']}")
    elif tot["replayed"]:
        print("\n  无同义重复行。")

    out = {"summary": tot, "key_shapes": dict(key_shapes), "offenders": offenders}
    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n  JSON → {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
