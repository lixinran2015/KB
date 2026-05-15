"""End-to-end tests covering main user workflows."""
from packages.adapters.mock_adapter import MockAdapter
from packages.engines.scoring_engine import ScoringEngine
from packages.engines.valuation_engine import ValuationEngine
from packages.engines.trigger_engine import TriggerEngine
from packages.engines.report_engine import ReportEngine
from packages.engines.watchlist_manager import WatchlistManager
from packages.domain.database import init_db


def test_end_to_end_scoring_workflow():
    """Full scoring workflow: data → score → valuation → report."""
    adapter = MockAdapter("stock_300308_q1_2024")

    scoring = ScoringEngine(adapter=adapter)
    score_result = scoring.calculate(
        stock_code="300308.SZ",
        segment="光模块",
        report_period="2024Q1",
    )
    assert score_result.status == "OK"
    assert score_result.total_score is not None

    valuation = ValuationEngine(adapter=adapter)
    val_result = valuation.calculate(
        stock_code="300308.SZ",
        segment="光模块",
        report_period="2024Q1",
    )
    assert val_result.status == "OK"
    assert val_result.overall_rating in ["cheap", "fair", "expensive"]

    report = ReportEngine()
    md = report.generate(
        stock_code="300308.SZ",
        segment="光模块",
        report_period="2024Q1",
    )
    assert "300308.SZ" in md
    assert "中际旭创" in md


def test_end_to_end_watchlist_workflow():
    """Watchlist CRUD + scoring integration."""
    init_db()
    wm = WatchlistManager()

    # Create watchlist
    wl = wm.create_watchlist("E2E测试组合", "端到端测试用")
    assert wl.id is not None

    # Add stock
    wm.add_stock(wl.id, "300308.SZ", status="holding")
    items = wm.get_items(wl.id)
    assert len(items) == 1
    assert items[0].stock_code == "300308.SZ"

    # Score the stock
    adapter = MockAdapter("stock_300308_q1_2024")
    engine = ScoringEngine(adapter=adapter)
    result = engine.calculate(
        stock_code="300308.SZ",
        segment="光模块",
        report_period="2024Q1",
    )
    assert result.status == "OK"

    # Remove stock
    wm.remove_stock(wl.id, "300308.SZ")
    items = wm.get_items(wl.id)
    assert len(items) == 0

    # Delete watchlist
    wm.delete_watchlist(wl.id)
    wls = wm.list_watchlists()
    assert wl.id not in [w.id for w in wls]


def test_end_to_end_trigger_detection():
    """Technical trigger detection workflow."""
    adapter = MockAdapter("stock_300308_technical")
    engine = TriggerEngine(adapter=adapter)

    result = engine.check(stock_code="300308.SZ", report_period="2024Q1")
    assert result.status == "OK"
    assert len(result.triggers) >= 1

    trigger_names = [t["name"] for t in result.triggers]
    assert "成交量倍量" in trigger_names
    assert "突破年线" in trigger_names
