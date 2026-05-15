import argparse
import os
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

from packages.domain.database import init_db, DB_PATH
from packages.domain.locks import WorkflowLock, create_backup, list_backups, rollback_to_backup
from packages.config.loader import load_stocks
from packages.config.validators import StockConfig
from packages.engines.scoring_engine import ScoringEngine
from packages.engines.watchlist_manager import WatchlistManager
from packages.adapters.akshare_adapter import AKShareAdapter
from packages.adapters.mock_adapter import MockAdapter
from packages.adapters.tushare_industry_adapter import TushareIndustryAdapter

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
    with WorkflowLock():
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


def cmd_quarterly():
    """Quarterly update workflow with backup"""
    with WorkflowLock():
        cmd_init()
        logger.info("Creating backup before quarterly update...")
        backup_path = create_backup(DB_PATH)
        logger.info(f"Backup created: {backup_path}")

        # Use AKShare if available, fall back to mock for testing
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

        logger.info("Quarterly workflow completed")


def cmd_rollback():
    """Rollback to most recent backup"""
    backups = list_backups()
    if not backups:
        logger.error("No backups found")
        sys.exit(1)

    latest = backups[0]
    logger.info(f"Rolling back to: {latest}")
    rollback_to_backup(DB_PATH, latest)
    logger.info("Rollback completed")


def cmd_score(segment: str = None):
    """Run scoring for all or specific segment"""
    cmd_init()
    # Use AKShare if available, fall back to mock for testing
    try:
        adapter = AKShareAdapter()
        engine = ScoringEngine(adapter=adapter)
    except Exception:
        logger.warning("AKShare not available, using mock data for testing")
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


def cmd_enrich_industry(industry_key: str, dry_run: bool = True):
    """Fetch industry chain stocks from Tushare concept boards."""
    try:
        adapter = TushareIndustryAdapter()
    except ValueError as e:
        logger.error(f"{e}")
        logger.info("Set TUSHARE_TOKEN env var or register at tushare.pro")
        sys.exit(1)
    except ImportError:
        logger.error("tushare not installed; run: pip install tushare")
        sys.exit(1)

    logger.info(f"Fetching concept stocks for industry: {industry_key}")
    results = adapter.enrich_industry(industry_key)

    total = sum(len(v) for v in results.values())
    logger.info(f"Found {total} stocks across {len(results)} segments")

    for seg_name, stocks in results.items():
        print(f"\n【{seg_name}】({len(stocks)}只)")
        for s in stocks[:10]:
            print(f"  {s['code']} {s['name']}")
        if len(stocks) > 10:
            print(f"  ... 还有 {len(stocks) - 10} 只")

    if not dry_run:
        new_entries = adapter.build_stocks_config(industry_key)
        logger.info(f"Would add {len(new_entries)} new stocks to stocks.yml")
        for e in new_entries[:5]:
            print(f"  + {e['code']} {e['name']} ({e['segment']})")
        if len(new_entries) > 5:
            print(f"  ... 还有 {len(new_entries) - 5} 只")
    else:
        logger.info("Dry-run mode. Use --apply to add to stocks.yml")


def main():
    parser = argparse.ArgumentParser(description="Stock KB CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize database")
    subparsers.add_parser("validate", help="Validate configurations")
    subparsers.add_parser("daily", help="Run daily update workflow")
    subparsers.add_parser("quarterly", help="Run quarterly update with backup")
    subparsers.add_parser("rollback", help="Rollback to latest backup")

    score_parser = subparsers.add_parser("score", help="Run scoring")
    score_parser.add_argument("--segment", help="Filter by segment")

    enrich_parser = subparsers.add_parser("enrich-industry", help="Fetch stocks from Tushare concept boards")
    enrich_parser.add_argument("--industry", choices=["ai", "robot"], default="ai", help="Industry to enrich")
    enrich_parser.add_argument("--apply", action="store_true", help="Apply changes to stocks.yml (default: dry-run)")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init()
    elif args.command == "validate":
        cmd_validate()
    elif args.command == "daily":
        cmd_daily()
    elif args.command == "quarterly":
        cmd_quarterly()
    elif args.command == "rollback":
        cmd_rollback()
    elif args.command == "score":
        cmd_score(args.segment)
    elif args.command == "enrich-industry":
        cmd_enrich_industry(args.industry, dry_run=not args.apply)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
