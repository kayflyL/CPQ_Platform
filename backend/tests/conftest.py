"""Pytest configuration and fixtures."""
import sys
import os
from pathlib import Path
import pytest
import pandas as pd
from unittest.mock import MagicMock

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_kp_repo():
    """Mock KPRepository."""
    repo = MagicMock()
    repo.get_all.return_value = []
    return repo


@pytest.fixture
def mock_l6_repo():
    """Mock L6Repository."""
    repo = MagicMock()
    return repo


@pytest.fixture
def mock_project_repo():
    """Mock ProjectRepository."""
    return MagicMock()


@pytest.fixture
def mock_rules_repo():
    """Mock RulesRepository."""
    repo = MagicMock()
    repo.get_all.return_value = []
    return repo




@pytest.fixture
def sample_l6_data():
    """Sample L6 data for matching tests."""
    return [
        {
            'l6_model': 'KH50000-2U-12B-4+2',
            'chassis': '2U',
            'model': '2U Server',
            'drive_bays': '12',
            'psu': '4+2',
            'motherboard': 'Polaris MB',
            'price': 15000.0
        },
        {
            'l6_model': 'KH30000-1U-4B-2+1',
            'chassis': '1U',
            'model': '1U Server',
            'drive_bays': '4',
            'psu': '2+1',
            'motherboard': 'Orion MB',
            'price': 8000.0
        }
    ]


@pytest.fixture
def sample_kp_data():
    """Sample KP data."""
    return [
        {
            'catalogue': 'CPU001',
            'model': 'Intel Xeon Gold 6248',
            'category': 'CPU',
            'price': 15000.0,
            'currency': 'RMB'
        },
        {
            'catalogue': 'MEM001',
            'model': 'DDR4 32GB 2933',
            'category': 'Memory',
            'price': 2000.0,
            'currency': 'RMB'
        }
    ]


@pytest.fixture
def sample_excel_df():
    """Sample Excel DataFrame for parse tests."""
    data = {
        'D': ['L6 Configuration', 'KH50000-2U-12B', 'Keyparts', 'CPU001', 'MEM001'],
        'E': ['', '2U Server', '', 'Intel Xeon Gold 6248', 'DDR4 32GB'],
        'F': ['', '1', '', '2', '4'],
        'G': ['', '', '', '15000', '8000']
    }
    return pd.DataFrame(data)
