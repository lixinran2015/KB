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


class IndustryTree(Base):
    """Global unified industry classification tree (self-referencing)."""
    __tablename__ = "industry_tree"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("industry_tree.id"), default=0)  # 0 = top-level root
    level = Column(Integer, nullable=False)  # 1/2/3/4
    sort = Column(Integer, default=0)

    # Relationships
    children = relationship("IndustryTree", backref="parent", remote_side=[id])
    stocks = relationship("StockIndustryKB", back_populates="industry")


class ConceptTag(Base):
    """Unified concept tag pool shared by all A-share stocks."""
    __tablename__ = "concept_tag"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)

    # Relationships
    stocks = relationship("StockIndustryKB", secondary="stock_concept_rel", back_populates="concepts")


class StockIndustryKB(Base):
    """Core knowledge base: stock -> leaf industry binding."""
    __tablename__ = "stock_industry_kb"

    stock_code = Column(String, primary_key=True)
    stock_name = Column(String, nullable=False)
    std_industry_id = Column(Integer, ForeignKey("industry_tree.id"), nullable=True)
    business_desc = Column(Text)

    # Tushare basic info
    area = Column(String)
    list_date = Column(String)
    market = Column(String)
    exchange = Column(String)
    industry_raw = Column(String)  # Tushare原始申万行业名
    main_business_raw = Column(Text)  # Tushare stock_company 主营业务
    is_hs = Column(String)
    enriched_at = Column(DateTime)

    # Relationships
    industry = relationship("IndustryTree", back_populates="stocks")
    concepts = relationship("ConceptTag", secondary="stock_concept_rel", back_populates="stocks")


class StockConceptRel(Base):
    """Many-to-many junction: stock <-> concept_tag."""
    __tablename__ = "stock_concept_rel"

    stock_code = Column(String, ForeignKey("stock_industry_kb.stock_code"), primary_key=True)
    concept_tag_id = Column(Integer, ForeignKey("concept_tag.id"), primary_key=True)

    # Relationships (read-only; use StockIndustryKB.concepts / ConceptTag.stocks for writes)
    stock = relationship("StockIndustryKB", viewonly=True)
    tag = relationship("ConceptTag", viewonly=True)
