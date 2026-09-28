# -*- coding: utf-8 -*-
"""解析模板服务：标准文件生成 / 自检回归 / 补丁存回翻译 / 另存新模板。

- 补丁执行在引擎层（excel_parser），这里只做「模板资产」：标准文件（可下发）、
  样例+期望快照（自检基线）、规则语义翻译。
- 模板归属在使用位置绑定（rules.parse_scope_bindings）：哪个入口用哪套模板在
  设置页配置，上传链路按 scope 取绑定，不做文件内容猜测、不在前端选。
- 全确定性，无 LLM/AI 参与（用户定调：加了 AI 会拖慢速度）。
- 规格即单一事实源：同一份 FANGANBU_SPEC 生成标准文件、自检样例与期望快照。
"""
import io
import json
import logging
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.repository.rules_repo import RulesRepository
from app.services.storage_adapter import get_storage

logger = logging.getLogger(__name__)

THIN = Side(style="thin", color="B7C0D4")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
FILL_EDIT = PatternFill("solid", fgColor="F4F7FD")
FILL_BANNER = PatternFill("solid", fgColor="E7EDF8")
GRAY_FONT = Font(color="9AA6BC", italic=True)
BOLD = Font(bold=True)
HEAD_FONT = Font(bold=True, size=11)
CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)

# ─────────────────────────────────────────────────────────────────
# 标准文件规格（LLW 桃红版式，单一事实源：布局 + 样例数据 + 期望）
# ─────────────────────────────────────────────────────────────────

# 使用位置注册表：哪些入口用解析，由后端定死；新入口在此登记，设置页自动出现绑定行
PARSE_SCOPES = [
    {"key": "cost_sheet_upload", "label": "成本核算 · 上传解析"},
]

# 布局（1-based 行号）
_MODEL_ROW = 1        # A=机型名
_INFO_ROW = 2         # B=Project Name, D=项目名(填写), E=Description, H=Sales
_MODEL_QTY_ROW = 3    # B=Model Name&Required quantity, D=机型(npcs)(填写), H=FAE
_DESC_ROW = 4         # B=PRODUCT SPEC SUPPORT, E=整机描述(填写)
_L6_MARKER = 5        # 1 | L6 | Catalogue | Configuration Description | Quantity | Quotation | Note（标记行兼表头）
_L6_FILL_N = 5        # L6 数据行数
_KP_MARKER = 11       # 2 | Keypats | (E)Component Description | (G)单价 | (H)总价（标记行兼表头）
_KP_FILL_N = 4        # KP 数据行数
_WAR_MARKER = 16      # 3 | Warranty | After-sales service description
_WAR_ROWS_N = 2
_TOTAL = 19

# 灰字示例行内容（引擎按「示例」标记自动跳过）
_L6_EXAMPLE_ROW = {"B": "示例", "C": "L6", "D": "Front backplane", "E": "12*3.5 SATA/SAS", "F": 1}
_KP_EXAMPLE_ROW = {"B": "示例", "C": "KP", "D": "CPU", "E": "AMD EPYC 9455", "F": 2, "G": 21500}

# 自检样例的填写内容（期望快照由同一份数据推导）
_SAMPLE_STATIC = {
    "project": "XX银行核心系统扩容",
    "server_model": "5308R",
    "sales": "张三",
    "fae": "李四",
    "description": "2U机架服务器，双路EPYC，整机描述示例",
}
_SAMPLE_L6 = [
    {"l6_chassis": "Riser卡", "spec": "x16 Riser", "qty": 2},
    {"l6_chassis": "电源", "spec": "2000W PSU", "qty": 2},
    {"l6_chassis": "风扇", "spec": "高性能风扇模组", "qty": 4},
]
_SAMPLE_KP = [
    {"kp_category": "CPU", "kp_model": "AMD EPYC 9455", "qty": 2, "kp_price": 21500},
    {"kp_category": "Memory", "kp_model": "64G DDR5", "qty": 8, "kp_price": 2100},
    {"kp_category": "SSD", "kp_model": "3.84T NVMe", "qty": 4, "kp_price": 4600},
    {"kp_category": "NIC", "kp_model": "双口25G", "qty": 2, "kp_price": 1300},
]
_SAMPLE_WAR = [
    {"part_name": "L6", "description": "整机三年上门质保"},
    {"part_name": "KP", "description": "配件三年保换"},
]

_GUIDE_LINES = [
    "· 只在浅色填写格里填内容，不要插入/删除列，不要改区块标题行（1 L6 / 2 Keypats / 3 Warranty）",
    "· 行数不够直接插入行即可——系统按区块关键词定位，不数行号",
    "· L6 区填：部件名 + 规格描述 + 数量；Keypats 区填：类别 + 型号描述 + 数量 + 单价",
    "· 单价列选填：只报配置不报价时整列留空",
    "· 灰字示例行照着填，系统会自动跳过，不要删",
    "· 多个配置：复制本 sheet 改名 CFG2、CFG3…每个 sheet 一个配置",
    "· 填完整份文件回传即可，无需改名",
]


def _cell(ws, row, col, value, font=None, fill=None, align=None, border=True):
    c = ws.cell(row=row, column=col, value=value)
    c.font = font or Font()
    if fill:
        c.fill = fill
    c.alignment = align or LEFT
    if border:
        c.border = BORDER
    return c


def build_std_workbook(sample: bool = False) -> Workbook:
    """构建标准配置表工作簿（LLW 桃红版式）；sample=True 时填入自检样例数据。

    版式特征：L6/Keypats/Warranty 标记行兼表头（C 列标记词 + 右侧表头词），
    静态区 = 机型行 / Project Name 行 / Model Name&Required quantity 行 / PRODUCT SPEC SUPPORT 行。
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "配置表"

    widths = {"A": 13, "B": 26, "C": 10, "D": 30, "E": 34, "F": 9, "G": 12, "H": 10, "I": 10}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    # ── 静态区（r1-r4）──
    _cell(ws, _MODEL_ROW, 1, _SAMPLE_STATIC["server_model"] if sample else None, font=BOLD)
    _cell(ws, _INFO_ROW, 2, "Project Name", font=BOLD)
    _cell(ws, _INFO_ROW, 4, _SAMPLE_STATIC["project"] if sample else None, fill=FILL_EDIT)
    _cell(ws, _INFO_ROW, 5, "Description", font=BOLD)
    _cell(ws, _INFO_ROW, 8, "Sales", font=BOLD)
    _cell(ws, _MODEL_QTY_ROW, 2, "Model Name&Required quantity", font=BOLD)
    _cell(ws, _MODEL_QTY_ROW, 4, f"{_SAMPLE_STATIC['server_model']}(1pcs)" if sample else None, fill=FILL_EDIT)
    _cell(ws, _MODEL_QTY_ROW, 8, "FAE", font=BOLD)
    _cell(ws, _DESC_ROW, 2, "PRODUCT SPEC SUPPORT", font=BOLD)
    _cell(ws, _DESC_ROW, 5, _SAMPLE_STATIC["description"] if sample else None, fill=FILL_EDIT)
    for r in (_MODEL_ROW, _INFO_ROW, _MODEL_QTY_ROW, _DESC_ROW):
        for c in range(1, 10):
            ws.cell(r, c).border = BORDER

    # ── L6 标记行（兼表头）+ 数据行 ──
    _cell(ws, _L6_MARKER, 1, "1", font=BOLD, fill=FILL_BANNER, align=CENTER)
    _cell(ws, _L6_MARKER, 2, "L6", font=BOLD, fill=FILL_BANNER, align=CENTER)
    _cell(ws, _L6_MARKER, 4, "Catalogue", font=HEAD_FONT, fill=FILL_BANNER, align=CENTER)
    _cell(ws, _L6_MARKER, 5, "Configuration Description", font=HEAD_FONT, fill=FILL_BANNER, align=CENTER)
    _cell(ws, _L6_MARKER, 6, "Quantity", font=HEAD_FONT, fill=FILL_BANNER, align=CENTER)
    _cell(ws, _L6_MARKER, 8, "Quotation", font=BOLD, fill=FILL_BANNER, align=CENTER)
    _cell(ws, _L6_MARKER, 9, "Note", font=BOLD, fill=FILL_BANNER, align=CENTER)
    for c in range(1, 10):
        ws.cell(_L6_MARKER, c).border = BORDER
    for i in range(_L6_FILL_N):
        r = _L6_MARKER + 1 + i
        _cell(ws, r, 1, f"1-{i + 1}", font=BOLD, align=CENTER)
        _cell(ws, r, 2, "L6", align=CENTER)
        for c in (4, 5, 6):
            _cell(ws, r, c, None, fill=FILL_EDIT)
        for c in (3, 7, 8, 9):
            _cell(ws, r, c, None)
        if sample and i < len(_SAMPLE_L6):
            row = _SAMPLE_L6[i]
            ws.cell(r, 4, row["l6_chassis"])
            ws.cell(r, 5, row["spec"])
            ws.cell(r, 6, row["qty"])

    # ── Keypats 标记行（兼表头）+ 数据行 ──
    _cell(ws, _KP_MARKER, 1, "2", font=BOLD, fill=FILL_BANNER, align=CENTER)
    _cell(ws, _KP_MARKER, 2, "Keypats", font=BOLD, fill=FILL_BANNER, align=CENTER)
    _cell(ws, _KP_MARKER, 5, "Component Description", font=HEAD_FONT, fill=FILL_BANNER, align=CENTER)
    _cell(ws, _KP_MARKER, 7, "单价", font=HEAD_FONT, fill=FILL_BANNER, align=CENTER)
    _cell(ws, _KP_MARKER, 8, "总价", font=HEAD_FONT, fill=FILL_BANNER, align=CENTER)
    for c in range(1, 10):
        ws.cell(_KP_MARKER, c).border = BORDER
    for i in range(_KP_FILL_N):
        r = _KP_MARKER + 1 + i
        _cell(ws, r, 1, f"2-{i + 1}", font=BOLD, align=CENTER)
        _cell(ws, r, 2, "KP", align=CENTER)
        for c in (4, 5, 6, 7):
            _cell(ws, r, c, None, fill=FILL_EDIT)
        for c in (3, 8, 9):
            _cell(ws, r, c, None)
        if sample and i < len(_SAMPLE_KP):
            row = _SAMPLE_KP[i]
            ws.cell(r, 4, row["kp_category"])
            ws.cell(r, 5, row["kp_model"])
            ws.cell(r, 6, row["qty"])
            ws.cell(r, 7, row["kp_price"])

    # ── Warranty 标记行 + 数据行 ──
    _cell(ws, _WAR_MARKER, 1, "3", font=BOLD, fill=FILL_BANNER, align=CENTER)
    _cell(ws, _WAR_MARKER, 2, "Warranty", font=BOLD, fill=FILL_BANNER, align=CENTER)
    _cell(ws, _WAR_MARKER, 4, "After-sales service description", font=HEAD_FONT)
    for c in range(1, 10):
        ws.cell(_WAR_MARKER, c).border = BORDER
    for i in range(_WAR_ROWS_N):
        r = _WAR_MARKER + 1 + i
        _cell(ws, r, 1, f"3-{i + 1}", font=BOLD, align=CENTER)
        _cell(ws, r, 2, "L6" if i == 0 else "KP", align=CENTER)
        _cell(ws, r, 3, None)
        _cell(ws, r, 4, _SAMPLE_WAR[i]["description"] if sample else None, fill=FILL_EDIT)
        for c in range(5, 10):
            _cell(ws, r, c, None)

    # ── Total 行 ──
    _cell(ws, _TOTAL, 1, "Total Price", font=BOLD, fill=FILL_BANNER, align=CENTER)
    _cell(ws, _TOTAL, 4, None, fill=FILL_EDIT)
    for c in range(1, 10):
        ws.cell(_TOTAL, c).border = BORDER

    # ── 填写说明 sheet ──
    doc = wb.create_sheet("填写说明")
    doc.column_dimensions["A"].width = 100
    doc.cell(1, 1, "填写说明").font = Font(bold=True, size=13)
    for i, line in enumerate(_GUIDE_LINES, start=3):
        doc.cell(i, 1, line)

    return wb


def std_expected_snapshot() -> dict:
    """期望解析快照（与样例填写数据同源推导；行号为 0-based，与引擎 _locate_regions 对齐）。"""
    def _s(rows):
        return [{k: str(v) for k, v in row.items()} for row in rows]
    return {
        "static_fields": {
            "server_model": _SAMPLE_STATIC["server_model"],
            "description": _SAMPLE_STATIC["description"],
        },
        "dynamic_regions": {
            "l6": _s(_SAMPLE_L6),
            "kp": _s(_SAMPLE_KP),
        },
        "region_bounds": {
            "l6": {"start_row": _L6_MARKER - 1, "end_row": _KP_MARKER - 1},
            "kp": {"start_row": _KP_MARKER - 1, "end_row": _WAR_MARKER - 1},
        },
    }


def workbook_bytes(wb: Workbook) -> bytes:
    """序列化工作簿。"""
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────
# 服务
# ─────────────────────────────────────────────────────────────────

class ParseTemplateService:
    def __init__(self, rules_repo: RulesRepository = None):
        self.repo = rules_repo or RulesRepository()
        self.storage = get_storage()

    # ── 模板裁决（上传链路与设置页预览共用）──

    def resolve_scope_template(self, scope_key: str | None,
                               template_id: int | None = None) -> dict:
        """裁决优先级：显式 template_id（存在且启用）> scope 绑定（存在且启用）> 通用兜底。

        显式 id 已删除/停用时落兜底——并发删除模板后旧页签带回死 id 不再静默解析出空。
        """
        templates = self.repo.get_parse_templates()
        by_id = {t["id"]: t for t in templates}
        fallback = next((t for t in templates if t.get("is_fallback")), None)

        def _default() -> dict:
            return {"template_id": fallback["id"] if fallback else None, "mode": "default"}

        if template_id is not None:
            t = by_id.get(template_id)
            if t and t.get("enabled", True):
                return {"template_id": template_id, "mode": "manual"}
            return _default()
        if scope_key:
            bound = self.repo.get_parse_scope_binding(scope_key)
            if bound is not None:
                t = by_id.get(bound)
                if t and t.get("enabled", True):
                    return {"template_id": bound, "mode": "scope", "scope": scope_key}
        return _default()

    # ── 使用位置绑定（设置页配置）──

    def list_scope_bindings(self) -> list[dict]:
        bound = {b["scope_key"]: b["template_id"] for b in self.repo.get_parse_scope_bindings()}
        names = {t["id"]: t["name"] for t in self.repo.get_parse_templates()}
        return [{
            "scope_key": s["key"], "label": s["label"],
            "template_id": bound.get(s["key"]),
            "template_name": names.get(bound.get(s["key"])) or "",
        } for s in PARSE_SCOPES]

    def set_scope_binding(self, scope_key: str, template_id: int) -> dict:
        if scope_key not in {s["key"] for s in PARSE_SCOPES}:
            raise ValueError("未知使用位置")
        tpl = self.repo.get_parse_template(template_id)
        if not tpl or not tpl.get("enabled", True):
            raise ValueError("模板不存在或已停用")
        self.repo.set_parse_scope_binding(scope_key, template_id)
        return {"scope_key": scope_key, "template_id": template_id}

    # ── 种子（startup 调用，带 guard）──

    def seed_fallback(self) -> int:
        """创建「通用」兜底模板并把存量区域/字段规则归入。"""
        tpl_id = self.repo.add_parse_template({
            "name": "通用", "is_fallback": True, "sort_order": 0,
            "note": "存量规则迁入；匹配不到专属模板时的兜底，不拦截",
        })
        regions = self.repo.get_parse_regions()
        for region in regions:
            self.repo.update_parse_region(region["id"], {"template_id": tpl_id})
        for rule in self.repo.get_parse_field_rules():
            # 直接改列（update_parse_field_rule 走 stale 标记，这里新模板无快照，无碍）
            self.repo.update_parse_field_rule(rule["id"], {"template_id": tpl_id})
        return tpl_id

    def seed_fallback_kp_marker_exclusion(self) -> None:
        """给通用 KP 区补行级排除词（替换 pricing_engine 旧硬编码剔除）。"""
        for region in self.repo.get_parse_regions():
            if (region.get("region_key") or "").lower() in ("kp", "keyparts", "keypats"):
                existing = {w.strip() for w in (region.get("exclude_keywords") or "").split(",") if w.strip()}
                markers = ["Keypats", "Key Parts", "keyparts", "keypats", "key parts", "kp", "catalogue"]
                merged = ",".join(sorted(existing | set(markers), key=str.lower))
                self.repo.update_parse_region(region["id"], {"exclude_keywords": merged})
                break

    # ── 标准文件 ──

    def generate_std_file(self, template_id: int) -> dict:
        """（重新）生成标准文件 + 自检样例 + 期望快照，并立即跑自检。"""
        tpl = self.repo.get_parse_template(template_id)
        if not tpl:
            raise ValueError("模板不存在")

        std_bytes = workbook_bytes(build_std_workbook(sample=False))
        sample_bytes = workbook_bytes(build_std_workbook(sample=True))
        version = (tpl["std_version"] or 0) + 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        std_key = self.storage.save_scoped(
            "rules-templates", f"tpl{template_id}_std_v{version}", std_bytes, ".xlsx")
        sample_key = self.storage.save_scoped(
            "rules-templates", f"tpl{template_id}_sample_v{version}", sample_bytes, ".xlsx")
        self.repo.update_parse_template(template_id, {
            "std_file_key": std_key, "std_version": version, "std_generated_at": now,
            "sample_file_key": sample_key,
            "expected_snapshot": {
                **std_expected_snapshot(),
                "_provenance": {"source": "generator", "recorded_at": now},
            },
        })
        check = self.run_selfcheck(template_id)
        return {"std_version": version, "std_file_key": std_key, "selfcheck": check}

    def replace_std_file(self, template_id: int, file_bytes: bytes) -> dict:
        """上传替换标准文件：校验为合法 xlsx 后落盘；样例/期望不动，自检照旧跑。"""
        tpl = self.repo.get_parse_template(template_id)
        if not tpl:
            raise ValueError("模板不存在")
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(file_bytes))
        content = workbook_bytes(wb)
        version = (tpl["std_version"] or 0) + 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        std_key = self.storage.save_scoped(
            "rules-templates", f"tpl{template_id}_std_v{version}", content, ".xlsx")
        self.repo.update_parse_template(template_id, {
            "std_file_key": std_key, "std_version": version, "std_generated_at": now,
        })
        return {"std_version": version, "std_file_key": std_key}

    def read_std_file(self, template_id: int) -> tuple[bytes, str]:
        tpl = self.repo.get_parse_template(template_id)
        if not tpl or not tpl["std_file_key"]:
            raise FileNotFoundError("该模板还没有标准文件")
        return self.storage.read_bytes(tpl["std_file_key"]), tpl["std_file_key"]

    # ── 自检 ──

    @staticmethod
    def _normalize_parse(parse_result: dict) -> dict:
        statics = {k: (v.get("value") if isinstance(v, dict) else v)
                   for k, v in (parse_result.get("static_fields") or {}).items()}
        regions = {}
        for key, rows in (parse_result.get("dynamic_regions") or {}).items():
            regions[key] = [
                {f: str(v) for f, v in row.items() if not str(f).startswith("_")}
                for row in rows
            ]
        return {"static_fields": statics, "dynamic_regions": regions}

    def run_selfcheck(self, template_id: int) -> dict:
        """样例文件跑引擎 vs 期望快照逐值回归；结果落模板，失败拦下发。"""
        from app.engine.excel_parser import ExcelParser
        import pandas as pd

        tpl = self.repo.get_parse_template(template_id)
        if not tpl:
            raise ValueError("模板不存在")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not tpl["sample_file_key"] or not tpl["has_expected"]:
            detail = {"ok": False, "reason": "缺少自检样例或期望快照（先生成标准文件或上传样例）"}
            self.repo.update_parse_template(template_id, {
                "selfcheck_status": "none", "selfcheck_ran_at": now,
                "selfcheck_detail": detail,
            })
            return detail

        expected = json.loads(self._load_template_raw(template_id, "expected_snapshot"))
        problems = []
        try:
            sample_bytes = self.storage.read_bytes(tpl["sample_file_key"])
            sheet = pd.read_excel(io.BytesIO(sample_bytes), sheet_name=0, header=None)
            parser = ExcelParser(self.repo)
            actual = self._normalize_parse(parser.parse(sheet, template_id=template_id))
        except Exception as e:
            detail = {"ok": False, "reason": f"自检执行异常: {e}"}
            self.repo.update_parse_template(template_id, {
                "selfcheck_status": "failed", "selfcheck_ran_at": now, "selfcheck_detail": detail,
            })
            return detail

        for field, want in (expected.get("static_fields") or {}).items():
            got = actual["static_fields"].get(field)
            if str(want) != ("" if got is None else str(got)):
                problems.append(f"静态字段 {field}: 期望「{want}」实得「{got}」")
        for region, want_rows in (expected.get("dynamic_regions") or {}).items():
            got_rows = actual["dynamic_regions"].get(region, [])
            if len(want_rows) != len(got_rows):
                problems.append(f"{region} 区行数: 期望 {len(want_rows)} 实得 {len(got_rows)}")
            for i, want_row in enumerate(want_rows):
                if i >= len(got_rows):
                    break
                for f, want_v in want_row.items():
                    got_v = got_rows[i].get(f, "")
                    if str(want_v) != str(got_v):
                        problems.append(f"{region} 区第{i + 1}行 {f}: 期望「{want_v}」实得「{got_v}」")
        if expected.get("region_bounds"):
            bounds = parser._locate_regions(sheet)
            for region, want_b in expected["region_bounds"].items():
                got_b = bounds.get(region) or {}
                for side in ("start_row", "end_row"):
                    if want_b.get(side) is not None and got_b.get(side) != want_b[side]:
                        problems.append(
                            f"{region} 区{side}: 期望 {want_b[side]} 实得 {got_b.get(side)}")

        prov = (expected.get("_provenance") or {}).get("source")
        if problems and prov not in (None, "generator"):
            problems.insert(0, "注意：期望基线由补丁/回填文件烘焙（规则自证），失败可能是基线过时而非规则回归"
                               "——重新生成标准文件可校准为权威基线")

        ok = not problems
        detail = {"ok": ok, "checks": len(problems) + 1, "problems": problems[:50]}
        self.repo.update_parse_template(template_id, {
            "selfcheck_status": "passed" if ok else "failed",
            "selfcheck_ran_at": now, "selfcheck_detail": detail,
        })
        return detail

    def _load_template_raw(self, template_id: int, column: str) -> str:
        """读模板原始 Text 列（期望快照等）。"""
        with self.repo.session_factory() as session:
            from app.models.rules import ParseTemplate
            row = session.query(ParseTemplate).filter_by(id=template_id).first()
            if not row:
                raise ValueError("模板不存在")
            return getattr(row, column)
