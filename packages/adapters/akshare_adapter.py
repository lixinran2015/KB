import pandas as pd
from packages.adapters.base import DataAdapter, DataNotFoundError

try:
    import akshare as ak
except ImportError:
    ak = None


class AKShareAdapter(DataAdapter):
    def fetch(self, stock_code: str) -> pd.DataFrame:
        if ak is None:
            raise DataNotFoundError("AKShare not installed")

        pure_code = stock_code.split(".")[0]

        try:
            df = ak.stock_financial_report_sina(stock=pure_code)
            if df.empty:
                raise DataNotFoundError(f"No financial data for {stock_code}")
            df["stock_code"] = stock_code
            return df
        except Exception as e:
            raise DataNotFoundError(f"AKShare error for {stock_code}: {e}")
