import os
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, Session
from packages.domain.models import Base, StockFinancial

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "stock_kb.sqlite")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},
)

# Enable SQLite foreign key constraints on every connection
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(bind=engine)


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    Base.metadata.create_all(engine)
    _create_views(engine)


def _create_views(engine):
    """Create database views for common queries."""
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE VIEW IF NOT EXISTS latest_financials AS "
                "SELECT sf.* FROM stock_financials sf "
                "INNER JOIN ("
                "  SELECT stock_code, MAX(snapshot_date) as max_date "
                "  FROM stock_financials "
                "  WHERE is_revised = 0 "
                "  GROUP BY stock_code"
                ") latest ON sf.stock_code = latest.stock_code AND sf.snapshot_date = latest.max_date "
                "WHERE sf.is_revised = 0"
            )
        )
        conn.commit()


def get_session() -> Session:
    return SessionLocal()


class Transaction:
    def __init__(self):
        self.session = get_session()

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.session.commit()
        else:
            self.session.rollback()
        self.session.close()


def get_latest_financial(stock_code: str):
    """Return the most recent non-revised StockFinancial for a stock."""
    session = get_session()
    try:
        record = (
            session.query(StockFinancial)
            .filter_by(stock_code=stock_code, is_revised=False)
            .order_by(StockFinancial.snapshot_date.desc())
            .first()
        )
        return record
    finally:
        session.close()
