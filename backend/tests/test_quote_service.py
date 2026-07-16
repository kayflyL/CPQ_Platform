"""Tests for QuoteService."""
import pytest
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
from app.services.quote_service import QuoteService


class TestQuoteServiceInit:
    """Test QuoteService initialization."""

    def test_init_creates_repos(self):
        """Test QuoteService initializes all repositories."""
        with patch('app.services.quote_service.KPRepository') as mock_kp, \
             patch('app.services.quote_service.L6Repository') as mock_l6, \
             patch('app.services.quote_service.ProjectRepository') as mock_project, \
             patch('app.services.quote_service.RulesRepository') as mock_rules, \
             patch('app.services.quote_service.ExportTemplateRepository') as mock_export:
            
            service = QuoteService()
            
            assert service.kp_repo is not None
            assert service.l6_repo is not None
            assert service.project_repo is not None
            assert service.rules_repo is not None

            assert service.engine is not None


class TestLoadConfig:
    """Test configuration loading."""

    def test_load_config_file_exists(self, tmp_path):
        """Test loading config from existing file."""
        config_data = {
            "tax_rate": 0.13,
            "usd_to_rmb": 7.0,
            "profit_margin": 0.1,
            "warranty_fee_rate": 0.02
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))
        
        with patch('app.services.quote_service.CONFIG_PATH', config_file):
            with patch('app.services.quote_service.KPRepository'), \
                 patch('app.services.quote_service.L6Repository'), \
                 patch('app.services.quote_service.ProjectRepository'), \
                 patch('app.services.quote_service.RulesRepository'), \
                 patch('app.services.quote_service.ExportTemplateRepository'):
                
                service = QuoteService()
                assert service.config['tax_rate'] == 0.13
                assert service.config['usd_to_rmb'] == 7.0

    def test_load_config_file_not_exists(self):
        """Test loading default config when file doesn't exist."""
        with patch('app.services.quote_service.CONFIG_PATH', Path('/nonexistent/config.json')):
            with patch('app.services.quote_service.KPRepository'), \
                 patch('app.services.quote_service.L6Repository'), \
                 patch('app.services.quote_service.ProjectRepository'), \
                 patch('app.services.quote_service.RulesRepository'), \
                 patch('app.services.quote_service.ExportTemplateRepository'):
                
                service = QuoteService()
                # Should have default values
                assert 'tax_rate' in service.config
                assert 'usd_to_rmb' in service.config
                assert 'profit_margin' in service.config


class TestProcessUpload:
    """Test Excel upload processing."""

    def test_process_upload_basic(self):
        """Test basic upload processing flow."""
        with patch('app.services.quote_service.KPRepository'), \
             patch('app.services.quote_service.L6Repository'), \
             patch('app.services.quote_service.ProjectRepository'), \
             patch('app.services.quote_service.RulesRepository'), \
             patch('app.services.quote_service.ExportTemplateRepository'):
            
            service = QuoteService()
            
            # Mock engine methods
            service.engine.parse_file = MagicMock(return_value=({}, None))
            
            # Create dummy Excel content
            excel_content = b"dummy excel content"
            
            # Process upload
            result = service.process_upload(excel_content, "test.xlsx")
            
            # Should return a result dict
            assert isinstance(result, dict)
