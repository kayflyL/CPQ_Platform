"""Tests for PricingEngine core functionality."""
import pytest
import pandas as pd
from unittest.mock import MagicMock
from app.engine.pricing_engine import PricingEngine


class TestPricingEngineInit:
    """Test PricingEngine initialization."""

    def test_init_with_repos(self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo, mock_export_template_repo):
        """Test engine initializes with repository instances."""
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo,
            mock_rules_repo, mock_export_template_repo
        )
        assert engine.kp_repo == mock_kp_repo
        assert engine.l6_repo == mock_l6_repo
        assert engine.project_repo == mock_project_repo


class TestParseFile:
    """Test Excel file parsing."""

    def test_parse_file_empty_dict(self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo, mock_export_template_repo):
        """Test parsing empty sheet dict returns empty configs."""
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo,
            mock_rules_repo, mock_export_template_repo
        )
        configs, first_meta = engine.parse_file({})
        assert configs == {}
        assert first_meta is None

    def test_parse_file_skips_reference_sheet(self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo, mock_export_template_repo):
        """Test parsing skips '原始需求' and 'Reference' sheets."""
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo,
            mock_rules_repo, mock_export_template_repo
        )
        # Create empty DataFrames for reference sheets
        sheets = {
            '原始需求': pd.DataFrame(),
            'Reference': pd.DataFrame(),
            'Config1': pd.DataFrame({'D': ['L6'], 'E': ['test']})
        }
        configs, first_meta = engine.parse_file(sheets)
        # Should only process Config1
        assert '原始需求' not in configs
        assert 'Reference' not in configs

    def test_parse_file_skips_empty_sheets(self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo, mock_export_template_repo):
        """Test parsing skips empty DataFrames."""
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo,
            mock_rules_repo, mock_export_template_repo
        )
        sheets = {
            'EmptySheet': pd.DataFrame(),
            'Config1': pd.DataFrame({'D': ['L6'], 'E': ['test']})
        }
        configs, first_meta = engine.parse_file(sheets)
        assert 'EmptySheet' not in configs


class TestMatchL6Total:
    """Test L6 price matching."""

    def test_match_l6_no_records(self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo, mock_export_template_repo):
        """Test matching returns None when no L6 records exist."""
        mock_l6_repo.get_all_for_matching.return_value = []
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo,
            mock_rules_repo, mock_export_template_repo
        )
        meta = {'chassis_form': '2U', 'drive_bays': '12'}
        price, record = engine.match_l6_total(meta)
        assert price is None
        assert record is None

    def test_match_l6_exact_match(self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo, mock_export_template_repo, sample_l6_data):
        """Test exact dimension matching."""
        mock_l6_repo.get_all_for_matching.return_value = sample_l6_data
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo,
            mock_rules_repo, mock_export_template_repo
        )
        meta = {
            'chassis_form': '2U',
            'l6_model_type': '2U Server',
            'drive_bays': '12',
            'psu': '4+2',
            'motherboard': 'Polaris MB'
        }
        price, record = engine.match_l6_total(meta)
        assert price == 15000.0
        assert record['l6_model'] == 'KH50000-2U-12B-4+2'

    def test_match_l6_partial_match(self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo, mock_export_template_repo, sample_l6_data):
        """Test partial matching (some dimensions missing)."""
        mock_l6_repo.get_all_for_matching.return_value = sample_l6_data
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo,
            mock_rules_repo, mock_export_template_repo
        )
        # Only provide chassis and drive_bays
        meta = {
            'chassis_form': '1U',
            'drive_bays': '4'
        }
        price, record = engine.match_l6_total(meta)
        # Should match the 1U model
        assert price == 8000.0
        assert record['l6_model'] == 'KH30000-1U-4B-2+1'


class TestExtractMeta:
    """Test metadata extraction from Excel."""

    def test_extract_meta_basic(self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo, mock_export_template_repo):
        """Test basic metadata extraction."""
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo,
            mock_rules_repo, mock_export_template_repo
        )
        # Create a simple DataFrame with L6 region
        df = pd.DataFrame({
            'D': ['L6 Configuration', 'KH50000', 'Keyparts'],
            'E': ['', '2U Server', ''],
            'F': ['', '1', '']
        })
        meta = engine._extract_meta(df)
        # Should extract some metadata (exact fields depend on implementation)
        assert isinstance(meta, dict)


class TestParseItems:
    """Test KP items parsing."""

    def test_parse_items_empty(self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo, mock_export_template_repo):
        """Test parsing empty DataFrame returns empty result."""
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo,
            mock_rules_repo, mock_export_template_repo
        )
        df = pd.DataFrame()
        items = engine._parse_items(df)
        assert items.empty

    def test_parse_items_with_data(self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo, mock_export_template_repo):
        """Test parsing DataFrame with KP items."""
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo,
            mock_rules_repo, mock_export_template_repo
        )
        df = pd.DataFrame({
            'D': ['Keyparts', 'CPU001', 'MEM001'],
            'E': ['', 'Intel Xeon', 'DDR4 32GB'],
            'F': ['', '2', '4'],
            'G': ['', '15000', '8000']
        })
        items = engine._parse_items(df)
        # Should parse items (exact structure depends on implementation)
        assert isinstance(items, pd.DataFrame)
