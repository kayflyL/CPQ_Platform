# -*- coding: utf-8 -*-
"""transaction_engine —— 事务管道内核（Windows 式：机制在内核，应用是声明）。

与需求分析引擎（推理管道）并列的第二台运行时的事务内核。内核只认契约，不认任何
具体业务：一个事务工作流应用 = DB 流（节点序/工具白名单/左栏规则，配置权威源）
+ 一张探针表（各节点产物是否已落，查业务真实表）+ 一张旗标表（工具事实→状态槽）
+ 一组案台事实行（大脑每轮看的现场）。应用只能声明，不能带自己的编排逻辑——
谁想塞第二套编排，内核拒收（这是防"每个应用一套小操作系统"回潮的护栏）。

案台原则：每轮从业务真实表现算现状（不信任叙事），步骤指针 = 流节点序里第一个
探针不过者。判断全在大脑，顺序在指针，状态在库。digest 是纯事实块（C1）。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class TransactionApp:
    """事务工作流应用契约。探针/事实行是应用的本职声明；旗标映射优先走流程配置的
    flag_rules（声明表），没配声明表的应用才回退 flags_from_facts 钩子（可省）。"""

    def __init__(self, *, flow_key: str, state_slot: str,
                 context_fn: Callable, digest_lines: Callable,
                 flags_from_facts: Optional[Callable] = None):
        self.flow_key = str(flow_key)
        self.state_slot = str(state_slot)
        self.context_fn = context_fn              # fn(thread_id, user) -> dict（域事实并入案台）
        self.digest_lines = digest_lines          # fn(view) -> list[str]（案台事实行）
        self.flags_from_facts = flags_from_facts  # fn(facts) -> dict | None（钩子兜底，可省）

    @property
    def label(self) -> str:
        return self.flow_key


# ── 应用注册表（安装清单）─────────────────────────────────────────────────

_APPS: dict = {}


def register(app: TransactionApp) -> None:
    _APPS[app.flow_key] = app


def resolve_app(flow_key: str) -> Optional[TransactionApp]:
    """按流 key 找已安装应用。未安装 = None（分发层降级，不进需求分析机器）。"""
    if not _APPS:
        from app.services import delivery_app  # 现阶段唯一已装应用；新应用 import 即注册
        register(delivery_app.APP)
    return _APPS.get(str(flow_key or "").strip())


# ── 状态槽（线程 reasoning_state，按应用+角色分槽）────────────────────────


def _slot_key(app: TransactionApp, role_key: str) -> str:
    return f"{app.state_slot}:{(role_key or 'assistant').strip() or 'assistant'}"


def load_state(app: TransactionApp, thread_id: str, role_key: str = "assistant") -> dict:
    from app.repository.assistant_repo import AssistantRepository
    repo = AssistantRepository()
    try:
        raw = repo.get_reasoning_state(thread_id)
    finally:
        repo.close()
    data = json.loads(raw or "{}") if raw else {}
    mem = data.get(_slot_key(app, role_key))
    return dict(mem) if isinstance(mem, dict) else {}


def save_state(app: TransactionApp, thread_id: str, role_key: str, state: dict) -> None:
    from app.repository.assistant_repo import AssistantRepository
    repo = AssistantRepository()
    try:
        repo.update_reasoning_state(thread_id, {_slot_key(app, role_key): state})
    finally:
        repo.close()


def clear_state(app: TransactionApp, thread_id: str, role_key: str = "assistant") -> None:
    save_state(app, thread_id, role_key, {})


def clear_thread_binding(thread_id: str) -> None:
    """fresh 装填：解绑线程商机。房间线程是共享工作台，每个开工单=独立任务——
    案台从第一步重算，新链建档时自然重新绑定；老商机在库里原样不动（历史归它）。"""
    from app.repository.assistant_repo import AssistantRepository
    repo = AssistantRepository()
    try:
        repo.update_thread_opportunity_id(thread_id, None)
    finally:
        repo.close()


def desk_complete(app: TransactionApp, thread_id: str, role_key: str = "assistant", user: dict = None) -> bool:
    """案台交割完毕（全探针通过=全链已完成）。同线程再发消息=新开工单的判定依据——
    案台每轮现算的同一口径；链中（未 complete）绝不据此重开，反问/等确认的续跑不受影响。"""
    return bool(state_view(app, thread_id, role_key, user if isinstance(user, dict) else {}).get("complete"))


# ── 流配置（DB 权威源：节点序 / 标签 / 工具白名单 / 左栏规则）────────────────


def load_flow_rules(flow_key: str) -> dict:
    """流配置：graph.manual_rules + 挂了工具白名单的节点序列（agent 干活节点 +
    output 出件节点；input 无工具不入列）。读不到流 = 空配置（调用方降级）。"""
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    repo = ReasoningFlowRepository()
    try:
        flow = repo.get_active_flow(flow_key)
    finally:
        repo.close()
    if not flow:
        return {"rules": "", "steps": []}
    graph = flow.get("graph") or {}
    cfgs = flow.get("node_configs") or {}
    steps = []
    for nd in graph.get("nodes") or []:
        key = str(nd.get("id") or "")
        cfg = cfgs.get(key) if isinstance(cfgs.get(key), dict) else {}
        tools = [str(t) for t in (cfg.get("enabled_tools") or [])]
        if not tools:
            continue
        # 节点契约（目标层/字段级）随步骤下发：runner 注入本步提示词，AI 照契约产出。
        # 字段级 = 目标层 fields[]（key/label/ask）：ask=true 的字段缺失时反问，
        # 全齐直接办——反问点是契约的缺口，不是模型的判断力（与需求分析同代设计）。
        tgt = cfg.get("target") or {}
        art0 = None
        if isinstance(tgt.get("artifact"), dict):
            art0 = tgt["artifact"]
        elif isinstance(tgt.get("artifacts"), list) and tgt["artifacts"]:
            art0 = tgt["artifacts"][0]
        target = (f"{art0.get('name')} → 写入 {art0.get('slot')}" if art0 else "")
        steps.append({"key": key, "label": str(nd.get("label") or key), "tools": tools,
                      "target": target, "fields": [f for f in ((art0 or {}).get("fields") or []) if isinstance(f, dict)],
                      "output": str(cfg.get("output_artifact") or ""),
                      "completion": cfg.get("completion") if isinstance(cfg.get("completion"), dict) else None,
                      "skip_note": str(cfg.get("skip_note") or ""),
                      "gated": bool(cfg.get("gated")),
                      "artifact_card": cfg.get("artifact_card") if isinstance(cfg.get("artifact_card"), (dict, list)) else None})
    edges = [{"id": str(e.get("id") or ""),
              "source": str(e.get("source") or ""),
              "target": str(e.get("target") or ""),
              "guard": dict(e["guard"]) if isinstance(e.get("guard"), dict) else None}
             for e in (graph.get("edges") or []) if isinstance(e, dict)]
    flag_rules = [dict(r) for r in (graph.get("flag_rules") or []) if isinstance(r, dict)]
    return {"rules": str(graph.get("manual_rules") or ""), "steps": steps,
            "edges": edges, "flag_rules": flag_rules}


def format_step_contract(step: dict) -> str:
    """步骤契约 → 提示词注入文本：目标层（写到哪张表）+ 字段级必填清单（缺哪个问哪个）。

    反问纪律由契约驱动：fields[].ask=true 即「该字段缺失时必须向用户要，不得自拟」；
    ask 未置位 = 大脑可从案台/对话自行推断。配置者改字段开关，下一轮反问行为同步变。
    """
    lines = []
    target = str((step or {}).get("target") or "").strip()
    if target:
        lines.append(f"本步目标：{target}。")
    if (step or {}).get("gated"):
        lines.append("本步是确认闸：执行前出确认卡，用户确认后才落库。")
    for tool in (step or {}).get("tools") or []:
        try:
            from app.services.agent_tool_display import TOOL_DISPLAY
            d = TOOL_DISPLAY.get(tool)
            if d and d.get("one_liner"):
                lines.append(f"· {tool}：{d['one_liner']}")
        except Exception:
            pass
    asks = [f for f in (step or {}).get("fields") or [] if f.get("ask")]
    if asks:
        need = "、".join(str(f.get("label") or f.get("key")) for f in asks)
        lines.append(f"本步必填字段：{need}。开工前对照案台与对话做缺口检查——"
                     "缺哪个先向用户要哪个（一次问齐），全部齐了直接办，不重复反问。")
        for f in asks:
            hint = str(f.get("hint") or "").strip()
            if hint:
                lines.append(f"· {f.get('label') or f.get('key')}：{hint}")
    return "\n".join(lines)


# ── 契约驱动的求值与装配 ──────────────────────────────────────────────────


def _skip_hit(comp: dict, view: dict) -> bool:
    """节点短路条件命中判定：skip_if={"flag": 旗标, "equals": 值}——旗标等于该值时
    本节点视为直接过关（分流链路不经过的节点，如成本表链跳过方案落位）。"""
    s = comp.get("skip_if") if isinstance(comp, dict) else None
    if not isinstance(s, dict) or not s.get("flag"):
        return False
    return (view.get("flags") or {}).get(str(s["flag"])) == s.get("equals")


def skip_note(comp: dict, view: dict) -> str:
    """节点被 skip_if 短路时返回配置的说明文案（skip_note）；未短路返回空。"""
    if isinstance(comp, dict) and _skip_hit(comp, view):
        return str(comp.get("skip_note") or "")
    return ""


_SKIP_DEFAULT_NOTE = "分流未经过此节点，已自动跳过"
_DONE_DEFAULT_NOTE = "本步未单独执行——产物由前序步骤直落"


def _guard_state(guard: Optional[dict], flags: dict) -> str:
    """边守卫三态：pass=放行；blocked=旗标已定且不满足（已决拦截）；
    undecided=旗标还没定（分流未判——下游既不算跳过也不冒充待办暴露）。"""
    if not isinstance(guard, dict) or not guard.get("flag"):
        return "pass"
    flag = str(guard["flag"])
    if flag not in (flags or {}):
        return "undecided"
    return "pass" if (flags or {}).get(flag) == guard.get("equals") else "blocked"


def branch_reach(steps: list, edges: list, view: dict) -> dict:
    """图遍历（分支一等公民）：可达性从「边 + 守卫」现算，不再靠节点 skip 补丁模拟。
    → {key: "reachable"（流程会经过） | "skipped"（每条路径都被已决守卫挡死=分流没走）
         | "undecided"（被旗标未定的守卫挡住：分流未判，暂不暴露）}
    边缺省/空图 → 全部 reachable（线性流向后兼容）。不动点迭代，流程图都是小图。"""
    keys = [str(s.get("key") or "") for s in steps or []]
    if not keys:
        return {}
    flags = view.get("flags") if isinstance(view, dict) else None
    flags = flags if isinstance(flags, dict) else {}
    edges_n = [(str(e.get("source") or ""), str(e.get("target") or ""), e.get("guard"))
               for e in (edges or []) if isinstance(e, dict)]
    if not edges_n:
        return {k: "reachable" for k in keys}
    keyset = set(keys)
    state = {k: "" for k in keys}
    if keys[0] in keyset:
        state[keys[0]] = "reachable"
    for _ in range(len(keys) + 1):
        changed = False
        for src, dst, guard in edges_n:
            if src not in keyset or dst not in keyset:
                continue
            ss = state.get(src)
            if ss == "reachable":
                g = _guard_state(guard, flags)
                if g == "pass":
                    if state.get(dst) != "reachable":
                        state[dst] = "reachable"
                        changed = True
                elif g == "undecided":
                    if state.get(dst) in ("", "skipped"):
                        state[dst] = "undecided"
                        changed = True
                elif state.get(dst) == "":
                    state[dst] = "skipped"
                    changed = True
            elif ss == "undecided":
                if state.get(dst) not in ("reachable", "undecided"):
                    state[dst] = "undecided"
                    changed = True
            elif ss == "skipped" and state.get(dst) == "":
                state[dst] = "skipped"
                changed = True
        if not changed:
            break
    return {k: (state.get(k) or "skipped") for k in keys}


def node_states(steps: list, view: dict) -> dict:
    """全链节点状态的唯一计算口（状态语义单一定义处）。

    - skipped：图遍历不可达（分流没走这条链）或 skip_if 条件命中——按条件本身判定，
      与 skip_note 文案配不配无关（2026-10-22 实锤：回合壳曾拿文案真假当判定，
      没配文案的跳过节点冒充完成绿）；
    - done：完成声明通过（无声明=配置缺失，不算完成，显性暴露）；
    - pending：其余（进行中/待办；分流未判的 undecided 下游也算 pending，不提前灰）。
    回合壳广播与画布渲染只搬运本结果（见 state_events），禁止二次推导。"""
    states: dict = {}
    edges = ((view.get("flow") or {}).get("edges")) if isinstance(view, dict) else None
    reach = branch_reach(steps, edges or [], view)
    for s in steps or []:
        key = str(s.get("key") or "")
        comp = s.get("completion")
        if reach.get(key) == "skipped" or _skip_hit(comp, view):
            states[key] = "skipped"
        elif reach.get(key) == "reachable" and comp is not None and _eval_completion(comp, view):
            states[key] = "done"
        else:
            states[key] = "pending"
    return states


def state_events(steps: list, view: dict, thread_id: str,
                 notes: Optional[dict] = None, only_keys: Optional[set] = None) -> list:
    """节点状态 → node_trace 广播载荷（回合壳↔画布间的状态契约）。
    only_keys 给增量补发用：只出这些键；None=出全部非 pending 节点。"""
    notes = notes or {}
    states = node_states(steps, view)
    out: list = []
    for s in steps or []:
        key = str(s.get("key") or "")
        st = states.get(key) or "pending"
        if st == "pending" or (only_keys is not None and key not in only_keys):
            continue
        if st == "skipped":
            note = (str(s.get("skip_note") or "")
                    or str(((s.get("completion") or {}).get("skip_note")) or "")
                    or _SKIP_DEFAULT_NOTE)
        else:
            note = str(notes.get(key) or "") or _DONE_DEFAULT_NOTE
        out.append({"type": "node_trace", "step": key, "label": str(s.get("label") or key),
                    "status": st, "summary": note, "thread_id": thread_id})
    return out


def _eval_completion(comp: dict, view: dict) -> bool:
    """完成声明求值：{"slot": 事实键} / {"flag": 旗标键} / {"any_of": [事实键...]}
    / {"all_of": [事实键...]}，可叠加 {"skip_if": {"flag","equals"}} 短路。
    事实键支持点路径（如 x.y.z，旗标即 flags.xxx）。全声明都是节点契约的配置，无一行代码。"""
    if not isinstance(comp, dict):
        return False

    def _truthy(path: str) -> bool:
        cur: Any = view
        for part in str(path).split("."):
            if not isinstance(cur, dict) or part not in cur:
                return False
            cur = cur[part]
        return bool(cur)

    if _skip_hit(comp, view):
        return True
    if comp.get("flag"):
        return bool((view.get("flags") or {}).get(str(comp["flag"])))
    all_of = comp.get("all_of")
    if isinstance(all_of, list) and all_of:
        return all(_truthy(p) for p in all_of)
    paths = comp.get("any_of") or ([comp["slot"]] if comp.get("slot") else [])
    return any(_truthy(p) for p in paths)


def _dig(scopes: dict, path: str) -> Any:
    """$result.x / $view.a.b 取值；非 $ 开头按字面量返回。"""
    if not isinstance(path, str) or not path.startswith("$"):
        return path
    cur: Any = scopes
    for part in path[1:].split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _norm_card_decls(decl) -> list:
    """artifact_card 兼容单声明与声明列表（双分支节点一个落位动作可发不同的卡）。"""
    if isinstance(decl, list):
        return [d for d in decl if isinstance(d, dict)]
    return [decl] if isinstance(decl, dict) else []


def build_card(decl: dict, result: dict, view: dict) -> Optional[dict]:
    """按节点声明的 artifact_card 装配产物卡（refs 只存 id，拉活数据是查看器的事）。"""
    if not isinstance(decl, dict):
        return None
    scopes = {"result": result or {}, "view": view or {}}
    refs = {k: _dig(scopes, p) for k, p in (decl.get("refs") or {}).items()}
    refs = {k: v for k, v in refs.items() if v}
    return {"artifact_type": decl.get("artifact_type"),
            "title": str(decl.get("title") or ""),
            "summary": str(_dig(scopes, decl.get("summary")) or decl.get("summary") or ""),
            "refs": refs}


# ── 案台视图与步骤指针 ────────────────────────────────────────────────────


def state_view(app: TransactionApp, thread_id: str, role_key: str, user: dict) -> dict:
    """案台现状：内核件（流配置/状态旗标/待确认）+ 应用域事实，指针按应用探针表走。

    返回 {flow, flags, pending, step, step_key, complete, **应用域事实}。
    step=None 且 complete=False = 流配置缺失（调用方降级）。"""
    view = {
        "thread_id": thread_id,
        "flow": load_flow_rules(app.flow_key),
        "flags": load_state(app, thread_id, role_key),
    }
    try:
        view.update(app.context_fn(thread_id, user if isinstance(user, dict) else {}))
    except Exception:
        logger.exception("案台域事实读取失败 flow=%s", app.flow_key)
    from app.services.agent_write_confirm import pending_tools
    view["pending"] = pending_tools(thread_id)
    step, complete = None, False
    steps = view["flow"]["steps"]
    if steps:
        # 指针走图（分支一等公民）：沿守卫放行的边从入节点可达；指针=首个可达且
        # 探针未过的节点。不可达=分流跳过不进指针；守卫未定（分流未判）也不进——
        # 判定节点完成、旗标落定后自然放行。
        reach = branch_reach(steps, view["flow"].get("edges") or [], view)
        for s in steps:
            k = str(s.get("key") or "")
            if reach.get(k) != "reachable":
                continue
            comp = s.get("completion")
            if comp is None or not _eval_completion(comp, view):
                step = s  # 无声明=配置缺失，指针停在该节点（显性暴露配置错误）
                break
        else:
            # 可达链全过 + 无未决守卫 = 链走完；还有 undecided（分流没判）不算完
            complete = not any(reach.get(str(s.get("key") or "")) == "undecided"
                               for s in steps)
    view["step"] = step
    view["step_key"] = step["key"] if step else ""
    view["complete"] = complete
    return view


def digest(app: TransactionApp, view: dict) -> str:
    """案台摘要（纯事实，供大脑看现场；行为指令只住左栏规则，此处永不出现）。"""
    lines = ["【当前案台】"]
    try:
        lines += list(app.digest_lines(view) or [])
    except Exception:
        logger.exception("案台事实行渲染失败 flow=%s", app.flow_key)
    for tool in sorted(view.get("pending") or {}):
        # 不给大脑看原始参数 JSON：sheet_id=0 这类哨兵值曾被当成"异常值"误读，
        # 引发自行改参数重试（2026-10-22 实锤）。执行由确认卡直达/带 confirm 重调，
        # 参数一律以 staged 为准，大脑无需背参数。
        lines.append(f"· 待确认: {tool}（确认卡已就绪：预览已出、未执行；"
                     f"有效期约 {max(1, int(view['pending'][tool]) // 60)} 分钟，用户点卡即执行）")
    return "\n".join(lines)


def _resolve_ref(v: Any, result: dict) -> Any:
    """声明旗标 set 值支持 $result.x.y 引用（携带工具结果里的动态值，任意深度）。"""
    if isinstance(v, str) and v.startswith("$result."):
        cur: Any = result
        for part in v[len("$result."):].split("."):
            if not isinstance(cur, dict) or part not in cur:
                return ""
            cur = cur[part]
        return cur
    if isinstance(v, dict):
        return {k: _resolve_ref(x, result) for k, x in v.items()}
    if isinstance(v, list):
        return [_resolve_ref(x, result) for x in v]
    return v


def apply_facts(app: TransactionApp, thread_id: str, role_key: str, facts: list) -> None:
    """把本轮工具执行事实回写状态槽。旗标映射优先走流配置的声明表
    （graph.flag_rules：[{tool, set: {旗标: 值|$result.路径}}]——建分支流零代码），
    没配声明表的应用回退自身旗标钩子；成败一律以工具返回为准。"""
    if not facts:
        return
    flags: dict = {}
    try:
        flow = load_flow_rules(app.flow_key)
        for f in facts or []:
            if not isinstance(f, dict) or not isinstance(f.get("result"), dict) \
                    or not f["result"].get("ok"):
                continue
            tool = str(f.get("tool") or "")
            for r in flow.get("flag_rules") or []:
                if str(r.get("tool") or "") != tool:
                    continue
                for fk, fv in (r.get("set") or {}).items():
                    flags[str(fk)] = _resolve_ref(fv, f["result"])
    except Exception:
        logger.exception("声明旗标回写失败 flow=%s", app.flow_key)
    if not flags and app.flags_from_facts is not None:
        try:
            flags = app.flags_from_facts(facts) or {}
        except Exception:
            logger.exception("旗标回写失败 flow=%s", app.flow_key)
            return
    if not flags:
        return
    state = load_state(app, thread_id, role_key)
    state.update(flags)
    save_state(app, thread_id, role_key, state)
