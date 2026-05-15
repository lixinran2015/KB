import pytest
from pydantic import ValidationError
from packages.config.validators import StockConfig, SegmentRule, MetricRule


def test_valid_stock_config():
    stock = StockConfig(
        code="300308.SZ", name="中际旭创", segment="光模块",
        style="白马股", market_cap_tier="大盘"
    )
    assert stock.code == "300308.SZ"


def test_invalid_stock_code_format():
    with pytest.raises(ValidationError, match="code"):
        StockConfig(
            code="300308", name="test", segment="test",
            style="白马股", market_cap_tier="大盘"
        )


def test_invalid_style():
    with pytest.raises(ValidationError, match="style"):
        StockConfig(
            code="300308.SZ", name="test", segment="test",
            style="未知风格", market_cap_tier="大盘"
        )


def test_metric_weight_format():
    rule = MetricRule(
        name="毛利率", weights={"excellent": ">40", "good": ">30"}, weight=0.5
    )
    assert rule.weights["excellent"] == ">40"


def test_invalid_weight_format():
    with pytest.raises(ValidationError, match="weight format"):
        MetricRule(
            name="毛利率", weights={"excellent": "invalid"}, weight=0.5
        )


def test_segment_weights_sum():
    metrics = [
        MetricRule(name="毛利率", weights={"excellent": ">40"}, weight=0.5),
        MetricRule(name="净利率", weights={"excellent": ">15"}, weight=0.6),
    ]
    with pytest.raises(ValidationError, match="sum to 1.0"):
        SegmentRule(segment="光模块", metrics=metrics)
