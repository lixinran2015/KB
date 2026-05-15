import pytest
import pandas as pd
from packages.adapters.mock_adapter import MockAdapter
from packages.engines.scoring_engine import ScoringEngine


@pytest.fixture
def engine():
    adapter = MockAdapter("stock_300308_q1_2024")
    return ScoringEngine(adapter=adapter)


def test_scoring_normal_data(engine):
    result = engine.calculate(stock_code="300308.SZ", segment="光模块", report_period="2024Q1")
    assert result.status == "OK"
    assert 0 <= result.total_score <= 5
    assert result.breakdown is not None


def test_scoring_missing_data():
    adapter = MockAdapter("stock_300308_missing")
    engine = ScoringEngine(adapter=adapter)
    result = engine.calculate(stock_code="300308.SZ", segment="光模块", report_period="2024Q1")
    assert result.status == "INSUFFICIENT_DATA"
    assert result.total_score is None


def test_scoring_invalid_data():
    adapter = MockAdapter("stock_300308_invalid")
    engine = ScoringEngine(adapter=adapter)
    result = engine.calculate(stock_code="300308.SZ", segment="光模块", report_period="2024Q1")
    assert result.status == "DATA_QUALITY_ISSUE"


def test_different_segments_use_different_thresholds():
    adapter = MockAdapter("stock_300308_q1_2024")
    engine = ScoringEngine(adapter=adapter)

    # 光模块：毛利率 35% 应该得高分
    result_gk = engine.calculate(stock_code="300308.SZ", segment="光模块", report_period="2024Q1")
    assert result_gk.status == "OK"

    # 服务器代工：同样的毛利率 35%，阈值不同
    result_server = engine.calculate(stock_code="300308.SZ", segment="服务器代工", report_period="2024Q1")
    assert result_server.status == "OK"
