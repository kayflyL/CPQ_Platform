"""服务器可视化图纸：SVG 清洗 + 区域标注校验 单元测试。"""
import pytest

from app.utils.svg_sanitizer import sanitize_svg
from app.api.server_catalog import _normalize_regions, _normalize_view_box


def test_sanitize_keeps_geometry_and_viewbox():
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 411 739" width="411" height="739">'
           b'<rect x="10" y="20" width="30" height="40" fill="#AAA"/>'
           b'<path d="M0 0L1 1" stroke="black"/></svg>')
    out, vb = sanitize_svg(svg)
    assert vb == [0, 0, 411, 739]
    assert 'viewBox="0 0 411 739"' in out
    assert "<rect" in out and "<path" in out


def test_sanitize_strips_script_and_handlers():
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           b'<script>alert(1)</script>'
           b'<rect onload="alert(2)" x="0" y="0" width="10" height="10"/>'
           b'<circle onclick="evil()" cx="5" cy="5" r="2"/></svg>')
    out, _ = sanitize_svg(svg)
    assert "script" not in out.lower()
    assert "onload" not in out.lower() and "onclick" not in out.lower()
    assert "alert" not in out


def test_sanitize_drops_foreignobject_and_external_hrefs():
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
           b'xmlns:xlink="http://www.w3.org/1999/xlink">'
           b'<foreignObject><div>hi</div></foreignObject>'
           b'<use xlink:href="https://evil.example/x.svg"/>'
           b'<image xlink:href="https://evil.example/x.png"/>'
           b'<rect x="0" y="0" width="10" height="10"/></svg>')
    out, _ = sanitize_svg(svg)
    assert "foreignObject" not in out and "foreignobject" not in out.lower()
    assert "https://" not in out
    assert "<rect" in out


def test_sanitize_keeps_internal_refs():
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           b'<defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/></linearGradient></defs>'
           b'<rect x="0" y="0" width="10" height="10" fill="url(#g)"/></svg>')
    out, _ = sanitize_svg(svg)
    assert "linearGradient" in out
    assert "url(#g)" in out


def test_sanitize_rejects_non_svg_root():
    with pytest.raises(ValueError):
        sanitize_svg(b"<html><body>x</body></html>")


def test_sanitize_rejects_bad_xml():
    with pytest.raises(ValueError):
        sanitize_svg(b"<svg><unclosed></svg>")


def test_normalize_regions_valid():
    rs = _normalize_regions([
        {"uid": "a", "name": "盘位", "region_type": "bays",
         "x": 10, "y": 20, "width": 100, "height": 50, "remark": "x"}
    ])
    assert rs[0]["name"] == "盘位" and rs[0]["region_type"] == "bays"
    assert _normalize_regions(None) == []


def test_normalize_regions_rejects_bad():
    with pytest.raises(ValueError):
        _normalize_regions([{"x": 0, "y": 0, "width": 1, "height": 1}])
    with pytest.raises(ValueError):
        _normalize_regions([{"name": "a", "region_type": "nope",
                             "x": 0, "y": 0, "width": 1, "height": 1}])
    with pytest.raises(ValueError):
        _normalize_regions([{"name": "a", "region_type": "io",
                             "x": 0, "y": 0, "width": 0, "height": 1}])


def test_normalize_viewbox():
    assert _normalize_view_box(None) is None
    assert _normalize_view_box([0, 0, 411, 739]) == [0, 0, 411, 739]
    with pytest.raises(ValueError):
        _normalize_view_box([0, 0, -1, 5])
