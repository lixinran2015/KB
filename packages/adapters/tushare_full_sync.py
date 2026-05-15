"""Tushare full-stock synchronization adapter.

Fetches the complete A-share stock list, concept boards, and stock-concept
relations from Tushare, then syncs them into the SQLite KB database.

Usage:
    from packages.adapters.tushare_full_sync import TushareFullSync
    sync = TushareFullSync()
    sync.run_full_sync()
"""

import logging
import os
import time
from typing import Dict, List, Optional, Set

import pandas as pd

from packages.adapters.industry_mapping import map_tushare_industry

logger = logging.getLogger(__name__)

try:
    import tushare as ts
except ImportError:
    ts = None


class TushareFullSync:
    """Sync all A-share stocks and concept data from Tushare to the KB DB."""

    def __init__(self, token: Optional[str] = None):
        if ts is None:
            raise ImportError("tushare not installed; run: pip install tushare")

        self.token = token or os.getenv("TUSHARE_TOKEN")
        if not self.token:
            raise ValueError(
                "Tushare token required. Set TUSHARE_TOKEN env var "
                "or pass token= to constructor."
            )
        self.pro = ts.pro_api(self.token)

        # Cached data
        self._all_stocks: Optional[pd.DataFrame] = None
        self._all_concepts: Optional[pd.DataFrame] = None
        self._concept_stock_map: Optional[Dict[str, List[str]]] = None

    # ── Fetch methods ──

    def fetch_all_stocks(self) -> pd.DataFrame:
        """Fetch the complete A-share stock list via stock_basic."""
        if self._all_stocks is not None:
            return self._all_stocks

        # exchange: 上交所/SZSE深交所/北交所/BSE
        # list_status: L上市/D退市/P暂停上市
        df = self.pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,exchange,list_date,is_hs",
        )
        if df is None:
            df = pd.DataFrame()
        self._all_stocks = df
        logger.info(f"Fetched {len(df)} stocks from Tushare stock_basic")
        return df

    def fetch_main_business(self, stock_codes: List[str]) -> Dict[str, str]:
        """Fetch main business description for a batch of stocks via stock_company.

        Returns: {ts_code: main_business_text, ...}
        """
        if not stock_codes:
            return {}

        results: Dict[str, str] = {}
        batch_size = 100

        for i in range(0, len(stock_codes), batch_size):
            batch = stock_codes[i:i + batch_size]
            codes = ",".join(batch)
            try:
                df = self.pro.stock_company(
                    ts_code=codes,
                    fields="ts_code,main_business",
                )
                time.sleep(0.3)
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        code = str(row.get("ts_code", "")).strip()
                        biz = str(row.get("main_business", "")).strip()
                        if code and biz:
                            results[code] = biz
                logger.info(f"  Main business fetched: {min(i + batch_size, len(stock_codes))}/{len(stock_codes)}")
            except Exception as e:
                logger.warning(f"Failed to fetch main business batch {i}: {e}")

        logger.info(f"Fetched main business for {len(results)} stocks")
        return results

    def fetch_all_concepts(self) -> pd.DataFrame:
        """Fetch all concept boards from Tushare."""
        if self._all_concepts is not None:
            return self._all_concepts

        df = self.pro.concept()
        if df is None:
            df = pd.DataFrame()
        self._all_concepts = df
        logger.info(f"Fetched {len(df)} concept boards from Tushare")
        return df

    def fetch_concept_stocks(self, concept_code: str) -> pd.DataFrame:
        """Fetch constituent stocks for a single concept board."""
        try:
            df = self.pro.concept_detail(id=concept_code, fields="ts_code,name")
            time.sleep(0.3)  # rate-limit courtesy
            return df if df is not None else pd.DataFrame()
        except Exception as e:
            logger.warning(f"Failed to fetch concept {concept_code}: {e}")
            return pd.DataFrame()

    def build_concept_stock_map(self) -> Dict[str, List[str]]:
        """Build a mapping: concept_code -> [ts_code, ...] for all concepts."""
        if self._concept_stock_map is not None:
            return self._concept_stock_map

        concepts = self.fetch_all_concepts()
        if concepts.empty:
            return {}

        mapping: Dict[str, List[str]] = {}
        total = len(concepts)

        for idx, row in concepts.iterrows():
            code = str(row.get("code", "")).strip()
            name = str(row.get("name", "")).strip()
            if not code:
                continue

            df = self.fetch_concept_stocks(code)
            stocks = [
                str(r.get("ts_code", "")).strip()
                for _, r in df.iterrows()
                if str(r.get("ts_code", "")).strip()
            ]
            if stocks:
                mapping[code] = stocks

            if (idx + 1) % 10 == 0 or (idx + 1) == total:
                logger.info(f"  Concept progress: {idx + 1}/{total} ({name})")

        self._concept_stock_map = mapping
        total_rels = sum(len(v) for v in mapping.values())
        logger.info(f"Built concept-stock map: {len(mapping)} concepts, {total_rels} relations")
        return mapping

    # ── Sync methods ──

    def sync_stocks_to_db(self, session) -> Set[str]:
        """Upsert all stocks from Tushare into stock_industry_kb.

        Returns the set of stock codes that were synced.
        """
        from packages.domain.models import StockIndustryKB

        df = self.fetch_all_stocks()
        if df.empty:
            logger.warning("No stocks fetched from Tushare")
            return set()

        synced = 0
        updated = 0
        unmapped_industries: Set[str] = set()
        stock_codes: Set[str] = set()

        for _, row in df.iterrows():
            code = str(row.get("ts_code", "")).strip()
            name = str(row.get("name", "")).strip()
            if not code:
                continue

            stock_codes.add(code)
            area = str(row.get("area", "")).strip() or None
            list_date = str(row.get("list_date", "")).strip() or None
            market = str(row.get("market", "")).strip() or None
            exchange_val = str(row.get("exchange", "")).strip() or None
            industry_raw = str(row.get("industry", "")).strip() or None
            is_hs = str(row.get("is_hs", "")).strip() or None

            # Map Tushare industry to our leaf node
            industry_id = None
            if industry_raw:
                industry_id = map_tushare_industry(industry_raw)
                if industry_id is None:
                    unmapped_industries.add(industry_raw)

            existing = session.query(StockIndustryKB).filter_by(stock_code=code).first()
            if existing:
                existing.stock_name = name
                if industry_id is not None:
                    existing.std_industry_id = industry_id
                if area:
                    existing.area = area
                if list_date:
                    existing.list_date = list_date
                if market:
                    existing.market = market
                if exchange_val:
                    existing.exchange = exchange_val
                if industry_raw:
                    existing.industry_raw = industry_raw
                if is_hs:
                    existing.is_hs = is_hs
                updated += 1
            else:
                session.add(StockIndustryKB(
                    stock_code=code,
                    stock_name=name,
                    std_industry_id=industry_id,
                    area=area,
                    list_date=list_date,
                    market=market,
                    exchange=exchange_val,
                    industry_raw=industry_raw,
                    is_hs=is_hs,
                ))
                synced += 1

            if (synced + updated) % 100 == 0:
                session.commit()
                logger.info(f"  Stock progress: {synced + updated} processed")

        session.commit()
        logger.info(f"Stock sync complete: {synced} inserted, {updated} updated")

        if unmapped_industries:
            logger.warning(f"Unmapped industries ({len(unmapped_industries)}): {sorted(unmapped_industries)}")

        # Fetch and update main_business for all synced stocks
        main_biz_map = self.fetch_main_business(list(stock_codes))
        if main_biz_map:
            mb_updated = 0
            for code, biz in main_biz_map.items():
                rec = session.query(StockIndustryKB).filter_by(stock_code=code).first()
                if rec:
                    rec.main_business_raw = biz
                    mb_updated += 1
                    if mb_updated % 100 == 0:
                        session.commit()
                        logger.info(f"  Main business progress: {mb_updated} updated")
            session.commit()
            logger.info(f"Main business updated: {mb_updated} stocks")

        return stock_codes

    def sync_concepts_to_db(self, session) -> Dict[str, int]:
        """Upsert all concept boards into concept_tag.

        Returns a mapping: concept_name -> concept_tag_id.
        """
        from packages.domain.models import ConceptTag

        df = self.fetch_all_concepts()
        if df.empty:
            logger.warning("No concepts fetched from Tushare")
            return {}

        name_to_id: Dict[str, int] = {}
        inserted = 0

        for _, row in df.iterrows():
            name = str(row.get("name", "")).strip()
            if not name:
                continue

            existing = session.query(ConceptTag).filter_by(name=name).first()
            if existing:
                name_to_id[name] = existing.id
            else:
                tag = ConceptTag(name=name)
                session.add(tag)
                session.flush()  # get auto-generated id
                name_to_id[name] = tag.id
                inserted += 1

        session.commit()
        logger.info(f"Concept sync complete: {inserted} new, {len(name_to_id)} total")
        return name_to_id

    def sync_stock_concepts_to_db(self, session, stock_codes: Set[str] = None):
        """Sync stock->concept relations into stock_concept_rel.

        Requires concepts to already be in concept_tag.
        """
        from packages.domain.models import ConceptTag, StockConceptRel

        concept_map = self.build_concept_stock_map()
        if not concept_map:
            logger.warning("No concept-stock data to sync")
            return

        # Build concept_code -> concept_name mapping
        concepts_df = self.fetch_all_concepts()
        code_to_name = {
            str(r.get("code", "")).strip(): str(r.get("name", "")).strip()
            for _, r in concepts_df.iterrows()
        }

        # Build concept_name -> tag_id mapping from DB
        name_to_id = {t.name: t.id for t in session.query(ConceptTag).all()}

        inserted = 0
        skipped = 0

        for concept_code, stocks in concept_map.items():
            concept_name = code_to_name.get(concept_code)
            if not concept_name:
                continue

            tag_id = name_to_id.get(concept_name)
            if tag_id is None:
                logger.warning(f"Concept '{concept_name}' not found in DB, skipping")
                continue

            for ts_code in stocks:
                if stock_codes and ts_code not in stock_codes:
                    continue

                # Check if relation already exists
                existing = session.query(StockConceptRel).filter_by(
                    stock_code=ts_code, concept_tag_id=tag_id
                ).first()
                if existing:
                    skipped += 1
                    continue

                session.add(StockConceptRel(
                    stock_code=ts_code,
                    concept_tag_id=tag_id,
                ))
                inserted += 1

                if inserted % 500 == 0:
                    session.commit()
                    logger.info(f"  Relation progress: {inserted} inserted")

        session.commit()
        logger.info(f"Stock-concept sync complete: {inserted} inserted, {skipped} already existed")

    # ── Orchestration ──

    def run_full_sync(self, skip_concepts: bool = False):
        """Run the full synchronization pipeline.

        1. Sync all stocks from Tushare stock_basic
        2. Sync all concept boards
        3. Sync stock-concept relations (unless skip_concepts=True)
        """
        from packages.domain.database import get_session

        logger.info("=" * 50)
        logger.info("Starting Tushare full sync")
        logger.info("=" * 50)

        session = get_session()
        try:
            # Step 1: stocks
            stock_codes = self.sync_stocks_to_db(session)

            # Step 2: concepts
            self.sync_concepts_to_db(session)

            # Step 3: stock-concept relations
            if not skip_concepts:
                self.sync_stock_concepts_to_db(session, stock_codes)

            logger.info("=" * 50)
            logger.info("Tushare full sync completed successfully")
            logger.info("=" * 50)

        except Exception as e:
            session.rollback()
            logger.error(f"Full sync failed: {e}")
            raise
        finally:
            session.close()
