# -*- coding: utf-8 -*-
"""model_reason 短路判定单测：点名机型不在目录 → 跳过 ReAct 直走规则降级（白盒省时）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unittest.mock import patch
from app.services.capabilities import _named_model_not_in_catalog

REQ = "AI算力服务器：联想 WA5480 G3、2×Intel 6530至强5代、8×RTX 5090 32G涡轮、16×DDR5 64G 5600、960GB SATA SSD + 2×3.84TB NVMe U.2、25G网卡、4×2700W、RAID卡、光模块"
GEN = "我要一台 2U 通用服务器，Intel 平台，32G 内存"
DETAIL = "2U 通用计算服务器，AMD EPYC 9654，64G*16，2*960G SSD，预算20万"
IN_CATALOG = "要一台 ESA24V3-P AI 服务器，8 卡"


def test_named_model_not_in_catalog_positive():
    """点名具体机型（WA5480 G3）且不在在售目录 → True（短路 ReAct）。"""
    with patch("app.services.catalog_guide.load_catalog") as m:
        m.return_value = ([], {"AI": [{"name": "ESA24V3-P"}, {"name": "ZSA24V2-P"}]})
        assert _named_model_not_in_catalog(REQ, {}, {}) is True


def test_no_model_code_false_positive_guard():
    """带单位规格/纯数字（32G/5090/5600）不是点名机型 → False。"""
    with patch("app.services.catalog_guide.load_catalog") as m:
        m.return_value = ([], {"AI": [{"name": "ESA24V3-P"}]})
        assert _named_model_not_in_catalog(GEN, {}, {}) is False
        assert _named_model_not_in_catalog(DETAIL, {}, {}) is False


def test_in_catalog_model_not_shortcut():
    """命中在售机型名（ESA24V3-P）→ False（ReAct 有意义：选它）。"""
    with patch("app.services.catalog_guide.load_catalog") as m:
        m.return_value = ([], {"AI": [{"name": "ESA24V3-P"}]})
        assert _named_model_not_in_catalog(IN_CATALOG, {}, {}) is False


def test_custom_token_pattern_configurable():
    """检测正则可配（model_missing_token_pattern），空=用默认机型代码特征。"""
    with patch("app.services.catalog_guide.load_catalog") as m:
        m.return_value = ([], {"AI": [{"name": "ESA24V3-P"}]})
        # 自定义只认「联想」开头 → WA5480 不命中 → False（用户收紧/放宽可配）
        assert _named_model_not_in_catalog(REQ, {"model_missing_token_pattern": r"联想[A-Za-z0-9]+"}, {}) is False
