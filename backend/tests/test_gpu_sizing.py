# -*- coding: utf-8 -*-
"""gpu_sizing 计算内核单测 —— 锚点=用户 Excel v10 速查表缓存值 + 两个科学修正 + 推荐档规则。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.services.gpu_sizing import (  # noqa: E402
    kv_per_token_gb, weight_gb, per_card_usable, need_cards, max_ctx, verdict_of,
    est_tok_s, recommend_cards, parse_gb, solve_machine, SYSTEM_RESERVE_GB,
)

Q7 = dict(params_b=7, hidden=3584, layers=28, heads=28, kv_heads=4, attn="GQA")
Q72 = dict(params_b=72, hidden=8192, layers=80, heads=64, kv_heads=8, attn="GQA")
DSV3 = dict(params_b=671, hidden=7168, layers=61, heads=128, kv_heads=1,
            attn="MLA", mla_latent=576)


def test_anchor_excel_q7_8bit_vllm_128g():
    """锚点：Excel 速查表缓存值 KV@4K=0.109375G / 总占用=6.628633G / 有效=125.5G。"""
    kvt = kv_per_token_gb(Q7, 8)
    assert abs(kvt * 4096 - 0.109375) < 1e-9
    usable = per_card_usable(128, 1.0)
    assert abs(usable - (128 - SYSTEM_RESERVE_GB - 1.0)) < 1e-9
    w = weight_gb(7, 8, 1.0)
    assert abs(w + kvt * 4096 * 1 - 6.628633) < 1e-5   # Excel 最小占用（batch=1）
    assert abs(usable * 1 - 125.5) < 1e-9


def test_concurrency_multiplies_kv():
    """修正①：并发乘进 KV。72B@8bit 并发4@64K = 40.03G；2×C500 有效 123G 时 max_ctx≈91.7K。"""
    kvt = kv_per_token_gb(Q72, 8)
    assert abs(kvt * 65536 * 4 - 40.0) < 0.01
    eff = per_card_usable(64, 1.0) * 2
    mctx = max_ctx(weight_gb(72, 8), 0, kvt, 4, eff)
    assert 90000 <= mctx <= 93000


def test_mla_compression_fix():
    """修正②：DSV3 MLA 按 576 维潜变量 ≈32.5KB/tok；Excel 落 MHA 分支 854KB/tok（偏大26倍）。"""
    kvt_mla = kv_per_token_gb(DSV3, 8) * 1024 ** 3 / 1024
    dsv_mha = {**DSV3, "attn": "MHA"}
    kvt_mha = kv_per_token_gb(dsv_mha, 8) * 1024 ** 3 / 1024
    assert 30 <= kvt_mla <= 35
    assert 850 <= kvt_mha <= 860
    assert 20 <= kvt_mha / kvt_mla <= 30


def test_recommend_cards_headroom_rule():
    """推荐档规则：最低卡数=CEILING(场景占用/单卡可用)；推荐=升档至余量≥30%。
    5090(32G) 跑 72B@8bit 64K×并发4：最低 4（余 9%）、推荐 6（余 39%）。"""
    usable = per_card_usable(32, 1.0)
    w = weight_gb(72, 8)
    kvt = kv_per_token_gb(Q72, 8)
    min_cards = need_cards(w, 0, kvt, 65536, 4, usable)
    rec = recommend_cards(min_cards, w, 0, kvt, 65536, 4, usable)
    assert min_cards == 4
    assert rec == 6


def test_verdict_tiers():
    assert verdict_of(occ_min=200, eff=100, mctx=99999) == "fail"
    assert verdict_of(occ_min=10, eff=100, mctx=2048) == "tight"
    assert verdict_of(occ_min=10, eff=100, mctx=16384) == "downgrade"
    assert verdict_of(occ_min=10, eff=100, mctx=65536) == "ok"


def test_speed_and_parse():
    w = weight_gb(72, 8)
    kvt = kv_per_token_gb(Q72, 8)
    sp = est_tok_s(w, kvt, 65536, 4, 1800)
    assert sp is not None and 14 <= sp <= 18          # C500 1.8TB/s ≈16 tok/s 总吞吐
    assert est_tok_s(w, kvt, 65536, 4, 0) is None
    assert parse_gb("64 GB") == 64
    assert parse_gb("1.8 TB/s") == 1800
    assert parse_gb("2039 GB/s") == 2039
    assert parse_gb("待核") is None


def test_solve_machine_no_gpu_config():
    r = solve_machine({"model_id": 6, "name": "ES220 V3", "cards": 0},
                      Q72, 8, 1.0, 1.0, 65536, 4)
    assert r["status"] == "no_gpu_config"
