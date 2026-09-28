# -*- coding: utf-8 -*-
"""产出物渲染服务 —— blocks+payload → HTML（预览/PDF 同一份）。

契约：
- payload = {"meta": {title, subtitle?, period_label, generated_by, generated_at},
             "answer": str(markdown), ...payload_map 其余字段}
- text 块 source="answer" 取整段答复；source="payload" + key 取 payload_map 产物字段
  （AI 填充=绿；chart/kpi/table 块走图表资产取数=蓝；meta=系统变量=灰）
- 图表 option 由 chart_assets 注册表解析（与驾驶舱同源），模板不自带图表定义

主题（theme）：选型期三份并存 business/github/softened，定稿后只留一份。
interactive=True（编辑器预览）：注入区块 data-idx + postMessage 双向协议 +
A4 分页参考线；PDF 路径恒 False。

PDF：Playwright chromium set_content → page.pdf(A4, print_background,
display_header_footer + header/footer template：页眉=报告名+日期，页脚=页码)。
playwright 不可用时抛 RuntimeError，由调用方（skill_node_runtime）回退 legacy reportlab。
"""
import asyncio
import html as _html
import re
from datetime import datetime
from typing import Optional

from . import chart_assets

_PDF_SEMAPHORE = asyncio.Semaphore(1)

_ECHARTS_DONE_FLAG = "window.__CHARTS_DONE__"

# ─────────────────────────── 主题 CSS（选型期三份，定稿删两份） ───────────────────────────

_THEME_BUSINESS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
@page { size: A4; margin: 0; }
body {
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
  color: #1A1A1A; background: #fff; font-size: 11px; line-height: 1.75;
}
.masthead {
  display: flex; justify-content: space-between; align-items: baseline;
  font-size: 8.5px; letter-spacing: 2px; color: #6B7280;
  border-bottom: 2.5px solid #111827; padding-bottom: 7px; margin-bottom: 30px;
}
h1.rpt-title {
  font-family: "Noto Serif SC", "Source Han Serif SC", "SimSun", "STSong", serif;
  font-size: 25px; font-weight: 700; color: #111827; letter-spacing: 2px; margin-bottom: 8px;
}
.rpt-sub {
  font-family: "Noto Serif SC", "Source Han Serif SC", "SimSun", "STSong", serif;
  font-size: 12.5px; color: #4B5563; margin-bottom: 18px;
}
.meta-row {
  display: flex; gap: 20px; flex-wrap: wrap; font-size: 9px; color: #6B7280;
  border-bottom: 1px solid #E5E7EB; padding-bottom: 8px; margin-bottom: 24px;
}
.meta-row b { color: #374151; font-weight: 600; margin-right: 4px; }
.blk-sec { margin-bottom: 22px; break-inside: avoid; }
.blk-title { font-size: 13.5px; font-weight: 700; color: #111827; margin-bottom: 10px; }
.sec-no {
  font-family: "Georgia", "Times New Roman", serif;
  font-size: 11px; font-weight: 400; color: #9CA3AF; margin-right: 8px;
}
.md h3.md-h { font-size: 12px; font-weight: 700; color: #1F2430; margin: 10px 0 5px; }
.md p { margin-bottom: 7px; text-align: justify; }
.md ul { padding-left: 18px; margin-bottom: 7px; }
.md li { margin-bottom: 3px; }
.md hr { border: 0; border-top: 1px solid #E5E7EB; margin: 10px 0; }
.md table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 9.5px; }
.md th { border-top: 1.5px solid #111827; border-bottom: 1px solid #111827; padding: 5px 8px; text-align: left; font-weight: 600; }
.md td { border-bottom: 1px solid #E5E7EB; padding: 5px 8px; }
.md table tr:last-child td { border-bottom: 1.5px solid #111827; }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 16px 20px; }
.kpi-cell { border-top: 1.5px solid #111827; padding-top: 7px; }
.kpi-label { font-size: 8.5px; color: #6B7280; letter-spacing: 1px; margin-bottom: 3px; }
.kpi-value { font-size: 22px; font-weight: 700; color: #111827; font-variant-numeric: tabular-nums; }
.kpi-unit { font-size: 10px; color: #6B7280; margin-left: 2px; font-weight: 400; }
.chart-box { padding: 0; }
.chart-box .ch { width: 100%; }
.rpt-table { width: 100%; border-collapse: collapse; font-size: 9.5px; }
.rpt-table thead th {
  border-top: 1.5px solid #111827; border-bottom: 1px solid #111827;
  padding: 6px 8px; text-align: left; font-weight: 600; color: #111827; background: none;
}
.rpt-table td { border-bottom: 1px solid #E5E7EB; padding: 6px 8px; }
.rpt-table tbody tr:last-child td { border-bottom: 1.5px solid #111827; }
.foot {
  margin-top: 26px; padding-top: 8px; border-top: 1px solid #E5E7EB;
  font-size: 8.5px; color: #9CA3AF; display: flex; justify-content: space-between;
}
"""

_THEME_GITHUB = """
* { box-sizing: border-box; margin: 0; padding: 0; }
@page { size: A4; margin: 0; }
body {
  font-family: -apple-system, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
  color: #1F2328; background: #fff; font-size: 11px; line-height: 1.65;
}
.masthead { display: none; }
h1.rpt-title { font-size: 22px; font-weight: 600; color: #1F2328; padding-bottom: 8px; border-bottom: 1px solid #D1D9E0; margin-bottom: 12px; }
.rpt-sub { font-size: 12px; color: #59636E; margin-bottom: 12px; }
.meta-row {
  display: flex; gap: 16px; flex-wrap: wrap; font-size: 9px; color: #59636E; margin-bottom: 20px;
}
.meta-row b { color: #1F2328; font-weight: 600; margin-right: 4px; }
.blk-sec { margin-bottom: 18px; break-inside: avoid; }
.blk-title { font-size: 14px; font-weight: 600; color: #1F2328; padding-bottom: 6px; border-bottom: 1px solid #D1D9E0; margin-bottom: 10px; }
.sec-no { font-size: 11px; font-weight: 400; color: #8C959F; margin-right: 7px; }
.md h3.md-h { font-size: 12px; font-weight: 600; color: #1F2328; margin: 10px 0 5px; }
.md p { margin-bottom: 7px; text-align: justify; }
.md ul { padding-left: 18px; margin-bottom: 7px; }
.md li { margin-bottom: 3px; }
.md hr { border: 0; border-top: 1px solid #D1D9E0; margin: 10px 0; }
.md table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 9.5px; }
.md th { border-bottom: 2px solid #D1D9E0; padding: 5px 8px; text-align: left; font-weight: 600; }
.md td { border-bottom: 1px solid #EFF2F5; padding: 5px 8px; }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 14px 18px; }
.kpi-cell { border-top: 2px solid #D1D9E0; padding-top: 6px; }
.kpi-label { font-size: 8.5px; color: #59636E; margin-bottom: 3px; }
.kpi-value { font-size: 21px; font-weight: 700; color: #1F2328; font-variant-numeric: tabular-nums; }
.kpi-unit { font-size: 10px; color: #59636E; margin-left: 2px; font-weight: 400; }
.chart-box { padding: 0; }
.chart-box .ch { width: 100%; }
.rpt-table { width: 100%; border-collapse: collapse; font-size: 9.5px; }
.rpt-table th { border-bottom: 2px solid #D1D9E0; padding: 6px 8px; text-align: left; font-weight: 600; }
.rpt-table td { border-bottom: 1px solid #EFF2F5; padding: 6px 8px; }
.foot {
  margin-top: 24px; padding-top: 8px; border-top: 1px solid #D1D9E0;
  font-size: 8.5px; color: #8C959F; display: flex; justify-content: space-between;
}
"""

_THEME_SOFTENED = """
* { box-sizing: border-box; margin: 0; padding: 0; }
@page { size: A4; margin: 0; }
body {
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
  color: #1F2430; background: #fff; font-size: 11px; line-height: 1.7;
}
.masthead {
  display: flex; justify-content: space-between; font-size: 8.5px; letter-spacing: 2px;
  color: #6B7280; border-bottom: 1px solid #E5E7EB; padding-bottom: 6px; margin-bottom: 24px;
}
h1.rpt-title { font-size: 24px; font-weight: 800; color: #111827; letter-spacing: 0.5px; margin-bottom: 4px; }
.rpt-sub { font-size: 12px; color: #6B7280; margin-bottom: 14px; }
.meta-row {
  display: flex; gap: 18px; flex-wrap: wrap; font-size: 9px; color: #6B7280;
  border-top: 1px solid #E5E7EB; border-bottom: 1px solid #E5E7EB; padding: 6px 0; margin-bottom: 18px;
}
.meta-row b { color: #374151; font-weight: 600; margin-right: 4px; }
.blk-sec { margin-bottom: 16px; break-inside: avoid; }
.blk-title { font-size: 13px; font-weight: 700; color: #111827; margin-bottom: 8px; }
.sec-no { font-size: 10.5px; font-weight: 400; color: #9CA3AF; margin-right: 7px; }
.md h3.md-h { font-size: 11.5px; font-weight: 700; color: #1F2430; margin: 8px 0 4px; }
.md p { margin-bottom: 6px; text-align: justify; }
.md ul { padding-left: 18px; margin-bottom: 6px; }
.md li { margin-bottom: 3px; }
.md hr { border: 0; border-top: 1px dashed #E5E7EB; margin: 8px 0; }
.md table { width: 100%; border-collapse: collapse; margin: 6px 0; font-size: 9.5px; }
.md th, .md td { border: 1px solid #E5E7EB; padding: 4px 8px; text-align: left; }
.md th { background: #F9FAFB; font-weight: 600; }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }
.kpi-cell { border: 1px solid #E5E7EB; padding: 11px 13px; }
.kpi-label { font-size: 9px; color: #6B7280; margin-bottom: 5px; }
.kpi-value { font-size: 20px; font-weight: 800; color: #111827; }
.kpi-unit { font-size: 10px; color: #6B7280; margin-left: 3px; font-weight: 400; }
.chart-box { border: 1px solid #E5E7EB; padding: 8px 10px 4px; }
.chart-box .ch { width: 100%; }
.rpt-table { width: 100%; border-collapse: collapse; font-size: 9.5px; }
.rpt-table th { background: #F3F4F6; color: #374151; font-weight: 600; padding: 7px 10px; text-align: left; }
.rpt-table td { border-bottom: 1px solid #E5E7EB; padding: 7px 10px; }
.foot {
  margin-top: 20px; padding-top: 8px; border-top: 1px solid #E5E7EB;
  font-size: 8.5px; color: #9CA3AF; display: flex; justify-content: space-between;
}
"""

_THEMES = {"business": _THEME_BUSINESS, "github": _THEME_GITHUB, "softened": _THEME_SOFTENED}

# interactive（编辑器预览）附加样式：选中态 / 分页参考线 / 预览态页边距
# （PDF 模式页边距由 page.pdf margin 提供，浏览器预览没有 PDF 引擎，用 padding 模拟）
_INTERACTIVE_CSS = """
body { padding: 14mm 15mm 16mm; }
.blk-sec { cursor: pointer; }
.blk-sec:hover { background: #F8FAFC; }
.blk-sec.atc-sel { outline: 2px dashed #2563EB; outline-offset: 5px; }
.atc-pageline {
  position: absolute; left: 0; right: 0; border-top: 1px dashed #94A3B8;
  font-size: 7.5px; color: #94A3B8; text-align: right; padding-top: 2px;
}
"""

_INTERACTIVE_JS = """
(function(){
  function pickIdx(el){ var n = el; while (n && n !== document.body){ if (n.dataset && n.dataset.atcIdx !== undefined) return n; n = n.parentElement; } return null; }
  document.addEventListener('click', function(ev){
    var t = pickIdx(ev.target);
    if (t) parent.postMessage({ type: 'atc-select', idx: parseInt(t.dataset.atcIdx, 10) }, '*');
  });
  var cur = -1;
  function applySel(idx){
    if (idx === cur) return; cur = idx;
    var el = null;
    document.querySelectorAll('.blk-sec[data-atc-idx]').forEach(function(n){
      var hit = parseInt(n.dataset.atcIdx, 10) === idx;
      n.classList.toggle('atc-sel', hit);
      if (hit) el = n;
    });
    if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
  window.addEventListener('message', function(ev){
    var d = ev.data || {};
    if (d.type === 'atc-highlight') applySel(d.idx);
  });
  function reportHeight(){ parent.postMessage({ type: 'atc-height', h: Math.ceil(document.body.scrollHeight) }, '*'); }
  function drawPageLines(){
    document.querySelectorAll('.atc-pageline').forEach(function(el){ el.remove(); });
    var H = 1123, pages = Math.max(1, Math.ceil(document.body.scrollHeight / H));
    for (var i = 1; i < pages; i++){
      var d = document.createElement('div');
      d.className = 'atc-pageline';
      d.style.top = (i * H) + 'px';
      d.textContent = '\\u7b2c ' + (i + 1) + ' \\u9875';
      document.body.appendChild(d);
    }
    if (document.body.style.position !== 'relative') document.body.style.position = 'relative';
  }
  function refresh(){ drawPageLines(); reportHeight(); }
  window.addEventListener('load', function(){ refresh(); setTimeout(refresh, 600); setTimeout(refresh, 1500); });
  if (window.__CHARTS_DONE__) refresh();
  var done = false;
  var timer = setInterval(function(){
    if (window.__CHARTS_DONE__ && !done){ done = true; refresh(); clearInterval(timer); }
  }, 200);
  window.addEventListener('resize', refresh);
})();
"""

# chromium page.pdf 页眉/页脚模板：不认外链 CSS，字号必须显式 px
_PDF_MARGIN = {"top": "20mm", "bottom": "16mm", "left": "15mm", "right": "15mm"}


def _pdf_header_template(title: str, date_str: str) -> str:
    return (
        f'<div style="font-size:8px;color:#9CA3AF;width:100%;padding:0 15mm;'
        f'display:flex;justify-content:space-between;border-bottom:0.75px solid #E5E7EB;'
        f'font-family:Microsoft YaHei,sans-serif;">'
        f"<span>{_esc(title)}</span><span>{_esc(date_str)}</span></div>"
    )


def _pdf_footer_template() -> str:
    return (
        '<div style="font-size:8px;color:#9CA3AF;width:100%;padding:0 15mm;'
        'display:flex;justify-content:space-between;font-family:Microsoft YaHei,sans-serif;">'
        '<span>CPQ Platform · 内部资料</span>'
        '<span>第 <span class="pageNumber"></span> 页 / 共 <span class="totalPages"></span> 页</span></div>'
    )


def _esc(s) -> str:
    return _html.escape(str(s if s is not None else ""))


def _inline_md(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _esc(s))


def _markdown_to_html(text: str) -> str:
    from .report_pdf import _parse_markdown_blocks
    parts: list[str] = ['<div class="md">']
    for b in _parse_markdown_blocks(text or ""):
        t = b.get("type")
        if t == "heading":
            parts.append(f'<h3 class="md-h">{_inline_md(b.get("text", ""))}</h3>')
        elif t == "bullet":
            parts.append(f"<ul><li>{_inline_md(b.get('text', ''))}</li></ul>")
        elif t == "rule":
            parts.append("<hr/>")
        elif t == "table":
            rows = b.get("rows") or []
            if rows:
                head = "".join(f"<th>{_inline_md(c)}</th>" for c in rows[0])
                body = "".join(
                    "<tr>" + "".join(f"<td>{_inline_md(c if c else '')}</td>" for c in r) + "</tr>"
                    for r in rows[1:]
                )
                parts.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
        else:
            parts.append(f"<p>{_inline_md(b.get('text', ''))}</p>")
    parts.append("</div>")
    return "".join(parts)


def _default_payload(payload: Optional[dict], template_name: str = "") -> dict:
    p = dict(payload or {})
    meta = dict(p.get("meta") or {})
    meta.setdefault("title", template_name or "业务报告")
    meta.setdefault("subtitle", "")
    meta.setdefault("period_label", f"统计区间：近 8 周（截至 {datetime.now().strftime('%Y-%m-%d')}）")
    meta.setdefault("generated_by", "AI 办公室")
    meta.setdefault("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    p["meta"] = meta
    return p


def render_report_html(
    blocks: list,
    payload: Optional[dict] = None,
    *,
    template_name: str = "",
    echarts_url: Optional[str] = None,
    echarts_inline_js: Optional[str] = None,
    theme: str = "business",
    interactive: bool = False,
) -> str:
    """blocks+payload → 完整 HTML 文档。iframe 预览传 echarts_url（相对 /api 由父文档 base 解析）；
    PDF 传 echarts_inline_js（磁盘 echarts.min.js 全文内联）。interactive=True 仅编辑器预览用
    （区块可点选+分页参考线），PDF 恒 False。"""
    p = _default_payload(payload, template_name)
    meta = p["meta"]
    body: list[str] = []
    charts: list[dict] = []
    sec_no = 0

    def sec_title(blk: dict) -> str:
        nonlocal sec_no
        if not blk.get("title"):
            return ""
        sec_no += 1
        return f'<div class="blk-title"><span class="sec-no">{sec_no:02d}</span>{_esc(blk["title"])}</div>'

    def sec_open(idx: int) -> str:
        # data-atc-idx = 区块在 blocks 里的下标，与编辑器左栏 selectedIdx 对齐（预览点击反选）
        mark = f' data-atc-idx="{idx}"' if interactive else ""
        return f'<section class="blk-sec"{mark}>'

    for idx, blk in enumerate(blocks or []):
        t = blk.get("type")
        if t == "title":
            sub = f'<div class="rpt-sub">{_esc(meta.get("subtitle", ""))}</div>' if meta.get("subtitle") else ""
            date_str = datetime.now().strftime("%Y-%m-%d")
            body.append(
                f'<div class="masthead"><span>CPQ PLATFORM</span><span>{date_str}</span></div>'
                f'<h1 class="rpt-title">{_esc(meta.get("title", ""))}</h1>{sub}'
                f'<div class="meta-row">'
                f'<span><b>统计区间</b>{_esc(meta.get("period_label", "").replace("统计区间：", ""))}</span>'
                f'<span><b>生成</b>{_esc(meta.get("generated_by", ""))}</span>'
                f'<span><b>时间</b>{_esc(meta.get("generated_at", ""))}</span>'
                f"</div>"
            )
        elif t == "text":
            src = blk.get("source") or "answer"
            text = ""
            if src == "payload":
                text = str(p.get(blk.get("key") or "") or "")
            else:
                text = str(p.get("answer") or "")
            if not text.strip():
                continue
            body.append(f'{sec_open(idx)}{sec_title(blk)}{_markdown_to_html(text)}</section>')
        elif t == "kpi":
            data = chart_assets.resolve_asset_data(blk.get("asset") or "", blk.get("params")) or {"items": []}
            cells = "".join(
                f'<div class="kpi-cell"><div class="kpi-label">{_esc(i.get("label", ""))}</div>'
                f'<span class="kpi-value">{_esc(i.get("value", ""))}</span>'
                f'<span class="kpi-unit">{_esc(i.get("unit", ""))}</span></div>'
                for i in data.get("items", [])
            )
            body.append(f'{sec_open(idx)}{sec_title(blk)}<div class="kpi-grid">{cells}</div></section>')
        elif t == "chart":
            asset_id = blk.get("asset") or ""
            option = chart_assets.resolve_chart_option(asset_id, blk.get("params"))
            if option is None:
                continue
            height = int(blk.get("height") or 240)
            dom_id = f"ch-{idx}"
            charts.append({"id": dom_id, "option": option})
            body.append(
                f'{sec_open(idx)}{sec_title(blk)}'
                f'<div class="chart-box"><div class="ch" id="{dom_id}" style="height:{height}px"></div></div></section>'
            )
        elif t == "table":
            data = chart_assets.resolve_asset_data(blk.get("asset") or "", blk.get("params"))
            if not data:
                continue
            cols = "".join(f"<th>{_esc(c)}</th>" for c in data.get("columns", []))
            rows = "".join(
                "<tr>" + "".join(f"<td>{_esc(r.get(k, ''))}</td>" for k in ("customer", "platform", "sales", "result", "created")) + "</tr>"
                for r in data.get("rows", [])
            )
            body.append(f'{sec_open(idx)}{sec_title(blk)}<table class="rpt-table"><thead><tr>{cols}</tr></thead><tbody>{rows}</tbody></table></section>')

    if not any(b.get("type") == "title" for b in (blocks or [])):
        body.insert(
            0,
            f'<div class="masthead"><span>CPQ PLATFORM</span><span>{datetime.now().strftime("%Y-%m-%d")}</span></div>'
            f'<h1 class="rpt-title">{_esc(meta.get("title", ""))}</h1>'
            f'<div class="meta-row"><span><b>生成</b>{_esc(meta.get("generated_by", ""))}</span>'
            f'<span><b>时间</b>{_esc(meta.get("generated_at", ""))}</span></div>',
        )

    import json as _json
    chart_js = _json.dumps(charts, ensure_ascii=False)
    foot = (
        f'<div class="foot"><span>本报告由 CPQ 产出物模板渲染 · 数据来自系统业务库</span>'
        f"<span>{_esc(meta.get('generated_at', ''))}</span></div>"
    )
    if echarts_inline_js:
        echarts_tag = f"<script>{echarts_inline_js}</script>"
    elif echarts_url:
        echarts_tag = f'<script src="{_esc(echarts_url)}"></script>'
    else:
        echarts_tag = ""
    css = _THEMES.get(theme, _THEME_BUSINESS)
    if interactive:
        css += _INTERACTIVE_CSS
    extra_js_tag = f"<script>{_INTERACTIVE_JS}</script>" if interactive else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>{_esc(meta.get('title', ''))}</title>
<style>{css}</style></head>
<body>
{''.join(body)}
{foot}
{echarts_tag}
<script>
window.__CHARTS__ = {chart_js};
(function(){{
  function run(){{
    var list = window.__CHARTS__ || [];
    list.forEach(function(c){{
      var el = document.getElementById(c.id);
      if (!el) return;
      var chart = window.echarts && window.echarts.init(el, null, {{renderer: 'canvas'}});
      if (chart) chart.setOption(c.option);
    }});
    window.__CHARTS_DONE__ = true;
  }}
  if (window.echarts) run(); else window.addEventListener('load', function(){{ setTimeout(run, 0); }});
}})();
</script>
{extra_js_tag}
</body></html>"""


def _vendor_echarts_js() -> Optional[str]:
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "vendor", "echarts.min.js")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _pdf_sync(html: str, header_tpl: str, footer_tpl: str) -> bytes:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1000, "height": 1400})
            page.set_content(html, wait_until="load")
            try:
                page.wait_for_function("window.__CHARTS_DONE__ === true", timeout=10000)
            except Exception:
                pass  # 无图表块或超时：照样出 PDF，不挡交付
            return page.pdf(
                format="A4",
                print_background=True,
                display_header_footer=True,
                header_template=header_tpl,
                footer_template=footer_tpl,
                margin=_PDF_MARGIN,
            )
        finally:
            browser.close()


async def render_report_pdf(
    blocks: list,
    payload: Optional[dict],
    *,
    template_name: str = "",
    theme: str = "business",
) -> bytes:
    """HTML → PDF（串行锁：同一时刻至多一个 chromium）。playwright 缺失抛 RuntimeError。"""
    js = _vendor_echarts_js()
    if js is None:
        raise RuntimeError("echarts vendor missing (backend/app/static/vendor/echarts.min.js)")
    p = _default_payload(payload, template_name)
    header = _pdf_header_template(p["meta"].get("title", ""), p["meta"].get("generated_at", ""))
    doc = render_report_html(
        blocks, payload, template_name=template_name, echarts_inline_js=js, theme=theme, interactive=False
    )
    async with _PDF_SEMAPHORE:
        return await asyncio.to_thread(_pdf_sync, doc, header, _pdf_footer_template())
