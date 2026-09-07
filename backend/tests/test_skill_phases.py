# -*- coding: utf-8 -*-
"""引擎（两器官架构）纯逻辑回归：信号门槛 / 无发明选件 / 场景守卫 / 缺口数据协议。"""
from app.services import part_selector as ps
from app.services.skill_phases import (
    inferred_confirm_gaps,
    kp_args_from_ext,
    kp_gate_gap,
    kp_mode_gap,
    model_signals_ready,
    parse_kp_mode,
    scene_gap,
)


def test_model_signal_gate_requires_type_or_series_form():
    assert not model_signals_ready({})
    assert not model_signals_ready({"usage": "跑数据库"})  # 原文/语义不是结构化信号
    assert model_signals_ready({"server_type_name": "通用计算服务器"})
    assert model_signals_ready({"series": "Orion", "form": "2U"})
    assert not model_signals_ready({"series": "Orion"})


def test_kp_args_only_from_structured_signals():
    ext = {"memory": {"total_gb": 128}, "gpu": [{"qty": 4}], "requirement_text": "随便"}
    args = kp_args_from_ext(ext)
    assert set(args) == {"memory", "gpu"}
    assert kp_args_from_ext({}) == {}


def test_parse_kp_mode_exact_match_only():
    assert parse_kp_mode("只要整机底座（L6）") == "l6_only"
    assert parse_kp_mode("需要配配件") == "need_parts"
    assert parse_kp_mode("不要配件") == ""  # 非业务选项值不猜（防关键词清单膨胀）
    assert parse_kp_mode("") == ""





def test_part_query_spec_filters_are_deterministic():
    """AI=配置器检索层：spec_filters 确定性收窄（Cores>=96→96 核、Capacity=480 GB、Media=HDD），
    不做排序/推荐——命中与否完全由库内真实 specs 决定，不再靠结构化 need 打分。"""
    from app.services.data_tools import part_query

    class _Repo:
        def get_categories(self):
            return [{"category": "CPU"}, {"category": "HDD/SSD"}]

        def get_by_category_with_specs(self, cat):
            cpu = [
                {"id": 1, "model": "KH50000 48C", "price": 1.0, "currency": "RMB",
                 "specs": {"Cores": "48", "Base Clock": "2.2 GHz"}},
                {"id": 2, "model": "KH50000 96C", "price": 2.0, "currency": "RMB",
                 "specs": {"Cores": "96", "Base Clock": "2.7 GHz"}},
                {"id": 3, "model": "AMD 9654", "price": 3.0, "currency": "RMB",
                 "specs": {"Cores": "96"}},
            ]
            hdd = [
                {"id": 4, "model": "480G SATA SSD", "price": 4.0, "currency": "RMB",
                 "specs": {"Capacity": "480 GB", "Media": "SSD"}},
                {"id": 5, "model": "6T SATA HDD", "price": 5.0, "currency": "RMB",
                 "specs": {"Capacity": "6 TB", "Media": "HDD"}},
            ]
            return {"CPU": cpu, "HDD/SSD": hdd}.get(cat, [])

    q = part_query("CPU", spec_filters=[{"spec_key": "Cores", "op": ">=", "value": 96}], _repo=_Repo())
    assert q["ok"] is True
    assert {r["name"] for r in q["rows"]} == {"KH50000 96C", "AMD 9654"}
    # 无关键词/无过滤 = 全量直出（确定性，不做排序/推荐）
    q2 = part_query("HDD/SSD", spec_filters=[{"spec_key": "Media", "op": "=", "value": "HDD"}], _repo=_Repo())
    assert [r["name"] for r in q2["rows"]] == ["6T SATA HDD"]
    q3 = part_query("HDD/SSD", _repo=_Repo())
    assert [r["name"] for r in q3["rows"]] == ["480G SATA SSD", "6T SATA HDD"]


def test_gap_protocol_is_data_only():
    """引擎缺口=纯数据（slot/reason_code/options），不含任何话术句子。"""
    gap = scene_gap({})
    assert gap["reason_code"] == "server_type_missing"
    assert gap["options"] and all(isinstance(o, dict) and o.get("value") for o in gap["options"])
    kgap = kp_mode_gap()
    assert kgap["reason_code"] == "kp_mode_undecided"
    assert set(kgap["options"]) == {"需要配配件", "只要整机底座（L6）"}


# ── 推断求证（2026-09-06）：凡推断必让客户确认 ─────────────────────────────

_CORPUS = "CPU：2颗兆芯50000 处理器\n内存：768GB DDR5\n服务：3年专业支持"


def test_inferred_slot_without_corpus_hit_gets_confirm_gap():
    ext = {"server_type": "通用计算服务器", "warranty_years": "3年"}
    gaps = inferred_confirm_gaps(ext, _CORPUS)
    assert len(gaps) == 1                       # warranty 原文有 → 只求证 server_type
    g = gaps[0]
    assert g["slot"] == "server_type" and g["reason_code"] == "inferred_confirm"
    assert g["current"] == "通用计算服务器"
    assert g["options"] and any(o.get("value") == "通用计算服务器" for o in g["options"])


def test_inferred_confirm_respects_marker_and_corpus():
    ext = {"server_type": "通用计算服务器",
           "confirmed_slots": {"server_type": "通用计算服务器"}}
    assert inferred_confirm_gaps(ext, _CORPUS) == []      # 点选确认过 → 不再问
    assert inferred_confirm_gaps({"server_type": "通用计算服务器"},
                                 _CORPUS + "\n就用通用计算服务器") == []  # 客户口头说过 → 不问
    # 值被大脑改写 → 确认标记失效，重新求证
    ext2 = {"server_type": "存储服务器", "confirmed_slots": {"server_type": "通用计算服务器"}}
    gaps2 = inferred_confirm_gaps(ext2, _CORPUS)
    assert gaps2 and gaps2[0]["current"] == "存储服务器"


def test_inferred_confirm_skips_qty_and_structured_slots():
    """purchase_qty 是引擎白盒默认；结构化值（list/dict）走部件表呈现，都不弹确认。"""
    ext = {"purchase_qty": 1, "memory": {"total_gb": 768}}
    assert inferred_confirm_gaps(ext, _CORPUS) == []


def test_kp_gate_requires_signals_or_decision():
    # AI=配置器：零信号/未决策不再拦截（交由大脑生成配置）；仅 l6_only 明确不放配件
    assert kp_gate_gap({"ext": {}}) is None
    assert kp_gate_gap({"ext": {"kp_mode": "只要整机底座（L6）"}}) is None
    assert kp_gate_gap({"kp_parts": [{"pn": "x"}]}) is None
    assert kp_gate_gap({"ext": {"memory": {"total_gb": 64}}}) is None


def test_cpu_without_model_never_invents_representative():
    rows = [{"model": "CheapCPU-1", "price": 1.0, "specs": {}},
            {"model": "AMD EPYC 9124", "price": 9999.0, "specs": {}}]

    class R:
        def get_by_category(self, cat):
            return rows

        def get_categories(self):
            return [{"category": "CPU"}]

    # 完全没提 CPU：不产行（旧实现会拿最低价代表件）
    parts = ps._ground_cpu(R(), "CPU", None, lambda r: min(r, key=lambda x: x["price"]))
    assert parts == []
    # 只给数量没型号：白盒缺口行，价 0，可手补
    parts = ps._ground_cpu(R(), "CPU", {"qty": 2}, lambda r: min(r, key=lambda x: x["price"]))
    assert len(parts) == 1 and parts[0]["unmatched"] and float(parts[0]["unit_price"]) == 0.0


# ── 2026-08-30 回归：多轮对话机型重弹 + 字符串信号瘫死 ────────────────────

def test_platform_not_derived_without_rule_store():
    """平台推导不在代码里（规则归策略中心，规则页待单独设计）：
    登记表只有 CPU 部件行时引擎不猜平台——platform_type 留空，交由用户/AI 选定。"""
    import asyncio
    from app.services.skill_phases import phase_normalize_slots

    async def _run():
        ctx = {"ext": {"kp_rows": [{"part_category": "CPU",
                                    "description": "2颗AMD EPYC 处理器", "qty": 2}]},
               "requirement_text": "2颗AMD EPYC"}
        gaps = await phase_normalize_slots(ctx, {}, None)
        return ctx, gaps

    ctx, gaps = asyncio.run(_run())
    assert not ctx["ext"].get("platform_type")
    assert not any(a.get("code") == "platform_derived" for a in ctx.get("assumptions") or [])
    # S1 一次问全：缺口以列表返回（空=放行；CPU-only 需求必有缺口，形状校验）
    assert isinstance(gaps, list)




# ── 2026-08-30 回归：系列适配过滤 + 场景推荐选项值回程解析 ──────────────────

def test_series_ok_canonical_semantics():
    from app.services.part_selector import _series_ok
    assert _series_ok(None, "Orion")            # 未标注=通用件
    assert _series_ok({}, "Orion")              # 无 series 键=通用件
    assert _series_ok({"series": ["Orion"]}, "Orion")
    assert not _series_ok({"series": ["Orion"]}, "Polaris")
    assert _series_ok({"series": ["Orion", "Polaris"]}, "Polaris")
    assert not _series_ok({"series": []}, "Orion")  # 空列表=全部隐藏
    assert _series_ok({"series": ["Orion"]}, "")    # 未锁系列=不过滤


def test_series_scoped_repo_filters_rows():
    from app.services.part_selector import _SeriesScopedRepo
    rows = [{"model": "u", "applicable": None},
            {"model": "o", "applicable": {"series": ["Orion"]}},
            {"model": "p", "applicable": {"series": ["Polaris"]}},
            {"model": "h", "applicable": {"series": []}}]

    class R:
        def get_by_category_with_specs(self, cat):
            return rows

    repo = _SeriesScopedRepo(R(), "Orion")
    got = [r["model"] for r in repo.get_by_category_with_specs("Memory")]
    assert got == ["u", "o"]


def test_option_signal_direct_apply():
    """场景推荐选项自带结构化 signal 载荷：点击直传 apply_structured_slots，
    不经过「构造字符串→再解析」的反序列化环。"""
    from app.services.slot_contract import apply_structured_slots
    ext = {}
    apply_structured_slots(ext, {"gpu": [{"model": "智铠100", "qty": 4}]}, "AI训练")
    apply_structured_slots(ext, {"cpu": {"model": "EPYC 9745", "qty": 2}}, "AI训练")
    apply_structured_slots(ext, {"memory": {"per_stick_gb": 32, "qty": 24}}, "AI训练")
    apply_structured_slots(ext, {"storage": [{"capacity_gb": 2048, "qty": 2, "media": "SSD"}]}, "AI训练")
    apply_structured_slots(ext, {"raid": [{"raid_levels": ["10"]}]}, "AI训练")
    assert isinstance(ext["gpu"], list) and ext["gpu"][0]["qty"] == 4
    assert "智铠" in str(ext["gpu"][0].get("model") or ext["gpu"][0].get("tokens"))
    assert ext["cpu"]["qty"] == 2 and "EPYC" in str(ext["cpu"].get("model"))
    assert ext["memory"]["qty"] == 24 and ext["memory"]["per_stick_gb"] == 32
    dg = ext["storage"]
    assert dg[0]["qty"] == 2 and dg[0].get("term") == "2048G" and dg[0].get("kind") == "SSD"
    assert ext["raid"][0].get("raid_levels") == ["10"]
    # 字符串形态的信号值不解析（语义归 LLM）：原样丢弃，不产生半结构
    ext2 = {"gpu": []}
    apply_structured_slots(ext2, {"gpu": "4张智铠100", "memory": "256G"}, "AI训练")
    assert ext2["gpu"] == [] and "memory" not in ext2


def test_decimal_capacity_parsing():
    # 容量解析统一收敛到 part_selector._gb_of（单一真值源，不再多份重复）
    from app.services.part_selector import _gb_of
    assert round(_gb_of("1.92T")) == 1966  # 不是 92T=94208
    assert round(_gb_of("3.84TB")) == 3932
    assert round(_gb_of("2TB")) == 2048
    assert round(_gb_of("256G")) == 256








def test_signal_with_qty_clamped_by_chassis():
    """stepper 数量参数：服务端克隆留底 signal 改数量，按机箱能力 clamp（客户端只传数字）。"""
    from app.services.skill_chat import _signal_with_qty
    meta = {"gpu_slots": 10, "max_dimm": 24, "max_cpu": 2}
    gpu = {"gpu": [{"model": "曙云C550", "qty": 10}]}
    sig = _signal_with_qty(gpu, 6, meta)
    assert sig["gpu"][0]["qty"] == 6 and gpu["gpu"][0]["qty"] == 10  # 原载荷不动
    assert _signal_with_qty(gpu, 99, meta)["gpu"][0]["qty"] == 10
    assert _signal_with_qty(gpu, 0, meta)["gpu"][0]["qty"] == 1
    mem = {"memory": {"per_stick_gb": 64, "qty": 24}}
    assert _signal_with_qty(mem, 17, meta)["memory"]["qty"] == 17
    assert _signal_with_qty(mem, 48, meta)["memory"]["qty"] == 24
    drives = {"storage": [{"capacity_gb": 2048, "qty": 2, "media": "SSD"}]}
    assert _signal_with_qty(drives, 4, meta)["storage"][0]["qty"] == 4
    assert _signal_with_qty(drives, 99, meta)["storage"][0]["qty"] == 16
    cpu = {"cpu": {"model": "EPYC 9745", "qty": 2}}
    assert _signal_with_qty(cpu, 1, meta)["cpu"]["qty"] == 1
    assert _signal_with_qty(cpu, 8, meta)["cpu"]["qty"] == 2


# ── 阶段3：配件确定性落地（引擎不再二次 AI 选型；未命中保持缺口交 AI 角色/用户决策）────────────────

def test_phase_kp_reason_surfaces_unmatched_as_gap(monkeypatch):
    """登记表已有 kp_rows 时：phase_kp_reason 只做占位落地，绝不虚构料号、绝不调 select_parts 预判。"""
    import asyncio
    from app.services import skill_phases

    def boom_select_parts(**kw):
        raise AssertionError("kp_rows 已存在时不应调 select_parts")

    monkeypatch.setattr("app.services.part_selector.select_parts", boom_select_parts)
    ctx = {"force_complete": True,
           "ext": {"kp_rows": [{"part_category": "CPU", "description": "KH50000", "qty": 2}]},
           "baselines": [{"server_model_id": 1, "id": 1, "series": "Orion", "server_type_name": "通用计算服务器"}]}
    asyncio.run(skill_phases.phase_kp_reason(ctx, {}, None))
    row = ctx["kp_parts"][0]
    assert row["category"] == "CPU"
    assert row["pn"] == ""                       # 不虚构料号
    assert row["unmatched"] is True
    assert row["request_spec"] == "KH50000"      # 需求原样交给下游选型
    assert row["unmatched_reason"] == "交由 AI 语义选型（引擎仅检索候选、不预判）"
    # AI=配置器：缺的必须反问类目补齐为占位骨架（CPU 已登记 + Memory/HDD-SSD/Raid/NIC/GPU）
    cats = {str(p.get("category")) for p in ctx["kp_parts"]}
    assert {"CPU", "Memory", "HDD/SSD", "Raid card", "NIC", "GPU"} <= cats
    assert ctx["kp_summary"]["unmatched_count"] == 6
    assert not any(a.get("code") == "kp_ai_grounded" for a in (ctx.get("assumptions") or []))


def test_phase_kp_reason_lands_matched_parts(monkeypatch):
    """登记表已有 kp_rows 时：占位行先落地，真实 SKU 由下游 AI 选型（引擎不做二次预判）。"""
    import asyncio
    from app.services import skill_phases

    def boom_select_parts(**kw):
        raise AssertionError("kp_rows 已存在时不应调 select_parts")

    monkeypatch.setattr("app.services.part_selector.select_parts", boom_select_parts)
    ctx = {"force_complete": True,
           "ext": {"kp_rows": [{"part_category": "HDD/SSD", "description": "1.92T SSD", "qty": 4}]},
           "baselines": [{"server_model_id": 1, "id": 1, "series": "Orion", "server_type_name": "通用计算服务器"}]}
    asyncio.run(skill_phases.phase_kp_reason(ctx, {}, None))
    row = ctx["kp_parts"][0]
    assert row["category"] == "HDD/SSD"
    assert row["pn"] == ""                       # 占位：不伪造料号
    assert row["unmatched"] is True
    assert row["request_spec"] == "1.92T SSD"
    cats = {str(p.get("category")) for p in ctx["kp_parts"]}
    assert {"CPU", "Memory", "HDD/SSD", "Raid card", "NIC", "GPU"} <= cats
    assert ctx["kp_summary"]["unmatched_count"] == 6


def test_build_plan_keeps_unmatched_out_of_kp_rows(monkeypatch):
    """方案配置表 KP 部分=纯库内料（2026-09-06 用户定调）：未匹配占位行不落表——
    客户原话/空描述混进配件表=黑盒污染；缺配信息由 plan.unmatched 载荷承载
    （硬门征询卡与汇报旁白消费）。"""
    from app.services import plan_builder as cs

    class FakeBaseConfigRepository:
        def __init__(self):
            pass

        def get_with_parts(self, _id):
            return {"parts": []}

    monkeypatch.setattr(cs, "BaseConfigRepository", FakeBaseConfigRepository)
    monkeypatch.setattr(
        "app.services.plan_rule_apply.apply_plan_selection_rules",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(cs, "_sync_plan_backplane", lambda *args, **kwargs: None)

    plan = cs.build_plan(
        {"id": None, "total_price": 0},
        [{
            "category": "CPU",
            "request_spec": "KH50000",
            "qty": 2,
            "unmatched": True,
            "unmatched_reason": "交由 AI 语义选型（引擎仅检索候选、不预判）",
        }],
    )
    kp_rows = [r for r in plan["cfg"]["bom_excel_rows"] if r.get("category") == "Key Parts"]
    assert kp_rows == []
    assert plan["unmatched"] == [{
        "category": "CPU",
        "reason": "交由 AI 语义选型（引擎仅检索候选、不预判）",
    }]
