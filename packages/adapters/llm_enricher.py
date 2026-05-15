"""DeepSeek AI enrichment adapter.

Uses DeepSeek's OpenAI-compatible API to refine business descriptions
for stocks based on their Tushare main_business_raw text.

Usage:
    from packages.adapters.llm_enricher import DeepSeekEnricher
    enricher = DeepSeekEnricher()
    enricher.run_enrichment(limit=10, dry_run=True)
"""

import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


PROMPT_TEMPLATE = """\
Tushare 记录的主营业务原文：
{main_business}

请用一句话（50-80字）精炼描述该公司的主营业务：
1. 保留核心业务和主要产品/服务
2. 去掉冗余和次要信息
3. 用专业但简洁的中文表述
4. 不要出现"该公司"、"主要从事"等冗余开头，直接描述业务
"""


class DeepSeekEnricher:
    """Enrich stock business descriptions via DeepSeek AI."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
    ):
        if OpenAI is None:
            raise ImportError(
                "openai not installed; run: pip install openai"
            )

        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError(
                "DeepSeek API key required. Set DEEPSEEK_API_KEY env var "
                "or pass api_key= to constructor."
            )

        self.client = OpenAI(api_key=self.api_key, base_url=base_url)
        self.model = model

    def _build_prompt(self, main_business: str) -> str:
        biz_str = main_business.strip() if main_business else ""
        return PROMPT_TEMPLATE.format(main_business=biz_str)

    def enrich_single(
        self,
        stock_code: str,
        main_business: str,
    ) -> Optional[str]:
        """Generate a refined business description for a single stock.

        Returns the generated description, or None if the API call fails.
        """
        if not main_business or not main_business.strip():
            logger.warning(f"No main_business for {stock_code}, skipping")
            return None

        prompt = self._build_prompt(main_business)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的A股分析师，擅长用简洁准确的语言描述上市公司主营业务。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=150,
                temperature=0.3,
            )
            desc = response.choices[0].message.content.strip()
            # Clean up: remove quotes, extra newlines
            desc = desc.replace('"', "").replace("'", "").strip()
            # Truncate to reasonable length
            if len(desc) > 200:
                desc = desc[:200] + "..."
            return desc
        except Exception as e:
            logger.warning(f"DeepSeek API failed for {stock_code}: {e}")
            return None

    def run_enrichment(
        self,
        limit: Optional[int] = None,
        batch_size: int = 10,
        dry_run: bool = False,
    ):
        """Run the enrichment pipeline for stocks missing business_desc.

        Args:
            limit: Max number of stocks to process (None = all unenriched)
            batch_size: Commit every N stocks
            dry_run: If True, print prompts without calling API or writing to DB
        """
        from packages.domain.database import get_session
        from packages.domain.models import StockIndustryKB

        session = get_session()
        try:
            # Query stocks that need enrichment AND have main_business_raw
            query = (
                session.query(StockIndustryKB)
                .filter(
                    ((StockIndustryKB.business_desc.is_(None))
                    | (StockIndustryKB.enriched_at.is_(None)))
                    & (StockIndustryKB.main_business_raw.isnot(None))
                )
            )
            if limit:
                query = query.limit(limit)

            stocks = query.all()
            total = len(stocks)
            logger.info(f"Found {total} stocks to enrich (with main_business_raw)")

            if total == 0:
                logger.info("No stocks need enrichment")
                return

            processed = 0
            enriched = 0
            failed = 0
            skipped = 0

            for stock in stocks:
                processed += 1
                main_biz = stock.main_business_raw or ""

                if not main_biz.strip():
                    skipped += 1
                    continue

                if dry_run:
                    prompt = self._build_prompt(main_biz)
                    print(f"\n[{processed}/{total}] {stock.stock_code} {stock.stock_name}")
                    print(f"Main business raw: {main_biz[:100]}...")
                    print(f"Prompt:\n{prompt}")
                    print("-" * 40)
                    continue

                desc = self.enrich_single(
                    stock_code=stock.stock_code,
                    main_business=main_biz,
                )

                if desc:
                    stock.business_desc = desc
                    stock.enriched_at = datetime.now()
                    enriched += 1
                    logger.info(f"  [{processed}/{total}] {stock.stock_code} enriched")
                else:
                    failed += 1
                    logger.warning(f"  [{processed}/{total}] {stock.stock_code} failed")

                if processed % batch_size == 0:
                    session.commit()
                    logger.info(f"  Committed batch: {processed}/{total}")

            session.commit()
            logger.info("=" * 50)
            logger.info(f"Enrichment complete: {enriched} enriched, {failed} failed, {skipped} skipped, {total} total")
            logger.info("=" * 50)

        except Exception as e:
            session.rollback()
            logger.error(f"Enrichment failed: {e}")
            raise
        finally:
            session.close()
