import os
import pandas as pd
from packages.adapters.base import DataAdapter, DataNotFoundError

MANUAL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "manual")


class ManualAdapter(DataAdapter):
    def fetch(self, stock_code: str) -> pd.DataFrame:
        path = os.path.join(MANUAL_DIR, f"{stock_code}.csv")
        if not os.path.exists(path):
            raise DataNotFoundError(f"No manual data for {stock_code}")
        return pd.read_csv(path)
