import pytest
from packages.adapters.mock_adapter import MockAdapter
from packages.engines.trigger_engine import TriggerEngine


@pytest.fixture
def engine():
    adapter = MockAdapter("stock_300308_technical")
    return TriggerEngine(adapter=adapter)


def test_volume_spike_trigger(engine):
    result = engine.check(stock_code="300308.SZ", report_period="2024Q1")
    assert result.status == "OK"
    trigger_names = [t["name"] for t in result.triggers]
    assert "成交量倍量" in trigger_names


def test_break_year_line_trigger(engine):
    result = engine.check(stock_code="300308.SZ", report_period="2024Q1")
    assert result.status == "OK"
    trigger_names = [t["name"] for t in result.triggers]
    assert "突破年线" in trigger_names


def test_no_trigger():
    adapter = MockAdapter("stock_300308_no_trigger")
    engine = TriggerEngine(adapter=adapter)
    result = engine.check(stock_code="300308.SZ", report_period="2024Q1")
    assert result.status == "OK"
    assert len(result.triggers) == 0


def test_trigger_missing_data():
    adapter = MockAdapter("stock_300308_missing")
    engine = TriggerEngine(adapter=adapter)
    result = engine.check(stock_code="300308.SZ", report_period="2024Q1")
    assert result.status == "INSUFFICIENT_DATA"
