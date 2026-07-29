"""Tests for QuoteService."""
import pandas as pd
from unittest.mock import MagicMock, patch
from app.services.quote_service import QuoteService


# quote_service 现在依赖这些 repo（名字与 import 一致）；SystemConfigRepository 在
# _load_config 内懒 import，patch 其源类即可。CONFIG_PATH 文件加载早已废弃，config 走 DB。
def _repo_and_sys_ctx():
    """返回一个上下文管理器组合：patch 4 个 repo + SystemConfigRepository（DB 给默认值）。"""
    from contextlib import ExitStack
    stack = ExitStack()
    mock_sys = stack.enter_context(patch('app.repository.system_config_repo.SystemConfigRepository'))
    mock_sys.return_value.get_value.side_effect = lambda k, d=None: d
    stack.enter_context(patch.multiple(
        'app.services.quote_service',
        KPRepository=MagicMock(),
        L6ChassisRepository=MagicMock(),
        OpportunityRepository=MagicMock(),
        RulesRepository=MagicMock(),
    ))
    return stack


class TestQuoteServiceInit:
    """Test QuoteService initialization."""

    def test_init_creates_repos(self):
        """Test QuoteService initializes all repositories + engine."""
        with _repo_and_sys_ctx():
            service = QuoteService()
            assert service.kp_repo is not None
            assert service.l6_repo is not None
            assert service.opportunity_repo is not None
            assert service.rules_repo is not None
            assert service.engine is not None
            assert isinstance(service.config, dict)


class TestLoadConfig:
    """配置从 system_config DB 加载（不再走 CONFIG_PATH 文件）。"""

    def test_load_config_uses_db_values(self):
        """get_value 的值应透传到 service.config。"""
        with patch('app.repository.system_config_repo.SystemConfigRepository') as mock_sys, \
             patch.multiple('app.services.quote_service',
                            KPRepository=MagicMock(), L6ChassisRepository=MagicMock(),
                            OpportunityRepository=MagicMock(), RulesRepository=MagicMock()):
            mock_sys.return_value.get_value.side_effect = lambda k, d=None: {
                'tax_rate': 0.13, 'usd_to_rmb': 7.0, 'profit_margin': 0.1,
                'warranty_fee_rate': 0.02
            }.get(k, d)
            service = QuoteService()
            assert service.config['tax_rate'] == 0.13
            assert service.config['usd_to_rmb'] == 7.0

    def test_load_config_falls_back_to_defaults(self):
        """DB 无值时回落默认。"""
        with _repo_and_sys_ctx():
            service = QuoteService()
            assert 'tax_rate' in service.config
            assert 'usd_to_rmb' in service.config
            assert 'profit_margin' in service.config


class TestProcessUpload:
    """Test Excel upload processing flow."""

    def test_process_upload_basic(self):
        with _repo_and_sys_ctx():
            service = QuoteService()
            service.engine.parse_file = MagicMock(return_value=({}, None))
            # 跳过真实 excel 解析（假字节无法 read_excel）
            with patch('app.services.quote_service.pd.read_excel', return_value={}):
                result = service.process_upload(b"dummy excel content", "test.xlsx")
            assert isinstance(result, dict)
