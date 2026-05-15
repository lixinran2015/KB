import argparse
import json
import os
import sys
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

from packages.domain.database import init_db, DB_PATH, Transaction
from packages.domain.models import StockFinancial, ScoreResult, TriggerEvent, Watchlist, WorkflowRun
from packages.domain.locks import WorkflowLock, create_backup, list_backups, rollback_to_backup
from packages.config.loader import load_stocks, save_stocks
from packages.config.validators import StockConfig
from packages.engines.scoring_engine import ScoringEngine
from packages.engines.valuation_engine import ValuationEngine
from packages.engines.trigger_engine import TriggerEngine
from packages.engines.report_engine import ReportEngine
from packages.engines.watchlist_manager import WatchlistManager
from packages.adapters.akshare_adapter import AKShareAdapter
from packages.adapters.mock_adapter import MockAdapter
from packages.adapters.tushare_industry_adapter import TushareIndustryAdapter

# Setup logging: stdout + rotating file
LOG_DIR = Path(__file__).parent.parent.parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "stock_kb.log"

handler_file = RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
handler_file.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
handler_console = logging.StreamHandler()
handler_console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

logging.basicConfig(level=logging.INFO, handlers=[handler_file, handler_console])
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
    """Quarterly update workflow with backup and full transaction boundaries"""
    with WorkflowLock():
        cmd_init()
        logger.info("Creating backup before quarterly update...")
        backup_path = create_backup(DB_PATH)
        logger.info(f"Backup created: {backup_path}")

        # Track workflow run
        with Transaction() as session:
            workflow = WorkflowRun(
                workflow_name="quarterly",
                status="running",
                started_at=datetime.now(),
                backup_path=backup_path,
            )
            session.add(workflow)
            session.flush()
            workflow_run_id = workflow.id

        # Use AKShare if available, fall back to mock for testing
        try:
            adapter = AKShareAdapter()
            engine = ScoringEngine(adapter=adapter)
        except Exception:
            logger.warning("AKShare not available, using mock data for testing")
            adapter = MockAdapter("stock_300308_q1_2024")
            engine = ScoringEngine(adapter=adapter)

        stocks = load_stocks()
        succeeded = 0
        failed = 0

        for s in stocks:
            try:
                result = engine.calculate(
                    stock_code=s["code"],
                    segment=s["segment"],
                    report_period="2024Q1",
                )
                logger.info(f"{s['code']}: score={result.total_score}, status={result.status}")

                # Persist score result within transaction boundary
                with Transaction() as session:
                    sr = ScoreResult(
                        stock_code=s["code"],
                        report_period="2024Q1",
                        total_score=result.total_score,
                        financial_score=result.financial_score,
                        qualitative_score=result.qualitative_score,
                        breakdown=json.dumps(result.breakdown, ensure_ascii=False) if result.breakdown else None,
                        raw_values=json.dumps(result.raw_values, ensure_ascii=False) if result.raw_values else None,
                        benchmarks=json.dumps(result.benchmarks, ensure_ascii=False) if result.benchmarks else None,
                        status=result.status,
                        missing_metrics=",".join(result.missing_metrics) if result.missing_metrics else None,
                        message=result.message,
                        workflow_run_id=workflow_run_id,
                    )
                    session.add(sr)
                succeeded += 1
            except Exception as e:
                logger.error(f"Failed to score {s['code']}: {e}")
                failed += 1

        # Mark workflow complete
        with Transaction() as session:
            wf = session.query(WorkflowRun).filter_by(id=workflow_run_id).first()
            if wf:
                wf.status = "completed" if failed == 0 else "partial"
                wf.completed_at = datetime.now()
                if failed > 0:
                    wf.error_message = f"{failed} stocks failed out of {len(stocks)}"

        logger.info(f"Quarterly workflow completed: {succeeded} succeeded, {failed} failed")


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
        if not new_entries:
            logger.info("No new stocks to add")
            return

        existing = load_stocks()
        merged = existing + new_entries
        save_stocks(merged)
        logger.info(f"Added {len(new_entries)} new stocks to stocks.yml (total: {len(merged)})")
        for e in new_entries[:5]:
            print(f"  + {e['code']} {e['name']} ({e['segment']})")
        if len(new_entries) > 5:
            print(f"  ... 还有 {len(new_entries) - 5} 只")
    else:
        new_entries = adapter.build_stocks_config(industry_key)
        logger.info(f"Dry-run: would add {len(new_entries)} new stocks to stocks.yml")
        for e in new_entries[:5]:
            print(f"  + {e['code']} {e['name']} ({e['segment']})")
        if len(new_entries) > 5:
            print(f"  ... 还有 {len(new_entries) - 5} 只")
        logger.info("Use --apply to persist")


def cmd_report(stock_code: str = None):
    """Generate Markdown report for a stock"""
    cmd_init()
    report = ReportEngine()
    stocks = load_stocks()

    targets = [s for s in stocks if stock_code is None or s["code"] == stock_code]
    if stock_code and not targets:
        logger.error(f"Stock {stock_code} not found in stocks.yml")
        sys.exit(1)

    for s in targets:
        try:
            md = report.generate(
                stock_code=s["code"],
                segment=s["segment"],
                report_period="2024Q1",
            )
            out_path = Path(__file__).parent.parent.parent / "docs" / "stocks" / f"{s['code']}.md"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md, encoding="utf-8")
            logger.info(f"Report saved: {out_path}")
        except Exception as e:
            logger.error(f"Failed to generate report for {s['code']}: {e}")


def cmd_check_triggers():
    """Run technical trigger detection for all stocks"""
    cmd_init()
    try:
        adapter = AKShareAdapter()
    except Exception:
        logger.warning("AKShare not available, using mock data")
        adapter = MockAdapter("stock_300308_technical")

    engine = TriggerEngine(adapter=adapter)
    stocks = load_stocks()
    triggered = 0

    for s in stocks[:50]:  # Limit to avoid rate limits
        try:
            result = engine.check(stock_code=s["code"], report_period="2024Q1")
            if result.triggers:
                triggered += 1
                for t in result.triggers:
                    logger.info(f"{s['code']} {s['name']}: {t['name']} ({t['category']})")
        except Exception as e:
            logger.debug(f"Trigger check failed for {s['code']}: {e}")

    logger.info(f"Trigger check completed. {triggered} stocks triggered.")


def cmd_revise(stock_code: str, report_period: str, reason: str = ""):
    """Mark existing financial record as revised and insert a corrected one."""
    cmd_init()
    with Transaction() as session:
        existing = (
            session.query(StockFinancial)
            .filter_by(stock_code=stock_code, report_period=report_period)
            .order_by(StockFinancial.revision_seq.desc())
            .first()
        )
        if not existing:
            logger.error(f"No existing record for {stock_code} {report_period}")
            sys.exit(1)

        # Mark old record as revised
        existing.is_revised = True
        existing.revised_by_snapshot = f"rev_{existing.revision_seq + 1}"
        existing.revision_reason = reason or "manual revision"

        logger.info(f"Marked revision {existing.revision_seq} as revised for {stock_code} {report_period}")
        logger.info(f"Use 'sync' or manual insert to add the corrected record")


def cmd_sync(report_period: str = None):
    """Sync financial data from adapters into the database."""
    cmd_init()
    try:
        adapter = AKShareAdapter()
    except Exception:
        logger.warning("AKShare not available, using mock data")
        adapter = MockAdapter("stock_300308_q1_2024")

    stocks = load_stocks()
    synced = 0
    skipped = 0

    for s in stocks:
        try:
            df = adapter.fetch_with_fallback(s["code"])
            if df.empty or "data_status" in df.columns:
                skipped += 1
                continue

            row = df.iloc[0]
            rp = report_period or row.get("report_period", "2024Q1")
            snapshot = row.get("snapshot_date", "")

            with Transaction() as session:
                # Upsert: delete existing same snapshot, then insert
                session.query(StockFinancial).filter_by(
                    stock_code=s["code"], report_period=rp, snapshot_date=snapshot
                ).delete()

                record = StockFinancial(
                    stock_code=s["code"],
                    report_period=rp,
                    snapshot_date=snapshot,
                    revenue=row.get("revenue"),
                    revenue_growth=row.get("revenue_growth"),
                    gross_margin=row.get("gross_margin"),
                    net_margin=row.get("net_margin"),
                    roe=row.get("roe"),
                    net_profit=row.get("net_profit"),
                    net_profit_growth=row.get("net_profit_growth"),
                    pe_ttm=row.get("pe_ttm"),
                    ps_ttm=row.get("ps_ttm"),
                    pb=row.get("pb"),
                    northbound_pct=row.get("northbound_pct"),
                    fund_hold_pct=row.get("fund_hold_pct"),
                    data_source="akshare",
                    is_filing=True,
                )
                session.add(record)
                synced += 1
        except Exception as e:
            logger.warning(f"Sync failed for {s['code']}: {e}")
            skipped += 1

    logger.info(f"Sync completed: {synced} synced, {skipped} skipped")


def cmd_sync_full():
    """Sync all available historical financial data."""
    # For MVP, same as sync but explicit intent
    logger.info("Full sync: fetching latest available data for all stocks...")
    cmd_sync()


def cmd_cache_stats():
    """Show database statistics."""
    cmd_init()
    with Transaction() as session:
        stock_count = session.query(StockFinancial.stock_code).distinct().count()
        financial_count = session.query(StockFinancial).count()
        score_count = session.query(ScoreResult).count()
        trigger_count = session.query(TriggerEvent).count()
        watchlist_count = session.query(Watchlist).count()
        workflow_count = session.query(WorkflowRun).count()

    print(f"\n{'=' * 40}")
    print(f"📊 Stock KB Cache Statistics")
    print(f"{'=' * 40}")
    print(f"  Unique stocks with financials: {stock_count}")
    print(f"  Total financial records:       {financial_count}")
    print(f"  Score results stored:          {score_count}")
    print(f"  Trigger events:                {trigger_count}")
    print(f"  Watchlists:                    {watchlist_count}")
    print(f"  Workflow runs:                 {workflow_count}")
    print(f"{'=' * 40}")


def cmd_add_industry(name: str, segments: list = None):
    """Create a new industry YAML template."""
    import os
    industry_dir = os.path.join(os.path.dirname(__file__), "..", "..", "config", "industries")
    os.makedirs(industry_dir, exist_ok=True)
    path = os.path.join(industry_dir, f"{name}.yml")

    if os.path.exists(path):
        logger.error(f"Industry '{name}' already exists at {path}")
        sys.exit(1)

    default_segments = segments or ["核心环节", "配套环节", "下游应用"]
    content = {
        "name": name,
        "description": f"{name} industry chain",
        "segments": [{"name": s, "description": ""} for s in default_segments],
    }

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(content, f, allow_unicode=True, sort_keys=False)

    logger.info(f"Created industry template: {path}")
    for s in default_segments:
        print(f"  - {s}")


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
    score_parser.add_argument("--all", action="store_true", help="Score all stocks (default if no filter)")

    enrich_parser = subparsers.add_parser("enrich-industry", help="Fetch stocks from Tushare concept boards")
    enrich_parser.add_argument("--industry", choices=["ai", "robot"], default="ai", help="Industry to enrich")
    enrich_parser.add_argument("--apply", action="store_true", help="Apply changes to stocks.yml (default: dry-run)")

    report_parser = subparsers.add_parser("report", help="Generate Markdown stock reports")
    report_parser.add_argument("--stock", help="Specific stock code (default: all)")

    subparsers.add_parser("check-triggers", help="Run technical trigger detection")

    revise_parser = subparsers.add_parser("revise", help="Mark financial record as revised")
    revise_parser.add_argument("--stock", required=True, help="Stock code")
    revise_parser.add_argument("--period", required=True, help="Report period (e.g. 2024Q1)")
    revise_parser.add_argument("--reason", default="", help="Revision reason")

    sync_parser = subparsers.add_parser("sync", help="Sync financial data to database")
    sync_parser.add_argument("--period", help="Specific report period (default: latest)")

    subparsers.add_parser("sync-full", help="Sync all historical financial data")
    subparsers.add_parser("cache-stats", help="Show database statistics")

    add_ind_parser = subparsers.add_parser("add-industry", help="Create new industry template")
    add_ind_parser.add_argument("name", help="Industry name (kebab-case)")
    add_ind_parser.add_argument("--segments", nargs="+", help="Segment names")

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
    elif args.command == "report":
        cmd_report(args.stock)
    elif args.command == "check-triggers":
        cmd_check_triggers()
    elif args.command == "revise":
        cmd_revise(args.stock, args.period, args.reason)
    elif args.command == "sync":
        cmd_sync(args.period)
    elif args.command == "sync-full":
        cmd_sync_full()
    elif args.command == "cache-stats":
        cmd_cache_stats()
    elif args.command == "add-industry":
        cmd_add_industry(args.name, args.segments)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
