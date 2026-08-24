"""SVG 上传安全清洗 —— 白名单式重写，防存储型 XSS。

风险面：SVG 支持 <script>、事件属性(on*)、<foreignObject>、外部资源引用，
直接在管理后台打开可触发存储型 XSS。本模块把上传内容解析为元素树后
按白名单重建：危险标签/属性一律丢弃，引用只允许内部锚点(#id)，
其余输出纯几何 + 表现属性，浏览器按 <img>/纹理加载时无可执行内容。

优先使用 defusedxml（防实体膨胀/XXE）；不可用时回退 stdlib ElementTree
（stdlib 不解析外部实体、遇到 DTD 实体声明直接抛错，同样安全，只是少了
超深嵌套防护）。
"""
import re
from typing import Optional, Tuple

try:
    from defusedxml.ElementTree import fromstring as _fromstring, tostring as _tostring
    _HAS_DEFUSEDXML = True
except ImportError:  # pragma: no cover
    from xml.etree.ElementTree import fromstring as _fromstring, tostring as _tostring  # type: ignore
    _HAS_DEFUSEDXML = False

# 允许的标签（Figma/Illustrator 常规导出子集；动画/交互/外部引用一律不给）
_ALLOWED_TAGS = {
    "svg", "g", "defs", "path", "rect", "circle", "ellipse", "line",
    "polyline", "polygon", "text", "tspan", "linearGradient", "radialGradient",
    "stop", "clipPath", "mask", "pattern", "marker", "use",
}

# 允许的属性（几何 + 表现；事件属性、style、外部引用不在此列，会被整体丢弃）
_ALLOWED_ATTRS = {
    # 根元素 / 坐标系
    "xmlns", "xmlns:xlink", "version", "viewBox", "width", "height",
    "id",
    "preserveAspectRatio", "baseProfile",
    # 几何
    "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "width", "height", "points", "d", "pathLength", "offset",
    "transform", "gradientTransform", "patternTransform",
    "gradientUnits", "patternUnits", "patternContentUnits",
    "maskUnits", "maskContentUnits", "clipPathUnits", "spreadMethod", "method",
    "textLength", "lengthAdjust",
    # 表现
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width",
    "stroke-opacity", "stroke-linecap", "stroke-linejoin", "stroke-dasharray",
    "stroke-dashoffset", "stroke-miterlimit", "opacity", "visibility", "display",
    "color", "stop-color", "stop-opacity", "clip-rule", "vector-effect",
    "shape-rendering", "font-size", "font-family", "font-weight", "font-style",
    "text-anchor", "dominant-baseline", "letter-spacing",
}

_ON_ATTR_RE = re.compile(r"^on", re.IGNORECASE)


def _repair_mojibake_id(s: str) -> str:
    """修复 id 双重编码乱码：部分本地 SVG 工具把 UTF-8 字节按 Latin-1 逐字节转义
    （如 '挂耳-左' 变成 '&#230;&#140;&#130;&#232;&#128;&#179;-&#229;&#183;&#166;'），
    或直接落成 CP1252 字面量（如 'æŒ¡ç‰‡'），解析后变成乱码字符。依次尝试
    Latin-1 / CP1252 两种还原；仅当重新编码能还原出含 CJK 的合法 UTF-8 时应用，
    ASCII 与正常文本原样返回。"""
    if not s or all(ord(ch) < 128 for ch in s):
        return s
    for enc in ("latin-1", "cp1252"):
        try:
            fixed = s.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if fixed == s:
            continue
        if any("\u4e00" <= ch <= "\u9fff" for ch in fixed):
            return fixed
    return s
_URL_REF_RE = re.compile(r"url\(\s*#([A-Za-z0-9_\-:]+)\s*\)")
_REFERENCE_ATTRS = {"clip-path", "mask", "filter", "marker-start", "marker-mid", "marker-end"}


def sanitize_svg(content: bytes) -> Tuple[str, Optional[list]]:
    """清洗 SVG 内容，返回 (清洗后的文本, viewBox 或 None)。

    输入必须是 UTF-8；解析/清洗失败抛 ValueError（调用方转 400）。
    """
    if not content:
        raise ValueError("空文件")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"仅支持 UTF-8 编码：{e}")
    try:
        root = _fromstring(text)
    except Exception as e:
        raise ValueError(f"SVG 解析失败（可能是非法 XML 或含 DTD 实体）：{e}")

    if (root.tag or "").rsplit("}", 1)[-1] != "svg":
        raise ValueError("根元素必须是 <svg>")

    view_box: Optional[list] = None
    vb = root.get("viewBox")
    if vb:
        parts = [float(v) for v in vb.replace(",", " ").split() if v.strip()]
        if len(parts) == 4:
            view_box = parts

    cleaned = _rebuild(root, is_root=True)
    out = _tostring(cleaned, encoding="unicode")
    return out, view_box


def _rebuild(el, is_root: bool = False):
    """白名单重建：返回新元素，或 None（该节点被丢弃）。"""
    tag = (el.tag or "").rsplit("}", 1)[-1] if isinstance(el.tag, str) else None
    if tag not in _ALLOWED_TAGS:
        return None
    import xml.etree.ElementTree as ET
    new = ET.Element(tag)
    for k, v in el.attrib.items():
        if k.startswith("{"):
            k = k.split("}", 1)[1]  # 去掉 namespace（xmlns:xlink 等）
        if k in ("xmlns", "xmlns:xlink") and not is_root:
            continue
        if _ON_ATTR_RE.match(k):
            continue
        if k in _REFERENCE_ATTRS:
            # 引用只允许内部锚点 url(#id)
            if v and _URL_REF_RE.fullmatch(v.strip()):
                new.set(k, _URL_REF_RE.fullmatch(v.strip()).group(0))
            continue
        if k not in _ALLOWED_ATTRS:
            continue
        # id 中文乱码自动修复（仅影响属性值，不影响几何/表现）
        if k == "id":
            v = _repair_mojibake_id(v)
        new.set(k, v)
    if is_root:
        new.set("xmlns", "http://www.w3.org/2000/svg")
        if "xmlns:xlink" in el.attrib:
            new.set("xmlns:xlink", "http://www.w3.org/1999/xlink")
    for child in el:
        rebuilt = _rebuild(child)
        if rebuilt is not None:
            new.append(rebuilt)
    # 空 defs/clipPath/mask 等容器没有意义，丢弃
    if not list(new) and tag in ("defs", "clipPath", "mask", "pattern", "marker"):
        return None
    return new
