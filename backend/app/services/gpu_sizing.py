# -*- coding: utf-8 -*-
"""gpu_sizing 确定性计算服务 —— AI 推理配置器计算内核（P1）。
公式 = docs/原型/gpu_sizing_reference.py（逐格复刻用户 Excel v10，速查表锚点已校验：
  Qwen2.5-7B@8bit vLLM 128G卡×1 → KV@4K=0.109375G / 总占用=6.628633G / 有效=125.5G）。
两个科学修正随公式生效：
  ① 并发乘进 KV（KV_total = 每token × ctx × 并发）；
  ② MLA（DeepSeek 系）KV 按压缩潜变量（kv_lora+rope 维，单潜变量）算，不走 MHA 的 25 倍偏大口径。
本模块纯函数、零 DB 访问、零业务值硬编码；DB 读取在 api/gpu_sizing.py。"""
import math

SYSTEM_RESERVE_GB = 1.5   # 每卡系统预留（Excel 口径）
TIERS_K = [4, 8, 16, 32, 64, 128]   # 上下文档位（展示用）
REC_HEADROOM = 0.30                 # 推荐档规则：余量 ≥30%


def kv_per_token_gb(m: dict, bits: int) -> float:
    """每 token 每 KV 开销(GB)。GQA/MHA 按 Excel；MLA 用压缩潜变量维（kv_lora+rope）。"""
    attn = (m.get("attn") or "GQA").upper()
    if attn == "MLA":
        kv_dim = m.get("mla_latent") or (512 + 64)   # DeepSeek 系默认 kv_lora_rank+qk_rope_dim
        head_bytes = kv_dim                           # K/V 合一存单潜变量
    elif attn == "GQA":
        head_bytes = 2 * (m["kv_heads"] * m["hidden"] // m["heads"])
    else:  # MHA
        head_bytes = 2 * m["hidden"]
    return head_bytes * m["layers"] * bits / 8 / 1024 ** 3


def weight_gb(params_b: float, bits: int, coeff: float = 1.0) -> float:
    return params_b * 1e9 * bits * coeff / 8 / 1024 ** 3


def per_card_usable(cap_gb: float, fw_overhead_gb: float) -> float:
    return cap_gb - SYSTEM_RESERVE_GB - fw_overhead_gb


def need_cards(weight: float, vision_gb: float, kvt: float, ctx: int, batch: int,
               usable: float) -> int:
    """CEILING 卡数（TP 可并的框架）：按场景 ctx×并发 的最小占用反推。"""
    occ = weight + vision_gb + kvt * ctx * batch
    return max(1, math.ceil(occ / usable)) if usable > 0 else 0


def max_ctx(weight: float, vision_gb: float, kvt: float, batch: int, eff: float) -> int:
    denom = kvt * batch
    if denom <= 0 or eff - weight - vision_gb <= 0:
        return 0
    return int((eff - weight - vision_gb) / denom)


def verdict_of(occ_min: float, eff: float, mctx: int) -> str:
    """四档门禁：❌跑不起来 / ⚠️勉强(<4K) / ⚠️可跑需降配 / ✅可以全GPU跑(≥32K)。"""
    if occ_min > eff:
        return "fail"
    if mctx < 4096:
        return "tight"
    if mctx >= 32768:
        return "ok"
    return "downgrade"


def est_tok_s(weight: float, kvt: float, ctx: int, batch: int, bw_gb_s: float) -> float | None:
    """带宽解码估速（总吞吐）：tok/s ≈ 带宽 / 每步读取字节（权重+KV×batch）。无带宽返回 None。"""
    if not bw_gb_s or bw_gb_s <= 0:
        return None
    bytes_per_step = (weight + kvt * ctx * batch) * 1024 ** 3
    return bw_gb_s * 1e9 / bytes_per_step


def recommend_cards(min_cards: int, weight: float, vision_gb: float, kvt: float,
                    ctx: int, batch: int, usable: float) -> int:
    """推荐卡数 = 从最低卡数起升档至余量 ≥30%（单卡满足则不升）。"""
    n = min_cards
    while n < 64:
        eff = usable * n
        occ = weight + vision_gb + kvt * ctx * batch
        if occ <= eff and (1 - occ / eff) >= REC_HEADROOM:
            return n
        n += 1
    return min_cards


def parse_gb(text: str | None) -> float | None:
    """从 spec 值解析容量/带宽数值（'64 GB'→64、'1.8 TB/s'→1800、'2039 GB/s'→2039、'1,344 GB/s'→1344）。"""
    if not text:
        return None
    t = str(text).strip().replace(",", "")
    num = ""
    for ch in t:
        if ch.isdigit() or ch in ".-":
            num += ch
        elif num:
            break
    try:
        v = float(num)
    except ValueError:
        return None
    if "tb" in t.lower():
        v *= 1000
    return v


def spec_value(specs: dict, *keys: str):
    """规范键取值 + 历史小写别名（确定性别名表，非模糊猜测）。"""
    for k in keys:
        if k in specs:
            return specs[k]
    return None


def solve_machine(mach: dict, model: dict, bits: int, coeff: float, fw_overhead: float,
                  ctx: int, batch: int) -> dict:
    """单机型判定。mach: {model_id, name, gpu_name, cap_gb, bw_gb_s, cards}；空卡配置→no_gpu_config。"""
    w = weight_gb(model["params_b"], bits, coeff) + (model.get("vision_gb") or 0)
    kvt = kv_per_token_gb(model, bits)
    base = {"model_id": mach.get("model_id"), "name": mach.get("name"),
            "gpu_name": mach.get("gpu_name"), "cards": mach.get("cards"),
            "cap_gb": mach.get("cap_gb"), "bw_gb_s": mach.get("bw_gb_s")}
    if not mach.get("cap_gb") or not mach.get("cards"):
        return {**base, "status": "no_gpu_config"}
    usable = per_card_usable(mach["cap_gb"], fw_overhead)
    if usable <= 0:
        return {**base, "status": "no_gpu_config"}
    eff = usable * mach["cards"]
    occ_ctx = w + kvt * ctx * batch
    occ_min = w + kvt * 4096 * batch
    mctx = max_ctx(w, 0, kvt, batch, eff)
    v = verdict_of(occ_min, eff, mctx)
    max_conc = int((eff - w) / (kvt * ctx)) if kvt > 0 and eff > w else 0
    speed = est_tok_s(weight_gb(model["params_b"], bits, coeff), kvt, ctx, batch,
                      mach.get("bw_gb_s") or 0)
    return {**base, "status": "ok", "usable_per_card": round(usable, 2), "eff_gb": round(eff, 2),
            "occ_at_ctx": round(occ_ctx, 2), "headroom": round(max(0.0, 1 - occ_ctx / eff), 4),
            "max_ctx": mctx, "max_concurrent": max(0, max_conc),
            "speed_tok_s": round(speed, 1) if speed else None,
            "verdict": v,
            "min_cards": need_cards(weight_gb(model["params_b"], bits, coeff),
                                    model.get("vision_gb") or 0, kvt, ctx, batch, usable),
            }


def tiers_for(weight: float, vision_gb: float, kvt: float, batch: int, eff: float,
              usable: float, rec_ctx: int, native_max_ctx: int | None) -> list:
    """档位数组：每档 fits（按 CEILING 卡数放不放得下）/ best（命中场景推荐档）/ 超原生上限。"""
    out = []
    for k in TIERS_K:
        ctx = k * 1024
        cards = need_cards(weight, vision_gb, kvt, ctx, batch, usable)
        fits = (weight + vision_gb + kvt * ctx * batch) <= usable * max(cards, 1)
        over_native = native_max_ctx is not None and ctx > native_max_ctx
        out.append({"k": k, "fits": fits and not over_native, "cards": cards,
                    "best": ctx == rec_ctx or (rec_ctx and abs(math.log2(ctx / rec_ctx)) < 0.01)})
    return out
