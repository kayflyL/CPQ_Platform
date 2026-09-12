# -*- coding: utf-8 -*-
"""节点私有状态容器（节点隔离的载体）—— 2026-09-10 结构手术 Step 2。

改造前：每个节点的可变工作状态（选型 pick、推荐、声明行、放弃类目…）全部堆在共享
`ext` 里，而 `ext` 同时又是「线索登记表」的存储。任一节点写 `ext` 都可能踩到别的
节点的键，结果是「改一处坏一处」，问题无法定位到单个节点。

本模块给出按节点分区的状态命名空间：

    st = kp_state(engine)        # engine = 引擎 ctx；跨轮持久化时容器是 mem
    st[KP_PICKS][row_key] = {...}

边界（红线）：
  * `ext` 只保留「线索登记表」这一份上游冻结文档；节点工作状态一律进本容器；
  * 每个节点只读写自己的分区，不读不写别人的分区；
  * 容器对象身份保持（同一个 dict 就地改），随 mem 整块落盘。

持久化：引擎回合内以 `engine["node_state"]` 为容器；回合结束原样回写
`mem["node_state"]`；下一回合从 mem 读回同一块对象。
"""
from __future__ import annotations

NODE_STATE_KEY = "node_state"

# 节点分区键（= 流程节点 key）
KP_NODE = "kp_reason"

# —— 冻结文档（上游产物）——
# 「线索登记表」写在共享 ext 里，但**只有它的属主节点可以写**；下游节点一律只读。
# 属主关系由节点插件声明（skill_node_plugins._FillNode.owns_doc），本文件不再维护
# `FILL_NODE` / `DOC_OWNER_BY_NODE` 两张与插件重复的硬编码表。
DOC_SNAPSHOT_KEY = "frozen_docs"

# —— kp_reason 分区内的键（原 ext.kp_picks / ext.kp_recommend / ext.kp_config / ext.kp_absent）——
KP_PICKS = "picks"          # 行键 → 已锁定真实料号（select_parts 落定，客户已确认）
KP_RECOMMEND = "recommend"  # 行键 → AI 建议料（待客户确认，未落地）
KP_CONFIG = "config"        # 大脑声明的待配行（客户原话未覆盖、AI 判断要配）
KP_ABSENT = "absent"        # 客户明确放弃配置的类目（如本机不配 GPU）
KP_WAIVED = "waived"        # 客户已知悉「库内无料」仍选择保持原需求的行键（行保留 + 标注，终检放行）
KP_ROW_IDS = "row_ids"      # 行来源(origin) → {row_id, rev, category, description}：身份铸造台账（P3-1）


def node_state(container: dict, node_key: str) -> dict:
    """取（必要时建）某节点的私有状态分区；对象身份保持，可跨函数就地改。"""
    if not isinstance(container, dict):
        return {}
    ns = container.get(NODE_STATE_KEY)
    if not isinstance(ns, dict):
        ns = {}
        container[NODE_STATE_KEY] = ns
    st = ns.get(node_key)
    if not isinstance(st, dict):
        st = {}
        ns[node_key] = st
    return st


def kp_state(container: dict) -> dict:
    """kp_reason 节点私有状态分区。"""
    return node_state(container, KP_NODE)


def fill_node() -> str:
    """线索登记表的唯一写入节点（由节点插件的 owns_doc 声明推导，而非硬编码）。"""
    from app.services.skill_node_plugins import all_plugins
    for plugin in all_plugins():
        if str(getattr(plugin, "owns_doc", "") or "").strip():
            return str(plugin.key)
    return "agent_fill"


def fill_state(container: dict) -> dict:
    """agent_fill（登记节点）私有状态分区。"""
    return node_state(container, fill_node())


def doc_owner(node_key: str) -> str:
    """某节点拥有的冻结文档槽名；非属主节点返回空串。"""
    from app.services.skill_node_plugins import plugin_for
    return str(getattr(plugin_for(node_key), "owns_doc", "") or "").strip()


def owned_doc_slots() -> dict:
    """全部「节点 → 冻结文档槽」的属主声明（来自节点插件）。"""
    from app.services.skill_node_plugins import all_plugins
    out = {}
    for plugin in all_plugins():
        slot = str(getattr(plugin, "owns_doc", "") or "").strip()
        if slot:
            out[str(plugin.key)] = slot
    return out


# —— KP_ROW_ANSWERS：客户对某条登记行的追问回答 ——
# 客户回答「这一行要什么」时，答案绝不写回登记表（登记表已冻结），而是按**登记行键**
# 记在本节点分区里；节点工作时把答案叠加成该行的检索文本，行键保持取自登记原文，
# 因此行键稳定、旧选型不会因为客户补一句话就失配作废。
KP_ROW_ANSWERS = "row_answers"


def row_answers(container: dict) -> dict:
    """kp_reason 分区里的「行键 → 客户回答列表」。"""
    st = kp_state(container)
    ans = st.get(KP_ROW_ANSWERS)
    if not isinstance(ans, dict):
        ans = {}
        st[KP_ROW_ANSWERS] = ans
    return ans


def add_row_answer(container: dict, row_key: str, answer: str) -> bool:
    """追加一条行回答（去重）。返回是否有变化。"""
    rk = str(row_key or "").strip()
    txt = str(answer or "").strip()
    if not rk or not txt:
        return False
    ans = row_answers(container)
    cur = [str(a) for a in (ans.get(rk) or []) if str(a).strip()]
    if txt in cur:
        return False
    cur.append(txt)
    ans[rk] = cur
    return True


def row_answer_text(container: dict, row_key: str) -> str:
    """该行的客户回答拼接文本（检索用；空串表示没有）。"""
    return " ".join(str(a) for a in (row_answers(container).get(str(row_key or "").strip()) or []))


# —— KP_WAIVED：行的第三个结局 ——
# 一条登记行的终局只有三种，引擎只认这三种白盒事实，不做语义猜测：
#   * picks[row]        已锁定库内真实料号（客户明确登记→AI 检索命中；或客户点选推荐料）
#   * absent[类目]      客户明确「不配/自备」→ 整行丢弃
#   * waived[row]       库内确实没有该行要的料，客户已知悉并选择「保持原需求」→ 行保留 + 标注
# waived 与 absent 的区别是语义级的：absent 是「不要这个类目」，waived 是「要，但库里没有，
# 客户认了」。前者整行消失、不进 BOM；后者进 BOM 行（标注留白），终检放行。
def waived_row_keys(container: dict) -> set:
    """客户已知悉库内无料、选择保持原需求的行键集合（kp_reason 分区）。"""
    st = kp_state(container)
    return {str(k).strip() for k in (st.get(KP_WAIVED) or []) if str(k).strip()}


def add_waived_rows(container: dict, keys) -> bool:
    """登记豁免行（去重）。keys 为行键（类目|描述）或单个行键；返回是否有变化。"""
    src = keys if isinstance(keys, (list, tuple, set)) else [keys]
    ks = [str(k).strip() for k in src if str(k).strip()]
    if not ks:
        return False
    st = kp_state(container)
    cur = [str(k).strip() for k in (st.get(KP_WAIVED) or []) if str(k).strip()]
    add = [k for k in ks if k not in cur]
    if not add:
        return False
    st[KP_WAIVED] = cur + add
    return True


def waived_categories(container: dict) -> set:
    """豁免行覆盖的部件大类（终检按类目核对）。

    豁免键可能是旧式行键（类目|描述）或新式 row_id（P3-2）；row_id 走身份台账反查类目。
    """
    st = kp_state(container)
    ledger = st.get(KP_ROW_IDS) if isinstance(st.get(KP_ROW_IDS), dict) else {}
    by_id = {str(v.get("row_id") or ""): str(v.get("category") or "")
             for v in ledger.values() if isinstance(v, dict)}
    out: set = set()
    for k in waived_row_keys(container):
        if "|" in k:
            out.add(k.split("|", 1)[0].strip())
        elif k in by_id:
            out.add(by_id[k].strip())
    return out - {""}


# —— 冻结文档只读视图（Step 4：类型级「下游只读不写」）——
class DocWriteForbidden(RuntimeError):
    """下游节点试图改写上游冻结文档。"""


class FrozenDocView(dict):
    """登记表的**只读**视图：非属主节点持有它，任何写入当场报错。

    冻结不是靠约定而是靠类型——工具上下文与引擎里的文档对象都是这个视图，
    `view["k"] = v` / `setdefault` / `pop` / `update` / `clear` 一律抛
    DocWriteForbidden，绝不静默丢弃；读操作（get/items/`in`/dict(view)）全部可用。

    做成 dict 子类（而不是 Mapping 包装）是为了兼容既有 `isinstance(x, dict)` 判断：
    下游节点读到的是登记表内容的只读快照，既不会因为类型不符被替换成空 dict，
    也不会被任何写入路径改到。

    属主节点（agent_fill）拿到的仍是原始 dict（登记表按契约由它写）。
    """

    __slots__ = ("_node",)

    def __init__(self, doc, node_key: str = "") -> None:
        super().__init__(doc if isinstance(doc, dict) else {})
        self._node = str(node_key or "")

    def unwrap(self) -> dict:
        """取回原始内容（落盘/比较时用；只给引擎，不给节点工具）。"""
        return dict(self)

    def _forbid(self, *args, **kwargs):
        raise DocWriteForbidden(
            "「" + (self._node or "下游节点") + "」只能读上游线索登记表（属主节点：" + fill_node() + "）")

    __setitem__ = _forbid
    __delitem__ = _forbid
    __ior__ = _forbid
    setdefault = _forbid
    update = _forbid
    pop = _forbid
    popitem = _forbid
    clear = _forbid

    def __repr__(self) -> str:
        return "FrozenDocView(%s, keys=%s)" % (self._node, sorted(str(k) for k in self)[:8])


def unwrap_doc(doc):
    """FrozenDocView → 原始 dict；其它原样返回（落盘前统一走它）。"""
    return doc.unwrap() if isinstance(doc, FrozenDocView) else doc


# —— 冻结文档快照 / 越界判定 ——
def _doc_digest(doc) -> str:
    import json
    doc = unwrap_doc(doc)
    if not isinstance(doc, dict):
        return json.dumps(doc, ensure_ascii=False, sort_keys=True, default=str)
    clean = {str(k): v for k, v in doc.items() if not str(k).startswith("_")}
    try:
        return json.dumps(clean, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return repr(sorted(clean.keys()))


def mark_doc_frozen(container: dict, node_key: str, doc) -> None:
    """属主节点该步落定时打快照（同一回合内可重复打，取最后一次）。"""
    slot = doc_owner(node_key)
    if not slot:
        return
    docs = container.get(DOC_SNAPSHOT_KEY)
    if not isinstance(docs, dict):
        docs = {}
        container[DOC_SNAPSHOT_KEY] = docs
    docs[slot] = _doc_digest(doc)


def freeze_snapshot(container: dict) -> dict:
    """冻结快照的**跨轮搬运**入口（记忆是 JSON，引擎内存对象每轮重建）。

    读写都走这一个口：少一处 `.get(KEY) or {}`，就少一个「快照只活在当轮、
    下一轮回填静默漏过」的缝。
    """
    docs = container.get(DOC_SNAPSHOT_KEY) if isinstance(container, dict) else None
    return dict(docs) if isinstance(docs, dict) else {}


def doc_freeze_violation(container: dict, node_key: str, doc) -> str:
    """下游节点写冻结文档 → 返回差异说明；没写 → 空串。"""
    if doc_owner(node_key):
        return ""
    docs = container.get(DOC_SNAPSHOT_KEY)
    if not isinstance(docs, dict) or not docs:
        return ""  # 登记表还没落定，谈不上冻结
    slot = next((s for s in owned_doc_slots().values() if s in docs), None)
    if not slot:
        return ""
    now = _doc_digest(doc)
    if now == docs[slot]:
        return ""
    import json as _json
    try:
        a = _json.loads(docs[slot])
        b = _json.loads(now)
        diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    except Exception:
        diff = ["<unparsable>"]
    return "线索登记表在「" + str(node_key) + "」回合被改写（越界回填上游）：" + "、".join(diff[:8])
