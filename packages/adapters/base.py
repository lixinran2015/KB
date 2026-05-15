import logging
import time
from abc import ABC, abstractmethod
from enum import Enum
import pandas as pd

logger = logging.getLogger(__name__)


class DataSourceStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class DataNotFoundError(Exception):
    pass


class APIChangedError(Exception):
    pass


class RateLimitError(Exception):
    pass


class DataAdapter(ABC):
    def __init__(self):
        self.status = DataSourceStatus.HEALTHY
        from packages.adapters.cache_adapter import CacheAdapter
        self.cache = CacheAdapter()

    @abstractmethod
    def fetch(self, stock_code: str) -> pd.DataFrame:
        pass

    def fetch_with_fallback(self, stock_code: str) -> pd.DataFrame:
        try:
            df = self.fetch(stock_code)
            self.cache.save(stock_code, df)
            self.status = DataSourceStatus.HEALTHY
            return df
        except APIChangedError as e:
            logger.warning(f"AKShare API may have changed: {e}")
            self.status = DataSourceStatus.DEGRADED
            cached = self.cache.load(stock_code)
            if cached is not None:
                return cached
            return self._try_manual(stock_code)
        except RateLimitError:
            logger.warning("Rate limited, waiting 60s...")
            time.sleep(60)
            return self.fetch_with_fallback(stock_code)
        except DataNotFoundError:
            logger.warning(f"No data for {stock_code}, trying manual fallback")
            return self._try_manual(stock_code)
        except Exception as e:
            logger.critical(f"All data sources failed for {stock_code}: {e}")
            self.status = DataSourceStatus.DOWN
            return self._empty_dataframe(stock_code, status="UNAVAILABLE")

    def _try_manual(self, stock_code: str) -> pd.DataFrame:
        try:
            from packages.adapters.manual_adapter import ManualAdapter
            adapter = ManualAdapter()
            df = adapter.fetch(stock_code)
            self.status = DataSourceStatus.DOWN
            return df
        except Exception as e:
            logger.error(f"Manual fallback also failed for {stock_code}: {e}")
            return self._empty_dataframe(stock_code, status="UNAVAILABLE")

    def _empty_dataframe(self, stock_code: str, status: str) -> pd.DataFrame:
        return pd.DataFrame({"stock_code": [stock_code], "data_status": [status]})
