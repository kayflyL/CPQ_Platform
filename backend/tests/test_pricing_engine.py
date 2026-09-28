"""Tests for PricingEngine core functionality."""
import pytest
import pandas as pd
from unittest.mock import MagicMock
from app.engine.pricing_engine import PricingEngine


class TestPricingEngineInit:
    """Test PricingEngine initialization."""

    def test_init_with_repos(self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo):
        """Test engine initializes with repository instances."""
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo,
            mock_rules_repo
        )
        assert engine.kp_repo == mock_kp_repo
        assert engine.l6_repo == mock_l6_repo
        assert engine.opportunity_repo == mock_project_repo


class TestParseFile:
    """Test Excel file parsing."""

    def test_parse_file_empty_dict(self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo):
        """Test parsing empty sheet dict returns empty configs."""
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo,
            mock_rules_repo
        )
        configs, first_meta = engine.parse_file({})
        assert configs == {}
        assert first_meta is None

    def test_parse_file_skips_reference_sheet(self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo):
        """Test parsing skips '原始需求' and 'Reference' sheets."""
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo,
            mock_rules_repo
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

    def test_parse_file_skips_empty_sheets(self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo):
        """Test parsing skips empty DataFrames."""
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo,
            mock_rules_repo
        )
        sheets = {
            'EmptySheet': pd.DataFrame(),
            'Config1': pd.DataFrame({'D': ['L6'], 'E': ['test']})
        }
        configs, first_meta = engine.parse_file(sheets)
        assert 'EmptySheet' not in configs


class TestRegionKeyCompatibility:
    """ExcelParser 将 dynamic_regions 键统一为小写 region_key 后，计价引擎仍需兼容读取。"""

    def test_convert_parser_items_reads_lowercase_region_keys(
        self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo
    ):
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo
        )
        dynamic_regions = {
            "kp": [
                {"kp_category": "CPU", "kp_model": "AMD EPYC 9654", "kp_price": "1000", "qty": 2}
            ],
            "warranty": [
                {"part_name": "Warranty", "description": "3 years onsite"}
            ],
        }

        items = engine._convert_parser_items(dynamic_regions)

        assert len(items) == 2
        assert items.iloc[0]["catalogue"] == "AMD EPYC 9654"
        assert items.iloc[0]["part_category"] == "CPU"
        assert items.iloc[0]["qty"] == 2
        assert items.iloc[1]["category"] == "Warranty"

    def test_convert_l6_rows_reads_lowercase_region_key(
        self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo
    ):
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo
        )
        dynamic_regions = {
            "l6": [
                {"l6_chassis": "2U Server", "spec": "2*KH-50000", "qty": 1}
            ],
        }

        rows = engine._convert_l6_rows(dynamic_regions)

        assert rows == [
            {"category": "L6", "catalogue": "2U Server", "description": "2*KH-50000", "qty": 1}
        ]

    def test_get_region_rows_returns_empty_for_missing_region(self):
        assert PricingEngine._get_region_rows({}, "L6", "l6") == []


class TestParserMetaMapping:
    """静态字段应归一成 service 层可消费的 meta 契约。"""

    def test_server_model_and_description_are_normalized(
        self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo
    ):
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo
        )
        static_fields = {
            "server_model": {"value": "ZSA240 V2(1pcs)"},
            "description": {"value": "1*4U KH50000 switch机型"},
        }

        meta = engine._convert_parser_meta(static_fields)

        assert meta["server_model"] == "ZSA240 V2"
        assert meta["model_qty"] == 1
        assert meta["description"] == "1*4U KH50000 switch机型"
        assert meta["l6_desc"] == meta["description"]

    def test_legacy_model_name_still_maps_to_server_model(
        self, mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo
    ):
        engine = PricingEngine(
            mock_kp_repo, mock_l6_repo, mock_project_repo, mock_rules_repo
        )
        meta = engine._convert_parser_meta({"model_name": {"value": "KH50000-2U(2pcs)"}})

        assert meta["server_model"] == "KH50000-2U"
        assert meta["model_name"] == "KH50000-2U"
        assert meta["model_qty"] == 2
