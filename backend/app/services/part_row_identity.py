# -*- coding: utf-8 -*-
"""配件行身份层（part_selector 拆分，2026-09-11）：行装配 / 行键 / 身份铸造 / pick 绑定。

身份由引擎铸造（P3）：row_id → origin → 精确行键，不猜文本。检索与落料都从这里取行身份。
"""
from __future__ import annotations

import hashlib
import re
import unicodedata


def _placeholder(db_cat, qty, want, origin=""):
    """确定性占位缺口行：把客户登记的需求原样呈现给 AI 选型，引擎不做预测。"""
    return _row(db_cat, None, int(qty or 1), unmatched=True,
                reason="待 AI 语义选型（引擎仅检索候选、不预判）",
                request_spec=str(want or ""), origin=origin)


def kp_rows_present(ext) -> bool:
    """登记表是否已登记部件（kp_rows 里有带类别或描述的部件行）。"""
    kp = (ext or {}).get("kp_rows")
    return isinstance(kp, list) and any(
        isinstance(r, dict) and (
            str(r.get("part_category") or r.get("category") or "").strip()
            or str(r.get("description") or "").strip())
        for r in kp)


def kp_rows_slot_keys(ext) -> set:
    """登记表 kp_rows 已覆盖的归一部件槽位（cpu/memory/storage/...），按 kp_slot_group_map 映射。"""
    try:
        from app.services.requirement_slots import _load_kp_slot_map
        m = _load_kp_slot_map()
    except Exception:
        m = {}
    rev: dict[str, set] = {}
    for cat, rule in (m or {}).items():
        if not isinstance(rule, dict):
            continue
        key = str(rule.get("key") or "").strip()
        if key:
            rev.setdefault(key, set()).add(str(cat))
    out: set = set()
    kp = (ext or {}).get("kp_rows")
    for r in kp or []:
        if not isinstance(r, dict):
            continue
        cat = str(r.get("part_category") or r.get("category") or "").strip()
        if not cat:
            continue
        for key, cats in rev.items():
            if cat in cats:
                out.add(key)
    return out


def requirement_rows_to_parts(kp_rows) -> list:
    """登记表部件行 → 待选型占位部件行（category/description/qty，交由下游 AI 落真实 SKU）。

    行身份锚定来源（P3-1）：同类目单行 → reg:类目（对行序变化免疫）；同类目多行 → reg:类目#n。
    """
    rows = [r for r in (kp_rows or []) if isinstance(r, dict)]
    counts: dict = {}
    for r in rows:
        cat = str(r.get("part_category") or r.get("category") or "").strip()
        if cat:
            counts[cat] = counts.get(cat, 0) + 1
    seen: dict = {}
    out = []
    for r in rows:
        cat = str(r.get("part_category") or r.get("category") or "").strip()
        desc = str(r.get("description") or r.get("catalogue") or "").strip()
        try:
            qty = int(float(r.get("qty", 1) or 1))
        except (TypeError, ValueError):
            qty = 1
        if not cat:
            continue
        seen[cat] = seen.get(cat, 0) + 1
        out.append(_placeholder(cat, qty, desc or cat,
                                origin=row_origin("reg", cat, seen[cat], counts[cat])))
    return out


def config_rows_to_parts(kp_config) -> list:
    """AI 声明的配置行（ext.kp_config：[{category, spec|description, qty}]）→ 待选型占位行。

    这是「AI=配置器 自己决定配什么」的落地载体：大脑决定要配某个类目（如 HBA/Bridge）
    就把行登记进 kp_config，下游按占位行走 search/select 或 ask_user，绝不静默丢类目。
    """
    rows = [r for r in (kp_config or []) if isinstance(r, dict)]
    counts: dict = {}
    for r in rows:
        cat = str(r.get("category") or "").strip()
        if cat:
            counts[cat] = counts.get(cat, 0) + 1
    seen: dict = {}
    out = []
    for r in rows:
        cat = str(r.get("category") or "").strip()
        if not cat:
            continue
        desc = str(r.get("spec") or r.get("description") or "").strip()
        try:
            qty = int(float(r.get("qty", 1) or 1))
        except (TypeError, ValueError):
            qty = 1
        seen[cat] = seen.get(cat, 0) + 1
        out.append(_placeholder(cat, qty, desc or cat,
                                origin=row_origin("cfg", cat, seen[cat], counts[cat])))
    return out


def ensure_pick_rows(parts: list, picks: dict, dup_ok: bool = False) -> list:
    """给 ext.kp_picks 里尚不存在的行键补占位行（按 类目|描述 解析），确保 apply 能落地。

    归一化能命中既有行（只差排版/数量词）时不补占位——pick 会按归一化落到那一行，补占位
    等于把同一需求变成两行（2026-09-11 P2）。
    """
    _rows = [p for p in (parts or []) if isinstance(p, dict)]
    have_ids = {str(p.get("row_id") or "").strip() for p in _rows if str(p.get("row_id") or "").strip()}
    have = {kp_row_key(str(p.get("category") or ""), str(p.get("request_spec") or "").strip()
                       or str(p.get("category") or "")) for p in _rows}
    pending: list = []
    for key, entry in (picks or {}).items():
        k = str(key or "")
        ent = entry if isinstance(entry, dict) else {}
        rid = str(ent.get("row_id") or "").strip()
        if rid and rid in have_ids:
            continue
        # P3-2：优先用条目自带的身份（category/description），键文本只作旧数据兜底。
        cat = str(ent.get("category") or "").strip()
        desc = str(ent.get("description") or "").strip()
        if not cat:
            if "|" in k:
                cat, desc = (k.split("|", 1) + [""])[:2]
            elif _is_row_id_key(k):
                # row_id 是身份暗号、不是类目：条目没带身份就无从知道该补哪一行（不铸幽灵行）
                continue
            else:
                cat, desc = k, k
            cat = str(cat).strip()
        if not cat:
            continue
        desc = str(desc).strip() or cat
        if k in have:
            continue
        # 归一化命中既有行（只差排版/数量词）→ 不补占位：pick 按归一化落到那一行，
        # 补占位等于把同一需求变成两行（2026-09-11 P2）。
        nk = row_key_norm(cat, desc)
        if any(row_key_norm(r.get("category"), r.get("request_spec") or r.get("category")) == nk
               for r in _rows):
            continue
        pending.append((cat, desc, str(ent.get("origin") or ""), rid))
    # 补行身份锚定来源（P3-1）：同类目多行才带序号；条目已带 row_id 的以条目为准（身份优先）
    counts: dict = {}
    for cat, _d, _o, _r in pending:
        counts[cat] = counts.get(cat, 0) + 1
    seen: dict = {}
    for cat, desc, origin, rid in pending:
        seen[cat] = seen.get(cat, 0) + 1
        origin = origin or row_origin("pick", cat, seen[cat], counts[cat])
        ph = _placeholder(cat, 1, desc, origin=origin)
        if rid:
            ph["row_id"] = rid
        parts.append(ph)
    return parts


def kp_row_key(category: str, request_spec: str) -> str:
    """部件行键 = 类目|描述。ext.kp_picks 与候选池共用：客户改过该行（类目/描述变了）
    键即失配，旧 pick 自动作废，下一回合重新选型。"""
    cat = str(category or "").strip()
    desc = str(request_spec or "").strip() or cat
    return f"{cat}|{desc}"

# —— 行描述归一（吸收措辞漂移，2026-09-11 P2）——
# 大脑手拼「类目|描述」时措辞每轮都会漂（实测：「系统盘 2块480G SSD」/「系统盘 480G SSD ×2」/
# 「系统盘480G SSD」是同一行的三种写法），描述一变行键就变 → 同一需求长成两行、客户被
# 重复问同一件事。归一只吸收**排版与数量词**噪声（空白、×N、N块/两块），不碰任何规格词，
# 也不碰「口/路/核/G」这类量纲词——所以「4个千兆网口」与「2个万兆网口」归一后仍是两行
# （同类目多行是合法需求）。
_ROW_NOISE_RE = re.compile(
    r"(?:(?<![\d.])(?:[×╳]|\*)\s*\d+)"                                  # ×2 / *2（不吃 12*3.5）
    r"|(?:(?:\d+|[两二三四五六七八九十])\s*(?:块|个|条|颗|片|根|只|张|组|对|套))")


def row_desc_norm(desc: str) -> str:
    """行描述归一：只用于「是不是同一行」的判定，不用于展示。"""
    s = unicodedata.normalize("NFKC", str(desc or "")).strip().lower()
    s = _ROW_NOISE_RE.sub("", s)
    s = re.sub(r"\s+", "", s)
    return s.strip("-_·,，、;；:：()（）[]【】")


def row_key_norm(category: str, desc: str) -> tuple:
    """行键（类目, 描述）归一元组；描述缺省按类目自身归一（与 kp_row_key 同口径）。"""
    cat = str(category or "").strip()
    d = str(desc or "").strip() or cat
    return (row_desc_norm(cat), row_desc_norm(d))


def kp_row_key_norm(key) -> tuple:
    """行键字符串（类目|描述）归一元组；没有竖线时整串当描述。"""
    k = str(key or "")
    cat, desc = ((k.split("|", 1) + [""])[:2] if "|" in k else (k, k))
    return row_key_norm(cat, desc)


def _ref_candidates(rows) -> list:
    return [{"row_id": r.get("row_id"), "row": r.get("row_key"),
             "status": str(r.get("status") or "")} for r in rows[:12]]


def _ref_hit(row: dict, why: str) -> dict:
    out = {"row": str(row.get("row_key") or ""), "row_id": str(row.get("row_id") or ""),
           "category": str(row.get("category") or ""),
           "description": str(row.get("description") or ""), "why": why}
    if row.get("settled"):
        out["settled"] = True
        out["status"] = str(row.get("status") or "")
        out["part"] = str(row.get("part") or "")
    return out


def resolve_row_ref(ref: str, rows) -> dict:
    """把行引用解析到行清单里的唯一一行——**只认身份，不猜文本**（P3-3）。

    两档：精确 row_id → 精确 row_key（等价别名）。都不中 → row_unknown（附可用 row_id 清单）。

    历史上还有第三档「归一化文本猜测」，已删除：那是机械正则式补丁，会让一个手拼措辞
    悄悄绑定到某一行。行身份现在由引擎铸造（P3-1），引用必须用清单里的 row_id 原文；
    要新增一行必须经 select_parts(new_row=true) 显式声明——这是工具契约在强制，不是劝告句。
    """
    want = str(ref or "").strip()
    src = [r for r in (rows or [])
           if isinstance(r, dict) and str(r.get("row_key") or "").strip()]
    if not want or not src:
        return {"error": "row_unknown", "candidates": []}
    for r in src:
        if str(r.get("row_id") or "").strip() == want:
            return _ref_hit(r, "row_id")
    for r in src:
        if str(r.get("row_key") or "").strip() == want:
            return _ref_hit(r, "row_key")
    return {"error": "row_unknown", "candidates": _ref_candidates(src)}


def row_ref_meta(ref: str, parts=None, ledger=None) -> dict:
    """行引用 → 行身份 {row_id, origin, row_key, category, description, rev}（P3-3 口径）。

    三档精确匹配：① row_id ② origin ③ 行键「类目|描述」。都不中 → {}——**不做文本相似度
    猜测**（拒绝机械式正则）。parts = 引擎行清单（kp_parts）；ledger = KP_ROW_IDS 身份
    台账（origin → 身份）。row_id/origin 是引擎自己铸造的暗号，解析它不等于猜文本。
    """
    want = str(ref or "").strip()
    if not want:
        return {}
    metas: list = []
    for p in (parts or []):
        if not isinstance(p, dict):
            continue
        cat = str(p.get("category") or "").strip()
        if not cat:
            continue
        desc = str(p.get("request_spec") or "").strip() or cat
        metas.append({"row_id": str(p.get("row_id") or "").strip() or kp_row_id(cat, desc),
                      "origin": str(p.get("origin") or "").strip(),
                      "row_key": kp_row_key(cat, desc), "category": cat, "description": desc,
                      "rev": str(p.get("rev") or "").strip() or row_content_rev(cat, desc)})
    if isinstance(ledger, dict):
        for _origin, _rec in ledger.items():
            if not isinstance(_rec, dict):
                continue
            cat = str(_rec.get("category") or "").strip()
            if not cat:
                continue
            desc = str(_rec.get("description") or "").strip() or cat
            metas.append({"row_id": str(_rec.get("row_id") or "").strip()
                                   or row_id_for_origin(str(_origin)),
                          "origin": str(_origin).strip(),
                          "row_key": kp_row_key(cat, desc), "category": cat, "description": desc,
                          "rev": str(_rec.get("rev") or "").strip() or row_content_rev(cat, desc)})
    for m in metas:
        if m["row_id"] and m["row_id"] == want:
            return m
    for m in metas:
        if m["origin"] and m["origin"] == want:
            return m
    for m in metas:
        if m["row_key"] == want:
            return m
    return {}


def pick_entry_identity(row: dict) -> dict:
    """pick / recommend 条目自带的身份字段（P3-2）。

    存储键改成 row_id 之后，条目仍要能自证「我是哪一行」——这样 ensure_pick_rows 不必
    再从键文本里反解类目/描述，也不怕键换了形态。
    """
    r = row if isinstance(row, dict) else {}
    cat = str(r.get("category") or "").strip()
    desc = str(r.get("description") or r.get("request_spec") or "").strip() or cat
    return {"origin": str(r.get("origin") or ""),
            "row_id": str(r.get("row_id") or ""),
            "category": cat,
            "description": desc,
            "rev": str(r.get("rev") or "") or row_content_rev(cat, desc)}


def pick_key_for_row(row: dict) -> str:
    """pick / recommend 的存储键：有身份用 row_id，无身份退回 类目|描述（兼容旧数据）。"""
    r = row if isinstance(row, dict) else {}
    rid = str(r.get("row_id") or "").strip()
    if rid:
        return rid
    return kp_row_key(str(r.get("category") or ""),
                     str(r.get("description") or r.get("request_spec") or ""))


def pick_is_stale(entry, category: str, desc: str) -> bool:
    """pick 落定时的内容版本 vs 当前行内容：不一致 = 该 pick 失效，须重选该行。

    只认**实质**内容（row_content_rev 已吸收排版/数量词噪声）；条目没记 rev（旧数据）→ 不判 stale。
    """
    if not isinstance(entry, dict):
        return False
    old = str(entry.get("rev") or "").strip()
    if not old:
        return False
    return old != row_content_rev(category, desc)


def _is_row_id_key(key) -> bool:
    """键是否是引擎铸造的 row_id（`kp-xxxxxxxx`）——区别于旧式 类目|描述 文本键。"""
    k = str(key or "").strip()
    return k.startswith("kp-") and "|" not in k


def _pick_entry_key_norm(entry, key) -> tuple:
    """pick 条目的归一化行键：优先条目自带身份（P3-2 新版），退回键文本（旧版）。"""
    if isinstance(entry, dict):
        cat = str(entry.get("category") or "").strip()
        if cat:
            return row_key_norm(cat, str(entry.get("description") or "").strip() or cat)
    return kp_row_key_norm(key)


def pick_for_row(picks: dict, category: str, desc: str, row=None):
    """按行身份取 pick：row_id 精确 → 旧键精确 → 归一行键（唯一命中才算）。

    P3-2：新数据键是 row_id、条目自带 category/description/rev；旧数据键是 类目|描述。
    两种形态都能解析，所以升级不需要数据迁移，旧线程里的 picks 继续生效。
    """
    if not isinstance(picks, dict) or not picks:
        return None
    rid = str((row or {}).get("row_id") or "").strip() if isinstance(row, dict) else ""
    if rid:
        exact = picks.get(rid)
        if exact is not None:
            return exact
    exact = picks.get(kp_row_key(category, desc))
    if exact is not None:
        return exact
    nk = row_key_norm(category, desc)
    # 归一化档只服务**旧数据**（键=类目|描述、条目无身份）：新数据键是 row_id，走上面的精确档，
    # 不再让文本相似度参与「哪一行」的判断（拒绝机械正则；2026-09-11 P3-3）。
    hits = [v for k, v in picks.items()
            if not _is_row_id_key(k) and _pick_entry_key_norm(v, k) == nk]
    return hits[0] if len(hits) == 1 else None

def kp_row_id(category: str, request_spec: str = "") -> str:
    """部件行公开id（供 AI 引用，不暴露内部复合键）：由 类目|描述 派生的稳定短id。

    AI 只复制 node_view 里给出的 row_id，绝不手拼 类目|描述 暗号；引擎按 row_id
    解析回标准行键。同一条需求行（客户改描述则 id 自动变，旧 picks 失配作废）。"""
    key = kp_row_key(category, request_spec or "")
    return "kp-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


# ── 行身份铸造（P3-1，2026-09-11）──────────────────────────────────────
# 行身份 = 行的**来源**（登记行 / 声明行 / pick 补行 + 同类目序号），不是行的**文本**。
# 旧实现 row_id = sha1(类目|描述)：描述改一个字就换 id、旧 pick 失配，同一需求因此长出两行。
# 现在 id 由 origin 铸造（描述改写不换身份）；内容变化另用 rev（内容版本）表达。
# 纯事实、无相似度判断：引擎从不按文本猜测「这两行是不是同一行」。


def row_origin(kind: str, category: str, ordinal: int = 1, total: int = 1) -> str:
    """行来源锚点。同类目只有一行 → kind:类目；同类目多行 → kind:类目#n（n 从 1 起）。"""
    cat = str(category or "").strip()
    if not cat:
        return ""
    base = f"{str(kind or '').strip()}:{cat}"
    return f"{base}#{max(1, int(ordinal or 1))}" if int(total or 1) > 1 else base


def row_id_for_origin(origin: str) -> str:
    """身份铸造：由来源派生稳定短 id（确定性，跨轮 / 跨进程一致）。"""
    o = str(origin or "").strip()
    if not o:
        return ""
    return "kp-" + hashlib.sha1(("origin|" + o).encode("utf-8")).hexdigest()[:8]


def row_content_rev(category: str, desc: str) -> str:
    """行内容版本：权威描述归一后的短哈希（描述真变了才变，身份不变）。"""
    cat = str(category or "").strip()
    d = row_desc_norm(str(desc or "").strip() or cat)
    return hashlib.sha1(("rev|" + row_desc_norm(cat) + "|" + d).encode("utf-8")).hexdigest()[:8]


def stamp_row_identity(parts: list, kind: str = "row") -> list:
    """给行清单补身份（origin / row_id / rev）；幂等——已有 origin 的行原样保留。

    只在行**缺**身份时按「来源 kind + 同类目序号」补，不按文本相似度猜（拒绝机械正则）。
    返回同一个 list（就地补，调用方无需接返回值）。
    """
    groups: dict = {}
    for p in parts or []:
        if not isinstance(p, dict) or str(p.get("origin") or "").strip():
            continue
        groups.setdefault((str(kind or "row"), str(p.get("category") or "").strip()), []).append(p)
    for (k, cat), rows in groups.items():
        total = len(rows)
        for i, p in enumerate(rows, start=1):
            p["origin"] = row_origin(k, cat, i, total)
            p["row_id"] = row_id_for_origin(p["origin"])
            p["rev"] = row_content_rev(cat, p.get("request_spec") or "")
    for p in parts or []:
        if not isinstance(p, dict):
            continue
        if not str(p.get("row_id") or "").strip() and str(p.get("origin") or "").strip():
            p["row_id"] = row_id_for_origin(p["origin"])
        if not str(p.get("rev") or "").strip():
            p["rev"] = row_content_rev(str(p.get("category") or ""), p.get("request_spec") or "")
    return parts


def kp_registered_specified(ext: dict, category: str) -> bool:
    """线索登记表是否已登记该类目的「明确值」（非仅类目名/空）。

    决策依据（2026-09-09 定调）：用户写了没 = 看线索登记表登记了没有。登记了具体型号
    （如「兆芯 KH50000 96C」）→ 该行选配可直接锁定；仅类目名/空 → 视为未写明，属必填
    类目则须调 ask_user 交客户确认（推荐作默认项），不许静默锁一个 AI 拍的料。
    """
    cat = str(category or "").strip()
    if not cat:
        return False
    for r in (ext or {}).get("kp_rows") or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("part_category") or r.get("category") or "").strip() != cat:
            continue
        desc = str(r.get("description") or r.get("catalogue") or "").strip()
        if desc and _norm_cat_key(desc) != _norm_cat_key(cat):
            return True
    return False


def apply_kp_picks(parts: list, picks: dict) -> tuple:
    """把 AI 选定（ext.kp_picks：行键 → {name, price, currency, reason[, qty][, substitute]}）应用到占位行。

    快照语义：选定时的名称/价格随 pick 落行（价格随行市波动，跨轮以 pick 时的库内
    价为准，同 BOM 快照）。行键失配（客户改行）自动跳过。返回 (新列表, 应用行数)。
    qty：大脑组合申报（如 768G=64G×12）覆盖行数量；substitute：近替代申报 → 行打
    spec_mismatch ⚠️ 白盒标记，grounded_spec 前缀替代说明。
    """
    out, applied = [], 0
    for p in parts or []:
        if not (isinstance(p, dict) and p.get("unmatched")):
            out.append(p)
            continue
        cat = str(p.get("category") or "").strip()
        desc = str(p.get("request_spec") or "").strip() or cat
        raw = pick_for_row(picks, cat, desc, row=p)
        pick_list = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])
        pick_list = [pk for pk in pick_list if isinstance(pk, dict) and str(pk.get("name") or "").strip()]
        # 客户改了口径（内容版本变了）→ 旧 pick 不再代表客户现在的意思，本行重跑选型。
        pick_list = [pk for pk in pick_list if not pick_is_stale(pk, cat, desc)]
        if not pick_list:
            out.append(p)
            continue
        for pick in pick_list:
            reason = str(pick.get("reason") or "").strip()
            try:
                pick_qty = int(pick.get("qty"))
            except (TypeError, ValueError):
                pick_qty = 0
            substitute = bool(pick.get("substitute"))
            grounded = ("AI 从候选池选定：" + reason) if reason else "AI 从候选池选定"
            if substitute:
                grounded = ("⚠️ 替代申报：" + (reason or "近替代") + "；" + grounded) if reason \
                    else "⚠️ 替代申报（近替代，无精确匹配）"
            out.append(_row(
                cat,
                {"model": pick.get("name"), "price": pick.get("price"), "currency": pick.get("currency")},
                pick_qty if pick_qty >= 1 else (p.get("qty") or 1),
                matched_spec="AI 选定",
                request_spec=p.get("request_spec") or "",
                grounded_spec=grounded,
                spec_mismatch=substitute,
                origin=p.get("origin") or "",
            ))
            applied += 1
    return out, applied

def apply_kp_waived(parts: list, waived) -> tuple:
    """把「客户已知悉库内无料、选择保持原需求」的行键落成 white-box 豁免行。

    这是行的第三个结局（见 skill_node_state.KP_WAIVED）：行**保留**在配件表里（客户原话
    规格仍在 request_spec 上，列契约照常取到值），但不再算「未落地」——所以终检放行、
    组装照跑。豁免是客户拍板的结果，不是引擎替 AI 下的台阶：调用方只接受客户点选
    （ask_user 选项带 waived）登记的豁免行键。返回 (新列表, 标记行数)。
    """
    keys = {str(k).strip() for k in (waived if isinstance(waived, (list, tuple, set)) else [waived])
            if str(k).strip()}
    if not keys:
        return list(parts or []), 0
    out, marked = [], 0
    for p in parts or []:
        if not isinstance(p, dict):
            continue
        rk = kp_row_key(str(p.get("category") or ""), str(p.get("request_spec") or "").strip()
                        or str(p.get("category") or ""))
        # P3-2：豁免行引用可能以 row_id / origin 落键（卡片引用引擎铸造的身份），三种形态都认。
        if (rk not in keys and str(p.get("row_id") or "") not in keys
                and str(p.get("origin") or "") not in keys):
            out.append(p)
            continue
        row = dict(p)
        row["waived"] = True
        row["unmatched"] = False
        row["unmatched_reason"] = ""
        row["grounded_spec"] = "库内无料，客户已知悉（保持原需求）"
        out.append(row)
        marked += 1
    return out, marked


def _pick(rows, mode):
    if not rows:
        return None
    if mode == "max_price":
        return max(rows, key=lambda r: float(r.get("price") or 0))
    if mode == "first":
        return rows[0]
    return min(rows, key=lambda r: float(r.get("price") or 0))

def _row(db_cat, rep, qty, matched_spec="", unmatched=False, reason="",
         request_spec="", grounded_spec="", spec_mismatch=False, origin=""):
    _origin = str(origin or "").strip()
    return {
        "category": db_cat,
        "origin": _origin,
        "row_id": row_id_for_origin(_origin) if _origin else kp_row_id(db_cat, request_spec),
        "rev": row_content_rev(db_cat, request_spec),
        "pn": str(rep.get("model") or "") if rep else "",
        "name": str(rep.get("model") or "") if rep else "",
        "unit_price": float(rep.get("price") or 0) if rep else 0.0,
        "currency": str(rep.get("currency") or "RMB") if rep else "RMB",
        "qty": int(qty or 1),
        "matched_spec": matched_spec or "",
        "unmatched": unmatched,
        "unmatched_reason": reason,
        "request_spec": request_spec or "",
        "grounded_spec": grounded_spec or "",
        "spec_mismatch": bool(spec_mismatch),
    }

def _unmatched(db_cat, qty, reason):
    return _row(db_cat, None, qty, unmatched=True, reason=reason)

def _norm_cat_key(s: str) -> str:
    """类目键归一：仅去分隔符/大小写，不做语义映射（HDD/SSD == HDD SSD == HDD-SSD）。"""
    return re.sub(r'[\s/_\-]+', '', str(s or '')).lower()
