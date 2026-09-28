# -*- coding: utf-8 -*-
"""输出节点文件产物（markdown→PDF 报告）测试（2026-09-15）。

锁三件事：
1. 渲染器：中文标题/列表/表格 markdown → 合法 PDF bytes；解析器块级单测
2. finalize_output 集成（真 event_sink）：声明 artifacts → payload.files 带 url 且落盘
3. 护栏：无 artifacts 声明 → files 为空；渲染不挡交付（answer 仍在 payload）
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MD = """## 商机趋势分析报告

数据范围：2026.02.13 ~ 2026.09.06

### 一、周数据（08.31 - 09.06）

| 平台 | 商机数 | 金额(万) |
| --- | --- | --- |
| Polaris | 12 | 340.5 |
| Orion | 8 | 210.0 |

- Polaris 占比 56.4%，**环比 +3.2%**
- 4U 机箱形态占比 48.1%

### 二、关键洞察

1. 国产化需求持续上行
"""


def test_render_markdown_report_pdf_basic():
    from app.services.report_pdf import render_markdown_report_pdf
    pdf = render_markdown_report_pdf("商机趋势分析报告", MD, meta={"created_at": "生成时间 2026-09-15 10:00"})
    assert isinstance(pdf, bytes)
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 5 * 1024


def test_parse_markdown_blocks_structure():
    from app.services.report_pdf import _parse_markdown_blocks
    blocks = _parse_markdown_blocks(MD)
    types = [b["type"] for b in blocks]
    assert "heading" in types and "table" in types and "bullet" in types
    # 表头分隔行（| --- | --- |）不产数据行
    tables = [b for b in blocks if b["type"] == "table"]
    assert len(tables) == 1
    assert tables[0]["rows"] == [
        ["平台", "商机数", "金额(万)"],
        ["Polaris", "12", "340.5"],
        ["Orion", "8", "210.0"],
    ]
    headings = [b for b in blocks if b["type"] == "heading"]
    assert headings[0]["level"] == 2
    assert headings[0]["text"] == "商机趋势分析报告"
    # 数字编号行按列表渲染
    numbered = [b for b in blocks if b["type"] == "bullet"]
    assert any("国产化需求" in b["text"] for b in numbered)


def _tmp_storage(monkeypatch, tmp_path):
    import app.services.storage_adapter as st
    adapter = st.LocalFileStorage(base_path=str(tmp_path))
    monkeypatch.setattr(st, "_storage", adapter)
    return adapter


def test_finalize_output_renders_pdf_artifact(monkeypatch, tmp_path):
    _tmp_storage(monkeypatch, tmp_path)
    from app.services.skill_node_runtime import finalize_output

    events: list[dict] = []

    async def sink(ev: dict) -> None:
        events.append(ev)

    ctx = {"agent_result": {"answer": MD}, "assembled": {"answer": MD}}
    config = {
        "output_kind": "data_answer",
        "artifacts": [{"kind": "document", "format": "pdf", "title": "商机趋势分析报告"}],
    }
    asyncio.run(finalize_output(ctx, config, sink))
    files = ctx["output_payload"]["files"]
    assert len(files) == 1
    f = files[0]
    assert f["url"].startswith("/api/office/reports/")
    assert f["filename"].endswith(".pdf")
    assert f["mime"] == "application/pdf"
    assert f["size"] > 1024
    # 落盘存在（office 中立桶）；url 形如 /api/office/reports/{object_id}/download
    local = tmp_path / "office" / "reports" / f"{f['url'].rsplit('/', 2)[-2]}.pdf"
    assert local.exists() and local.read_bytes()[:5] == b"%PDF-"
    # 交付不被文件产物改写：answer 仍在（finalize 会 strip 尾空白）
    assert ctx["output_payload"]["answer"] == MD.strip()
    # 广播走 handoff_ready（payload 是真 payload，files 在其中）
    handoff = [e for e in events if e["type"] == "handoff_ready"]
    assert handoff and handoff[0]["payload"]["files"][0]["url"] == f["url"]


def test_finalize_output_without_artifacts(monkeypatch, tmp_path):
    _tmp_storage(monkeypatch, tmp_path)
    from app.services.skill_node_runtime import finalize_output

    events: list[dict] = []

    async def sink(ev: dict) -> None:
        events.append(ev)

    ctx = {"agent_result": {"answer": "SSD 涨 3%"}, "assembled": {}}
    config = {"output_kind": "data_answer"}
    asyncio.run(finalize_output(ctx, config, sink))
    assert ctx["output_payload"]["files"] == []
    assert ctx["output_payload"]["answer"] == "SSD 涨 3%"
