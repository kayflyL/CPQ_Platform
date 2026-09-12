# -*- coding: utf-8 -*-
"""节点插件注册表（契约化重构：拆节点机制）。

编排壳（run_skill_agent_turn / _engine_begin_step / prepare_step / validate_step_end）
只调用插件钩子；「这个节点有什么机制」全部由插件声明，编排壳里不再出现
`if step_key == "xxx"` / `if node_key == "xxx"`。新增节点 = 注册一个插件（换插头），
编排壳零改动。未注册节点走 DefaultNodePlugin（无预处理、无专属卡片、校验通过）。

钩子（DefaultNodePlugin 全是空实现）：
- narration_key            该节点的旁白键（引擎下游消费）。非空 = 大脑节点。
- prepare(ctx, cfg, bcast) 步骤开始前的确定性预处理（引擎自动调用）
- bridge_ctx(engine, ctx)  把该步干活所需上下文桥接进工具上下文
- delivery_gap(engine)     推进/交付卡住时的**结构化**出路卡（数据驱动，非话术）
- enrich_ask_gap(...)      ask_user 升格成缺口卡时的节点专属装饰
- extra_ask_options(...)    行卡上由节点**结构性**补全的选项（如「保持原需求」出路）
- validate(ctx)            步骤结束校验：该步产物在不在
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 行卡第三结局的出路文案（结构性出口：客户点名了型号、库里没有时由插座补上）
ROW_KEEP_ORIGINAL_LABEL = "保持原需求（库里暂无此料，本行按原需求留白）"


def _row_meta(engine: dict, row_ref: str) -> dict:
    """行引用（row_id / origin / 行键）→ 行身份；解析不到返回 {}（绝不猜文本）。"""
    from app.services.part_selector import row_ref_meta
    from app.services.skill_node_state import KP_ROW_IDS, kp_state
    return row_ref_meta(row_ref, engine.get("kp_parts"), kp_state(engine).get(KP_ROW_IDS))


def _row_part(engine: dict, meta: dict) -> dict:
    """按身份取回行清单里的那一行（行清单是身份的权威表）。"""
    from app.services.part_selector import kp_row_id
    if not isinstance(meta, dict) or not meta.get("row_id"):
        return {}
    for p in (engine.get("kp_parts") or []):
        if not isinstance(p, dict):
            continue
        cat = str(p.get("category") or "").strip()
        if not cat:
            continue
        _spec = str(p.get("request_spec") or "").strip() or cat
        if (str(p.get("row_id") or "").strip() or kp_row_id(cat, _spec)) == meta.get("row_id"):
            return p
    return {}


def _series_of(engine: dict) -> str:
    """行卡候选/豁免判定共用的机型平台（已锁定机箱的 series）。"""
    return str(((engine.get("_locked_baseline") or {}).get("series")) or "")


class DefaultNodePlugin:
    """未注册 / 无专属机制的节点：声明式空实现，编排壳可直接调。"""

    key = ""
    narration_key = ""
    owns_doc = ""          # 该节点拥有的上游冻结文档槽名；空串 = 不拥有任何冻结文档

    async def prepare(self, ctx: dict, cfg: dict, broadcast=None) -> dict:
        return {"ok": True, "step": self.key, "hint": "步骤就绪"}

    def bridge_ctx(self, engine: dict, ctx: dict) -> None:
        return None

    def delivery_gap(self, engine: dict) -> Optional[dict]:
        return None

    def stuck_gap(self, engine: dict) -> Optional[dict]:
        """本步回喂耗尽、**推进不动**时的结构化出路卡（默认无：如实交给大脑重述提问）。

        与 delivery_gap 的区别只在触发时机：delivery_gap 是「出路一就绪就即刻交客户」
        （如机型候选池）；stuck_gap 只在编排壳确认该步真的卡住之后才被调用，
        不会抢在大脑自己提问之前把机制话术抛给客户。
        """
        return None

    def enrich_ask_gap(self, engine: dict, gap: dict, ask: dict) -> dict:
        return gap

    def extra_ask_options(self, engine: dict, ask: dict, row_key: str) -> list:
        """行卡上由节点**结构性**补全的选项（默认无：选项由大脑给）。

        只在「这个状态必然有这条出路」时覆写——选项仍由统一信号出口
        （skill_plan_runtime.ask_option_signal）解释，节点不自己造信号。
        """
        return []

    def wire_result(self, engine: dict, result: dict) -> None:
        """把大脑本轮的工具结果接进引擎产物（默认什么都不接）。"""
        return None

    def artifact_contract(self, node_cfg: dict) -> str:
        """该节点产物的输出契约文本（默认取抽屉 target.artifacts 第一条；无则空串）。"""
        from app.services.skill_target_contract import first_artifact, format_contract
        return format_contract(first_artifact(node_cfg))

    async def validate(self, ctx: dict) -> dict:
        return {"ok": True}


class _FillNode(DefaultNodePlugin):
    """agent_fill：理解需求并登记线索登记表（登记表属主节点）。

    校验 = 必填闸门：契约里的必填字段没填完 → 不通过（回喂大脑补做，
    绝不把机制文案抛给客户）。目录字段可初判（可错、不必反问），非目录字段才要客户确认。
    """

    key = "agent_fill"
    narration_key = "fill_narration"
    owns_doc = "requirement_slots"

    def artifact_contract(self, node_cfg: dict) -> str:
        """登记表契约走通用目标层插头解释（slot=requirement_slots），不再有 kind=form 特判。"""
        return fill_contract_brief(node_cfg)

    async def prepare(self, ctx: dict, cfg: dict, broadcast=None) -> dict:
        """步骤就绪 + 选型规则推导值（事实摆桌）：登记事实（如 CPU 行兆芯信号）命中 CRE
        赋值型 derive 时，把空缺目录槽的推导值放进步骤提示。怎么用住在任务规则
        （19：推断值须经客户确认；13：不既填又追问）——这里只报事实，不写指令。
        """
        ext = ctx.get("ext") or {}
        hint = "步骤就绪"
        try:
            from app.services.plan_rule_apply import catalog_derivations_for_registration
            derived = catalog_derivations_for_registration(ext)
            if derived:
                from app.services.slot_contract import slot_label
                hint += "；选型规则推导值：" + "；".join(
                    f"{slot_label(s)}({s})={v}" for s, v in derived) + "（推断值）"
        except Exception:
            logger.exception("登记阶段目录推导失败（降级：不带推导值继续）")
        return {"ok": True, "step": self.key, "hint": hint}

    def wire_result(self, engine: dict, result: dict) -> None:
        """登记回合结束后做语义契约后处理（工作负载/国产化等确定性补全）+ 写回需求草稿。

        2026-09-12 B2：登记表属主节点每轮把当轮工作副本原地写回该商机的需求草稿
        （create_or_update_requirement_draft 已保证一商机一草稿），真相因此落在真实表上；
        写模式非 draft（试运行/无商机）时持久化层直接返回 None，不落库、只出预览。
        """
        ext = engine.get("ext")
        if not isinstance(ext, dict):
            return
        try:
            from app.services.capabilities import _enrich_agent_semantic
            _enrich_agent_semantic(ext, (engine.get("flow_configs") or {}).get(self.key),
                                   str(engine.get("requirement_text") or ""))
        except Exception:
            logger.exception("登记表语义后处理失败")
        try:
            from app.services.portal_flow_adapter import persist_requirement_from_ctx
            persist_requirement_from_ctx(engine, str(engine.get("operator_name") or ""))
        except Exception:
            logger.exception("写回需求草稿失败 opp=%s", engine.get("opportunity_id"))

    async def validate(self, ctx: dict) -> dict:
        ext = ctx.get("ext") or {}
        try:
            from app.services.slot_contract import _missing_critical, slot_label, slot_spec
            from app.services.capabilities import _slot_now_filled
            missing = [m for m in _missing_critical(ext) if not _slot_now_filled(ext, m)]
        except Exception:
            logger.exception("agent_fill end 校验回读失败")
            missing = []
        if missing:
            # 契约化：目录字段从目录候选初判填充（可错，不必反问）；非目录字段才需要客户确认。
            # 字段契约（candidate_source/catalog_dimension）是唯一真相源，避免「工具不许填、校验又要填」死锁。
            spec = {str(s.get("key") or ""): s for s in slot_spec()}
            cat_miss = [m for m in missing if (spec.get(m) or {}).get("candidate_source") == "catalog"]
            free_miss = [m for m in missing if (spec.get(m) or {}).get("candidate_source") != "catalog"]
            if cat_miss:
                parts = []
                for m in cat_miss:
                    dim = str((spec.get(m) or {}).get("catalog_dimension") or "").strip()
                    parts.append(f"{slot_label(m)}（目录维度 {dim}）" if dim else slot_label(m))
                # 只报事实（缺哪些目录字段）。怎么补由左栏任务规则与工具契约决定——
                # 代码里再写「先问哪个 / 怎么措辞」就是第二套提示词。
                return {"ok": False, "hint": f"目录字段还缺：{'、'.join(parts)}"}
            if free_miss:
                names = "、".join(slot_label(m) for m in free_miss[:3])
                dv = (spec.get(free_miss[0]) or {}).get("default_value")
                if dv is not None:
                    return {"ok": False, "hint": f"非目录字段还缺：{names}（契约默认值 {dv}）"}
                return {"ok": False, "hint": f"非目录字段还缺：{names}"}
        # 目录前提闸门：决定「库里有没有料」的字段（配件适用性按系列过滤）必须先经客户拍板。
        # 客户完全没提时你先推断一个没问题，但**不能带着推断值进配件选配**——推断错会让下游
        # 每一行都无料可锁。引擎只提供事实（哪些值不在客户确认记录里），怎么说由大脑组织。
        from app.services.slot_contract import unconfirmed_premise_fields
        gaps = unconfirmed_premise_fields(ext)
        if gaps:
            detail = "、".join(f"{g['label']}={g['value']}" for g in gaps)
            # 只报事实（哪些前提字段没有客户确认记录）。申报通道（customer_stated）与
            # 选项卡参数（slot/value）住在工具契约里，确认时机住在任务规则 19 里。
            return {"ok": False, "hint": f"前提字段无客户确认记录：{detail}"}
        return {"ok": True}


class _ModelNode(DefaultNodePlugin):
    """model_reason：机型选型。预处理=候选池/显式锁定；出路卡=结构化机型候选卡；校验=机型已锁定。"""

    key = "model_reason"
    narration_key = "model_narration"
    # 结果接线契约：把「哪个工具、结果的哪个字段、落到引擎的哪个候选池」声明在这里，
    # wire_result 只做通用接线，不出现 choose_model / server_model_id 等业务名。
    result_tool = "choose_model"
    result_selected_key = "selected"
    result_id_key = "model_id"
    result_name_key = "name"
    result_pool_key = "baselines_pool"
    pool_id_keys = ("server_model_id", "id")
    pool_name_key = "name"
    default_reason = "AI 按需求在候选池内选定"
    lock_func_path = "app.services.skill_phases:_lock_baseline"
    progress_func_path = "app.services.portal_flow_adapter:save_scheme_progress_from_ctx"

    async def prepare(self, ctx: dict, cfg: dict, broadcast=None) -> dict:
        key = self.key
        from app.services.skill_phases import prepare_model_step
        info = prepare_model_step(ctx)
        if info.get("invalid_scene"):
            return {"ok": False, "hint": "登记的类型不在在售目录且系列/形态不全"}
        locked = info.get("auto_locked")
        if locked:
            return {"ok": True, "step": key, "auto_locked": locked,
                    "hint": f"已按登记信号自动锁定「{locked}」（客户指定/目录唯一命中）"}
        if not (info.get("pool") or 0):
            return {"ok": False, "hint": "登记信号不足以查目录（缺类型/场景）"}
        return {"ok": True, "step": key, "pool": info.get("pool"),
                "hint": f"候选池 {info.get('pool')} 个机型已就绪"}

    def bridge_ctx(self, engine: dict, ctx: dict) -> None:
        ctx["model_pool"] = [c for c in (engine.get("baselines_pool") or [])
                             if isinstance(c, dict)][:12]

    def wire_result(self, engine: dict, result: dict) -> None:
        """大脑 choose_model 的结果落锁：写本节点产物（baseline/model_selection），不回填登记表。"""
        for c in reversed((result or {}).get("tool_calls_log") or []):
            if (c or {}).get("name") != self.result_tool:
                continue
            res = c.get("result")
            if not isinstance(res, dict) or not res.get("ok"):
                break
            sel = res.get(self.result_selected_key) if isinstance(res.get(self.result_selected_key), dict) else {}
            sid = str(sel.get(self.result_id_key) or "").strip()
            sname = str(sel.get(self.result_name_key) or "").strip().lower()
            hit = None
            for cand in (engine.get(self.result_pool_key) or []):
                if not isinstance(cand, dict):
                    continue
                cid = next((str(cand.get(k) or "").strip() for k in self.pool_id_keys
                            if str(cand.get(k) or "").strip()), "")
                cname = str(cand.get(self.pool_name_key) or "").strip()
                if (sid and cid and cid == sid) or (sname and cname and cname.lower() == sname):
                    hit = cand
                    break
            if hit is None:
                logger.warning("%s 结果不在候选池，忽略落锁 name=%s", self.result_tool, sel.get(self.result_name_key))
                break
            import importlib
            mod_name, _, func_name = self.lock_func_path.partition(":")
            _lock_baseline = getattr(importlib.import_module(mod_name), func_name)
            reason = str(res.get("reason") or "").strip() or self.default_reason
            engine["model_pick"] = {self.result_id_key: sid,
                                    self.result_name_key: str(hit.get(self.pool_name_key) or "")}
            engine["model_pick_reason"] = reason
            _lock_baseline(engine, hit, reason)
            # B3：机型一锁就把当前进度原地写回该商机的方案配置草稿（L6 段先落，配件段随后补）。
            try:
                mod_name, _, func_name = self.progress_func_path.partition(":")
                save_progress = getattr(importlib.import_module(mod_name), func_name)
                save_progress(engine, str(engine.get("operator_name") or ""))
            except Exception:
                logger.exception("写方案配置草稿失败 opp=%s", engine.get("opportunity_id"))
            break

    def delivery_gap(self, engine: dict) -> Optional[dict]:
        """机型候选已就绪但未锁定 → 系统结构化候选卡（可点选/手输）；否则 None。"""
        pool = [c for c in (engine.get("baselines_pool") or []) if isinstance(c, dict)]
        if not pool:
            return None
        locked = (engine.get("_locked_baseline") or {}).get("name") \
            or str((engine.get("ext") or {}).get("server_model") or "").strip()
        if locked:
            return None
        from app.services.skill_phases import model_gap
        return model_gap(pool, include_price=bool(engine.get("price_access", True)))

    async def validate(self, ctx: dict) -> dict:
        locked = (ctx.get("_locked_baseline") or {}).get("name") \
            or str((ctx.get("ext") or {}).get("server_model") or "").strip()
        if not locked:
            return {"ok": False, "hint": "机型尚未锁定（choose_model 与客户指定都没有）"}
        return {"ok": True, "locked": locked}


class _KpNode(DefaultNodePlugin):
    """kp_reason：配件选型。预处理=行就绪；工具上下文=行清单/类目；校验=行全部落地。"""

    key = "kp_reason"
    narration_key = "kp_narration"

    async def prepare(self, ctx: dict, cfg: dict, broadcast=None) -> dict:
        key = self.key
        from app.services.skill_phases import phase_kp_reason
        await phase_kp_reason(ctx, cfg, broadcast)
        summary = dict(ctx.get("kp_summary") or {})
        return {"ok": True, "step": key,
                "kp_parts": ctx.get("kp_parts") or [],
                "landed": summary.get("kp_count") or 0,
                "unmatched": summary.get("unmatched_count") or 0,
                "hint": (f"配件行已就绪：已落地 {summary.get('kp_count')} 行、待选型 "
                         f"{summary.get('unmatched_count')} 行"
                         + (f"、库内无料已获客户知悉 {summary.get('waived_count')} 行"
                            if summary.get("waived_count") else ""))}

    def bridge_ctx(self, engine: dict, ctx: dict) -> None:
        ctx["kp_series"] = str(((engine.get("_locked_baseline") or {}).get("series")) or "")
        from app.services.part_selector import (kp_row_key, kp_row_id, kp_registered_specified,
                                               pick_for_row, pick_is_stale)
        from app.services.skill_node_state import (KP_ROW_IDS, KP_PICKS, KP_RECOMMEND, kp_state,
                                           row_answer_text, waived_row_keys)
        _st = kp_state(engine)
        _picks = _st.get(KP_PICKS) if isinstance(_st.get(KP_PICKS), dict) else {}
        _recs = _st.get(KP_RECOMMEND) if isinstance(_st.get(KP_RECOMMEND), dict) else {}
        _waived = waived_row_keys(engine)
        rows: list = []
        _seen_ids: set = set()   # 行身份唯一：同一 row_id 只发布一条（P3-4）
        all_rows: list = []
        for p in (engine.get("kp_parts") or []):
            if not isinstance(p, dict):
                continue
            cat = str(p.get("category") or "").strip()
            if not cat:
                continue
            desc = str(p.get("request_spec") or "").strip() or cat
            # 行身份唯一（P3-4 实测）：组合件会让同一行在 BOM 里落成多条明细（实测 NIC 一行 =
            # 网卡+光模块共 3 条），但**行清单是身份的权威表**——同一 row_id 只发布一条，
            # 否则清单里同一个 row_id 出现三次，AI 引用的「唯一权威」就不成立了。
            _rid = str(p.get("row_id") or "").strip() or kp_row_id(cat, desc)
            if _rid in _seen_ids:
                continue
            _seen_ids.add(_rid)
            _rk = kp_row_key(cat, desc)
            _ans = row_answer_text(engine, _rk)
            if not _ans:
                # 卡片行引用已改绑 row_id（P3-3），客户回答可能按身份记，两种键都读。
                _ans = row_answer_text(engine, str(p.get("row_id") or ""))
            _row = {"row_key": _rk,
                    "row_id": _rid,
                    "origin": str(p.get("origin") or ""),
                    "rev": str(p.get("rev") or ""),
                    "category": cat,
                    "description": desc, "qty": p.get("qty") or 1,
                    "specified": kp_registered_specified(ctx.get("ext"), cat)}
            if _ans:
                _row["answer"] = _ans
            # 行状态（含**已了结**行）：大脑看不见自己处理过哪几行，就会从客户原话重新拼一个
            # 措辞略不同的行键、把同一件事再问一遍（2026-09-11 实测靶心：RAID 卡/系统盘各问 3 次）。
            status, part = "待处理", ""
            # P3-2：pick/推荐按行身份解析（row_id 键），豁免键可能是行键/row_id/origin 三种形态。
            _got = pick_for_row(_picks, cat, desc, row=p)
            _got_first = _got[0] if isinstance(_got, list) and _got else _got
            _got_stale = pick_is_stale(_got_first, cat, desc)
            if (p.get("waived") or _rk in _waived
                    or str(p.get("row_id") or "") in _waived
                    or str(p.get("origin") or "") in _waived):
                status = "已了结（库内无料，客户已知悉）"
            elif _got and not _got_stale:
                _items = _got if isinstance(_got, list) else [_got]
                _names = [str(i.get("name") or "") for i in _items if isinstance(i, dict)]
                status = "已锁定"
                part = "+".join(n for n in _names if n)
            if status == "待处理" and not p.get("unmatched") and str(p.get("name") or "").strip():
                # 已落地的行即使本节点没记 pick（历史通路留下的真实料号行）也算已了结。
                status, part = "已锁定", str(p.get("name") or "")
            if status == "待处理":
                _rc = pick_for_row(_recs, cat, desc, row=p)
                _rec = _rc[0] if isinstance(_rc, list) and _rc else _rc
                if isinstance(_rec, dict) and not pick_is_stale(_rec, cat, desc):
                    status, part = "推荐待确认", str(_rec.get("name") or "")
            all_rows.append({**_row, "status": status, "part": part,
                             "settled": status != "待处理" and status != "推荐待确认"})
            if p.get("unmatched"):
                rows.append(_row)
        ctx["kp_rows_ctx"] = rows
        # 全量行清单（含已了结）：行引用的唯一权威表——AI 只能用这里的 row_id，
        # 手拼措辞不再能悄悄长出一行新部件。
        ctx["kp_rows_all"] = all_rows
        # 身份铸造台账（P3-1）：按来源记账，rev/描述可更新，row_id 一经铸造不再变。
        _ids = _st.get(KP_ROW_IDS) if isinstance(_st.get(KP_ROW_IDS), dict) else {}
        for _r in all_rows:
            _o = str(_r.get("origin") or "").strip()
            if not _o or not str(_r.get("row_id") or "").strip():
                continue
            _prev = _ids.get(_o) if isinstance(_ids.get(_o), dict) else {}
            _ids[_o] = {**_prev, "row_id": str(_r.get("row_id") or ""),
                        "rev": str(_r.get("rev") or ""),
                        "category": str(_r.get("category") or ""),
                        "description": str(_r.get("description") or "")}
        if _ids:
            _st[KP_ROW_IDS] = _ids
        from app.services.skill_phases import kp_required_categories
        _kc = (engine.get("flow_configs") or {}).get("kp_reason")
        _kc = _kc if isinstance(_kc, dict) else {}
        ctx["kp_required_cats"] = kp_required_categories(_kc)

    def _row_qty(self, engine: dict, row_key: str) -> int:
        part = _row_part(engine, _row_meta(engine, row_key))
        try:
            return max(1, int(part.get("qty") or 1))
        except (TypeError, ValueError):
            return 1

    def _row_pick_options(self, engine: dict, row_key: str, qty: int) -> list:
        """该行**库内候选** → 卡选项（数据驱动）。

        候选实时回库按行描述召回（2026-09-12 去台账：不再读「本轮检索留底」的索引）；
        召回零命中就返回空（宁缺毋滥，绝不把整库端上来、更不编料号）。
        """
        meta = _row_meta(engine, row_key) or {}
        cat = str(meta.get("category") or "").strip()
        if not cat:
            return []
        desc = str(meta.get("description") or "").strip() or cat
        from app.services.data_tools import part_recall
        q = part_recall(cat, desc=desc, series=_series_of(engine), limit=8,
                        price_ok=bool(engine.get("price_access")))
        opts: list = []
        for c in ((q.get("rows") or []) if q.get("ok") else [])[:8]:
            if not isinstance(c, dict) or not str(c.get("name") or "").strip():
                continue
            name = str(c.get("name"))
            pick = {"part_id": str(c.get("part_id") or ""), "name": name,
                    "currency": str(c.get("currency") or "RMB"), "qty": qty}
            if c.get("price") is not None:
                pick["price"] = c.get("price")
            brief = " · ".join(f"{k}:{v}" for k, v in (c.get("specs") or {}).items())[:80]
            opts.append({"label": name, "value": name, "pick": pick, "description": brief,
                         "desc": brief, "qty": qty, "qty_max": max(qty, 24),
                         "group": "配件库候选"})
        return opts

    def _waived_options(self, engine: dict, row_key: str) -> list:
        """客户点名型号、库内确实无料时的第三条出路（行保留 + 标注，终检放行）。

        两个前提都成立才给：① 该行是客户**点名登记**的（`kp_registered_specified`，
        只看状态、不做任何文本匹配）；② 该行点名的型号按**料号名**回库精确核对查无此名，
        且没有被机型平台挡在门外的同名料（那是「适配不符」不是「库里没有」）。

        2026-09-12 去台账：判定从「大脑本轮检索留底为空」改成当场按料号名回库核对。
        与行卡候选（_row_pick_options 当场按行描述回库召回）同源：点名的型号在库里
        就是「有料可换」，库内查无此名才让客户在「换料 / 就这样」里选——两条出路可并存。
        """
        meta = _row_meta(engine, row_key) or {}
        cat = str(meta.get("category") or "").strip()
        if not cat:
            return []
        from app.services.part_selector import kp_registered_specified
        if not kp_registered_specified(engine.get("ext"), cat):
            return []
        from app.services.data_tools import lookup_parts_by_name
        desc = str(meta.get("description") or "").strip() or cat
        lk = lookup_parts_by_name(cat, desc, series=_series_of(engine),
                                  price_ok=bool(engine.get("price_access")))
        if not lk.get("ok") or lk.get("rows") or lk.get("out_of_scope"):
            return []
        note = "库里确实没有该行点名的型号：行保留并标注「库内无料、客户已知悉」"
        return [{"label": ROW_KEEP_ORIGINAL_LABEL, "value": ROW_KEEP_ORIGINAL_LABEL,
                 "description": note, "desc": note, "waived": True, "group": ""}]

    def extra_ask_options(self, engine: dict, ask: dict, row_key: str) -> list:
        """行卡上由节点**结构性**补全的选项：插座保证「行卡一定有可点的出路」。

        大脑给的行卡选项如果**一条都不带信号**（忘给 pick/absent/waived，或只丢了个问题
        过来），客户点上去什么都不会发生——那等于没给卡，线程就此停住（实测形态：
        旁白说「选项卡已发出」、卡上零选项）。此时由插座补上该行**库内候选**
        （实时回库按行描述召回）＋客户点名型号无料时的「保持原需求」。
        大脑自己给了可用选项就不抢，只补它漏掉的「保持原需求」。
        """
        if not _row_meta(engine, row_key):
            return []
        brain_opts = [o for o in ((ask or {}).get("options") or []) if isinstance(o, dict)]
        usable = any(o.get("pick") or o.get("absent") or o.get("waived") for o in brain_opts)
        out = [] if usable else self._row_pick_options(engine, row_key,
                                                       self._row_qty(engine, row_key))
        if not any(o.get("waived") for o in list(out) + brain_opts):
            out = out + self._waived_options(engine, row_key)
        # 选项 → 信号仍由统一出口解释（skill_plan_runtime.ask_option_signal），节点不造信号
        return out

    def enrich_ask_gap(self, engine: dict, gap: dict, ask: dict) -> dict:
        """行级选件卡：大脑对某条登记行提问时，把该行绑进卡（选项可带 pick 直接落地）。"""
        row = str((ask or {}).get("row") or "").strip()
        meta = _row_meta(engine, row) if row else {}
        if meta:
            cat = str(meta.get("category") or "").strip()
            spec = str(meta.get("description") or "").strip()
        elif "|" in row:
            # 旧数据兼容：行引用仍是引擎自己的复合行键「类目|描述」（P3-3 前的卡）
            cat, spec = row.split("|", 1)
            cat, spec = cat.strip(), spec.strip()
        else:
            return gap
        gap["parts_card"] = True
        gap["row"] = row
        gap["pick_meta"] = {"row": row, "category": cat.strip(), "request_spec": spec.strip(),
                            "series": str(((engine.get("_locked_baseline") or {}).get("series")) or ""),
                            "pool": [], "pool_source": "brain_ask"}
        return gap

    def stuck_gap(self, engine: dict) -> Optional[dict]:
        """配件选型**卡住**（仍有未落地行）时，由插座自己把该行交客户拍板。

        这是「插座兜底」而不是「引擎替大脑决策」：选项全是数据——库内候选取自大脑本轮
        行描述实时回库召回，客户点名型号库内无料时再补「保持原需求」（waived）；
        选项信号仍由唯一出口（ask_option_signal）解释。引擎不替客户认账、也不编料号。
        """
        row = next((p for p in (engine.get("kp_parts") or [])
                    if isinstance(p, dict) and p.get("unmatched")), None)
        if row is None:
            return None
        from app.services.part_selector import kp_row_key
        cat = str(row.get("category") or "").strip()
        if not cat:
            return None
        desc = str(row.get("request_spec") or "").strip() or cat
        row_key = kp_row_key(cat, desc)
        # 卡一律按行身份绑行（P3-3）：身份未铸造（旧线程）才退回复合行键
        ref = str((_row_meta(engine, row_key) or {}).get("row_id") or "").strip() or row_key
        row_qty = self._row_qty(engine, ref)
        opts = (self._row_pick_options(engine, ref, row_qty)
                + self._waived_options(engine, ref))
        if not opts:
            return None
        from app.services.skill_plan_runtime import ask_option_signal
        for o in opts:
            sig = ask_option_signal(ref, o, "kp_row", category=cat)
            if sig:
                o["signal"] = sig
        if not any(o.get("signal") for o in opts):
            return None
        for o in opts:  # 卡渲染只认 slot/value/desc
            o.setdefault("slot", "kp_row")
        return {"slot": "kp_row", "reason_code": "kp_pick", "question": "",
                "row": ref, "parts_card": True,
                "qty": row_qty, "qty_max": max(row_qty, 24),
                "pick_meta": {"row": ref, "category": cat, "request_spec": desc,
                              "row_qty": row_qty,
                              "series": str(((engine.get("_locked_baseline") or {}).get("series")) or "")},
                "options": opts}

    async def validate(self, ctx: dict) -> dict:
        await refresh_kp_state(ctx)  # 大脑刚提交的 pick 落进行表后再校验（快照会误判）
        # B3：配件段一落定就把当前进度原地写回该商机的方案配置草稿（L6 + KP 段）；
        # 写模式非 draft（试运行/无商机）时持久化层直接不写，仍只出预览。
        try:
            from app.services.portal_flow_adapter import save_scheme_progress_from_ctx
            save_scheme_progress_from_ctx(ctx, str(ctx.get("operator_name") or ""))
        except Exception:
            logger.exception("写方案配置草稿失败 opp=%s", ctx.get("opportunity_id"))
        summary = dict(ctx.get("kp_summary") or {})
        unmatched = int(summary.get("unmatched_count") or 0)
        if unmatched > 0:
            return {"ok": False, "hint": f"仍有 {unmatched} 行未落地"}
        if int(summary.get("kp_count") or 0) == 0 and int(summary.get("waived_count") or 0) == 0:
            return {"ok": False, "hint": "没有任何配件行落地——核对登记表部件是否漏登记"}
        return {"ok": True, "landed": summary.get("kp_count")}


class _ComposeNode(DefaultNodePlugin):
    """compose：BOM 组装。前置齐备后由引擎自动组装（确定性）。"""

    key = "compose"

    async def prepare(self, ctx: dict, cfg: dict, broadcast=None) -> dict:
        key = self.key
        done = ctx.get("steps_done") or set()
        missing_pre = [s for s in ("agent_fill", "model_reason", "kp_reason") if s not in done]
        if missing_pre:
            return {"ok": False, "hint": f"前置步骤未完成：{'、'.join(missing_pre)}"}
        await refresh_kp_state(ctx)  # 大脑提交过的选型落进行表后再判终检
        # 局部导入（同 skill_plan_runtime 风格，避开模块环）：此前漏了这行，
        # 整个函数一调用就 NameError——只是恰好没被走到，才没炸在脸上。
        from app.services.skill_plan_runtime import final_gate
        gate = final_gate(ctx, composing=True)
        if not gate.get("ok"):
            return gate
        return {"ok": True, "step": key, "hint": "前置齐备，系统将自动组装整机方案"}

    async def validate(self, ctx: dict) -> dict:
        return {"ok": True} if ctx.get("plans") else {"ok": False, "hint": "尚未组装整机方案"}


def fill_contract_brief(node_cfg: dict | None = None) -> str:
    """登记契约简报 = 目标层插头解释（slot=requirement_slots）的产物，零业务话术。

    字段/值域/部件大类全部读配置与数据（见 skill_target_contract.format_requirement_slots_contract）；
    填写规则属于抽屉 description（节点使命）。换目标层（改登记表字段 / KP 大类 / 在售目录）
    此处自动跟随——这是 agent_fill 可复用到其他 skill 的接口要求：树干只描述形状，
    业务内容全部来自配置与数据。
    """
    from app.services.skill_target_contract import first_artifact, format_contract
    art = first_artifact(node_cfg) or {'slot': 'requirement_slots', 'name': '线索登记表'}
    return format_contract(art)


# ── 注册表：节点 key → 插件。新增节点只在这里加一行（编排壳零改动）。────────────────────
_PLUGINS: dict = {p.key: p for p in (_FillNode(), _ModelNode(), _KpNode(), _ComposeNode())}

_DEFAULT = DefaultNodePlugin()


def register(plugin) -> None:
    """注册/覆盖一个节点插件（新增节点的唯一入口）。"""
    if str(getattr(plugin, "key", "") or "").strip():
        _PLUGINS[str(plugin.key)] = plugin


def plugin_for(node_key: str) -> DefaultNodePlugin:
    """取节点插件；未注册节点走默认插件（无专属机制）。"""
    return _PLUGINS.get(str(node_key or "").strip()) or _DEFAULT


def all_plugins() -> tuple:
    return tuple(_PLUGINS.values())


def brain_node_keys() -> set:
    """需要大脑回合执行的节点（有旁白键 = 有产物接线）。"""
    return {k for k, p in _PLUGINS.items() if p.narration_key}


def narration_key_of(node_key: str) -> str:
    return plugin_for(node_key).narration_key


def first_delivery_gap(engine: dict) -> Optional[dict]:
    """推进/交付卡住时的结构化出路卡：由注册了该出路的节点插件提供。"""
    for p in _PLUGINS.values():
        gap = p.delivery_gap(engine)
        if isinstance(gap, dict) and gap:
            return gap
    return None


def first_stuck_gap(engine: dict) -> Optional[dict]:
    """回喂耗尽后的结构化出路卡（同 first_delivery_gap，只是走 stuck_gap 的时机）。"""
    for p in _PLUGINS.values():
        gap = p.stuck_gap(engine)
        if isinstance(gap, dict) and gap:
            return gap
    return None


async def refresh_kp_state(ctx: dict) -> None:
    """重跑 kp 占位/落地装配（确定性、幂等）。"""
    from app.services.skill_phases import phase_kp_reason
    flow_configs = ctx.get("flow_configs") or {}
    cfg = flow_configs.get("kp_reason") if isinstance(flow_configs.get("kp_reason"), dict) else {}
    await phase_kp_reason(ctx, cfg, None)
