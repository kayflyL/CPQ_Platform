# -*- coding: utf-8 -*-
"""引擎边界守卫（第 5 步"画边界"执法载体，声明=app/core/engine_boundary.py）。

四条法：
  L1 严格区现行法：STRICT 模块不得 import app.api.*、不得摸严格区之外的
     app.services 模块——两种模式都红（严格区没有宽容档）。
  L2 清单不许烂：FUSED 模块实际宿主边清零 → 提醒升严格区（两种模式都红，
     这是声明准确性问题不是边界问题）；声明模块文件必须存在。
  L3 融合区工作清单：report 模式（默认）打印各融合模块的宿主边=解耦工作清单，
     测试通过；ENGINE_BOUNDARY_MODE=enforce 后融合区带宿主边即红（终态目标）。
  L4 基线快照锁（v4 第 1 步）：融合区宿主边只许变少不许变多——新增边=红，
     防止等待拉动的窗口期里引擎悄悄长出新的宿主依赖。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

import pytest

from app.core import engine_boundary as eb

SERVICES = Path(__file__).resolve().parent.parent / "app" / "services"


def _source(module: str) -> str:
    return (SERVICES / f"{module}.py").read_text(encoding="utf-8")


# ── L0 声明结构 ────────────────────────────────────────────────────────────


def test_declared_modules_exist():
    for m in {**eb.STRICT_MODULES, **eb.FUSED_MODULES}:
        assert (SERVICES / f"{m}.py").exists(), f"声明的引擎模块不存在：{m}"


def test_layers_legal():
    legal = {"loop", "state", "harness", "server", "host"}
    for m, layer in eb.STRICT_MODULES.items():
        assert layer in legal, f"{m} 层词汇非法：{layer}"
    for m, (layer, _note) in eb.FUSED_MODULES.items():
        assert layer in legal, f"{m} 层词汇非法：{layer}"


def test_strict_and_fused_disjoint():
    overlap = set(eb.STRICT_MODULES) & set(eb.FUSED_MODULES)
    assert not overlap, f"模块同时出现在严格区与融合区：{overlap}"


# ── L1 严格区现行法（两种模式都红）──────────────────────────────────────


def test_strict_import_direction():
    """严格区：无 api 反向依赖、无宿主摸取。今天红=有人刚把宿主 import 进了内核。"""
    bad = {}
    for m in eb.STRICT_MODULES:
        v = eb.strict_violations(m, _source(m))
        if v["api"] or v["host"]:
            bad[m] = v
    assert not bad, (
        "严格区引擎模块 import 方向违规（引擎不得依赖 api 层/宿主业务）：\n"
        + "\n".join(f"  {m}: {v}" for m, v in bad.items()))


# ── 守卫逻辑本身（合成源码自测，不依赖真实文件状态）────────────────────────


def test_strict_violations_detects_host_and_api():
    src = ("from app.services.delivery_core import x\n"
           "from app.services.turn_breaker import y\n"
           "import app.api.assistant\n")
    v = eb.strict_violations("fake", src)
    assert v["api"] == ["app.api.assistant"]
    assert v["host"] == ["app.services.delivery_core"]  # turn_breaker 在严格区=合法


def test_fused_edges_excludes_engine_modules():
    src = ("from app.services.part_selector import p\n"
           "from app.services.human_query import h\n")
    e = eb.fused_edges("fake", src)
    assert e["host"] == ["app.services.part_selector"]  # human_query 已声明引擎=不算宿主边


# ── L2 清单不许烂 ─────────────────────────────────────────────────────────


def test_fused_modules_ready_for_promotion_must_be_promoted():
    """升区棘轮：融合区模块的引擎内 import 已全部落在严格区内（且无宿主/api 边）
    → 它已经够格当严格区模块，清单必须跟着升（防烂）。只清了宿主边但还 import
    其他融合区模块的（如 flow_validation）不算够格，等上游升区后链式升。"""
    not_ready, ready = [], []
    for m in eb.FUSED_MODULES:
        e = eb.fused_edges(m, _source(m))
        if e["host"] or e["api"]:
            not_ready.append(m)
            continue
        imports = eb._app_imports(_source(m))
        engine_imports = {i.rsplit(".", 1)[-1] for i in imports
                          if i.startswith("app.services.")}
        (ready if engine_imports <= set(eb.STRICT_MODULES) else not_ready).append(m)
    assert not ready, f"融合区这些模块已够格，请升入严格区：{ready}"


# ── L3 融合区工作清单 ─────────────────────────────────────────────────────


# ── L4 基线快照锁（v4 第 1 步）─────────────────────────────────────────────


def test_baseline_covers_edge_holding_fused_modules():
    """基线不许烂：带边的融合模块必须都进基线快照；基线里不许有已升区的模块。"""
    with_edge = {m for m in eb.FUSED_MODULES
                 if (lambda e: e["host"] or e["api"])(eb.fused_edges(m, _source(m)))}
    missing = sorted(with_edge - set(eb.FUSED_EDGE_BASELINE))
    stale = sorted(set(eb.FUSED_EDGE_BASELINE) - set(eb.FUSED_MODULES))
    assert not missing, (
        "这些融合模块带宿主/api 边但没进基线快照（生成方式见 engine_boundary.py "
        "FUSED_EDGE_BASELINE 注释，生成后随本测试锁定）：" + repr(missing))
    assert not stale, "基线里有已不在融合区的模块（升区时忘了删基线）：" + repr(stale)


def test_fused_edges_within_baseline():
    """快照锁：融合区不许长出基线以外的新宿主/api 边（等待拉动期清单只许变小）。
    解掉的边不受影响（子集）；整模块清零后走 L2 升区 + 删基线。"""
    grown = {}
    for m in eb.FUSED_MODULES:
        new = eb.baseline_new_edges(m, _source(m))
        if new["api"] or new["host"]:
            grown[m] = new
    assert not grown, (
        "融合区新增宿主/api 依赖（解耦期清单只许变小不许变大）：\n"
        + "\n".join(f"  {m}: {v}" for m, v in grown.items()))


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
