from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey,
    create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime

Base = declarative_base()


class StockFinancial(Base):
    __tablename__ = "stock_financials"

    stock_code = Column(String, nullable=False, primary_key=True)
    report_period = Column(String, nullable=False, primary_key=True)
    snapshot_date = Column(String, nullable=False, primary_key=True)
    revenue = Column(Float)
    revenue_growth = Column(Float)
    gross_margin = Column(Float)
    net_margin = Column(Float)
    roe = Column(Float)
    net_profit = Column(Float)
    net_profit_growth = Column(Float)
    pe_ttm = Column(Float)
    ps_ttm = Column(Float)
    pb = Column(Float)
    northbound_pct = Column(Float)
    fund_hold_pct = Column(Float)
    data_source = Column(String)
    is_filing = Column(Boolean, default=False)
    revision_seq = Column(Integer, default=0)
    is_revised = Column(Boolean, default=False)
    revised_by_snapshot = Column(String)
    revision_reason = Column(Text)


class ScoreResult(Base):
    __tablename__ = "score_results"

    stock_code = Column(String, nullable=False, primary_key=True)
    report_period = Column(String, nullable=False, primary_key=True)
    scored_at = Column(DateTime, default=datetime.now, primary_key=True)
    total_score = Column(Float)
    financial_score = Column(Float)
    qualitative_score = Column(Float)
    breakdown = Column(Text)
    raw_values = Column(Text)
    benchmarks = Column(Text)
    ranking_in_segment = Column(Integer)
    total_in_segment = Column(Integer)
    config_version = Column(String)
    data_source_versions = Column(Text)
    workflow_run_id = Column(Integer)
    status = Column(String, default="OK")
    missing_metrics = Column(Text)
    message = Column(Text)


class TriggerEvent(Base):
    __tablename__ = "trigger_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(String, nullable=False)
    instance_date = Column(String)
    name = Column(String)
    category = Column(String)
    status = Column(String, default="watching")
    impact_score = Column(Integer)
    description = Column(Text)
    related_stocks = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class Watchlist(Base):
    __tablename__ = "watchlists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    items = relationship("WatchlistItem", back_populates="watchlist", cascade="all, delete-orphan")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    watchlist_id = Column(Integer, ForeignKey("watchlists.id"), primary_key=True)
    stock_code = Column(String, primary_key=True)
    added_at = Column(DateTime, default=datetime.now)
    status = Column(String, default="watching")
    notes = Column(Text)
    alert_rules = Column(Text)
    watchlist = relationship("Watchlist", back_populates="items")


class QualitativeScore(Base):
    __tablename__ = "qualitative_scores"

    stock_code = Column(String, primary_key=True)
    global_ranking = Column(Integer)
    localization_potential = Column(Integer)
    customer_health = Column(Integer)
    tam_usd_billion = Column(Float)
    current_penetration = Column(Float)
    catalyst_timeline = Column(String)
    last_updated = Column(String)
    update_trigger_note = Column(Text)


class ConfigVersion(Base):
    __tablename__ = "config_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_type = Column(String, nullable=False)
    version = Column(String, nullable=False)
    content_hash = Column(String)
    applied_at = Column(DateTime, default=datetime.now)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_name = Column(String, nullable=False)
    status = Column(String)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    backup_path = Column(String)
    error_message = Column(Text)
