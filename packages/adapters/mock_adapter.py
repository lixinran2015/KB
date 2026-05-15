import os
import pandas as pd
from packages.adapters.base import DataAdapter, DataNotFoundError

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "tests", "fixtures")


class MockAdapter(DataAdapter):
    def __init__(self, fixture_name: str = None):
        super().__init__()
        self.fixture_name = fixture_name or "default"
        self.data = self._load_fixture()

    def fetch(self, stock_code: str) -> pd.DataFrame:
        df = self.data[self.data["stock_code"] == stock_code]
        if df.empty:
            raise DataNotFoundError(f"No fixture data for {stock_code}")
        return df.copy()

    def _load_fixture(self) -> pd.DataFrame:
        path = os.path.join(FIXTURES_DIR, f"{self.fixture_name}.csv")
        if not os.path.exists(path):
            raise DataNotFoundError(f"Fixture not found: {path}")
        return pd.read_csv(path)
