import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

CACHE_DB = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cache", "adapter_cache.db")


class CacheAdapter:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or CACHE_DB
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    stock_code TEXT PRIMARY KEY,
                    data BLOB,
                    cached_at TIMESTAMP
                )
            """)

    def save(self, stock_code: str, df: pd.DataFrame):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (stock_code, data, cached_at) VALUES (?, ?, ?)",
                (stock_code, df.to_json().encode(), datetime.now().isoformat()),
            )

    def load(self, stock_code: str, max_age_hours: int = 24) -> pd.DataFrame | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT data, cached_at FROM cache WHERE stock_code = ?", (stock_code,)
            ).fetchone()
            if row is None:
                return None
            data, cached_at = row
            cached_time = datetime.fromisoformat(cached_at)
            if datetime.now() - cached_time > timedelta(hours=max_age_hours):
                return None
            import io
            return pd.read_json(io.BytesIO(data))
