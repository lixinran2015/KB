import argparse
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from packages.domain.database import init_db
from packages.config.loader import load_stocks
from packages.config.validators import StockConfig
from packages.engines.scoring_engine import ScoringEngine
from packages.engines.watchlist_manager import WatchlistManager
from packages.adapters.akshare_adapter import AKShareAdapter
from packages.adapters.mock_adapter import MockAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def cmd_init():
    """Initialize database and directories"""
    init_db()
    logger.info("Database initialized")


def cmd_validate():
    """Validate all configuration files"""
    errors = []
    stocks = load_stocks()
    for s in stocks:
        try:
            StockConfig(**s)
        except Exception as e:
            errors.append(f"Stock {s.get('code', '?' )}: {e}")

    if errors:
        for e in errors:
            logger.error(e)
        sys.exit(1)
    logger.info("All configurations valid")


def cmd_daily():
    """Daily update workflow"""
    cmd_init()
    logger.info("Starting daily workflow...")

    # For MVP, use mock adapter if AKShare is not available
    try:
        adapter = AKShareAdapter()
        engine = ScoringEngine(adapter=adapter)
    except Exception:
        logger.warning("AKShare not available, using mock data for testing")
        adapter = MockAdapter("stock_300308_q1_2024")
        engine = ScoringEngine(adapter=adapter)

    stocks = load_stocks()
    for s in stocks:
        try:
            result = engine.calculate(
                stock_code=s["code"],
                segment=s["segment"],
                report_period="2024Q1",
            )
            logger.info(f"{s['code']}: score={result.total_score}, status={result.status}")
        except Exception as e:
            logger.error(f"Failed to score {s['code']}: {e}")

    logger.info("Daily workflow completed")


def cmd_score(segment: str = None):
    """Run scoring for all or specific segment"""
    cmd_init()
    adapter = MockAdapter("stock_300308_q1_2024")
    engine = ScoringEngine(adapter=adapter)
    stocks = load_stocks()

    for s in stocks:
        if segment and s["segment"] != segment:
            continue
        result = engine.calculate(
            stock_code=s["code"],
            segment=s["segment"],
            report_period="2024Q1",
        )
        print(f"{s['code']} {s['name']}: {result.total_score} ({result.status})")


def main():
    parser = argparse.ArgumentParser(description="Stock KB CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize database")
    subparsers.add_parser("validate", help="Validate configurations")
    subparsers.add_parser("daily", help="Run daily update workflow")

    score_parser = subparsers.add_parser("score", help="Run scoring")
    score_parser.add_argument("--segment", help="Filter by segment")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init()
    elif args.command == "validate":
        cmd_validate()
    elif args.command == "daily":
        cmd_daily()
    elif args.command == "score":
        cmd_score(args.segment)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
