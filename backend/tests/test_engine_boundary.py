# -*- coding: utf-8 -*-
"""引擎边界守卫（位置即法律版执法载体，声明=ai_office/engine_boundary.py）。

四条法：
  L1 严格区现行法：STRICT 模块不得 import app.api/**、不得 import app.services/**
     （宿主）——两种模式都红；冻结内核（app.core/models/repository）允许。
  L2 清单不许烂：FUSED 模块实际宿主边清零 → 提醒升严格区（两种模式都红）；
     声明模块文件必须存在于引擎树。
  L3 融合区工作清单：report 模式（默认）打印各融合模块的宿主边=解耦工作清单；
     ENGINE_BOUNDARY_MODE=enforce 后融合区带宿主边即红（终态目标）。
  L4 基线快照锁（v4 第 1 步）：融合区宿主边只许变少不许变多——新增边=红。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'ai-office'))

from pathlib import Path

import pytest

from ai_office import engine_boundary as eb

ENGINE_DIR = Path(__file__).resolve().parent.parent.parent / "ai-office" / "ai_office"


def _source(module: str) -> str:
    return (ENGINE_DIR / f"{module}.py").read_text(encoding="utf-8")


# ── L0 声明结构 ────────────────────────────────────────────────────────────


def test_declared_modules_exist():
    for m in {**eb.STRICT_MODULES, **eb.FUSED_MODULES}:
        assert (ENGINE_DIR / f"{m}.py").exists(), f"声明的引擎模块不在引擎树：{m}"


def test_layers_legal():
    legal = {"loop", "state", "harness", "server", "host"}
    for m, layer in eb.STRICT_MODULES.items():
        assert layer in legal, f"{m} 层词汇非法：{layer}"
    for m, (layer, _note) in eb.FUSED_MODULES.items():
        assert layer in legal, f"{m} 层词汇非法：{layer}"


def test_strict_and_fused_disjoint():
    overlap = set(eb.STRICT_MODULES) & set(eb.FUSED_MODULES)
    assert not overlap, f"模块同时出现在严格区与融合区：{overlap}"


def test_engine_tree_imports_nothing_host_outside_baseline():
    """整树终检：引擎树里任何模块对宿主的 import 都必须被 L4 基线或声明收录。
    混进引擎树的新文件若私自 import 宿主而没进融合区声明 → 在这里红（盲区关闭）。"""
    rogue = {}
    for f in ENGINE_DIR.glob("*.py"):
        mod = f.stem
        if mod in ("__init__", "engine_boundary"):
            continue
        if mod in eb.STRICT_MODULES or mod in eb.FUSED_MODULES:
            continue
        e = eb.fused_edges(mod, _source(mod))
        if e["api"] or e["host"]:
            rogue[mod] = e
    assert not rogue, (
        "引擎树里有未声明模块带着宿主边（要么它不是引擎，请移去宿主树；"
        "要么它是引擎，请进 FUSED_MODULES + 基线）：\n"
        + "\n".join(f"  {m}: {v}" for m, v in rogue.items()))


# ── L1 严格区现行法（两种模式都红）──────────────────────────────────────


def test_strict_import_direction():
    """严格区：无 api 反向依赖、无宿主摸取（冻结内核允许）。今天红=有人刚把宿主 import 进了内核。"""
    bad = {}
    for m in eb.STRICT_MODULES:
        v = eb.strict_violations(m, _source(m))
        if v["api"] or v["host"]:
            bad[m] = v
    assert not bad, (
        "严格区引擎模块 import 方向违规（引擎不得依赖 api 层/宿主业务）:\n"
        + "\n".join(f"  {m}: {v}" for m, v in bad.items()))


def test_kernel_imports_are_legal_and_recorded():
    """冻结内核合法：严格区模块 import app.core/models/repository 不算违规，
    且内核依赖面可枚举（进程拆分时它就是存储接口清单，只许收缩）。"""
    src = ("from app.models.base import SessionLocal\n"
           "from ai_office.turn_breaker import y\n")
    v = eb.strict_violations("fake", src)
    assert v == {"api": [], "host": []}, "内核 import 不得判违规"
    k = eb.kernel_imports("fake", src)
    assert k == {"app.models": ["app.models.base"]}


# ── 守卫逻辑本身（合成源码自测，不依赖真实文件状态）────────────────────────


def test_strict_violations_detects_host_and_api():
    src = ("from app.services.delivery_core import x\n"
           "from ai_office.turn_breaker import y\n"
           "import app.api.assistant\n")
    v = eb.strict_violations("fake", src)
    assert v["api"] == ["app.api.assistant"]
    assert v["host"] == ["app.services.delivery_core"]  # ai_office.* 引擎互引=合法


def test_fused_edges_count_all_services_as_host():
    src = ("from app.services.part_selector import p\n"
           "from ai_office.human_query import h\n")
    e = eb.fused_edges("fake", src)
    assert e["host"] == ["app.services.part_selector"]  # 引擎已迁出 services 树：任何 services import=宿主边


# ── L2 清单不许烂 ─────────────────────────────────────────────────────────


def test_fused_modules_ready_for_promotion_must_be_promoted():
    """升区棘轮：融合区模块的宿主/api 边已清零、且引擎内 import 全落严格区
    → 它已够格当严格区模块，清单必须跟着升（防烂）。"""
    not_ready, ready = [], []
    for m in eb.FUSED_MODULES:
        e = eb.fused_edges(m, _source(m))
        if e["host"] or e["api"]:
            not_ready.append(m)
            continue
        imports = eb.all_imports(_source(m))
        engine_imports = {i.rsplit(".", 1)[-1] for i in imports
                          if i.startswith("ai_office.")}
        (ready if engine_imports <= set(eb.STRICT_MODULES) else not_ready).append(m)
    assert not ready, f"融合区这些模块已够格，请升入严格区：{ready}"


# ── L4 基线快照锁（v4 第 1 步）─────────────────────────────────────────────


def test_baseline_covers_edge_holding_fused_modules():
    """基线不许烂：带边的融合模块必须都进基线快照；基线里不许有已升区的模块。"""
    with_edge = {m for m in eb.FUSED_MODULES
                 if (lambda e: e["host"] or e["api"])(eb.fused_edges(m, _source(m)))}
    missing = sorted(with_edge - set(eb.FUSED_EDGE_BASELINE))
    stale = sorted(set(eb.FUSED_EDGE_BASELINE) - set(eb.FUSED_MODULES))
    assert not missing, (
        "这些融合模块带宿主/api 边但没进基线快照（生成方式见 engine_boundary.py "
        "FUSED_EDGE_BASELINE 注释）：" + repr(missing))
    assert not stale, "基线里有已不在融合区的模块（升区时忘了删基线）：" + repr(stale)


def test_fused_edges_within_baseline():
    """快照锁：融合区不许长出基线以外的新宿主/api 边（等待拉动期清单只许变小）。"""
    grown = {}
    for m in eb.FUSED_MODULES:
        new = eb.baseline_new_edges(m, _source(m))
        if new["api"] or new["host"]:
            grown[m] = new
    assert not grown, (
        "融合区新增宿主/api 依赖（解耦期清单只许变小不许变大）：\n"
        + "\n".join(f"  {m}: {v}" for m, v in grown.items()))


# ── L3 融合区工作清单 ──────────────────────────────────────────────────────


def test_fused_worklist_report_or_enforce():
    mode = eb.boundary_mode()
    assert mode in ("report", "enforce"), f"ENGINE_BOUNDARY_MODE 非法：{mode}"
    worklist = {}
    for m in eb.FUSED_MODULES:
        e = eb.fused_edges(m, _source(m))
        if e["host"] or e["api"]:
            worklist[m] = e
    if mode == "enforce":
        assert not worklist, (
            "enforce 模式：融合区仍带宿主/api 边（解耦完成前不要开 enforce）：\n"
            + "\n".join(f"  {m}: {v}" for m, v in worklist.items()))
    # report 模式：打印工作清单（pytest -s 可见），测试通过
    print(f"\n═══ 融合区解耦工作清单（{len(worklist)} 模块带边，report 模式）═══")
    for m, v in sorted(worklist.items(), key=lambda kv: -len(kv[1]["host"])):
        layer, note = eb.FUSED_MODULES[m]
        print(f"  {m} [{layer}] 宿主边×{len(v['host'])} api边×{len(v['api'])} — {note}")
