# -*- coding: utf-8 -*-
"""输出节点文件产物渲染：markdown 结论 → PDF 报告（reportlab，确定性后处理零 LLM）。

插头插座契约：渲染器只认「markdown 文本 + 标题 + meta」，不认识任何具体流程
（趋势分析/未来任何 data_answer 流声明 artifacts 即得 PDF 产物）。

中文字体链：环境变量 REPORT_PDF_FONT（ttf/ttc 路径）→ Windows msyh.ttc →
reportlab 内置 CID 字体 STSong-Light（零文件兜底，任何环境可用）。
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, Paragraph, SimpleDocTemplate, Table,
                                TableStyle)

import logging

logger = logging.getLogger(__name__)

_ACCENT = colors.HexColor("#2E6BE6")
_GRID = colors.HexColor("#CBD6E8")
_HEADER_BG = colors.HexColor("#EDF3FF")
_META_GRAY = colors.HexColor("#6B7280")

_FONT_STATE: Optional[tuple] = None


def _register_fonts() -> tuple:
    """返回 (正文字体名, 粗体字体名)；进程内只注册一次。"""
    global _FONT_STATE
    if _FONT_STATE:
        return _FONT_STATE
    normal = bold = "STSong-Light"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except Exception:
        pass  # 已注册
    try:
        from app.core.config import get_settings
        path = str(getattr(get_settings(), "REPORT_PDF_FONT", "") or "").strip()
    except Exception:
        path = ""
    if not path and Path("C:/Windows/Fonts/msyh.ttc").exists():
        path = "C:/Windows/Fonts/msyh.ttc"
    if path and Path(path).exists():
        try:
            pdfmetrics.registerFont(TTFont("CPQReport", path, subfontIndex=0))
            normal = "CPQReport"
            bold_path = ""
            if path.replace("\\", "/").lower().endswith("msyh.ttc"):
                _bd = Path(path).with_name("msyhbd.ttc")
                if _bd.exists():
                    bold_path = str(_bd)
            if bold_path:
                pdfmetrics.registerFont(TTFont("CPQReport-Bold", bold_path, subfontIndex=0))
                bold = "CPQReport-Bold"
        except Exception:
            logger.warning("REPORT_PDF_FONT 注册失败，回退内置 CID 字体 path=%s", path, exc_info=True)
            normal = bold = "STSong-Light"
    pdfmetrics.registerFontFamily(normal, normal=normal, bold=bold, italic=normal, boldItalic=bold)
    _FONT_STATE = (normal, bold)
    return _FONT_STATE


def _visual_len(s: str) -> int:
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(s or ""))


def _inline(text: str) -> str:
    """行内 markdown → reportlab 段落标记：先转义再恢复 **加粗**。"""
    s = str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    return s


_TABLE_SEP_CHARS = set("|-: \u2014\u3000")


def _is_table_separator(row: str) -> bool:
    body = row.strip().strip("|")
    return bool(body) and set(row.strip()) <= _TABLE_SEP_CHARS


def _parse_markdown_blocks(text: str) -> list:
    """markdown 子集 → 块序列（heading/para/bullet/table/rule）。

    覆盖趋势分析答复的全部结构：# 标题、- 列表、| 表格（|---| 表头分隔）、**加粗**、
    --- 分隔线；其余按段落。宽松解析：不认识的行原样落段落，绝不抛错。
    """
    blocks: list = []
    lines = [ln.rstrip() for ln in str(text or "").replace("\r\n", "\n").split("\n")]
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if s.startswith("|") and s.endswith("|") and len(s) > 1:
            rows = []
            while i < len(lines):
                r = lines[i].strip()
                if not (r.startswith("|") and r.endswith("|") and len(r) > 1):
                    break
                if not _is_table_separator(r):
                    rows.append([c.strip() for c in r.strip("|").split("|")])
                i += 1
            if rows:
                blocks.append({"type": "table", "rows": rows})
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            blocks.append({"type": "heading", "level": min(len(m.group(1)), 4), "text": m.group(2).strip()})
        elif re.match(r"^[-*•]\s+", s):
            blocks.append({"type": "bullet", "text": re.sub(r"^[-*•]\s+", "", s)})
        elif re.match(r"^\d{1,3}[.、)]\s*", s) or re.match(r"^\d{1,3}[.、)]$", s):
            blocks.append({"type": "bullet", "text": s})
        elif re.match(r"^-{3,}$", s) or re.match(r"^\*{3,}$", s):
            blocks.append({"type": "rule"})
        else:
            blocks.append({"type": "para", "text": s})
        i += 1
    return blocks


def _col_widths(rows: list, avail: float) -> list:
    ncols = max(len(r) for r in rows)
    weights = []
    for c in range(ncols):
        w = max((_visual_len(r[c]) if c < len(r) else 0) for r in rows)
        weights.append(max(3, min(46, w)))
    total = sum(weights)
    return [max(1.2 * cm, avail * w / total) for w in weights]


def render_markdown_report_pdf(title: str, md_text: str, *, meta: Optional[dict] = None) -> bytes:
    """markdown 结论渲染成 A4 报告 PDF（页眉标题条 + meta 行 + 页脚页码）。"""
    normal, bold = _register_fonts()
    meta = meta or {}
    body = ParagraphStyle("body", fontName=normal, fontSize=9.5, leading=15.5,
                          wordWrap="CJK", spaceAfter=5, textColor=colors.HexColor("#1F2430"))
    bullet = ParagraphStyle("bullet", parent=body, leftIndent=12, firstLineIndent=0, spaceAfter=3)
    h1 = ParagraphStyle("h1", fontName=bold, fontSize=13.5, leading=19, spaceBefore=10,
                        spaceAfter=5, textColor=colors.HexColor("#111827"), wordWrap="CJK")
    h2 = ParagraphStyle("h2", fontName=bold, fontSize=11.5, leading=17, spaceBefore=8,
                        spaceAfter=4, textColor=colors.HexColor("#1F2937"), wordWrap="CJK")
    h3 = ParagraphStyle("h3", fontName=bold, fontSize=10.2, leading=15, spaceBefore=6,
                        spaceAfter=3, textColor=colors.HexColor("#374151"), wordWrap="CJK")
    cell = ParagraphStyle("cell", parent=body, fontSize=8.8, leading=13, spaceAfter=0)
    cell_head = ParagraphStyle("cell_head", parent=cell, fontName=bold)

    buf = io.BytesIO()
    margin = 1.9 * cm
    doc = SimpleDocTemplate(
        buf, pagesize=A4, title=str(title or "数据报告"),
        leftMargin=margin, rightMargin=margin, topMargin=1.7 * cm, bottomMargin=1.8 * cm)
    avail = A4[0] - 2 * margin

    story: list = []
    story.append(Paragraph(_inline(title or "数据报告"),
                           ParagraphStyle("title", fontName=bold, fontSize=17, leading=24,
                                          textColor=colors.HexColor("#111827"), wordWrap="CJK")))
    meta_bits = [str(v) for v in [meta.get("range"), meta.get("author"), meta.get("created_at")] if v]
    if meta_bits:
        story.append(Paragraph(" · ".join(re.sub(r"[&<>]", " ", b) for b in meta_bits),
                               ParagraphStyle("meta", fontName=normal, fontSize=8.5, leading=13,
                                              textColor=_META_GRAY, spaceBefore=3, wordWrap="CJK")))
    story.append(HRFlowable(width="100%", thickness=1.4, color=_ACCENT,
                            spaceBefore=6, spaceAfter=12))

    for blk in _parse_markdown_blocks(md_text):
        t = blk["type"]
        if t == "heading":
            story.append(Paragraph(_inline(blk["text"]), {1: h1, 2: h2}.get(blk["level"], h3)))
        elif t == "bullet":
            story.append(Paragraph(_inline(blk["text"]), bullet, bulletText="•"))
        elif t == "rule":
            story.append(HRFlowable(width="100%", thickness=0.6, color=_GRID,
                                    spaceBefore=4, spaceAfter=8))
        elif t == "table":
            rows = blk["rows"]
            ncols = max(len(r) for r in rows)
            norm = [r + [""] * (ncols - len(r)) for r in rows]
            data = [[Paragraph(_inline(c), cell_head if ri == 0 else cell)
                     for c in r] for ri, r in enumerate(norm)]
            tbl = Table(data, colWidths=_col_widths(norm, avail), repeatRows=1, hAlign="LEFT")
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
                ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFF")]),
            ]))
            story.append(tbl)
            story.append(Paragraph("", ParagraphStyle("gap", parent=body, fontSize=5, spaceAfter=0)))
        else:
            story.append(Paragraph(_inline(blk["text"]), body))

    def _footer(canv, _doc):
        canv.saveState()
        canv.setFont(normal, 8)
        canv.setFillColor(_META_GRAY)
        canv.drawCentredString(A4[0] / 2, 1.05 * cm, f"第 {canv.getPageNumber()} 页")
        canv.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


OFFICE_REPORTS_DIR = "office/reports"


def save_office_report(object_id: str, content: bytes) -> str:
    """落 office 中立桶并返回下载 URL（不进商机附件体系——趋势报告无商机上下文）。"""
    from app.services.storage_adapter import get_storage
    get_storage().save_scoped(OFFICE_REPORTS_DIR, object_id, content, ".pdf")
    return f"/api/office/reports/{object_id}/download"


def report_meta_now(author: str = "") -> dict:
    return {"created_at": f"生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "author": f"生成同事 {author}" if author else ""}
