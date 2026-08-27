# -*- coding: utf-8 -*-
"""case_provider 检索单测：归一化 / 字符 2+3-gram / TF-IDF 加权 / retrieve 排序。

纯函数不碰 DB；retrieve 用 mock session（不碰真库），可 pytest 跑，
也可 `python -X utf8 tests/test_case_provider.py` 自跑。
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import case_provider as cp
# 提前导入规则库模块，避免 test 的 Rules_SessionLocal mock 在惰性首次导入时
# 污染 requirement_rule_repo 的会话类绑定（否则后续配件工具规则读取会拿到 mock 返回空）。
import app.services.requirement_rule_catalog  # noqa: F401


# ── 归一化 / 2+3-gram ────────────────────────────────────────────────

def test_normalize_keeps_cjk_alnum_drops_noise():
    assert cp._normalize("AI 训练服务器！8×GPU_测试") == "ai训练服务器8gpu测试"
    assert cp._normalize("  GPU  ") == "gpu"
    assert cp._normalize("") == ""


def test_tokenize_2_3_gram_counts():
    toks = cp._tokenize("GPU服务器")
    # 3-gram 保英文词 gpu；2-gram 也覆盖相邻字符
    assert toks["gpu"] == 1
    assert toks["gp"] == 1 and toks["pu"] == 1
    assert toks["服务"] == 1 and toks["务器"] == 1
    # 归一化后 6 字符（gpu + 服务器）→ 2-gram 5 个 + 3-gram 4 个
    assert sum(toks.values()) == 5 + 4


# ── TF-IDF 加权 ──────────────────────────────────────────────────────

def _scores_for(corpus, query):
    vecs, idf, max_idf, norms = cp._build_index(corpus)
    q = cp._tokenize(query)
    return [cp._kw_score(q, vecs[i], norms[i], idf, max_idf) for i in range(len(corpus))]


def test_tfidf_ranks_similar_higher():
    corpus = [
        "AI 深度学习训练服务器",
        "办公 数据库 服务器 虚拟化",
        "通用 办公 业务 服务器",
    ]
    scores = _scores_for(corpus, "深度学习训练服务器")
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]


def test_tfidf_rare_phrase_beats_common_gram():
    """「深度学习」只出现在一条 → IDF 高；仅共享「服务器」拉不动分。"""
    corpus = [
        "AI 深度学习训练服务器 8卡 GPU",
        "办公 数据库 服务器 虚拟化",
        "通用 办公 业务 服务器",
    ]
    scores = _scores_for(corpus, "深度学习训练")
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]
    # 只含"服务器"的案例得分应明显低于含"深度学习"的
    assert scores[1] < scores[0] * 0.5


def test_english_word_3gram_matches():
    corpus = ["AI 8卡 GPU 训练服务器", "办公 数据库 服务器"]
    scores = _scores_for(corpus, "GPU 训练")
    assert scores[0] > scores[1]


# ── retrieve（mock session，不碰真库）────────────────────────────────

def _mock_session(cases):
    fake = MagicMock()
    fake.query.return_value.filter.return_value.all.return_value = cases
    return fake


def _case(requirement, tags=None, l6=None, kp=None):
    return SimpleNamespace(
        scenario_tags=tags or [],
        requirement=requirement,
        l6_rows=l6 or [],
        kp_lines=kp or [],
    )


def test_retrieve_ranks_tags_plus_tfidf():
    cases = [
        _case("AI 8卡 GPU 深度学习训练服务器", tags=["AI", "8卡GPU"]),  # 标签+文本都命中
        _case("AI 服务器 通用办公", tags=["通用"]),                     # 标签不同、文本弱重叠
        _case("AI 8卡 GPU 深度学习训练服务器", tags=[]),               # 文本相似但无标签
    ]
    with patch("app.models.base.Rules_SessionLocal", return_value=_mock_session(cases)):
        prov = cp.InternalBomCaseProvider()
        res = prov.retrieve("AI 8卡GPU 深度学习训练", top_k=3)
    # 全 3 条都有得分；标签命中 + 文本最相似的排最前
    assert len(res) == 3
    assert res[0]["requirement"] == cases[0].requirement
    # 无标签但文本强相似的，排在只有标签的通用案例之前
    assert res[1]["requirement"] == cases[2].requirement
    assert res[2]["requirement"] == cases[1].requirement


def test_retrieve_tags_mode_only_tag_overlap():
    cases = [
        _case("AI 深度学习训练服务器", tags=["AI"]),
        _case("办公 数据库 服务器", tags=["通用"]),
        _case("AI 深度学习训练服务器", tags=[]),
    ]
    with patch("app.models.base.Rules_SessionLocal", return_value=_mock_session(cases)):
        prov = cp.InternalBomCaseProvider(match="tags")
        res = prov.retrieve("深度学习训练", tags=["AI"], top_k=3)
    assert len(res) == 1 and res[0]["requirement"] == cases[0].requirement


def test_retrieve_empty_query_still_tag_matches():
    """query 为空 → 余弦为 0，但标签命中仍能出结果（不崩、不退零样本）。"""
    cases = [
        _case("AI 深度学习训练服务器", tags=["AI"]),
        _case("办公 数据库 服务器", tags=["通用"]),
    ]
    with patch("app.models.base.Rules_SessionLocal", return_value=_mock_session(cases)):
        prov = cp.InternalBomCaseProvider()
        res = prov.retrieve("", tags=["AI"], top_k=2)
    assert len(res) == 1 and res[0]["requirement"] == cases[0].requirement


def test_retrieve_no_match_returns_empty():
    cases = [_case("办公 数据库 服务器", tags=["通用"])]
    with patch("app.models.base.Rules_SessionLocal", return_value=_mock_session(cases)):
        prov = cp.InternalBomCaseProvider()
        res = prov.retrieve("存储 NAS 大容量", tags=["存储"], top_k=2)
    assert res == []


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  ✅ {fn.__name__}"); passed += 1
        except Exception:
            print(f"  ❌ {fn.__name__}"); traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
