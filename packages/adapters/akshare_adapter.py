import datetime
import pandas as pd
from packages.adapters.base import DataAdapter, DataNotFoundError

try:
    import akshare as ak
except ImportError:
    ak = None


def _latest_report_date() -> str:
    """Return the latest completed quarterly report date as YYYYMMDD."""
    now = datetime.datetime.now()
    year = now.year
    month = now.month
    if month >= 5:  # Q1 report released by April
        q = "0331"
    elif month >= 9:  # H1 report released by August
        q = "0630"
    elif month >= 11:  # Q3 report released by October
        q = "0930"
    else:
        # Q4 of previous year
        year -= 1
        q = "1231"
    return f"{year}{q}"


def _map_yjbb_row(row: pd.Series, stock_code: str, report_period: str) -> dict:
    """Map AKShare stock_yjbb_em row to our schema."""
    revenue = row.get("营业总收入-营业总收入")
    net_profit = row.get("净利润-净利润")
    revenue_growth = row.get("营业总收入-同比增长")
    net_profit_growth = row.get("净利润-同比增长")
    gross_margin = row.get("销售毛利率")
    roe = row.get("净资产收益率")

    # Convert percentages to decimals
    if gross_margin is not None and not pd.isna(gross_margin):
        gross_margin = float(gross_margin) / 100
    if roe is not None and not pd.isna(roe):
        roe = float(roe) / 100
    if revenue_growth is not None and not pd.isna(revenue_growth):
        revenue_growth = float(revenue_growth) / 100
    if net_profit_growth is not None and not pd.isna(net_profit_growth):
        net_profit_growth = float(net_profit_growth) / 100

    # Convert to billions
    if revenue is not None and not pd.isna(revenue):
        revenue = float(revenue) / 1e8
    if net_profit is not None and not pd.isna(net_profit):
        net_profit = float(net_profit) / 1e8

    # Compute net margin
    net_margin = None
    if revenue and net_profit and revenue > 0:
        net_margin = round(net_profit / revenue, 4)

    snapshot_date = row.get("最新公告日期", "")
    if pd.isna(snapshot_date):
        snapshot_date = ""

    return {
        "stock_code": stock_code,
        "report_period": report_period,
        "snapshot_date": str(snapshot_date),
        "revenue": revenue,
        "revenue_growth": revenue_growth,
        "gross_margin": gross_margin,
        "net_margin": net_margin,
        "roe": roe,
        "net_profit": net_profit,
        "net_profit_growth": net_profit_growth,
        "pe_ttm": None,
        "ps_ttm": None,
        "pb": None,
        "northbound_pct": None,
        "fund_hold_pct": None,
    }


class AKShareAdapter(DataAdapter):
    def fetch(self, stock_code: str) -> pd.DataFrame:
        if ak is None:
            raise DataNotFoundError("AKShare not installed")

        pure_code = stock_code.split(".")[0]
        report_period = self._to_report_period(_latest_report_date())

        # Try current and previous two quarters
        dates_to_try = self._recent_report_dates()
        for date_str in dates_to_try:
            try:
                df = ak.stock_yjbb_em(date=date_str)
                if df.empty:
                    continue
                row = df[df["股票代码"] == pure_code]
                if not row.empty:
                    rp = self._to_report_period(date_str)
                    data = _map_yjbb_row(row.iloc[0], stock_code, rp)
                    return pd.DataFrame([data])
            except Exception:
                continue

        raise DataNotFoundError(f"No financial data for {stock_code} from AKShare")

    def _recent_report_dates(self) -> list:
        now = datetime.datetime.now()
        year = now.year
        month = now.month
        quarters = []
        if month >= 5:
            quarters.append((year, "0331"))
        if month >= 9:
            quarters.append((year, "0630"))
        if month >= 11:
            quarters.append((year, "0930"))
        quarters.append((year - 1, "1231"))
        # Ensure we have at least 3 dates to try
        if len(quarters) < 3:
            quarters.append((year - 1, "0930"))
        return [f"{y}{q}" for y, q in quarters]

    def _to_report_period(self, date_str: str) -> str:
        year = date_str[:4]
        month = date_str[4:6]
        day = date_str[6:]
        if month == "03":
            return f"{year}Q1"
        elif month == "06":
            return f"{year}Q2"
        elif month == "09":
            return f"{year}Q3"
        elif month == "12":
            return f"{year}Q4"
        return f"{year}Q1"
