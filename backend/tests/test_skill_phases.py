# -*- coding: utf-8 -*-
"""引擎（两器官架构）纯逻辑回归：信号门槛 / 无发明选件 / 场景守卫 / 缺口数据协议。"""
from app.services import skill_signals
from unittest.mock import patch

from app.services import part_selector as ps
from app.services.skill_phases import model_signals_ready


def test_prepare_model_step_platform_suffices_when_type_unaligned():
    """通用服务器 + Polaris（缺形态）不再被当成场景缺口，直接查候选。"""
    from app.services.skill_phases import prepare_model_step

    class _Cat:
        def list_types(self):
            return [{"id": 1, "name": "通用计算服务器"},
                    {"id": 2, "name": "AI / 加速计算服务器"}]

    cand = {"server_model_id": 1, "id": 1, "name": "Polaris 2U 12盘",
            "server_type_name": "通用计算服务器", "series": "Polaris",
            "form": "2U", "total_price": 100.0}
    wl = {"types": ["通用计算服务器", "AI / 加速计算服务器", "存储服务器"],
          "series": ["Polaris", "Orion"], "forms": ["2U", "4U"]}
    with patch("app.repository.server_catalog_repo.ServerCatalogRepository", _Cat), \
         patch("app.services.catalog_options.catalog_whitelist", return_value=wl), \
         patch("app.services.model_candidates.select_models", return_value=[cand]):
        ctx = {"ext": {"server_type": "通用服务器", "platform_type": "Polaris"},
               "price_access": True}
        info = prepare_model_step(ctx)
    assert info.get("invalid_scene") is not True
    assert info.get("pool") == 1


def test_model_signal_gate_requires_type_or_series_form():
    assert not model_signals_ready({})
    assert not model_signals_ready({"usage": "跑数据库"})  # 原文/语义不是结构化信号
    assert model_signals_ready({"server_type_name": "通用计算服务器"})
    assert model_signals_ready({"series": "Orion", "form": "2U"})
    assert not model_signals_ready({"series": "Orion"})


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
    from app.services.skill_signals import _signal_with_qty
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
    ctx = {
           "ext": {"kp_rows": [{"part_category": "CPU", "description": "KH50000", "qty": 2}]},
           "baselines": [{"server_model_id": 1, "id": 1, "series": "Orion", "server_type_name": "通用计算服务器"}]}
    asyncio.run(skill_phases.phase_kp_reason(ctx, {}, None))
    row = ctx["kp_parts"][0]
    assert row["category"] == "CPU"
    assert row["pn"] == ""                       # 不虚构料号
    assert row["unmatched"] is True
    assert row["request_spec"] == "KH50000"      # 需求原样交给下游选型
    assert row["unmatched_reason"] == "待 AI 语义选型（引擎仅检索候选、不预判）"
    # AI=配置器：只认「客户已登记/AI 已声明」的行；目标层未登记类目（如这条需求没要 GPU）
    # 不作为占用行，交给 AI 看着目标表自己判断要不要配（引擎不再预判/替 AI 加行）。
    assert len(ctx["kp_parts"]) == 1
    assert ctx["kp_parts"][0]["category"] == "CPU"
    assert ctx["kp_summary"]["unmatched_count"] == 1
    # 未登记类目不得被自动注入成幽灵行
    cats = {str(p.get("category")) for p in ctx["kp_parts"]}
    assert cats == {"CPU"}
    assert not any(a.get("code") == "kp_ai_grounded" for a in (ctx.get("assumptions") or []))


def test_phase_kp_reason_lands_matched_parts(monkeypatch):
    """登记表已有 kp_rows 时：占位行先落地，真实 SKU 由下游 AI 选型（引擎不做二次预判）。"""
    import asyncio
    from app.services import skill_phases

    def boom_select_parts(**kw):
        raise AssertionError("kp_rows 已存在时不应调 select_parts")

    monkeypatch.setattr("app.services.part_selector.select_parts", boom_select_parts)
    ctx = {
           "ext": {"kp_rows": [{"part_category": "HDD/SSD", "description": "1.92T SSD", "qty": 4}]},
           "baselines": [{"server_model_id": 1, "id": 1, "series": "Orion", "server_type_name": "通用计算服务器"}]}
    asyncio.run(skill_phases.phase_kp_reason(ctx, {}, None))
    row = ctx["kp_parts"][0]
    assert row["category"] == "HDD/SSD"
    assert row["pn"] == ""                       # 占位：不伪造料号
    assert row["unmatched"] is True
    assert row["request_spec"] == "1.92T SSD"
    # 只认已登记/AI 声明行；未登记类目不注入
    assert len(ctx["kp_parts"]) == 1
    assert ctx["kp_parts"][0]["category"] == "HDD/SSD"
    assert ctx["kp_summary"]["unmatched_count"] == 1


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
            "unmatched_reason": "待 AI 语义选型（引擎仅检索候选、不预判）",
        }],
    )
    kp_rows = [r for r in plan["cfg"]["bom_excel_rows"] if r.get("category") == "Key Parts"]
    assert kp_rows == []
    assert plan["unmatched"] == [{
        "category": "CPU",
        "reason": "待 AI 语义选型（引擎仅检索候选、不预判）",
    }]


def test_part_query_offset_pagination():
    """检索分页：offset 跳过、truncated/total/next_offset，默认 offset=0 行为不变。"""
    from app.services.data_tools import part_query
    class _Repo:
        def get_categories(self):
            return [{"category": "CPU"}]
        def get_by_category_with_specs(self, cat):
            return [{"id": i, "model": f"CPU-{i}", "price": float(i),
                     "currency": "RMB", "specs": {"Cores": str(i * 8)}}
                    for i in range(1, 6)]
    q = part_query("CPU", limit=2, offset=0, _repo=_Repo())
    assert [r["name"] for r in q["rows"]] == ["CPU-1", "CPU-2"]
    assert q["truncated"] is True
    assert q["total"] == 5
    assert q["next_offset"] == 2
    q2 = part_query("CPU", limit=2, offset=4, _repo=_Repo())
    assert [r["name"] for r in q2["rows"]] == ["CPU-5"]
    assert q2["truncated"] is False
    assert q2["total"] == 5
    assert q2["next_offset"] is None
    q3 = part_query("CPU", _repo=_Repo())
    assert len(q3["rows"]) == 5
    assert q3["truncated"] is False

def test_lock_baseline_records_own_artifact_not_registration():
    """B1：机型自动锁定写 model_reason 自己的产物（baseline/_locked_baseline/model_selection），
    不回填登记表 ext.server_model；跨轮持久化走 mem.locked_baseline。"""
    from app.services.skill_phases import _lock_baseline
    ctx = {"ext": {}}
    baseline = {"server_model_id": 1, "id": 1, "name": "ZS220 V2",
                "server_type_name": "通用计算服务器", "series": "Polaris", "form": "2U"}
    _lock_baseline(ctx, baseline, "目录唯一命中")
    assert ctx.get("_locked_baseline") is baseline
    assert ctx["baselines"][0]["name"] == "ZS220 V2"
    assert ctx["model_selection"]["name"] == "ZS220 V2"
    assert str((ctx.get("ext") or {}).get("server_model") or "").strip() == ""

