"""ExcelParser region-key driven behavior tests."""
import io
import json

import openpyxl
import pandas as pd
import pytest
from unittest.mock import MagicMock

from app.engine.excel_parser import ExcelParser


def _parser(regions, rules=None):
    parser = ExcelParser(MagicMock())
    parser._parse_regions = regions
    parser._parse_field_rules = rules or []
    return parser


def _region(id, name, key, start, region_type="dynamic", sort=0, skip=0,
            end_keywords=""):
    return {
        "id": id,
        "name": name,
        "region_key": key,
        "region_type": region_type,
        "start_keywords": start,
        "end_keywords": end_keywords,
        "sort_order": sort,
        "enabled": True,
        "skip_header_rows": skip,
        "start_mode": "keyword",
        "start_config": None,
    }


def _df(values):
    return pd.DataFrame({0: values})


def test_locate_regions_no_end_keyword_uses_next_region_start():
    parser = _parser([
        _region(1, "Header", "header", "Header", "static", 0),
        _region(2, "L6", "l6", "L6", "dynamic", 1, 1),
        _region(3, "Keyparts", "kp", "Keyparts", "dynamic", 2, 1),
    ])
    bounds = parser._locate_regions(_df(["Header", "quote_date", "L6", "item", "Keyparts", "cpu"]))

    assert list(bounds) == ["header", "l6", "kp"]
    assert bounds["header"]["start_row"] == 0
    assert bounds["header"]["end_row"] == 2
    assert bounds["l6"]["start_row"] == 2
    assert bounds["l6"]["end_row"] == 4
    assert bounds["kp"]["start_row"] == 4
    assert bounds["kp"]["end_row"] == 6


def test_locate_regions_same_name_uses_region_key_not_overwrite():
    parser = _parser([
        _region(1, "Header", "header_main", "Header", "static", 0),
        _region(2, "Header", "header_extra", "Extra", "dynamic", 1),
    ])
    bounds = parser._locate_regions(_df(["Header", "quote_date", "Extra", "value"]))

    assert list(bounds) == ["header_main", "header_extra"]
    assert bounds["header_main"]["region_name"] == "Header"
    assert bounds["header_extra"]["region_name"] == "Header"
    assert bounds["header_main"]["start_row"] == 0
    assert bounds["header_extra"]["start_row"] == 2


def test_parse_binds_field_rule_by_region_id():
    parser = _parser(
        [
            _region(1, "Header", "header", "Header", "static", 0),
            _region(2, "L6", "l6", "L6", "dynamic", 1, 1),
            _region(3, "Keyparts", "kp", "Keyparts", "dynamic", 2, 1),
        ],
        [
            {
                "id": 1,
                "field_key": "model",
                "region_id": 2,
                "region": "",
                "source_type": "column",
                "source_config": {"col": "A"},
                "fallback_config": None,
                "enabled": True,
                "sort_order": 0,
            }
        ],
    )
    result = parser.parse(_df(["Header", "quote_date", "L6", "server-01", "Keyparts", "cpu"]))

    assert "l6" in result["dynamic_regions"]
    assert result["dynamic_regions"]["l6"][0]["model"] == "server-01"
    assert "kp" not in result["dynamic_regions"]


def test_preview_includes_region_bounds_even_without_field_rules():
    parser = _parser([
        _region(1, "Server", "server", "Server", "dynamic", 0),
    ])
    preview = parser.preview_parse(_df(["Server", "value", "end"]), max_row=10, max_col=5)

    assert "server" in preview["region_bounds"]
    assert preview["region_bounds"]["server"]["region_name"] == "Server"


def test_api_create_region_uses_single_create(monkeypatch):
    from app.api import rules as rules_mod

    fake = MagicMock()
    fake.add_parse_region.return_value = 42
    monkeypatch.setattr(rules_mod, "rules_repo", fake)

    payload = {"name": "Server", "region_type": "dynamic", "start_keywords": "Server"}
    assert rules_mod.save_parse_regions(payload) == {"status": "success", "id": 42}
    fake.add_parse_region.assert_called_once_with(payload)


def test_api_create_field_rule_uses_single_create(monkeypatch):
    from app.api import rules as rules_mod

    fake = MagicMock()
    fake.add_parse_field_rule.return_value = 9
    monkeypatch.setattr(rules_mod, "rules_repo", fake)

    payload = {"field_key": "model", "region_id": 2, "source_type": "column", "source_config": {"col": "A"}}
    assert rules_mod.save_parse_field_rules(payload) == {"status": "success", "id": 9}
    fake.add_parse_field_rule.assert_called_once_with(payload)

def test_keyword_extract_applies_value_pattern():
    parser = _parser([])
    df = pd.DataFrame({0: ["Model Name&Required quantity"], 1: ["ZS220 V2(1pcs)"]})
    value, _ = parser._extract_by_keyword(df, {
        "keywords": ["Model Name&Required quantity"],
        "value_offset": 1,
        "value_pattern": "^([^\\(]+)",
    })
    assert value == "ZS220 V2"


def test_keyword_extract_keeps_raw_value_without_pattern():
    parser = _parser([])
    df = pd.DataFrame({0: ["Model Name&Required quantity"], 1: ["ZS220 V2(1pcs)"]})
    value, _ = parser._extract_by_keyword(df, {
        "keywords": ["Model Name&Required quantity"],
        "value_offset": 1,
    })
    assert value == "ZS220 V2(1pcs)"


def test_locate_regions_end_keyword_clamped_at_next_region_start():
    """结束关键词命中行越过下一区域起点时，收口钳在下一区域起点，两区域不重叠。"""
    parser = _parser([
        _region(1, "L6", "l6", "L6", "dynamic", 0, end_keywords="cpu"),
        _region(2, "KP", "kp", "KP", "dynamic", 1),
    ])
    bounds = parser._locate_regions(_df(["L6", "chassis", "KP", "cpu"]))

    assert bounds["l6"]["end_row"] == 2  # 关键词命中行3越过KP起点2，钳在2
    assert bounds["kp"]["start_row"] == 2


def test_parse_does_not_swallow_sheet_when_skip_exhausts_region():
    """区域起点行 + skip_header_rows 恰好耗尽区域时，不得把剩余整个 sheet 吞进该区域。"""
    parser = _parser(
        [
            _region(1, "L6", "l6", "L6", "dynamic", 0, skip=1),
            _region(2, "KP", "kp", "KP", "dynamic", 1),
        ],
        [
            {"id": 1, "field_key": "chassis", "region_id": 1, "region": "",
             "source_type": "column", "source_config": {"col": "A"},
             "fallback_config": None, "enabled": True, "sort_order": 0},
            {"id": 2, "field_key": "model", "region_id": 2, "region": "",
             "source_type": "column", "source_config": {"col": "A"},
             "fallback_config": None, "enabled": True, "sort_order": 0},
        ],
    )
    df = pd.DataFrame({0: ["L6-row", "", "cpu-01", "cpu-02"], 1: ["", "KP", "", ""]})
    result = parser.parse(df)

    # L6 区域 = 行0，skip=1 后为空 → 不产生行，也绝不吞并 KP 区
    assert "l6" not in result["dynamic_regions"]
    assert [it["model"] for it in result["dynamic_regions"]["kp"]] == ["cpu-01", "cpu-02"]


def test_locate_regions_not_found_bounds_negative_pair():
    """未命中的区域边界是 (-1, -1) 而非 (-1, 下一区域起点)——下游行归属不再把
    sheet 头部行错记到不存在的区域名下。"""
    parser = _parser([
        _region(1, "L6", "l6", "L6", "dynamic", 0),
        _region(2, "Ghost", "ghost", "不存在的标记", "dynamic", 1),
    ])
    bounds = parser._locate_regions(_df(["L6", "a", "b"]))

    assert bounds["ghost"]["start_row"] == -1
    assert bounds["ghost"]["end_row"] == -1
    assert bounds["l6"]["start_row"] == 0
    assert bounds["l6"]["end_row"] == 3


def test_preview_exhausted_region_does_not_mark_following_rows():
    """耗尽区域（skip 恰好用完）解析产出零行，热力图也不得把后续行标成该区域数据。"""
    parser = _parser(
        [
            _region(1, "L6", "l6", "L6", "dynamic", 0, 1),
            _region(2, "KP", "kp", "KP", "dynamic", 1),
        ],
        [
            {"id": 1, "field_key": "chassis", "region_id": 1, "region": "",
             "source_type": "column", "source_config": {"col": "A"},
             "fallback_config": None, "enabled": True, "sort_order": 0},
            {"id": 2, "field_key": "model", "region_id": 2, "region": "",
             "source_type": "column", "source_config": {"col": "A"},
             "fallback_config": None, "enabled": True, "sort_order": 0},
        ],
    )
    df = pd.DataFrame({0: ["L6", "KP", "cpu"]})  # L6 区=行0，skip=1 → 耗尽

    preview = parser.preview_parse(df, max_row=10, max_col=5)
    l6_rows = {m["row"] for m in preview["cell_marks"] if m["type"] == "l6_region"}
    assert l6_rows == {0}  # 只有起点标记，KP 行不得被标成 L6 数据


def test_locate_regions_end_keyword_first_match_among_candidates_wins():
    """end_keywords 多候选（中英文模板共存）时，任一关键词命中即结束区域。

    历史回归：KP 区域 end_keywords 曾只配中文「售后服务」导致英文 Warranty 模板
    的质保段被吞进 KP；配回双候选后两套模板都必须在各自标记行收口。
    """
    parser = _parser([
        _region(1, "KP", "kp", "KP", "dynamic", 0,
                end_keywords="Warranty,售后服务"),
    ])
    df = pd.DataFrame({
        0: ["KP", "cpu", "Warranty", "x"],
        1: ["", "100", "", ""],
    })
    bounds = parser._locate_regions(df)
    assert bounds["kp"]["start_row"] == 0
    assert bounds["kp"]["end_row"] == 2  # 停在 Warranty 行，质保行不进 KP


def _field_rule(id, key, region_id, col, header_keywords=None):
    return {
        "id": id,
        "field_key": key,
        "region_id": region_id,
        "region": "",
        "source_type": "column",
        "source_config": {"col": col, "header_keywords": header_keywords or []},
        "fallback_config": None,
        "enabled": True,
        "sort_order": 0,
    }


def test_column_rule_header_keywords_follows_shifted_layout():
    """配置了 header_keywords 的列规则按表头定位，两个偏移不同的 sheet 都取对列。"""
    rules = [
        _field_rule(1, "category", 1, "E", ["规格型号"]),
        _field_rule(2, "model", 1, "F", ["产品描述"]),
        _field_rule(3, "qty", 1, "G", ["数量"]),
    ]
    parser = _parser([_region(1, "KP", "kp", "KP", "dynamic", 0)], rules)

    # 布局A：表头从 A 列开始；布局B：表头前多一个空列（客户模板两种变体）
    df_a = pd.DataFrame({
        0: ["编号", "KP", ""],
        1: ["产品名称", "", ""],
        2: ["规格型号", "", "CPU"],
        3: ["产品描述", "", "Xeon 6530"],
        4: ["数量", "", "2"],
    })
    df_b = pd.DataFrame({
        0: ["", "", "KP", ""],
        1: ["编号", "", "", ""],
        2: ["产品名称", "", "", ""],
        3: ["规格型号", "", "", "CPU"],
        4: ["产品描述", "", "", "Xeon 6530"],
        5: ["数量", "", "", "2"],
    })

    for df in (df_a, df_b):
        result = parser.parse(df)
        assert [{k: v for k, v in it.items() if not k.startswith('_')}
                for it in result["dynamic_regions"]["kp"] if it.get("category")] == [
            {"category": "CPU", "model": "Xeon 6530", "qty": "2"}
        ]


def test_column_rule_header_keywords_falls_back_to_fixed_col():
    """表头关键词找不到时退回固定列字母，行为与未配置 header_keywords 一致。"""
    rules = [
        _field_rule(1, "model", 1, "A", ["不存在的表头"]),
        _field_rule(2, "qty", 1, "B"),
    ]
    parser = _parser([_region(1, "KP", "kp", "KP", "dynamic", 0)], rules)
    df = pd.DataFrame({0: ["KP", "m-01"], 1: ["", "7"]})

    assert parser._resolve_header_columns(df) == {}
    items = parser.parse(df)["dynamic_regions"]["kp"]
    assert {k: v for k, v in items[-1].items() if not k.startswith('_')} == {"model": "m-01", "qty": "7"}


def test_locate_regions_region_ends_override_first_region():
    """会话收口补丁作用于任意区域（含首个）不再崩溃。

    历史回归：override 块曾在 region_key 赋值前引用它——带 region_ends 的
    定位在首个区域必抛 UnboundLocalError，后续区域还会错用上一区域的键。
    """
    parser = _parser([
        _region(1, "L6", "l6", "L6", "dynamic", 0),
        _region(2, "KP", "kp", "KP", "dynamic", 1),
    ])
    df = _df(["L6", "noise", "KP", "cpu"])
    bounds = parser._locate_regions(df, region_ends={"l6": 1})

    assert bounds["l6"]["end_row"] == 1  # 收口补丁生效（默认会扩到 KP 起点 2）
    assert bounds["kp"]["start_row"] == 2


def test_locate_regions_region_ends_ignored_when_not_past_start():
    parser = _parser([
        _region(1, "L6", "l6", "L6", "dynamic", 0),
        _region(2, "KP", "kp", "KP", "dynamic", 1),
    ])
    df = _df(["L6", "noise", "KP", "cpu"])
    bounds = parser._locate_regions(df, region_ends={"kp": 2})

    assert bounds["kp"]["end_row"] == 4  # 收口值不大于自身起点 → 忽略，退回表尾


def test_parse_applies_region_ends_override_end_to_end():
    """弹窗「收口到区域」主链路：parse(overrides=region_ends) 不崩溃且生效。"""
    parser = _parser(
        [
            _region(1, "L6", "l6", "L6", "dynamic", 0, 1),
            _region(2, "KP", "kp", "KP", "dynamic", 1, 1),
        ],
        [
            {"id": 1, "field_key": "chassis", "region_id": 1, "region": "",
             "source_type": "column", "source_config": {"col": "A"},
             "fallback_config": None, "enabled": True, "sort_order": 0},
            {"id": 2, "field_key": "model", "region_id": 2, "region": "",
             "source_type": "column", "source_config": {"col": "A"},
             "fallback_config": None, "enabled": True, "sort_order": 0},
        ],
    )
    df = pd.DataFrame({0: ["L6", "noise", "KP", "cpu"]})
    result = parser.parse(df, overrides={"region_ends": {"l6": 1}})

    assert "l6" not in result["dynamic_regions"]  # 噪声行被收口切走
    assert [it["model"] for it in result["dynamic_regions"]["kp"]] == ["cpu"]


def test_find_region_row_short_latin_keyword_not_hijacked_by_substring():
    """短拉丁关键词（L6/KP）不得因子串匹配命中 ML600 之类型号，劫持区域起点。"""
    parser = _parser([
        _region(1, "L6", "l6", "L6", "dynamic", 0),
    ])
    df = pd.DataFrame({0: ["ML600 chassis note", "L6", "x"]})

    assert parser._locate_regions(df)["l6"]["start_row"] == 1


def test_find_region_row_chinese_keyword_substring_round_still_matches():
    """中文关键词无词边界概念，子串轮仍须兜底（「…含售后服务条款」要能收口）。"""
    parser = _parser([
        _region(1, "KP", "kp", "KP", "dynamic", 0, end_keywords="售后服务"),
    ])
    df = pd.DataFrame({0: ["KP", "cpu", "整机含售后服务条款", "x"]})

    assert parser._locate_regions(df)["kp"]["end_row"] == 2


def test_numeric_cells_rendered_without_float_artifacts():
    """数值格整值化：整数 2 → "2" 而非 "2.0"；浮点尾差收敛（…9996 → 24521）。"""
    rules = [
        {"id": 1, "field_key": "qty", "region_id": 1, "region": "",
         "source_type": "column", "source_config": {"col": "A"},
         "fallback_config": None, "enabled": True, "sort_order": 0},
    ]
    parser = _parser([_region(1, "KP", "kp", "KP", "dynamic", 0, 1)], rules)
    df = pd.DataFrame({0: ["KP", 2, 0.5, 24520.999999999996]})

    items = parser.parse(df)["dynamic_regions"]["kp"]
    assert [it["qty"] for it in items] == ["2", "0.5", "24521"]


def test_col_binds_invalid_letter_ignored():
    """非法列字母（"1A"）的会话绑定被忽略，退回规则固定列，不产生乱索引。"""
    rules = [
        {"id": 1, "field_key": "model", "region_id": 1, "region": "",
         "source_type": "column", "source_config": {"col": "A"},
         "fallback_config": None, "enabled": True, "sort_order": 0},
    ]
    parser = _parser([_region(1, "KP", "kp", "KP", "dynamic", 0)], rules)
    df = pd.DataFrame({0: ["KP", "m-01"], 1: ["", "7"]})

    result = parser.parse(df, overrides={"col_binds": {"model": "1A"}})
    assert result["dynamic_regions"]["kp"][-1]["model"] == "m-01"


def test_keyword_extract_scans_beyond_row_10():
    """静态字段关键词扫描放宽到 30 行：第 13 行的标签也要能取到值。"""
    parser = _parser([])
    df = pd.DataFrame({0: [""] * 12 + ["客户名称"], 1: [""] * 12 + ["ACME"]})

    value, _ = parser._extract_by_keyword(df, {"keywords": ["客户名称"], "value_offset": 1})
    assert value == "ACME"


class _StatefulRepo:
    """写入即生效的假仓库：译文核验要真读到写回后的新规则。"""

    def __init__(self, regions, rules):
        self.regions = [dict(r) for r in regions]
        self.rules = [dict(r) for r in rules]
        self.updates = []
        self.stale_marked = None

    def get_parse_regions(self, tid=None):
        return [dict(r) for r in self.regions]

    def get_parse_field_rules(self, tid=None):
        return [dict(r) for r in self.rules]

    def update_parse_region(self, rid, data):
        self.updates.append((rid, dict(data)))
        for r in self.regions:
            if r["id"] == rid:
                r.update(data)

    def update_parse_field_rule(self, rid, data):
        for r in self.rules:
            if r["id"] == rid:
                r.update(data)

    def mark_template_selfcheck_stale(self, tid):
        self.stale_marked = tid

    def clone_parse_template(self, tid, name):
        return 9

    def update_parse_template(self, tid, data):
        if not hasattr(self, "template_updates"):
            self.template_updates = []
        self.template_updates.append((tid, dict(data)))


def _svc_with(repo):
    from app.services.parse_template_service import ParseTemplateService
    svc = ParseTemplateService.__new__(ParseTemplateService)
    svc.repo = repo
    return svc


def _col_rule(id, field, region_id, col="A"):
    return {"id": id, "field_key": field, "region_id": region_id, "region": "",
            "source_type": "column", "source_config": {"col": col},
            "fallback_config": None, "enabled": True, "sort_order": 0}


def test_kp_marker_row_with_header_words_excluded():
    """ZHY 族客户表：KP 标记行独占一行且 A 列带编号（'2|Keypats|Component Description|单价'），
    行内提取不出类别——排除词必须按「行内任一已提取字段值整词」命中把表头残留剔掉。"""
    region = _region(3, "Keyparts", "kp", "Keyparts", "dynamic", 2, 0,
                     end_keywords="Warranty")
    region["exclude_keywords"] = "Keypats,Component Description,单价,总价"
    parser = _parser(
        [region],
        [_col_rule(31, "kp_category", 3, "D"),
         _col_rule(32, "kp_model", 3, "E"),
         _col_rule(33, "kp_price", 3, "G")],
    )
    df = pd.DataFrame([
        ["2", "Keypats", None, "Component Description", None, None, "单价"],
        ["2-1", None, None, "CPU", "AMD EPYC 9455", 2, 24521],
        ["2-2", None, None, "Memory", "64G DDR5", 2, 18000],
        ["3", "Warranty", None, None, None, None, None],
    ])
    result = parser.parse(df)
    kp = result["dynamic_regions"]["kp"]
    assert [r["kp_model"] for r in kp] == ["AMD EPYC 9455", "64G DDR5"]


def test_rules_write_endpoints_gated_by_settings_perm(monkeypatch):
    """设置页结构写操作的 page.settings.excel 门禁：无权限 403，有权限放行。"""
    from app.api import deps
    import app.core.config as cfg

    class S:
        AUTH_ENABLED = True

    monkeypatch.setattr(cfg, "get_settings", lambda: S())
    checker = deps.require_perms("page.settings.excel")
    user = {"user_id": "u1", "role": "cost"}

    monkeypatch.setattr(deps, "_user_permissions", lambda u: ["page.opportunities_all"])
    with pytest.raises(Exception) as ei:
        checker(user)
    assert getattr(ei.value, "status_code", None) == 403

    monkeypatch.setattr(deps, "_user_permissions", lambda u: ["page.settings.excel"])
    assert checker(user) is user


def test_run_selfcheck_flags_rule_derived_baseline(monkeypatch):
    """规则自证基线（补丁/回填烘焙）自检失败时，problems 首条注明基线来源提示。"""
    svc = _svc_with(MagicMock())
    svc.repo.get_parse_template.return_value = {
        "id": 1, "sample_file_key": "k", "has_expected": True}
    svc.storage = MagicMock()

    wb = openpyxl.Workbook()
    wb.active.append(["KP"])
    wb.active.append(["old"])
    buf = io.BytesIO()
    wb.save(buf)
    svc.storage.read_bytes.return_value = buf.getvalue()

    monkeypatch.setattr(svc, "_load_template_raw", lambda tid, col: json.dumps({
        "static_fields": {},
        "dynamic_regions": {"kp": [{"model": "new"}]},
        "_provenance": {"source": "user_confirmed"},
    }))

    detail = svc.run_selfcheck(1)
    assert detail["ok"] is False
    assert detail["problems"] and "规则自证" in detail["problems"][0]