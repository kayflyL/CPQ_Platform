# -*- coding: utf-8 -*-
"""节点隔离回归（Step 2，2026-09-10 结构手术）。

kp_reason 的可变工作状态（picks / recommend / config / absent）原先堆在共享 `ext`，
而 `ext` 同时是上游「线索登记表」的存储 —— 任一节点写 ext 都可能踩到别人的键，
这就是「改一处坏一处、问题无法定位到单个节点」的根因。现在它们进节点私有分区
`node_state.kp_reason`，随 mem 跨轮持久。

本文件锁住三条性质（防回潮）：
  1) 分区各节点互不串扰，也不写共享 ext；
  2) 分区对象身份稳定，引擎改的就是 mem 里那块对象；
  3) select_parts 落定只进节点状态，`ext` 保持只有上游冻结文档。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import skill_tool_context
from app.services import skill_tools_select
from app.services.skill_node_state import (
    KP_ABSENT, KP_PICKS, NODE_STATE_KEY, kp_state, node_state)


def test_partitions_are_isolated():
    container: dict = {}
    kp = kp_state(container)
    model = node_state(container, "model_reason")
    assert kp is not model
    kp[KP_PICKS] = {"CPU|x": {"name": "A"}}
    model["baseline"] = {"name": "ZS22V2-P"}
    assert kp_state(container)[KP_PICKS] == {"CPU|x": {"name": "A"}}
    assert node_state(container, "model_reason")["baseline"] == {"name": "ZS22V2-P"}
    assert set(container[NODE_STATE_KEY]) == {"kp_reason", "model_reason"}


def test_partition_object_identity_is_stable():
    container: dict = {}
    assert kp_state(container) is kp_state(container)


def test_state_survives_mem_round_trip():
    mem: dict = {}
    kp_state(mem)[KP_PICKS] = {"CPU|x": {"name": "A"}}
    # 下一轮：引擎容器直接取 mem 里那块对象（run_skill_agent_turn 的做法）
    engine = {"node_state": mem.get(NODE_STATE_KEY) or {}}
    assert kp_state(engine)[KP_PICKS] == {"CPU|x": {"name": "A"}}
    kp_state(engine)[KP_ABSENT] = ["GPU"]
    assert kp_state(mem)[KP_ABSENT] == ["GPU"], "引擎就地改的必须就是 mem 里那块对象"


def test_select_parts_never_writes_shared_ext(monkeypatch):
    from app.services import data_tools
    from app.services import skill_chat

    def _by_name(category, name, *, series="", price_ok=True, _repo=None):
        rows = [{"part_id": "101", "name": "兆芯 KH-50000 32核", "category": "CPU",
                 "price": 4500.0, "currency": "RMB"}]
        want = re.sub(r"\s+", "", str(name or "")).lower()
        hit = [r for r in rows if str(r.get("category")) == str(category)
               and re.sub(r"\s+", "", r["name"]).lower() == want]
        return {"ok": True, "category": category, "source": "kp_library/name_lookup",
                "rows": hit, "total": len(hit)}

    monkeypatch.setattr(data_tools, "lookup_parts_by_name", _by_name)
    ext: dict = {"kp_rows": [{"part_category": "CPU",
                              "description": "兆芯 50000 32核 处理器", "qty": 2}]}
    engine: dict = {"ext": ext}
    skill_tool_context.TOOL_CTX.set({
        "ext": ext, "engine": engine, "task_active": True,
        "kp_rows_ctx": [{"row_key": "CPU|兆芯 50000 32核 处理器", "category": "CPU",
                         "description": "兆芯 50000 32核 处理器", "qty": 2, "specified": True}],
        "save": lambda: None,
    })
    res = skill_tools_select.tool_select_parts({"picks": [
        {"row": "CPU|兆芯 50000 32核 处理器", "name": "兆芯 KH-50000 32核",
         "reason": "核数一致"}]})
    assert res.get("ok") is True
    picks = kp_state(engine)[KP_PICKS]
    assert picks["CPU|兆芯 50000 32核 处理器"]["name"] == "兆芯 KH-50000 32核"
    assert set(ext) == {"kp_rows"}, "共享 ext 只保留上游冻结文档，节点状态不得回潮"
