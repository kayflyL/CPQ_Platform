# -*- coding: utf-8 -*-
"""flow_validation —— 流声明完备性校验器（发布闸）。

《AI办公室引擎化方案》第 1 步"立规矩"的执法面：契约事实的存在性由机制保证，
不押搭流者（人或 AI）的自觉——漏声明在保存时被人话报错拦下，而不是用户在画布
上发现空抽屉/空输出物。条款与《docs/引擎ABI-v0.md》节点契约分册一一对应。

模式（环境变量 FLOW_VALIDATION_MODE，默认 report）：
  report  = 只记日志不拦截（存量流补缺口期，方案规定的过渡周）
  enforce = error 级条款 400 拦截保存

severity 约定：
  error   = 声明自相矛盾/引用不存在（槽未注册、节点无标签、边指空）——机器可判死
  warning = 完备性缺口（干活节点没声明产物插头/白名单、流级规则为空）——
            存量流补齐后逐条升级为 error
"""
from __future__ import annotations

import os

# 干活节点（产出/改数据的节点）：必须有产物插头声明（W1/E3 条款的对象）
WORKER_TYPES = {"agent", "agent_fill", "model_reason", "kp_reason", "compose"}
# 其中真正靠大脑调工具干活的节点：必须有工具白名单（W2 条款的对象）；
# model_reason/kp_reason/compose 是确定性引擎节点，不走工具，不适用
TOOLING_TYPES = {"agent", "agent_fill"}

_PRODUCT_REGISTRY: set | None = None


def _product_slots() -> set:
    """产物槽注册表（skill_node_artifacts.builder_kinds）。惰性 import 防环。"""
    global _PRODUCT_REGISTRY
    if _PRODUCT_REGISTRY is None:
        try:
            from ai_office.skill_node_artifacts import builder_kinds
            _PRODUCT_REGISTRY = builder_kinds()
        except Exception:
            _PRODUCT_REGISTRY = set()
    return _PRODUCT_REGISTRY or set()


def mode() -> str:
    return str(os.environ.get("FLOW_VALIDATION_MODE") or "report").strip().lower()


def is_enforce() -> bool:
    return mode() == "enforce"


def runtime_of(flow_key: str) -> str:
    """流所属运行时：事务内核已注册的 flow_key → "transaction"，其余 → "skill"。
    两台运行时的节点产物契约不同（skill=产物槽分发，transaction=artifact_card），
    W1/E3 条款只对 skill 运行时有意义。"""
    if not str(flow_key or "").strip():
        return "skill"
    try:
        from ai_office.transaction_engine import resolve_app
        return "transaction" if resolve_app(str(flow_key)) is not None else "skill"
    except Exception:
        return "skill"


def _issue(code: str, severity: str, message: str, node: str = "") -> dict:
    return {"code": code, "severity": severity, "node": node, "message": message}


def validate_node(node_key: str, node_type: str, config: dict, runtime: str = "skill") -> list:
    """单节点条款（抽屉保存节点配置时的闸）。config = 即将入库的节点配置。"""
    issues: list = []
    cfg = config if isinstance(config, dict) else {}
    # E6 决策点声明完备性（任何节点都可声明决策点，不限干活节点）：闸按它发卡停轮，
    # 缺要素=闸不生效。放在 WORKER_TYPES 分支之前——input 节点声明决策点同样纳检。
    for d in (cfg.get("decisions") or []) if isinstance(cfg.get("decisions"), list) else []:
        if not isinstance(d, dict):
            issues.append(_issue("E6", "error", "decisions 声明项必须是对象", node_key))
            continue
        for f in ("slot", "match_category", "question"):
            if not str(d.get(f) or "").strip():
                issues.append(_issue("E6", "error",
                                     f"决策点声明缺 {f}（决策闸按它发卡停轮，缺了闸不生效）", node_key))
    if node_type not in WORKER_TYPES:
        return issues
    if runtime == "skill":
        from ai_office.skill_target_contract import target_artifacts
        arts = target_artifacts(cfg)
        if not arts:
            issues.append(_issue("W1", "warning",
                                 "干活节点未声明产物插头（目标层 target.artifacts）——"
                                 "运行时该节点没有输出物，画布点开为空", node_key))
        for a in arts:
            slot = str((a or {}).get("slot") or "").strip()
            if slot and slot not in _product_slots():
                issues.append(_issue("E3", "error",
                                     f"产物插头 slot「{slot}」不在产物槽注册表——分发不认，运行时产物为空",
                                     node_key))
    if node_type in TOOLING_TYPES:
        tools = cfg.get("enabled_tools")
        if not isinstance(tools, list) or not tools:
            issues.append(_issue("W2", "warning",
                                 "干活节点未声明工具白名单（enabled_tools）——"
                                 "运行时大脑在本步无工具可用", node_key))
    # W4（P2 产物契约域化）：input/output 节点未声明产物（target.artifacts）→ 画布点开为空。
    # 趋势域化实证：声明即有产出（requirement_text/data_report 现成 builder）。
    # 仅 skill 运行时；warning 级——需求分析 input/output 走引擎内建通道，补显式声明后可升 error。
    if runtime == "skill" and node_type in ("input", "output"):
        from ai_office.skill_target_contract import target_artifacts as _ta
        if not _ta(cfg):
            issues.append(_issue("W4", "warning",
                                 "输入/输出节点未声明产物（target.artifacts）——"
                                 "画布点开无产出物（参照趋势分析：input=requirement_text / output=data_report）",
                                 node_key))
    return issues


def validate_flow(graph: dict, node_configs: dict, manual_rules: str = "",
                  flow_key: str = "") -> list:
    """整流条款（画布保存/版本发布时的闸）。graph/node_configs = 即将入库的声明。
    flow_key 用于判定流所属运行时（事务内核已注册的流不走 W1/E3 产物插头条款）。"""
    issues: list = []
    runtime = runtime_of(flow_key)
    g = graph if isinstance(graph, dict) else {}
    nodes = [n for n in (g.get("nodes") or []) if isinstance(n, dict)]
    cfgs = node_configs if isinstance(node_configs, dict) else {}
    if not nodes:
        issues.append(_issue("E1", "error", "图为空：没有节点"))
        return issues
    types: dict = {}
    for nd in nodes:
        key = str(nd.get("id") or "")
        types[key] = str(nd.get("type") or "")
        if not str(nd.get("label") or "").strip():
            issues.append(_issue("E2", "error",
                                 "节点缺少画布标签（label）——步骤条/骨架以它为权威", key))
    type_values = set(types.values())
    if "input" not in type_values:
        issues.append(_issue("E1", "error", "流缺少 input 节点（用户输入/开工单没有入口）"))
    if "output" not in type_values:
        issues.append(_issue("E1", "error", "流缺少 output 节点（产物没有出口）"))
    ids = set(types)
    for e in (g.get("edges") or []):
        if not isinstance(e, dict):
            continue
        for side in ("source", "target"):
            ref = str(e.get(side) or "")
            if ref and ref not in ids:
                issues.append(_issue("E4", "error", f"边引用了不存在的节点（{side}={ref}）", ref))
    for nd in nodes:
        key = str(nd.get("id") or "")
        cfg = cfgs.get(key) if isinstance(cfgs.get(key), dict) else {}
        issues.extend(validate_node(key, types.get(key, ""), cfg, runtime))
    if not str(manual_rules or "").strip():
        issues.append(_issue("W3", "warning",
                             "流级左栏规则（manual_rules）为空——大脑行为纪律没有唯一出处"))
    return issues
