"""Unit tests for TushareIndustryAdapter without real API calls."""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from packages.adapters.tushare_industry_adapter import TushareIndustryAdapter


def _make_adapter(mock_pro):
    """Return adapter with a mocked tushare pro_api."""
    with patch("packages.adapters.tushare_industry_adapter.ts.pro_api", return_value=mock_pro):
        adapter = TushareIndustryAdapter(token="fake_token")
    return adapter


def test_init_without_token_raises():
    with patch("packages.adapters.tushare_industry_adapter.os.getenv", return_value=None):
        with pytest.raises(ValueError):
            TushareIndustryAdapter()


def test_find_concept_codes():
    mock_pro = MagicMock()
    adapter = _make_adapter(mock_pro)

    # Seed the internal concept cache directly
    adapter._concept_cache = pd.DataFrame({
        "code": ["CONCEPT_1", "CONCEPT_2", "CONCEPT_3"],
        "name": ["人工智能", "CPO概念", "新能源"],
    })

    codes = adapter.find_concept_codes(["人工智能", "CPO"])
    assert "CONCEPT_1" in codes
    assert "CONCEPT_2" in codes
    assert "CONCEPT_3" not in codes


def test_fetch_concept_stocks():
    mock_pro = MagicMock()
    mock_pro.concept_detail.return_value = pd.DataFrame({
        "ts_code": ["300308.SZ", "300502.SZ"],
        "name": ["中际旭创", "新易盛"],
    })
    adapter = _make_adapter(mock_pro)

    df = adapter.fetch_concept_stocks("CONCEPT_1")
    assert len(df) == 2
    assert "300308.SZ" in df["ts_code"].values


def test_enrich_segment_combines_multiple_concepts():
    mock_pro = MagicMock()

    # concept() returns the board list
    mock_pro.concept.return_value = pd.DataFrame({
        "code": ["C1", "C2"],
        "name": ["光模块概念", "CPO概念"],
    })

    # concept_detail returns constituents per board
    def detail_side_effect(*, id, fields):
        if id == "C1":
            return pd.DataFrame({
                "ts_code": ["300308.SZ"],
                "name": ["中际旭创"],
            })
        elif id == "C2":
            return pd.DataFrame({
                "ts_code": ["300308.SZ", "300502.SZ"],
                "name": ["中际旭创", "新易盛"],
            })
        return pd.DataFrame()

    mock_pro.concept_detail.side_effect = detail_side_effect
    mock_pro.stock_basic.return_value = pd.DataFrame({
        "ts_code": ["300308.SZ", "300502.SZ"],
        "name": ["中际旭创", "新易盛"],
    })

    adapter = _make_adapter(mock_pro)
    stocks = adapter.enrich_segment("光模块/CPO")

    codes = [s["code"] for s in stocks]
    assert "300308.SZ" in codes
    assert "300502.SZ" in codes
    # Should dedupe across concepts
    assert len(codes) == len(set(codes))


def test_build_stocks_config_dedupes_existing():
    mock_pro = MagicMock()
    mock_pro.concept.return_value = pd.DataFrame({
        "code": ["C1"],
        "name": ["光模块"],
    })
    mock_pro.concept_detail.return_value = pd.DataFrame({
        "ts_code": ["300308.SZ"],
        "name": ["中际旭创"],
    })
    mock_pro.stock_basic.return_value = pd.DataFrame({
        "ts_code": ["300308.SZ"],
        "name": ["中际旭创"],
    })

    adapter = _make_adapter(mock_pro)

    with patch("packages.adapters.tushare_industry_adapter.load_stocks", return_value=[
        {"code": "300308.SZ", "name": "中际旭创", "segment": "光模块"},
    ]):
        entries = adapter.build_stocks_config("ai")

    # 300308 already exists, should not be duplicated
    assert not any(e["code"] == "300308.SZ" for e in entries)
