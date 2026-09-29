# -*- coding: utf-8 -*-
"""产出物渲染服务 —— blocks+payload → HTML（预览/PDF 同一份）。

契约：
- payload = {"meta": {title, subtitle?, period_label, generated_by, generated_at},
             "answer": str(markdown), ...payload_map 其余字段}
- text 块 source="answer" 取整段答复；source="payload" + key 取 payload_map 产物字段
  （AI 填充=绿；chart/kpi/table 块走图表资产取数=蓝；meta=系统变量=灰）
- 图表 option 由 chart_assets 注册表解析（与驾驶舱同源），模板不自带图表定义

主题（theme）：单一「规格书同源」主题 house——视觉 token 镜像导出模板 SpecSheet
（品牌蓝 #1668C0 抬头细线 / 蓝色小节题+发丝线 / 灰表头 #F7F8FA / 浅灰圆角 KPI 卡），
无封面直接进正文；历史 theme 取值一律回落 house。
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

# ─────────── 主题 CSS：单一「规格书同源」主题，视觉 token 镜像导出模板 SpecSheet ───────────

_THEME_HOUSE_HEAD = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
  color: #1F2329; background: #fff; font-size: 11.5px; line-height: 1.7;
}
.rpt-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
  padding-bottom: 14px; border-bottom: 1.5px solid #1668C0; margin-bottom: 20px; }
.rpt-brand-name { font-size: 16px; font-weight: 700; color: #1F2329; }
.rpt-brand-tag { font-size: 10.5px; color: #6B7280; margin-top: 3px; }
.rpt-doc { text-align: right; }
.rpt-doc-period { font-size: 12px; font-weight: 700; color: #1668C0; }
.rpt-doc-meta { font-size: 10.5px; color: #6B7280; margin-top: 4px; }
.rpt-title-block { padding: 2px 0 2px 14px; border-left: 4px solid #1668C0; margin-bottom: 22px; }
h1.rpt-title { font-size: 24px; font-weight: 700; color: #111418; line-height: 1.25; }
.rpt-sub { font-size: 12px; color: #6B7280; margin-top: 6px; }
"""


_THEME_HOUSE_SEC = """
.blk-sec { margin-bottom: 22px; break-inside: avoid; }
.blk-title { font-size: 12px; font-weight: 700; letter-spacing: .6px; color: #1668C0;
  border-bottom: 1px solid #E5E7EB; padding-bottom: 6px; margin-bottom: 12px; }
.sec-no { font-size: 10.5px; font-weight: 700; color: #9CA3AF; margin-right: 8px; }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; }
.kpi-cell { background: #F7F8FA; border: 1px solid #E5E7EB; border-radius: 8px; padding: 12px 14px 10px; }
.kpi-label { font-size: 10px; color: #6B7280; margin-bottom: 5px; }
.kpi-value { font-size: 22px; font-weight: 700; color: #1668C0; font-variant-numeric: tabular-nums; }
.kpi-unit { font-size: 10.5px; color: #6B7280; font-weight: 400; margin-left: 3px; }
.chart-box { padding: 0; }
.chart-box .ch { width: 100%; }
"""


_THEME_HOUSE_MD = """
.md h3.md-h { font-size: 12px; font-weight: 700; color: #1F2329; margin: 10px 0 5px; }
.md p { margin-bottom: 7px; text-align: justify; }
.md ul { padding-left: 18px; margin-bottom: 7px; }
.md li { margin-bottom: 3px; }
.md hr { border: 0; border-top: 1px solid #E5E7EB; margin: 10px 0; }
.md table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 10px; }
.md th { background: #F7F8FA; border-bottom: 1px solid #E5E7EB; padding: 6px 8px;
  text-align: left; font-weight: 600; color: #6B7280; }
.md td { border-bottom: 1px solid #EEF0F3; padding: 6px 8px; }
"""


_THEME_HOUSE_TBL = """
.rpt-table { width: 100%; border-collapse: collapse; font-size: 10px; }
.rpt-table thead th { padding: 7px 10px; text-align: left; font-weight: 700; font-size: 10px;
  letter-spacing: .4px; color: #6B7280; background: #F7F8FA; border-bottom: 1px solid #E5E7EB; }
.rpt-table td { padding: 7px 10px; border-bottom: 1px solid #EEF0F3; color: #1F2329; line-height: 1.45; }
.rpt-fields th { width: 168px; text-align: left; font-weight: 500; color: #6B7280;
  background: none; border-bottom: 1px solid #EEF0F3; padding: 7px 10px; vertical-align: top; }
.foot { margin-top: 26px; padding-top: 10px; border-top: 1px solid #E5E7EB;
  font-size: 9px; color: #9CA3AF; display: flex; justify-content: space-between; }
"""

# 主题注册表：单一「规格书同源」主题；历史 theme 取值一律回落 house
_THEME_SPECS = {
    "house": {"css": _THEME_HOUSE_HEAD + _THEME_HOUSE_SEC + _THEME_HOUSE_MD + _THEME_HOUSE_TBL},
}

# interactive（编辑器预览）附加样式：选中态 / 分页参考线 / 预览态页边距
# （PDF 模式页边距由 page.pdf margin 提供，浏览器预览没有 PDF 引擎，用 padding 模拟）
_INTERACTIVE_CSS = """
body { padding: 14mm 18mm 16mm; }
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
_PDF_MARGIN = {"top": "20mm", "bottom": "16mm", "left": "18mm", "right": "18mm"}


def _pdf_header_template(title: str, date_str: str) -> str:
    return (
        f'<div style="font-size:8px;color:#9CA3AF;width:100%;padding:0 18mm;'
        f'display:flex;justify-content:space-between;border-bottom:0.75px solid #E5E7EB;'
        f'font-family:Microsoft YaHei,sans-serif;">'
        f"<span>{_esc(title)}</span><span>{_esc(date_str)}</span></div>"
    )


def _pdf_footer_template() -> str:
    return (
        '<div style="font-size:8px;color:#9CA3AF;width:100%;padding:0 18mm;'
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


# payload 行/字段表的列标签（镜像 compose 节点「方案配置表」列契约的既有事实，未覆盖的键显示原键名）
_CELL_LABELS = {
    "part_category": "Catalogue",
    "catalogue": "Configuration Description",
    "qty": "Quantity",
}


def _fmt_cell(v) -> str:
    """结构化单元格 → 文本：列表顿号连接，嵌套 dict 平铺为 k: v，None 空，bool 中文化。"""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, (list, tuple)):
        return "、".join(str(x) for x in v)
    if isinstance(v, dict):
        return "；".join(f"{k}: {_fmt_cell(x)}" for k, x in v.items())
    return str(v)


def render_report_html(
    blocks: list,
    payload: Optional[dict] = None,
    *,
    template_name: str = "",
    echarts_url: Optional[str] = None,
    echarts_inline_js: Optional[str] = None,
    theme: str = "house",
    interactive: bool = False,
    asset_params: Optional[dict] = None,
) -> str:
    """blocks+payload → 完整 HTML 文档。iframe 预览传 echarts_url（相对 /api 由父文档 base 解析）；
    PDF 传 echarts_inline_js（磁盘 echarts.min.js 全文内联）。interactive=True 仅编辑器预览用
    （区块可点选+分页参考线），PDF 恒 False。asset_params=运行时资产参数覆盖（如报告数据范围
    推出的 days），按 schema clamp 后不认该参数的资产自动忽略，编辑器预览不传。"""
    if asset_params:
        blocks = [
            ({**b, "params": {**(b.get("params") or {}), **asset_params}}
             if b.get("type") in ("kpi", "chart", "table") else b)
            for b in (blocks or [])
        ]
    p = _default_payload(payload, template_name)
    meta = p["meta"]
    spec = _THEME_SPECS.get(theme) or _THEME_SPECS["house"]
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

    # 抬头（镜像 SpecSheet .ss-header：左品牌 / 右文档信息，蓝线收底）+ 标题块（左 4px 蓝杠）
    period = str(meta.get("period_label", "")).replace("统计区间：", "").strip()
    period_html = f'<div class="rpt-doc-period">统计区间　{_esc(period)}</div>' if period else ""
    sub_html = f'<div class="rpt-sub">{_esc(meta.get("subtitle", ""))}</div>' if meta.get("subtitle") else ""
    head_html = (
        '<div class="rpt-head">'
        '<div><div class="rpt-brand-name">CPQ PLATFORM</div>'
        f'<div class="rpt-brand-tag">{_esc(meta.get("generated_by", ""))}</div></div>'
        f'<div class="rpt-doc">{period_html}'
        f'<div class="rpt-doc-meta">生成时间 {_esc(meta.get("generated_at", ""))}</div></div></div>'
        f'<div class="rpt-title-block"><h1 class="rpt-title">{_esc(meta.get("title", ""))}</h1>{sub_html}</div>'
    )

    for idx, blk in enumerate(blocks or []):
        t = blk.get("type")
        if t == "title":
            continue  # 抬头+标题块由 meta 统一构造在 body 头部（规格书同源抬头，无封面）
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
        elif t == "fields":
            fdata = p.get(blk.get("key") or "")
            if not isinstance(fdata, dict) or not fdata:
                continue
            flat: list[tuple[str, object]] = []

            def _flat(d: dict, prefix: str = "") -> None:
                for k, v in d.items():
                    name = f"{prefix}.{k}" if prefix else str(k)
                    if isinstance(v, dict) and v:
                        _flat(v, name)
                    else:
                        flat.append((name, _fmt_cell(v)))

            _flat(fdata)
            rows = "".join(
                f'<tr><th>{_esc(_CELL_LABELS.get(k, k))}</th><td>{_esc(str(v))}</td></tr>'
                for k, v in flat
            )
            body.append(f'{sec_open(idx)}{sec_title(blk)}<table class="rpt-table rpt-fields"><tbody>{rows}</tbody></table></section>')
        elif t == "table":
            if blk.get("source") == "payload":
                prows = p.get(blk.get("key") or "")
                if not isinstance(prows, list) or not prows or not all(isinstance(r, dict) for r in prows):
                    continue
                keys: list = []
                for r in prows:
                    for k in r.keys():
                        if k not in keys:
                            keys.append(k)
                cols = "".join(f"<th>{_esc(_CELL_LABELS.get(k, k))}</th>" for k in keys)
                rows = "".join(
                    "<tr>" + "".join(f"<td>{_esc(str(_fmt_cell(r.get(k))))}</td>" for k in keys) + "</tr>"
                    for r in prows
                )
                body.append(f'{sec_open(idx)}{sec_title(blk)}<table class="rpt-table"><thead><tr>{cols}</tr></thead><tbody>{rows}</tbody></table></section>')
                continue
            data = chart_assets.resolve_asset_data(blk.get("asset") or "", blk.get("params"))
            if not data:
                continue
            cols = "".join(f"<th>{_esc(c)}</th>" for c in data.get("columns", []))
            rows = "".join(
                "<tr>" + "".join(f"<td>{_esc(r.get(k, ''))}</td>" for k in ("customer", "platform", "sales", "result", "created")) + "</tr>"
                for r in data.get("rows", [])
            )
            body.append(f'{sec_open(idx)}{sec_title(blk)}<table class="rpt-table"><thead><tr>{cols}</tr></thead><tbody>{rows}</tbody></table></section>')

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
    css = spec["css"]
    if interactive:
        css += _INTERACTIVE_CSS
    extra_js_tag = f"<script>{_INTERACTIVE_JS}</script>" if interactive else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>{_esc(meta.get('title', ''))}</title>
<style>{css}</style></head>
<body>
{head_html}{''.join(body)}
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
      if (chart) {{ var opt = c.option || {{}}; opt.animation = false; chart.setOption(opt); }}
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
    theme: str = "house",
    asset_params: Optional[dict] = None,
) -> bytes:
    """HTML → PDF（串行锁：同一时刻至多一个 chromium）。playwright 缺失抛 RuntimeError。
    asset_params 透传 render_report_html（运行时数据范围→图表资产参数覆盖）。"""
    js = _vendor_echarts_js()
    if js is None:
        raise RuntimeError("echarts vendor missing (backend/app/static/vendor/echarts.min.js)")
    p = _default_payload(payload, template_name)
    header = _pdf_header_template(p["meta"].get("title", ""), p["meta"].get("generated_at", ""))
    doc = render_report_html(
        blocks, payload, template_name=template_name, echarts_inline_js=js, theme=theme,
        interactive=False, asset_params=asset_params,
    )
    async with _PDF_SEMAPHORE:
        return await asyncio.to_thread(_pdf_sync, doc, header, _pdf_footer_template())
