# -*- coding: utf-8 -*-
"""引擎边界守卫（位置即法律版执法载体，声明=ai_office/engine_boundary.py）。

两条法：
  L1 严格区现行法：引擎模块不得 import app.api/**、不得 import app.services/**
     （宿主）——违者红；冻结内核（app.core/models/repository）允许。
  L2 整树终检：引擎树里任何模块带宿主边 = 红（新文件逃不过位置法，无声明盲区）。

引擎取宿主能力的唯一合法通道 = host_ports 端口。曾经的融合区申报通道已于
2026-11-01 退役（45 条边清零后脚手架拆除）——没有自助申报，红=架构决策。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'ai-office'))

from pathlib import Path

from ai_office import engine_boundary as eb

ENGINE_DIR = Path(__file__).resolve().parent.parent.parent / "ai-office" / "ai_office"


def _source(module: str) -> str:
    return (ENGINE_DIR / f"{module}.py").read_text(encoding="utf-8")


# ── 清单结构 ──────────────────────────────────────────────────────────────


def test_declared_modules_exist():
    for m in eb.STRICT_MODULES:
        assert (ENGINE_DIR / f"{m}.py").exists(), f"声明的引擎模块不在引擎树：{m}"


def test_layers_legal():
    legal = {"loop", "state", "harness", "server", "host"}
    for m, layer in eb.STRICT_MODULES.items():
        assert layer in legal, f"{m} 层词汇非法：{layer}"


# ── L2 整树终检（位置法，无声明盲区）──────────────────────────────────────


def test_engine_tree_rogue_check():
    """整树终检：引擎树里任何模块对宿主的 import 都违规（含未进清单的新文件）。
    合法通道=host_ports 端口、宿主侧 engine_wiring 接线；融合区申报通道已退役。"""
    rogue = {}
    for f in ENGINE_DIR.glob("*.py"):
        mod = f.stem
        if mod in ("__init__", "engine_boundary"):
            continue
        e = eb.strict_violations(mod, _source(mod))
        if e["api"] or e["host"]:
            rogue[mod] = e
    assert not rogue, (
        "引擎树里有模块带着宿主边（要么它不是引擎，请移去宿主树；要么它是引擎，"
        "取宿主能力请走 host_ports 端口、宿主侧 engine_wiring 接线——融合区申报"
        "通道已退役，红=架构决策）：\n"
        + "\n".join(f"  {m}: {v}" for m, v in rogue.items()))


# ── L1 严格区现行法 ───────────────────────────────────────────────────────


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
    """冻结内核合法：引擎模块 import app.core/models/repository 不算违规，
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


def test_no_exception_hatch():
    """组合根白名单清除回归（2026-11-01）：strict_violations 没有豁免机制，
    任何模块（含曾经的白名单户）的宿主 import 一律违规。"""
    v = eb.strict_violations("transaction_engine",
                             "from app.services.delivery_app import APP\n")
    assert v["host"] == ["app.services.delivery_app"]
