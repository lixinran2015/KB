import pytest
from packages.adapters.mock_adapter import MockAdapter
from packages.engines.valuation_engine import ValuationEngine


@pytest.fixture
def engine():
    adapter = MockAdapter("stock_300308_q1_2024")
    return ValuationEngine(adapter=adapter)


def test_valuation_normal_data(engine):
    result = engine.calculate(stock_code="300308.SZ", segment="光模块", report_period="2024Q1")
    assert result.status == "OK"
    assert result.overall_rating in ["cheap", "fair", "expensive"]
    assert "PE_TTM" in result.breakdown
    assert result.raw_values["PE_TTM"] == 45.0


def test_valuation_different_segment_thresholds():
    adapter = MockAdapter("stock_300308_q1_2024")
    engine = ValuationEngine(adapter=adapter)

    # 光模块: PE=45 属于合理区间
    result_gk = engine.calculate(stock_code="300308.SZ", segment="光模块", report_period="2024Q1")
    assert result_gk.status == "OK"
    assert result_gk.breakdown["PE_TTM"] == "fair"

    # 服务器代工: PE=45 属于高估区间
    result_server = engine.calculate(stock_code="300308.SZ", segment="服务器代工", report_period="2024Q1")
    assert result_server.status == "OK"
    assert result_server.breakdown["PE_TTM"] == "expensive"


def test_valuation_missing_data():
    adapter = MockAdapter("stock_300308_missing")
    engine = ValuationEngine(adapter=adapter)
    result = engine.calculate(stock_code="300308.SZ", segment="光模块", report_period="2024Q1")
    assert result.status == "INSUFFICIENT_DATA"
    assert result.overall_rating is None
