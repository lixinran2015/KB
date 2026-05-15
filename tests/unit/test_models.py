import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from packages.domain.models import Base, StockFinancial, ScoreResult, Watchlist, WatchlistItem


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_stock_financial_creation(db_session):
    fin = StockFinancial(
        stock_code="300308.SZ",
        report_period="2024Q1",
        snapshot_date="2024-04-30",
        revenue=100.0,
        gross_margin=0.35,
    )
    db_session.add(fin)
    db_session.commit()

    result = db_session.query(StockFinancial).first()
    assert result.stock_code == "300308.SZ"
    assert result.gross_margin == 0.35


def test_score_result_with_status(db_session):
    score = ScoreResult(
        stock_code="300308.SZ",
        report_period="2024Q1",
        total_score=4.5,
        status="OK",
    )
    db_session.add(score)
    db_session.commit()

    result = db_session.query(ScoreResult).first()
    assert result.status == "OK"
    assert result.total_score == 4.5


def test_watchlist_with_items(db_session):
    wl = Watchlist(name="AI核心仓")
    db_session.add(wl)
    db_session.commit()

    item = WatchlistItem(watchlist_id=wl.id, stock_code="300308.SZ", status="holding")
    db_session.add(item)
    db_session.commit()

    assert len(wl.items) == 1
    assert wl.items[0].stock_code == "300308.SZ"
