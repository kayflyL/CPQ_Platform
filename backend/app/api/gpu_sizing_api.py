"""gpu_sizing API —— AI 推理配置器（P1）。
数据链：三软库(rules.llm_models/scene_params/inference_frameworks) + 方案平台(model_id)
  → 机型(l6.server_models) → 基准 gpu_default → KP GPU spec(显存/带宽)。
计算全在 services/gpu_sizing.py 纯函数（单测锚点=Excel v10 速查表）；本层只做 DB 读取与组装。
无价格输出，不涉及 price_access。gpu_default 未维护的机型返回 no_gpu_config，不猜。"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

import json

from app.models.base import rules_engine, l6_engine, kp_engine
from app.services import gpu_sizing as G

router = APIRouter(prefix="/api/gpu-sizing", tags=["gpu-sizing"])

# v1 默认框架口径（Excel 主推行）：系数/开销读 inference_frameworks，找不到走此兜底
_DEFAULT_FW = {"name": "vLLM", "coeff_4bit": 1.05, "coeff_8bit": 1.0, "coeff_16bit": 1.0,
               "overhead_gb": 1.0, "tensor_parallel": True}
BITS_OPTIONS = [4, 8, 16]


@router.get("/catalog")
def catalog():
    """配置器选择器数据：模型（按公司分组）/ 场景 / 量化档位。"""
    with rules_engine.connect() as c:
        models = [dict(r) for r in c.execute(text(
            "SELECT id, vendor, name, params_b, default_bits, attn, confidence, max_ctx"
            " FROM rules.llm_models ORDER BY vendor, id")).mappings().all()]
        scenes = [dict(r) for r in c.execute(text(
            "SELECT id, name, recommend_ctx, min_tok_s, need_vision FROM rules.scene_params"
            " ORDER BY sort_order, id")).mappings().all()]
        frameworks = [dict(r) for r in c.execute(text(
            "SELECT name, default_quant FROM rules.inference_frameworks ORDER BY id")).mappings().all()]
    vendors: dict = {}
    for m in models:
        vendors.setdefault(m["vendor"], []).append(m)
    return {"vendors": [{"vendor": v, "models": ms} for v, ms in vendors.items()],
            "scenes": scenes, "frameworks": frameworks, "bits_options": BITS_OPTIONS}


def _framework(name: str = None):
    with rules_engine.connect() as c:
        r = c.execute(text("SELECT name, coeff_4bit, coeff_8bit, coeff_16bit, overhead_gb,"
                           " tensor_parallel FROM rules.inference_frameworks WHERE name=:n"),
                      {"n": name or _DEFAULT_FW["name"]}).mappings().first()
    return dict(r) if r else {**_DEFAULT_FW, "name": name or _DEFAULT_FW["name"]}


def _load_model_scene(model_id: int, scene_id: int):
    with rules_engine.connect() as c:
        m = c.execute(text("SELECT id, vendor, name, params_b, attn, confidence, max_ctx, vision_gb, hidden_dim,"
                           " num_layers, num_heads, kv_heads FROM rules.llm_models WHERE id=:i"),
                      {"i": model_id}).mappings().first()
        sc = c.execute(text("SELECT id, name, recommend_ctx FROM rules.scene_params WHERE id=:i"),
                       {"i": scene_id}).mappings().first()
    if not m or not sc:
        raise HTTPException(404, "模型或场景不存在")
    model = dict(m)
    if not model.get("params_b") or model["params_b"] <= 0:
        raise HTTPException(409, f"模型 {model['name']} 为自定义占位（参数量=0），请先在模型库维护参数")
    if not all(model.get(k) for k in ("hidden_dim", "num_layers", "num_heads", "kv_heads")):
        raise HTTPException(409, f"模型 {model['name']} 缺结构参数(hidden/layers/heads/kv_heads)，请先在模型库补齐")
    model.update(hidden=model["hidden_dim"], layers=model["num_layers"], heads=model["num_heads"])
    return model, int(dict(sc)["recommend_ctx"] or 8192)


@router.get("/solve")
def solve(model_id: int = Query(...), bits: int = Query(8), scene_id: int = Query(...),
          concurrency: int = Query(1, ge=1, le=128), framework: str = Query("vLLM")):
    """需求侧计算:权重/KV/总需(含并发)。卡的判定全部走 /evaluate。"""
    if bits not in BITS_OPTIONS:
        raise HTTPException(400, f"量化档位仅支持 {BITS_OPTIONS}")
    model, ctx = _load_model_scene(model_id, scene_id)
    fw = _framework(framework)
    coeff = {4: fw.get("coeff_4bit"), 8: fw.get("coeff_8bit"), 16: fw.get("coeff_16bit")}[bits] or 1.0
    overhead = float(fw.get("overhead_gb") or 0.0)
    w0 = G.weight_gb(model["params_b"], bits, coeff)
    kvt = G.kv_per_token_gb(model, bits)
    occ = w0 + (model.get("vision_gb") or 0) + kvt * ctx * concurrency
    return {"model": {"id": model["id"], "vendor": model["vendor"], "name": model["name"],
                      "confidence": model["confidence"], "native_max_ctx": model.get("max_ctx")},
            "bits": bits, "framework": fw.get("name"),
            "scene": {"id": scene_id, "recommend_ctx": ctx, "concurrency": concurrency},
            "need": {"weight_gb": round(w0, 2), "vision_gb": model.get("vision_gb") or 0,
                     "kv_per_tok_gb": round(kvt, 10), "kv_at_ctx_gb": round(kvt * ctx * concurrency, 2),
                     "total_gb": round(occ, 2)},
            "params": {"w0": round(w0, 4), "kvt": kvt, "occ": round(occ, 4),
                       "ctx": ctx, "batch": concurrency, "overhead": overhead}}


def _cards_all() -> list:
    """KP GPU 卡库全量(含显存/带宽/TDP/适配机型)。"""
    with kp_engine.connect() as c:
        rows = c.execute(text(
            "SELECT p.id, p.name, p.brand, p.applicable FROM kp.kp_parts p"
            " JOIN kp.kp_categories t ON t.id = p.category_id"
            " WHERE t.name = 'GPU' ORDER BY p.brand, p.id")).mappings().all()
        specs_map = {}
        for r in c.execute(text(
                "SELECT s.part_id, s.spec_key, s.spec_value FROM kp.kp_part_specs s"
                " JOIN kp.kp_categories t ON t.id = (SELECT category_id FROM kp.kp_parts WHERE id = s.part_id)"
                " WHERE t.name = 'GPU'")).fetchall():
            specs_map.setdefault(r[0], {})[r[1]] = r[2]
    return [{"id": r["id"], "name": r["name"], "brand": r["brand"], "applicable": r["applicable"],
             "cap_gb": G.parse_gb(G.spec_value(specs_map.get(r["id"], {}), "Capacity", "显存")),
             "bw_gb_s": G.parse_gb(G.spec_value(specs_map.get(r["id"], {}), "Memory Bandwidth")),
             "tdp_w": G.parse_gb(G.spec_value(specs_map.get(r["id"], {}), "TDP", "tdp"))} for r in rows]


@router.get("/cards")
def cards():
    return {"cards": _cards_all()}


@router.get("/evaluate")
def evaluate(model_id: int = Query(...), bits: int = Query(8), scene_id: int = Query(...),
             concurrency: int = Query(1, ge=1, le=128), framework: str = Query("vLLM")):
    """批量卡试算(Excel 速查表的动态版):对全部有显存的卡算 推荐张数/最低张数/余量/上下文/吞吐,
    排序 = 装得下 → 推荐张数升序 → 余量降序;推荐张数 >12 张视为不实用(fits=False)。"""
    if bits not in BITS_OPTIONS:
        raise HTTPException(400, f"量化档位仅支持 {BITS_OPTIONS}")
    model, ctx = _load_model_scene(model_id, scene_id)
    fw = _framework(framework)
    coeff = {4: fw.get("coeff_4bit"), 8: fw.get("coeff_8bit"), 16: fw.get("coeff_16bit")}[bits] or 1.0
    overhead = float(fw.get("overhead_gb") or 0.0)
    w0 = G.weight_gb(model["params_b"], bits, coeff)
    vision = model.get("vision_gb") or 0
    kvt = G.kv_per_token_gb(model, bits)
    occ = w0 + vision + kvt * ctx * concurrency
    tp = bool(fw.get("tensor_parallel"))
    rows = []
    for card in _cards_all():
        if not card.get("cap_gb"):
            continue
        usable = G.per_card_usable(card["cap_gb"], overhead)
        if usable <= 0:
            continue
        if tp:
            mn = G.need_cards(w0, vision, kvt, ctx, concurrency, usable)
            rc = G.recommend_cards(mn, w0, vision, kvt, ctx, concurrency, usable)
            eff = usable * rc
        else:  # Excel 口径:不支持张量并行的框架多卡不并显存,所需卡数 N/A,单卡装得下即 1 张
            mn = None
            rc = 1 if occ <= usable else None
            eff = usable
        mctx = G.max_ctx(w0 + vision, 0, kvt, concurrency, eff)
        speed = G.est_tok_s(w0, kvt, ctx, concurrency, (card.get("bw_gb_s") or 0) * (rc or 1))
        rows.append({**card, "usable_per_card": round(usable, 2), "rec": rc, "min": mn,
                     "headroom": round(max(0.0, 1 - occ / eff), 4), "over": occ > eff,
                     "max_ctx": int(mctx),
                     "speed_tok_s": round(speed, 1) if speed else None,
                     "fits": rc is not None and rc <= 12})
    rows.sort(key=lambda r: (not (r["fits"] and not r["over"]), r["rec"] or 999, -r["headroom"]))
    return {"model": {"id": model["id"], "name": model["name"], "native_max_ctx": model.get("max_ctx")},
            "bits": bits, "framework": fw.get("name"), "tp": tp,
            "scene": {"recommend_ctx": ctx, "concurrency": concurrency},
            "need": {"weight_gb": round(w0, 2), "vision_gb": vision,
                     "kv_per_tok_gb": kvt, "kv_at_ctx_gb": round(kvt * ctx * concurrency, 2),
                     "total_gb": round(occ, 2)},
            "params": {"w0": round(w0, 4), "kvt": kvt, "occ": round(occ, 4),
                       "vision_gb": vision, "ctx": ctx, "batch": concurrency, "overhead": overhead},
            "rows": rows,
            "skipped": sum(1 for c0 in _cards_all() if not c0.get("cap_gb"))}


# ── 管理面 CRUD（策略中心·解决方案域：三软库行编辑；与 solutions 管理同水位鉴权）──
from fastapi import Body  # noqa: E402
from app.models.base import Rules_SessionLocal  # noqa: E402
from app.models.llm_catalog import LlmModel, InferenceFramework, SceneParam  # noqa: E402

_MODEL_FIELDS = {"vendor": str, "name": str, "params_b": float, "default_bits": int,
                 "hidden_dim": int, "num_layers": int, "attn": str, "num_heads": int,
                 "kv_heads": int, "vision_gb": float, "note": str, "confidence": str,
                 "max_ctx": int, "measured_size_gb": float}
_FW_FIELDS = {"name": str, "default_quant": str, "coeff_4bit": float, "coeff_8bit": float,
              "coeff_16bit": float, "tensor_parallel": bool, "offload": str,
              "overhead_gb": float, "kv_cache_note": str, "note": str}
_SCENE_FIELDS = {"name": str, "recommend_ctx": int, "min_tok_s": float,
                 "need_vision": bool}


def _clean(data: dict, fields: dict) -> dict:
    out = {}
    for k, cast in fields.items():
        if k not in data or data[k] is None or data[k] == "":
            continue
        try:
            out[k] = cast(data[k]) if cast is not str else str(data[k]).strip()
        except (TypeError, ValueError):
            raise HTTPException(400, f"字段 {k} 类型错误")
    return out


@router.get("/admin/models")
def admin_models():
    with Rules_SessionLocal() as s:
        rows = s.query(LlmModel).order_by(LlmModel.vendor, LlmModel.id).all()
        return {"models": [{"id": r.id, "vendor": r.vendor, "name": r.name,
                            "params_b": r.params_b, "default_bits": r.default_bits,
                            "attn": r.attn, "confidence": r.confidence,
                            "hidden_dim": r.hidden_dim, "num_layers": r.num_layers,
                            "num_heads": r.num_heads, "kv_heads": r.kv_heads,
                            "vision_gb": r.vision_gb, "max_ctx": r.max_ctx,
                            "measured_size_gb": r.measured_size_gb,
                            "note": r.note} for r in rows]}


@router.post("/admin/models")
def admin_create_model(data: dict = Body(...)):
    d = _clean(data, _MODEL_FIELDS)
    if not d.get("vendor") or not d.get("name") or "params_b" not in d:
        raise HTTPException(400, "公司/模型名/参数量必填")
    with Rules_SessionLocal() as s:
        if s.query(LlmModel).filter_by(vendor=d["vendor"], name=d["name"]).first():
            raise HTTPException(409, "同公司下已有同名模型")
        s.add(LlmModel(**d, created_at=__import__("datetime").date.today().isoformat()))
        s.commit()
    return {"ok": True}


@router.put("/admin/models/{mid}")
def admin_update_model(mid: int, data: dict = Body(...)):
    d = _clean(data, _MODEL_FIELDS)
    with Rules_SessionLocal() as s:
        row = s.query(LlmModel).get(mid)
        if not row:
            raise HTTPException(404, "模型不存在")
        for k, v in d.items():
            setattr(row, k, v)
        s.commit()
    return {"ok": True}


@router.delete("/admin/models/{mid}")
def admin_delete_model(mid: int):
    with Rules_SessionLocal() as s:
        s.query(LlmModel).filter_by(id=mid).delete()
        s.commit()
    return {"ok": True}


@router.get("/admin/frameworks")
def admin_frameworks():
    with Rules_SessionLocal() as s:
        rows = s.query(InferenceFramework).order_by(InferenceFramework.id).all()
        return {"frameworks": [{"id": r.id, "name": r.name, "default_quant": r.default_quant,
                                "coeff_4bit": r.coeff_4bit, "coeff_8bit": r.coeff_8bit,
                                "coeff_16bit": r.coeff_16bit, "tensor_parallel": r.tensor_parallel,
                                "overhead_gb": r.overhead_gb, "kv_cache_note": r.kv_cache_note,
                                "note": r.note} for r in rows]}


@router.post("/admin/frameworks")
def admin_create_framework(data: dict = Body(...)):
    d = _clean(data, _FW_FIELDS)
    if not d.get("name"):
        raise HTTPException(400, "框架名必填")
    with Rules_SessionLocal() as s:
        if s.query(InferenceFramework).filter_by(name=d["name"]).first():
            raise HTTPException(409, "框架已存在")
        s.add(InferenceFramework(**d))
        s.commit()
    return {"ok": True}


@router.put("/admin/frameworks/{fid}")
def admin_update_framework(fid: int, data: dict = Body(...)):
    d = _clean(data, _FW_FIELDS)
    with Rules_SessionLocal() as s:
        row = s.query(InferenceFramework).get(fid)
        if not row:
            raise HTTPException(404, "框架不存在")
        for k, v in d.items():
            setattr(row, k, v)
        s.commit()
    return {"ok": True}


@router.delete("/admin/frameworks/{fid}")
def admin_delete_framework(fid: int):
    with Rules_SessionLocal() as s:
        s.query(InferenceFramework).filter_by(id=fid).delete()
        s.commit()
    return {"ok": True}


@router.get("/admin/scenes")
def admin_scenes():
    with Rules_SessionLocal() as s:
        rows = s.query(SceneParam).order_by(SceneParam.sort_order, SceneParam.id).all()
        return {"scenes": [{"id": r.id, "name": r.name, "recommend_ctx": r.recommend_ctx,
                            "min_tok_s": r.min_tok_s, "need_vision": r.need_vision} for r in rows]}


@router.post("/admin/scenes")
def admin_create_scene(data: dict = Body(...)):
    d = _clean(data, _SCENE_FIELDS)
    if not d.get("name"):
        raise HTTPException(400, "场景名必填")
    with Rules_SessionLocal() as s:
        if s.query(SceneParam).filter_by(name=d["name"]).first():
            raise HTTPException(409, "场景已存在")
        s.add(SceneParam(**d, sort_order=s.query(SceneParam).count()))
        s.commit()
    return {"ok": True}


@router.put("/admin/scenes/{sid}")
def admin_update_scene(sid: int, data: dict = Body(...)):
    d = _clean(data, _SCENE_FIELDS)
    with Rules_SessionLocal() as s:
        row = s.query(SceneParam).get(sid)
        if not row:
            raise HTTPException(404, "场景不存在")
        for k, v in d.items():
            setattr(row, k, v)
        s.commit()
    return {"ok": True}


@router.delete("/admin/scenes/{sid}")
def admin_delete_scene(sid: int):
    with Rules_SessionLocal() as s:
        s.query(SceneParam).filter_by(id=sid).delete()
        s.commit()
    return {"ok": True}


# ── 按卡试算(Excel「GPU配置器」本体的复现:卡库全量任选,判定四档)──

def _card(card_id: int) -> dict | None:
    with kp_engine.connect() as c:
        r = c.execute(text(
            "SELECT p.id, p.name, p.brand, p.applicable FROM kp.kp_parts p WHERE p.id = :i"),
            {"i": card_id}).mappings().first()
        if not r:
            return None
        t = c.execute(text(
            "SELECT t.name FROM kp.kp_categories t JOIN kp.kp_parts p ON p.category_id = t.id WHERE p.id = :i"),
            {"i": card_id}).scalar()
    if t != "GPU":
        return None
    with kp_engine.connect() as c:
        sp = {k: v for k, v in c.execute(text(
            "SELECT spec_key, spec_value FROM kp.kp_part_specs WHERE part_id = :i"),
            {"i": card_id}).fetchall()}
    return {"id": r["id"], "name": r["name"], "brand": r["brand"], "applicable": r["applicable"],
            "cap_gb": G.parse_gb(G.spec_value(sp, "Capacity", "显存")),
            "bw_gb_s": G.parse_gb(G.spec_value(sp, "Memory Bandwidth")),
            "tdp_w": G.parse_gb(G.spec_value(sp, "TDP", "tdp"))}


@router.get("/try-card")
def try_card(model_id: int = Query(...), bits: int = Query(8), scene_id: int = Query(...),
             concurrency: int = Query(1, ge=1, le=128), card_id: int = Query(...),
             cards: int = Query(1, ge=1, le=64), framework: str = Query("vLLM")):
    """单卡×张数试算 = Excel「GPU配置器」口径:判定四档 + 最低/推荐张数 + 余量 + 估速 + 适配机型。"""
    if bits not in BITS_OPTIONS:
        raise HTTPException(400, f"量化档位仅支持 {BITS_OPTIONS}")
    card = _card(card_id)
    if not card:
        raise HTTPException(404, "显卡不存在或不是 GPU 类配件")
    if not card.get("cap_gb"):
        raise HTTPException(409, f"{card['name']} 未维护显存(Capacity),无法试算——请在料号库补齐")
    with rules_engine.connect() as c:
        m = c.execute(text("SELECT id, name, params_b, attn, max_ctx, vision_gb, hidden_dim,"
                           " num_layers, num_heads, kv_heads FROM rules.llm_models WHERE id=:i"),
                      {"i": model_id}).mappings().first()
        sc = c.execute(text("SELECT id, name, recommend_ctx FROM rules.scene_params WHERE id=:i"),
                       {"i": scene_id}).mappings().first()
    if not m or not sc:
        raise HTTPException(404, "模型或场景不存在")
    model = dict(m)
    if not model.get("params_b") or model["params_b"] <= 0:
        raise HTTPException(409, f"模型 {model['name']} 为自定义占位（参数量=0），请先在模型库维护参数")
    if not all(model.get(k) for k in ("hidden_dim", "num_layers", "num_heads", "kv_heads")):
        raise HTTPException(409, f"模型 {model['name']} 缺结构参数，请先在模型库补齐")
    model.update(hidden=model["hidden_dim"], layers=model["num_layers"], heads=model["num_heads"])
    ctx = int(dict(sc)["recommend_ctx"] or 8192)
    fw = _framework(framework)
    coeff = {4: fw.get("coeff_4bit"), 8: fw.get("coeff_8bit"), 16: fw.get("coeff_16bit")}[bits] or 1.0
    overhead = float(fw.get("overhead_gb") or 0.0)

    w0 = G.weight_gb(model["params_b"], bits, coeff)
    w = w0 + (model.get("vision_gb") or 0)
    kvt = G.kv_per_token_gb(model, bits)
    usable = G.per_card_usable(card["cap_gb"], overhead)
    if usable <= 0:
        raise HTTPException(409, f"{card['name']} 显存 {card['cap_gb']}G 过小,扣除开销后为 0")
    tp = bool(fw.get("tensor_parallel"))
    eff = usable * cards if tp else usable  # Excel 口径:非 TP 框架多卡不并显存
    occ = w + kvt * ctx * concurrency
    mctx = G.max_ctx(w, 0, kvt, concurrency, eff)
    verdict = G.verdict_of(w + kvt * 4096 * concurrency, eff, mctx)
    if tp:
        min_cards = G.need_cards(w0, model.get("vision_gb") or 0, kvt, ctx, concurrency, usable)
        rec_cards = G.recommend_cards(min_cards, w0, model.get("vision_gb") or 0, kvt, ctx, concurrency, usable)
    else:  # 所需卡数 N/A(框架不支持张量并行);单卡装得下即 1 张
        min_cards = None
        rec_cards = 1 if occ <= usable else None
    speed = G.est_tok_s(w0, kvt, ctx, concurrency, (card.get("bw_gb_s") or 0) * (rec_cards or 1))
    return {
        "card": card, "cards": cards, "framework": fw.get("name"),
        "usable_per_card": round(usable, 2), "eff_gb": round(eff, 2), "occ_gb": round(occ, 2),
        "headroom": round(max(0.0, 1 - occ / eff), 4) if occ <= eff else 0.0,
        "over": occ > eff,
        "verdict": verdict, "max_ctx": mctx,
        "min_cards": min_cards, "rec_cards": rec_cards, "tensor_parallel": tp,
        "speed_tok_s": round(speed, 1) if speed else None,
        "native_max_ctx": model.get("max_ctx"),
        "recommend_ctx": ctx, "concurrency": concurrency,
    }
