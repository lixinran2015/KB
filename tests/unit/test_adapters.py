import pytest
import pandas as pd
from packages.adapters.mock_adapter import MockAdapter
from packages.adapters.cache_adapter import CacheAdapter


def test_mock_adapter_returns_data():
    adapter = MockAdapter("stock_300308_q1_2024")
    df = adapter.fetch("300308.SZ")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "stock_code" in df.columns


def test_mock_adapter_not_found():
    adapter = MockAdapter("stock_300308_q1_2024")
    with pytest.raises(Exception):
        adapter.fetch("999999.SZ")


def test_cache_save_and_load(tmp_path):
    cache = CacheAdapter(str(tmp_path / "cache.db"))
    df = pd.DataFrame({"stock_code": ["300308.SZ"], "revenue": [100.0]})
    cache.save("300308.SZ", df)
    loaded = cache.load("300308.SZ")
    assert loaded is not None
    assert loaded.iloc[0]["revenue"] == 100.0


def test_cache_load_miss(tmp_path):
    cache = CacheAdapter(str(tmp_path / "cache.db"))
    loaded = cache.load("999999.SZ")
    assert loaded is None
