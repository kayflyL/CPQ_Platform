"""推导 API — 传当前配置状态，返回各步推导结果 + 约束校验。

state: { kp_lines: [{cat, pn, qty}], gpu_arch: "none|pt|switch", psu_options?: [...] }
KP 配件从 kp.kp_parts 查详情（tdp/kind/cables_per/specs），电源/NVSwitch/NVLink 仍从 parts_master 查。
再用 DerivationEngine + rules.derivation_rules 推导。
"""
import json
from fastapi import APIRouter
from sqlalchemy import text
from app.engine.derivation_engine import DerivationEngine
from app.repository.parts_master_repo import PartsMasterRepository
from app.models.base import rules_engine, kp_engine

router = APIRouter(prefix="/api/derive", tags=["derive"])


def _load_rules() -> dict:
    """从 rules.derivation_rules 读所有启用规则参数"""
    out: dict = {}
    with rules_engine.connect() as c:
        rows = c.execute(text(
            "SELECT rule_key, params FROM rules.derivation_rules WHERE enabled=true"
        )).all()
    for r in rows:
        params = r[1]
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {}
        out[r[0]] = params or {}
    return out


# category 命名归一化：前端传 DB 类别名（CPU/HDD-SSD），DerivationEngine 用小写 key（cpu/drive）
CAT_NORMALIZE = {
    "CPU": "cpu", "GPU": "gpu", "HDD/SSD": "drive", "Memory": "memory",
    "NIC": "nic", "Raid card": "raid", "MB": "mb",
}


def _norm_cat(cat):
    if cat is None:
        return cat
    return CAT_NORMALIZE.get(cat, str(cat).lower())


def _kp_part_by_pn(pn: str) -> dict:
    """从 kp.kp_parts 按料号查 KP 配件详情（pn=oem_sku，空则取 name，与 /api/kp/parts 一致）"""
    q = """
        SELECT COALESCE(NULLIF(p.oem_sku, ''), p.name) AS pn,
               p.name, c.name AS category, p.brand,
               COALESCE((SELECT jsonb_object_agg(spec_key, spec_value)
                         FROM kp.kp_part_specs WHERE part_id = p.id), '{}'::jsonb) AS specs,
               p.applicable,
               COALESCE(ph.price, 0) AS unit_price
        FROM kp.kp_parts p
        JOIN kp.kp_categories c ON p.category_id = c.id
        LEFT JOIN LATERAL (
            SELECT price FROM kp.kp_price_history
            WHERE part_id = p.id ORDER BY price_date DESC LIMIT 1
        ) ph ON true
        WHERE COALESCE(NULLIF(p.oem_sku, ''), p.name) = :pn
    """
    with kp_engine.connect() as c:
        row = c.execute(text(q), {"pn": pn}).mappings().first()
    return dict(row) if row else {}


def _psu_options() -> list:
    """从 parts_master 拉电源料号作为可选集"""
    out = []
    for p in PartsMasterRepository().list(category="电源"):
        specs = p.get("specs") or {}
        out.append({"pn": p["pn"], "name": p["name"],
                    "wattage": specs.get("wattage", 0), "price": p.get("unit_price", 0)})
    return out


@router.post("")
def derive(state: dict):
    rules = _load_rules()
    eng = DerivationEngine(rules)
    l6_repo = PartsMasterRepository()
    # 给每个 kp_line 按 pn 补 part 详情（从 kp.kp_parts 查），并归一化 cat 给 DerivationEngine
    kp = []
    for l in state.get("kp_lines", []):
        part = _kp_part_by_pn(l.get("pn"))
        kp.append({**l, "cat": _norm_cat(l.get("cat")), "part": part})
    state["kp_lines"] = kp
    if "psu_options" not in state:
        state["psu_options"] = _psu_options()
    result = eng.derive_all(state)
    # 补充 switch_extra 实际料号（NVSwitch/NVLink 属 L6 件，从 parts_master 查）
    if result.get("switch_extra"):
        switch_parts = []
        for item in result["switch_extra"]:
            cat = item["category"]
            gpu_count = item["gpu_count"]
            parts_in_cat = [p for p in l6_repo.list(category=cat)]
            for p in parts_in_cat:
                if cat == "NVSwitch":
                    qty = max(1, gpu_count // 2)
                elif cat == "NVLink":
                    qty = gpu_count
                else:
                    qty = 1
                switch_parts.append({
                    "pn": p["pn"], "name": p["name"], "category": cat,
                    "qty": qty, "unit_price": p.get("unit_price", 0)
                })
        result["switch_extra_parts"] = switch_parts
    return result
