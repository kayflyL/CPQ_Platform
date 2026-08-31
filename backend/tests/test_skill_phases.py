# -*- coding: utf-8 -*-
"""引擎（两器官架构）纯逻辑回归：信号门槛 / 无发明选件 / 场景守卫 / 缺口数据协议。"""
from app.services import part_selector as ps
from app.services.skill_phases import (
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
    ext = {"mem_signal": {"total_gb": 128}, "gpu_groups": [{"qty": 4}], "requirement_text": "随便"}
    args = kp_args_from_ext(ext)
    assert set(args) == {"mem_signal", "gpu_groups"}
    assert kp_args_from_ext({}) == {}


def test_parse_kp_mode_exact_match_only():
    assert parse_kp_mode("只要整机底座（L6）") == "l6_only"
    assert parse_kp_mode("需要配配件") == "need_parts"
    assert parse_kp_mode("不要配件") == ""  # 非业务选项值不猜（防关键词清单膨胀）
    assert parse_kp_mode("") == ""






def test_gap_protocol_is_data_only():
    """引擎缺口=纯数据（slot/reason_code/options），不含任何话术句子。"""
    gap = scene_gap({})
    assert gap["reason_code"] == "scene_missing"
    assert gap["options"] and all(isinstance(o, dict) and o.get("value") for o in gap["options"])
    kgap = kp_mode_gap()
    assert kgap["reason_code"] == "kp_mode_undecided"
    assert set(kgap["options"]) == {"需要配配件", "只要整机底座（L6）"}


def test_kp_gate_requires_signals_or_decision():
    assert kp_gate_gap({"ext": {}}) is not None  # 零信号+未决策 → 缺口
    assert kp_gate_gap({"ext": {"kp_mode": "只要整机底座（L6）"}}) is None
    assert kp_gate_gap({"kp_parts": [{"pn": "x"}]}) is None
    assert kp_gate_gap({"ext": {"mem_signal": {"total_gb": 64}}}) is None


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

def test_freeze_guard_keeps_model_named_in_prior_turn():
    """冻结守卫按需求文本剥臆造机型：多轮证据基准（含早前轮次原话）里点名的机型不能剥。

    回放：用户上轮点选 ESA24V3-P，本轮只说"256G内存"——只用本句会把已确认机型
    当臆造剥掉，机型问题无限重弹。
    """
    from app.services.capabilities import _freeze_requirement
    ext = {"server_model": "ESA24V3-P", "model": "ESA24V3-P", "baseline_model": "ESA24V3-P"}
    ctx: dict = {}
    # 本句不含机型名 + 无历史 → 剥（守卫对纯臆造仍生效）
    stripped = dict(ext)
    _freeze_requirement(ctx, stripped, "256G内存")
    assert not stripped.get("server_model")
    # 累计证据（近期用户原话并入后）含机型名 → 保留
    kept = dict(ext)
    _freeze_requirement(ctx, kept, "我想要一台服务器\nESA24V3-P\n256G内存，2块2TB SSD硬盘")
    assert kept.get("server_model") == "ESA24V3-P"




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
    from app.services.slot_extractor import apply_structured_slots
    ext = {}
    apply_structured_slots(ext, {"gpu": [{"model": "智铠100", "qty": 4}]}, "AI训练")
    apply_structured_slots(ext, {"cpu": {"model": "EPYC 9745", "qty": 2}}, "AI训练")
    apply_structured_slots(ext, {"memory": {"per_stick_gb": 32, "qty": 24}}, "AI训练")
    apply_structured_slots(ext, {"drives": [{"capacity_gb": 2048, "qty": 2, "media": "SSD"}]}, "AI训练")
    apply_structured_slots(ext, {"raid": [{"raid_levels": ["10"]}]}, "AI训练")
    assert isinstance(ext["gpu_groups"], list) and ext["gpu_groups"][0]["qty"] == 4
    assert "智铠" in str(ext["gpu_groups"][0].get("model") or ext["gpu_groups"][0].get("tokens"))
    assert ext["cpu_signal"]["qty"] == 2 and "EPYC" in str(ext["cpu_signal"].get("model"))
    assert ext["mem_signal"]["qty"] == 24 and ext["mem_signal"]["per_stick_gb"] == 32
    dg = ext["drive_groups"]
    assert dg[0]["qty"] == 2 and dg[0].get("term") == "2048G" and dg[0].get("kind") == "SSD"
    assert ext["raid_groups"][0].get("raid_levels") == ["10"]
    # 字符串形态的信号值不解析（语义归 LLM）：原样丢弃，不产生半结构
    ext2 = {"gpu_groups": []}
    apply_structured_slots(ext2, {"gpu": "4张智铠100", "memory": "256G"}, "AI训练")
    assert ext2["gpu_groups"] == [] and "mem_signal" not in ext2


def test_decimal_capacity_parsing():
    from app.services.slot_extractor import _parse_gb
    assert _parse_gb("1.92T") == 1966  # 不是 92T=94208
    assert _parse_gb("3.84TB") == 3932
    assert _parse_gb("2TB") == 2048
    assert _parse_gb("256G") == 256








def test_scenario_gap_options_carry_signal_slots():
    """场景推荐缺口（逐组问）：一次只出第一个未填组，选项各落自己的信号槽
    并带数量元数据（qty/qty_max/unit_gb），跳过逃生项登记 scenario_skips。"""
    from app.services.part_selector import scenario_parts_gap_data

    class FakeRepo:
        def close(self):
            pass

        def get_categories(self):
            return [{"category": c, "count": 1} for c in
                    ("CPU", "Memory", "GPU", "HDD/SSD", "Raid card")]

        def get_by_category_with_specs(self, cat):
            data = {
                "GPU": [{"model": "智铠100", "price": 20000.0, "applicable": None,
                         "specs": {"Capacity": "32G"}}],
                "CPU": [{"model": "EPYC 9124", "price": 9000.0, "applicable": None,
                         "specs": {"Cores": "16"}}],
                "Memory": [{"model": "DDR5-5600-64G", "price": 3000.0, "applicable": None,
                            "specs": {"Capacity": "64G", "Type": "DDR5"}}],
                "HDD/SSD": [{"model": "NVMe 1.92T", "price": 5200.0, "applicable": None,
                             "specs": {"Capacity": "1.92T", "Media": "SSD"}}],
                "Raid card": [{"model": "RAID-9460", "price": 4000.0, "applicable": None,
                               "specs": {}}],
            }
            return data.get(cat, [])

    from app.services import part_selector as ps
    from app.services.slot_extractor import apply_structured_slots
    orig = ps.KPRepository
    ps.KPRepository = lambda: FakeRepo()
    try:
        if not ps._scenario_categories("AI / 加速计算服务器"):
            import pytest
            pytest.skip("本地 system_config 无 AI 场景包（依赖种子数据）")
        baseline = {"series": "Orion", "gpu_slots": 10, "max_dimm": 24, "max_cpu": 2}
        # 逐组推进：每轮只应有一个信号槽 + 跳过/终止逃生项；点击落槽后下一组接上
        seen: list[str] = []
        ext: dict = {}
        for _ in range(8):
            code, opts = scenario_parts_gap_data(
                "AI / 加速计算服务器", baseline=baseline, ext=dict(ext),
                include_price=True, only_unfilled=True)
            sig_slots = {o["slot"] for o in opts} - {"kp_scenario_skip", "kp_scenario_done"}
            if not sig_slots:
                break  # 全组填完 → 空缺口（code=""），逐组问自然终止
            assert code == "scenario_incomplete"
            assert len(sig_slots) == 1, f"逐组问一次只出第一个未填组：{sig_slots}"
            assert any(o["slot"] == "kp_scenario_skip" for o in opts)
            assert any(o["slot"] == "kp_scenario_done" for o in opts)
            slot = sig_slots.pop()
            assert slot not in seen
            seen.append(slot)
            opt = next(o for o in opts if o["slot"] == slot)
            assert opt.get("value") and opt.get("group")
            assert isinstance(opt.get("signal"), dict) and opt["signal"]
            if slot in ("gpu_groups", "mem_signal", "drive_groups"):
                assert 1 <= opt["qty"] <= opt["qty_max"] and opt["unit_gb"] >= 1
            probe_keys_before = set(ext.keys())
            apply_structured_slots(ext, opt["signal"], "场景推荐")
            assert ext.get(slot), f"signal 载荷未落到 {slot}"
            assert set(ext.keys()) >= probe_keys_before  # 就地合并不清已填组
        assert {"gpu_groups", "cpu_signal", "mem_signal", "drive_groups"} <= set(seen)
        # 跳过逃生项：signal 登记 scenario_skips，后续同组不再被问
        _, opts = scenario_parts_gap_data(
            "AI / 加速计算服务器", baseline=baseline, ext={}, include_price=True)
        skip = next(o for o in opts if o["slot"] == "kp_scenario_skip")
        probe = {}
        apply_structured_slots(probe, skip["signal"], "")
        assert probe["scenario_skips"] == skip["signal"]["scenario_skips"]
        _, opts2 = scenario_parts_gap_data(
            "AI / 加速计算服务器", baseline=baseline, ext=dict(probe), include_price=True)
        assert not any(o["slot"] == "cpu_signal" for o in opts2), "被跳过的组不应再被问"
    finally:
        ps.KPRepository = orig


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
    drives = {"drives": [{"capacity_gb": 2048, "qty": 2, "media": "SSD"}]}
    assert _signal_with_qty(drives, 4, meta)["drives"][0]["qty"] == 4
    assert _signal_with_qty(drives, 99, meta)["drives"][0]["qty"] == 16
    cpu = {"cpu": {"model": "EPYC 9745", "qty": 2}}
    assert _signal_with_qty(cpu, 1, meta)["cpu"]["qty"] == 1
    assert _signal_with_qty(cpu, 8, meta)["cpu"]["qty"] == 2


# ── 2026-08-31 回归：阶段3 配件 AI 接地（未命中/规格偏差 → 库内候选受约束选型）────────────────

def test_kp_gap_rows_groups_unmatched_and_spec_mismatch():
    from app.services.skill_phases import _kp_gap_rows
    parts = [
        {"category": "CPU", "unmatched": True, "spec_mismatch": False, "qty": 2, "unmatched_reason": "库无", "request_spec": "KH50000"},
        {"category": "HDD/SSD", "unmatched": False, "spec_mismatch": True, "qty": 4, "request_spec": "1.92T SATA"},
        {"category": "HDD/SSD", "unmatched": False, "spec_mismatch": False, "qty": 1},
    ]
    gaps = _kp_gap_rows(parts)
    assert set(gaps) == {"CPU", "HDD/SSD"}
    assert len(gaps["CPU"]) == 1 and len(gaps["HDD/SSD"]) == 1
    assert gaps["CPU"][0] is parts[0]  # 保留原 dict 引用，便于替换


def test_kp_apply_ground_replaces_gap_with_lib_candidate():
    from app.services.skill_phases import _kp_gap_rows, _apply_kp_ground
    parts = [{"category": "HDD/SSD", "unmatched": True, "qty": 4, "request_spec": "1.92T SATA", "unmatched_reason": "库无"}]
    gaps = _kp_gap_rows(parts)
    cands = {"HDD/SSD": [{"id": 4, "model": "SATA SSD 1.92T", "price": 1200.0, "currency": "RMB", "specs": {}}]}
    n = _apply_kp_ground(parts, gaps, cands, [{"category": "HDD/SSD", "selected_id": "4", "qty": 4, "reason": "库内最接近"}])
    assert n == 1
    row = parts[0]
    assert row["pn"] == "SATA SSD 1.92T" and not row["unmatched"]
    assert float(row["unit_price"]) == 1200.0 and row["qty"] == 4
    assert "库内最接近" in row["replacement_note"]


def test_kp_apply_ground_keeps_gap_on_invalid_or_empty_id():
    from app.services.skill_phases import _kp_gap_rows, _apply_kp_ground
    parts = [{"category": "CPU", "unmatched": True, "qty": 2, "request_spec": "KH50000", "unmatched_reason": "库无"}]
    gaps = _kp_gap_rows(parts)
    cands = {"CPU": [{"id": 128, "model": "KH50000 96C", "price": 9000.0}]}
    assert _apply_kp_ground(parts, gaps, cands, [{"category": "CPU", "selected_id": "999", "qty": 2, "reason": "x"}]) == 0
    assert parts[0]["unmatched"]
    assert _apply_kp_ground(parts, gaps, cands, [{"category": "CPU", "selected_id": "", "qty": 2, "reason": "x"}]) == 0
    assert parts[0]["unmatched"]


def test_kp_llm_pick_kp_respects_chat_json_contract(monkeypatch):
    import asyncio
    from app.services import skill_phases
    captured = {}

    async def fake_chat(messages, **kw):
        captured["sys"] = messages[0]["content"]
        captured["user"] = messages[1]["content"]
        return {"selections": [{"category": "HDD/SSD", "selected_id": "4", "qty": 4, "reason": "最接近"}]}

    monkeypatch.setattr("app.services.llm_client.chat_json", fake_chat)
    ctx = {"requirement_text": "配1块1.92T SATA硬盘", "ext": {"drive_groups": [{"qty": 1}]}}
    baseline = {"server_type_name": "存储服务器", "series": "Orion", "form": "2U", "max_dimm": 16, "gpu_slots": 0}
    gap_rows = {"HDD/SSD": [{"category": "HDD/SSD", "unmatched": True, "qty": 1, "request_spec": "1.92T"}]}
    cands = {"HDD/SSD": [{"id": 4, "model": "SATA SSD 1.92T",
                          "specs": {"Capacity": "1.92 TB", "Media": "SSD", "Type": "SATA"},
                          "price": 1200.0}]}
    out = asyncio.run(skill_phases._llm_pick_kp(ctx, baseline, gap_rows, cands))
    assert out[0]["selected_id"] == "4"
    assert "候选" in captured["user"]
    # 可读能力描述进入候选，供 AI 语义匹配（非词表穷举）
    assert '"desc"' in captured["user"]
    assert "Capacity:1.92 TB" in captured["user"]


def test_kp_ai_ground_upgrades_gap_and_reports_count(monkeypatch):
    import asyncio
    from app.services import skill_phases

    async def fake_llm(ctx, baseline, gap_rows, cands):
        return [{"category": "CPU", "selected_id": "128", "qty": 2, "reason": "库内最接近"}]

    monkeypatch.setattr(skill_phases, "_kp_candidates_for",
                        lambda gap_rows, series: {"CPU": [{"id": 128, "model": "KH50000 96C", "price": 9000.0, "currency": "RMB"}]})
    monkeypatch.setattr(skill_phases, "_llm_pick_kp", fake_llm)
    parts = [{"category": "CPU", "unmatched": True, "qty": 2, "request_spec": "KH50000", "unmatched_reason": "库无"}]
    n = asyncio.run(skill_phases._kp_ai_ground({}, {"series": "Orion"}, parts, series="Orion"))
    assert n == 1
    assert parts[0]["pn"] == "KH50000 96C" and not parts[0]["unmatched"]
    assert "replacement_note" in parts[0]


def test_phase_kp_reason_grounds_gap_in_force_complete(monkeypatch):
    import asyncio
    from app.services import skill_phases
    from app.services import part_selector

    def fake_select_parts(**kw):
        return [{"category": "CPU", "unmatched": True, "qty": 2, "request_spec": "KH50000",
                 "unmatched_reason": "库无", "unit_price": 0.0, "spec_mismatch": False}]

    async def fake_llm(ctx, baseline, gap_rows, cands):
        return [{"category": "CPU", "selected_id": "128", "qty": 2, "reason": "库内最接近"}]

    monkeypatch.setattr(part_selector, "select_parts", fake_select_parts)
    monkeypatch.setattr(skill_phases, "_kp_candidates_for",
                        lambda gap_rows, series: {"CPU": [{"id": 128, "model": "KH50000 96C", "price": 9000.0, "currency": "RMB"}]})
    monkeypatch.setattr(skill_phases, "_llm_pick_kp", fake_llm)
    ctx = {"force_complete": True,
           "ext": {"cpu_signal": {"model": "KH50000", "qty": 2}},
           "baselines": [{"server_model_id": 1, "id": 1, "series": "Orion", "server_type_name": "通用计算服务器"}]}
    asyncio.run(skill_phases.phase_kp_reason(ctx, {}, None))
    row = ctx["kp_parts"][0]
    assert not row["unmatched"] and row["pn"] == "KH50000 96C"
    assert ctx["kp_summary"]["unmatched_count"] == 0
    assert any(a.get("code") == "kp_ai_grounded" for a in ctx["assumptions"])


def test_phase_kp_reason_grounds_gap_in_dialogue_path(monkeypatch):
    """对话路径（force_complete 缺省=False）也走 AI 接地：语义判断交回 AI 角色，不再静默留缺口。"""
    import asyncio
    from app.services import skill_phases
    from app.services import part_selector

    def fake_select_parts(**kw):
        return [{"category": "CPU", "unmatched": True, "qty": 2, "request_spec": "KH50000",
                 "unmatched_reason": "库无", "unit_price": 0.0, "spec_mismatch": False}]

    async def fake_llm(ctx, baseline, gap_rows, cands):
        return [{"category": "CPU", "selected_id": "128", "qty": 2, "reason": "库内最接近"}]

    monkeypatch.setattr(part_selector, "select_parts", fake_select_parts)
    monkeypatch.setattr(skill_phases, "_kp_candidates_for",
                        lambda gap_rows, series: {"CPU": [{"id": 128, "model": "KH50000 96C", "price": 3500.0, "currency": "RMB"}]})
    monkeypatch.setattr(skill_phases, "_llm_pick_kp", fake_llm)
    ctx = {"ext": {"cpu_signal": {"model": "KH50000", "qty": 2}},
           "baselines": [{"server_model_id": 1, "id": 1, "series": "Orion", "server_type_name": "通用计算服务器"}]}
    asyncio.run(skill_phases.phase_kp_reason(ctx, {}, None))
    row = ctx["kp_parts"][0]
    assert not row["unmatched"] and row["pn"] == "KH50000 96C"
    assert ctx["kp_summary"]["unmatched_count"] == 0
    assert any(a.get("code") == "kp_ai_grounded" for a in ctx["assumptions"])


def test_golden_dialog_path_grounds_cpu_and_raid(monkeypatch):
    """原始需求（兆芯50000 96C + Raid 卡 1G缓存）走真实对话路径：
    CPU/RAID 不再静默丢弃，由 AI 从库内候选接地；无法命中则如实报缺口。"""
    import asyncio
    from app.services import skill_phases
    from app.services import part_selector

    def fake_select_parts(**kw):
        return [
            {"category": "CPU", "unmatched": True, "qty": 2, "request_spec": "兆芯50000 96C",
             "unmatched_reason": "库无", "unit_price": 0.0, "spec_mismatch": False},
            {"category": "Raid card", "unmatched": True, "qty": 1, "request_spec": "Raid卡 1G缓存/RAID0-6/JBOD",
             "unmatched_reason": "库无", "unit_price": 0.0, "spec_mismatch": False},
        ]

    async def fake_llm(ctx, baseline, gap_rows, cands):
        return [
            {"category": "CPU", "selected_id": "128", "qty": 2, "reason": "库内最接近"},
            {"category": "Raid card", "selected_id": "192", "qty": 1, "reason": "库内最接近"},
        ]

    monkeypatch.setattr(part_selector, "select_parts", fake_select_parts)
    monkeypatch.setattr(skill_phases, "_kp_candidates_for",
                        lambda gap_rows, series: {
                            "CPU": [{"id": 128, "model": "KH50000 96C", "price": 3500.0, "currency": "RMB"}],
                            "Raid card": [{"id": 192, "model": "LSI 9361-8i 1G cache",
                                           "price": 2200.0, "currency": "RMB",
                                           "specs": {"Cache": "1 GB", "Ports": "8", "电容": "无"}}],
                        })
    monkeypatch.setattr(skill_phases, "_llm_pick_kp", fake_llm)
    ctx = {"ext": {"cpu_signal": {"model": "KH50000", "qty": 2},
                   "raid_groups": [{"qty": 1, "level": "0/1/5/6/JBOD"}]},
           "baselines": [{"server_model_id": 1, "id": 1, "series": "Orion", "server_type_name": "通用计算服务器"}]}
    asyncio.run(skill_phases.phase_kp_reason(ctx, {}, None))
    by_cat = {p["category"]: p for p in ctx["kp_parts"]}
    cpu = by_cat["CPU"]
    raid = by_cat["Raid card"]
    assert cpu["pn"] == "KH50000 96C" and cpu["qty"] == 2 and not cpu["unmatched"]
    assert raid["pn"] == "LSI 9361-8i 1G cache" and raid["qty"] == 1 and not raid["unmatched"]
    assert ctx["kp_summary"]["unmatched_count"] == 0
    assert any(a.get("code") == "kp_ai_grounded" for a in ctx["assumptions"])
