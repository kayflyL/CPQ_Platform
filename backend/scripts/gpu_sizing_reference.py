# -*- coding: utf-8 -*-
"""
gpu_sizing 参照实现 —— 逐格复刻《本地大模型部署GPU配置器 v10.xlsx》公式,作为校对基准。
公式出处(Excel 单元格):
  权重   C35 = C18*1e9*C33*C34/8/1024^3          参数量×bit×框架系数/8
  KV/tok C36 = GQA: 2*(kv_heads*hidden/heads)*layers*bits/8/1024^3
              否则 MHA: 2*hidden*layers*bits/8/1024^3      (MLA 在 Excel 里落 MHA 分支=偏保守,本实现附 MLA 修正)
  有效显存 C39 = (支持TP ? 单卡*卡数 : 单卡) - 1.5(系统) - 框架开销
  门禁   C42: min占用(4K)>有效 → ❌;maxctx<4K → ⚠️勉强;>=32K → ✅;否则 ⚠️降配
  卡数   C47 = CEILING(min占用/单卡可用)   (仅支持TP的框架)
档位可行性速查表校验锚点(表内缓存值):
  Qwen2.5-7B @8bit vLLM 128GB卡×1 → KV@4K=0.109375G, 总占用=6.628633G, 有效=125.5G
"""
import math

def kv_per_token_gb(m: dict, bits: int, attn_override: str | None = None) -> float:
    """每 token KV 开销(GB)。GQA/MHA 按 Excel;MLA 用压缩潜变量维(kv_lora+rope)。"""
    attn = attn_override or m.get("attn", "GQA")
    if attn == "MLA":
        kv_dim = m.get("mla_latent", 512 + 64)          # DeepSeek 系:kv_lora_rank+qk_rope_dim
        head_bytes = kv_dim                              # K/V 合一存单潜变量
    elif attn == "GQA":
        head_bytes = 2 * (m["kv_heads"] * m["hidden"] // m["heads"])
    else:  # MHA
        head_bytes = 2 * m["hidden"]
    return head_bytes * m["layers"] * bits / 8 / 1024**3

def weight_gb(params_b: float, bits: int, coeff: float = 1.0) -> float:
    return params_b * 1e9 * bits * coeff / 8 / 1024**3

def effective_gb(vram: float, cards: int, fw_overhead: float, tp_ok: bool):
    per = vram - 1.5 - fw_overhead
    return per * cards if tp_ok else per, per

def gate(model: dict, bits: int, coeff: float, vram: float, cards: int,
         fw_overhead: float, tp_ok: bool, batch: int = 1):
    w = weight_gb(model["params"], bits, coeff)
    kvt = kv_per_token_gb(model, bits)
    eff, per = effective_gb(vram, cards, fw_overhead, tp_ok)
    min_occ = w + kvt * 4096 * batch                       # Excel 口径:最小占用按4K
    max_ctx = 0 if eff - w <= 0 else (eff - w) / (kvt * batch)
    need_cards = None if not tp_ok else math.ceil((w + kvt * 4096 * batch) / per)
    if min_occ > eff:            verdict = "❌ 跑不起来"
    elif max_ctx < 4096:         verdict = "⚠️ 勉强(<4K ctx)"
    elif max_ctx >= 32768:       verdict = "✅ 可以全GPU跑(32K+)"
    else:                        verdict = "⚠️ 可跑需降配"
    return dict(weight=round(w, 3), kv_per_tok_gb=kvt, eff=round(eff, 3),
                min_occ=round(min_occ, 3), max_ctx=int(max_ctx),
                need_cards=need_cards, verdict=verdict)

# 带宽解码估速(GPU-Poor 思路,借鉴项):tok/s ≈ 显存带宽 / 每token读取字节
def est_tok_s(model: dict, bits: int, coeff: float, ctx: int, batch: int, bw_tbps: float):
    bytes_per_tok = weight_gb(model["params"], bits, coeff) * 1024**3 \
        + kv_per_token_gb(model, bits) * ctx * batch * 1024**3
    return bw_tbps * 1e12 / bytes_per_tok

if __name__ == "__main__":
    Q7  = dict(params=7,  hidden=3584, layers=28, heads=28, kv_heads=4, attn="GQA")
    Q72 = dict(params=72, hidden=8192, layers=80, heads=64, kv_heads=8, attn="GQA")
    QP235 = dict(params=235, hidden=8192, layers=80, heads=64, kv_heads=8, attn="GQA")
    DSV3  = dict(params=671, hidden=7168, layers=61, heads=128, kv_heads=1,
                 attn="MLA", mla_latent=512 + 64)

    print("== 校验1:复刻速查表锚点(Qwen2.5-7B@8bit vLLM 128G卡×1) ==")
    r = gate(Q7, 8, 1.0, 128, 1, 1.0, True)
    print(f"  KV@4K={r['kv_per_tok_gb']*4096:.6f}G (表值0.109375)  "
          f"总占用={r['min_occ']:.6f}G (表值6.628633)  有效={r['eff']}G (表值125.5)")

    print("== 校验2:原型③演示数(Qwen2.5-72B@8bit vLLM 沐曦C500-64G) ==")
    for cards, batch in [(2, 4), (1, 1)]:
        r = gate(Q72, 8, 1.0, 64, cards, 1.0, True, batch)
        sp = est_tok_s(Q72, 8, 1.0, 65536, batch, 1.8)
        print(f"  {cards}卡×并发{batch}: 权重{r['weight']}G KV@64K={r['kv_per_tok_gb']*65536:.1f}G "
              f"min={r['min_occ']}G eff={r['eff']}G maxctx={r['max_ctx']} 需卡{r['need_cards']}"
              f" {'带宽估速(64K)' if cards==2 else '估速'}≈{sp:.0f}tok/s  {r['verdict']}")

    print("== 校验3:原型②演示数(Qwen3-235B@8bit) ==")
    for cards in (8, 4):
        r = gate(QP235, 8, 1.0, 64, cards, 1.0, True)
        print(f"  {cards}×C500: 权重{r['weight']}G KV@64K={r['kv_per_tok_gb']*65536:.1f}G "
              f"eff={r['eff']}G maxctx={r['max_ctx']} 需卡{r['need_cards']}  {r['verdict']}")

    print("== 校验4:MLA 修正对比(DeepSeek-V3@8bit 8×C500) ==")
    r_mla = gate(DSV3, 8, 1.0, 64, 8, 1.0, True)
    r_xls = gate(DSV3, 8, 1.0, 64, 8, 1.0, True, ) if False else None
    import copy
    dsv_xls = copy.copy(DSV3); dsv_xls["attn"] = "MHA"   # Excel 实际走的分支
    r_xls = gate(dsv_xls, 8, 1.0, 64, 8, 1.0, True)
    print(f"  MLA修正: KV/tok={r_mla['kv_per_tok_gb']*1024**3/1024:.0f}KB 权重{r_mla['weight']}G {r_mla['verdict']}")
    print(f"  Excel口径: KV/tok={r_xls['kv_per_tok_gb']*1024**3/1024:.0f}KB 权重{r_xls['weight']}G {r_xls['verdict']}")
