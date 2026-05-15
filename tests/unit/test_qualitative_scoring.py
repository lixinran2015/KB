import pytest
from packages.adapters.mock_adapter import MockAdapter
from packages.engines.scoring_engine import ScoringEngine
from packages.domain.database import init_db, get_session
from packages.domain.models import QualitativeScore


@pytest.fixture
def engine():
    adapter = MockAdapter("stock_300308_q1_2024")
    return ScoringEngine(adapter=adapter)


def test_qualitative_score_included(engine):
    init_db()
    session = get_session()
    # Remove any existing record to avoid unique constraint
    existing = session.query(QualitativeScore).filter_by(stock_code="300308.SZ").first()
    if existing:
        session.delete(existing)
        session.commit()

    qs = QualitativeScore(
        stock_code="300308.SZ",
        global_ranking=8,
        localization_potential=9,
        customer_health=7,
        tam_usd_billion=50.0,
        current_penetration=0.15,
        catalyst_timeline="2024H2",
        last_updated="2024-05-15",
    )
    session.add(qs)
    session.commit()
    session.close()

    result = engine.calculate(stock_code="300308.SZ", segment="光模块", report_period="2024Q1")
    assert result.status == "OK"
    assert result.qualitative_score is not None
    assert result.total_score != result.financial_score  # 总分包含定性评分


def test_qualitative_data_missing(engine):
    init_db()
    session = get_session()
    # Remove any existing record so the test sees no qualitative data
    existing = session.query(QualitativeScore).filter_by(stock_code="300308.SZ").first()
    if existing:
        session.delete(existing)
        session.commit()
    session.close()

    result = engine.calculate(stock_code="300308.SZ", segment="光模块", report_period="2024Q1")
    assert result.status == "OK"
    assert result.qualitative_score is None
