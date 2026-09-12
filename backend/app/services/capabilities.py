"""需求分析 skill 的能力/契约辅助层。

- 只负责：登记表槽位确定性落槽、冻结守卫、语义归一（目录白名单/agent_fill 契约在 catalog_options.py）。
- 不做：任何 LLM 调用、固定选料兜底、节点内独立 ReAct、模型/配件决策。
- 登记由唯一大脑在 agent_fill 节点回合亲自完成（skill_chat.run_skill_agent_turn + 节点插件）；本层只做确定性落表与校验。
"""
import logging
from typing import Optional

from app.services.slot_contract import canonical_get, canonical_key, canonical_set

logger = logging.getLogger(__name__)

def _compose_config(config: Optional[dict]) -> dict:
    """归一化 compose 节点配置；配件来源与电源覆盖策略不再写死。"""
    cfg = dict(config or {})
    from app.services import reasoning_node_contract
    defaults = reasoning_node_contract.node_defaults().get("compose", {})
    for key, value in defaults.items():
        cfg.setdefault(key, value)
    return cfg
def _get_nested(data: dict, path: str, default=None):
    """按点分路径读取嵌套字典值；路径非法返回 default。"""
    cur = data
    for part in str(path or "").split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _slot_now_filled(ext: dict, key: str) -> bool:
    """反问回填后判断某 slot 是否已确认（统一走 slot_contract 契约口径，避免重复映射）。"""
    from app.services.slot_contract import _slot_filled
    return _slot_filled(ext, key)




def _confirmed_text(ext: dict) -> str:
    """把已确认的选型要点拼成一行（只做状态展示，不做话术）。"""
    parts = []
    _st = canonical_get(ext, "server_type")
    if _st:
        parts.append(f"服务器类型={_st}")
    _series = canonical_get(ext, "series")
    if _series:
        parts.append(f"平台系列={_series}")
    _form = canonical_get(ext, "form")
    if _form:
        parts.append(f"机箱形态={_form}")
    _model = canonical_get(ext, "server_model")
    if _model:
        parts.append(f"机型={_model}")
    _qty = canonical_get(ext, "purchase_qty")
    if _qty:
        parts.append(f"数量={_qty}")
    return "；".join(parts) or "（暂无明确约束）"


def _normalize_kp_rows(value) -> list:
    """把 LLM 填表契约的 kp_rows 收口成唯一部件行结构（only description+qty+catalogue）。

    规格/型号不在此拆分（如 CPU 主频、显存、RAID 级别），原样保留在 description，
    具体选型交给下游配件选配环节。返回空列表表示无效输入。
    """
    if not isinstance(value, list):
        return []
    rows: list = []
    for item in value[:64]:
        if not isinstance(item, dict):
            continue
        part_category = str(item.get("part_category") or item.get("category") or "").strip()
        if part_category:
            from app.services.part_selector import resolve_kp_category
            resolved = resolve_kp_category(part_category)
            if not resolved:
                # 解析不到库类目（如「电源」属机箱，不是 KP 配件）：不入 KP 行，保留在需求原文
                continue
            part_category = resolved
        description = str(item.get("description") or "").strip()
        catalogue = str(item.get("catalogue") or "").strip()
        note = str(item.get("note") or "").strip()
        if not part_category and not description:
            continue
        row: dict = {"part_category": part_category, "description": description,
                     "catalogue": catalogue, "note": note}
        try:
            qty = int(float(item.get("qty", 1) or 1))
            row["qty"] = qty if 1 <= qty <= 1000 else 1
        except (TypeError, ValueError):
            row["qty"] = 1
        rows.append(row)
    return rows


def _merge_kp_rows_locked(ext: dict, norm: list, allow_overwrite: bool = False,
                          picks: Optional[dict] = None) -> tuple:
    """登记行合并（已锁行保护）：大脑重发全表时，已确认料号的行冻结描述/行键。

    行键 = 类目|描述（part_selector.kp_row_key），描述一变行键就变 → 已确认 pick
    作废 → 客户被重复问同一行、已提交行被覆盖吞掉（2026-09-07 P0 复拍实测：
    CPU/Memory 确认后被大脑「规范化描述」引发级联重确认 + 1.92T/千兆行丢失）。
    规则：带 pick 的旧行原样冻结；新表里与已锁行同类目且描述包含已选料号名的
    「确认后变体」行丢弃；其余（新行/未锁行更新）正常采纳。返回 (合并结果, 冻结数)。

    已锁定行由调用方传入（节点隔离：kp 选型是 kp_reason 的私有状态，不在 ext 里）。

    allow_overwrite=False（默认，填槽而非常规改口）：kp_rows 以「类目」为键增量合并
    —— 新表同类目覆盖（客户修正了该部件描述），新表未列出的已登记类目保留不丢，
    防止大脑同回合分批/重试只发部分行时把先前登记的部件整批覆盖吞掉。
    allow_overwrite=True（replace=true，客户改口确认整表）：整批替换（仍冻结已锁行）。"""
    from app.services.part_selector import kp_row_key, kp_row_key_norm, row_key_norm
    picks = picks if isinstance(picks, dict) else {}
    existing_rows = ext.get("kp_rows") or []
    if not picks:
        if allow_overwrite:
            return norm, 0
        return _merge_kp_rows_incremental(existing_rows, norm), 0
    # 类目 → 已选料号名集合（识别「确认后变体」：新描述里含已选料号名）
    locked_names: dict = {}
    locked_keys = set(picks.keys())
    locked_norms: set = set()
    # P3-2：pick 键可能是 row_id，行身份取自条目自带的 category/description（旧数据退回键文本）。
    for rk, pk in picks.items():
        for ent in (pk if isinstance(pk, list) else [pk]):
            if not isinstance(ent, dict):
                continue
            _c = str(ent.get("category") or "").strip()
            _d = str(ent.get("description") or "").strip()
            locked_norms.add(row_key_norm(_c, _d or _c) if (_c or _d) else kp_row_key_norm(rk))
            cat = (_c or (str(rk).split("|", 1)[0] if "|" in str(rk) else "")).strip().lower()
            nm = str(ent.get("name") or "").strip().lower()
            if cat and nm:
                locked_names.setdefault(cat, set()).add(nm)
    out: list = []
    # 旧行：已锁的冻结保留；未锁的若新表有同描述行则交给新表（去重），否则保留（不丢行）
    new_sig = {(str(r.get("part_category") or "").strip(), str(r.get("description") or "").strip())
               for r in norm if isinstance(r, dict)}
    # 未锁行的归属（2026-09-12）：新表提到这个类目 → 旧行**让位**（客户改口=更新同一行），
    # 新表没提到 → 保留（不丢行）。旧实现只在新表出现「完全相同的 (类目,描述)」时才让位，
    # 于是「CPU|通用计算服务器处理器（客户未指定型号）」这类占位行会与客户后补的
    # 「CPU|兆芯 9654」**同类目并存**（§14 残留②的一手成因）。两类合并分支口径就此对齐
    # （无 picks 的 `_merge_kp_rows_incremental` 本来就是「同类目覆盖」）。
    # 已锁行仍冻结（P0 保护不动）：那是行键稳定化，与归属无关。
    new_cats = {c for c, _ in new_sig if c}
    frozen = 0
    for row in existing_rows:
        if not isinstance(row, dict):
            continue
        cat = str(row.get("part_category") or "").strip()
        desc = str(row.get("description") or "").strip()
        if kp_row_key(cat, desc) in locked_keys or row_key_norm(cat, desc or cat) in locked_norms:
            out.append(row)
            frozen += 1
        elif cat not in new_cats:
            out.append(row)
    # 新行：跳过已锁行变体与精确重复
    for row in norm:
        if not isinstance(row, dict):
            continue
        cat = str(row.get("part_category") or "").strip()
        desc = str(row.get("description") or "").strip()
        names = locked_names.get(cat.lower()) or set()
        if any(nm and nm in desc.lower() for nm in names):
            continue
        if (cat, desc) in {(str(r.get("part_category") or "").strip(),
                            str(r.get("description") or "").strip()) for r in out}:
            continue
        out.append(row)
    return out, frozen


def _merge_kp_rows_incremental(existing: list, norm: list) -> list:
    """无已确认料号时的增量合并：新表同类目覆盖，新表未列出的已登记类目保留。"""
    if not isinstance(existing, list) or not existing:
        return list(norm)
    new_cats = {str(r.get("part_category") or "").strip()
                for r in norm if isinstance(r, dict) and str(r.get("part_category") or "").strip()}
    out: list = list(norm)
    new_sig = {(str(r.get("part_category") or "").strip(), str(r.get("description") or "").strip())
               for r in out if isinstance(r, dict)}
    for row in existing:
        if not isinstance(row, dict):
            continue
        cat = str(row.get("part_category") or "").strip()
        sig = (cat, str(row.get("description") or "").strip())
        if cat in new_cats or sig in new_sig:
            continue
        out.append(dict(row))
    return out


def _apply_extracted_slots(ext: dict, slots: dict, allow_overwrite: bool = False,
                           picks: Optional[dict] = None) -> bool:
    """把 LLM 抽取的需求层 slots 应用到 ext（信任模型语义）。

    allow_overwrite=True 用于 edit 意图：允许覆盖已确认值；默认只填空槽。
    kp_rows（部件清单）直接按唯一结构落；仅拒绝 None 与明显空值。
    """
    if not isinstance(slots, dict):
        return False
    changed = False
    for key, value in (slots or {}).items():
        if value is None:
            continue
        if isinstance(value, bool) and not value:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        key = str(key).strip()
        if not key:
            continue
        if canonical_key(key) == "kp_rows":
            norm = _normalize_kp_rows(value)
            if norm:
                merged, frozen = _merge_kp_rows_locked(ext, norm, allow_overwrite=allow_overwrite,
                                                       picks=picks)
                ext["kp_rows"] = merged
                ext["_kp_rows_frozen"] = frozen
                changed = True
            continue
        if isinstance(value, (dict, list)):
            continue
        if canonical_key(key) == "server_type":
            v = str(value).strip()
            if not v:
                continue
            if v.isdigit():
                continue
            if allow_overwrite or not _slot_now_filled(ext, "server_type"):
                canonical_set(ext, "server_type", v)
                changed = True
        elif canonical_key(key) == "series":
            v = str(value).strip()
            if not v:
                continue
            if allow_overwrite or not _slot_now_filled(ext, "series"):
                canonical_set(ext, "series", v)
                changed = True
        elif canonical_key(key) == "form":
            v = str(value).strip()
            if not v:
                continue
            if allow_overwrite or not _slot_now_filled(ext, "form"):
                canonical_set(ext, "form", v)
                changed = True
        elif canonical_key(key) == "server_model":
            v = str(value).strip()
            if not v:
                continue
            if allow_overwrite or not _slot_now_filled(ext, "server_model"):
                canonical_set(ext, "server_model", v)
                changed = True
        elif canonical_key(key) == "purchase_qty":
            try:
                qty = int(float(value))
            except Exception:
                continue
            if allow_overwrite or not _slot_now_filled(ext, "purchase_qty"):
                canonical_set(ext, "purchase_qty", qty)
                changed = True
        elif canonical_key(key) == "warranty_years":
            try:
                years = int(float(value))
            except (TypeError, ValueError):
                continue
            if years <= 0:
                continue
            if allow_overwrite or not _slot_now_filled(ext, "warranty_years"):
                ext["warranty_years"] = years
                changed = True
        else:
            if allow_overwrite or not _slot_now_filled(ext, key):
                ext[key] = value
                changed = True
    return changed

def _enrich_agent_semantic(ext: dict, config: Optional[dict], req_text: Optional[str]) -> None:
    """agent 吐出的语义契约后处理：按规则补齐 workload/国产化/GPU 卡数，不硬编码业务。"""
    from app.services import semantic_contract as _sc
    rtext = str(req_text or "").lower()
    # 模型输出的 semantic 已经过 schema 收口，此处作为 advisor；侧重在“事实确定性”。
    wl = dict(_sc.workload(ext))
    if wl:
        _sc.set_value(ext, "workload", wl)
        if wl.get("kind") and _sc.intent(ext) in (None, "general"):
            _sc.set_value(ext, "intent", str(wl.get("kind")))
    comp = dict(_sc.compliance(ext))
    if comp.get("domestic_only"):
        if _sc.intent(ext) in (None, "general"):
            _sc.set_value(ext, "intent", "domestic_compliance")

def _model_in_catalog(name: str) -> bool:
    """机型名是否为在售目录真实机型（数据驱动校验；目录读取失败时保留原值，不因基础设施故障剥合法数据）。"""
    try:
        from app.services.catalog_guide import load_catalog
        _types, models_by_type = load_catalog()
        want = str(name or "").strip().lower()
        if not want:
            return False
        for models in (models_by_type or {}).values():
            for m in models or []:
                if str(m.get("name") or "").strip().lower() == want:
                    return True
    except Exception:
        logger.exception("在售目录读取失败（freeze 守卫放行机型 %s）", name)
        return True
    return False


def _freeze_requirement(ctx: dict, ext: dict, req_text: str = "") -> None:
    """把登记事实固化为「线索登记表」快照 ctx.requirement。

    下游（机型/KP/组装）只读该快照，绝不回写；后续持久化与运行面板都以它为准。
    机型字段只有在在售目录里真实存在时才保留：不在目录 = 臆造，从 ext 与快照一并剔除
    （2026-09-02 起：目录存在性校验，数据驱动；旧的「原话必须含机型名」文本剥除退役——
    它会把点选/早前轮次登记的合法机型误剥，且依赖前端发可读文案这种隐式契约）。
    """
    import copy as _copy
    model = str(canonical_get(ext, "server_model") or "").strip()
    if model and not _model_in_catalog(model):
        ext.pop("server_model", None)
        ext.pop("model", None)
        ext.pop("baseline_model", None)
        ctx.setdefault("assumptions", []).append(
            {"code": "model_dropped", "slot": "server_model", "dropped": model,
             "reason": "机型不在在售目录，按臆造剔除"})
    ctx["requirement"] = _copy.deepcopy(ext)
    ctx["requirement_text_snapshot"] = str(req_text or "")
