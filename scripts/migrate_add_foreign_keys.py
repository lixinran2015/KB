"""Migrate existing tables to add foreign key constraints.

SQLite does not support ALTER TABLE ADD FOREIGN KEY, so we must
recreate the tables and copy data over.

Usage:
    python -m scripts.migrate_add_foreign_keys
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3

DB_PATH = Path(__file__).parent.parent / "data" / "stock_kb.sqlite"

MIGRATION_SQL = """
-- ============================================
-- 1. stock_concept_rel: add FK constraints
-- ============================================
CREATE TABLE stock_concept_rel_new (
    stock_code VARCHAR NOT NULL,
    concept_tag_id INTEGER NOT NULL,
    PRIMARY KEY (stock_code, concept_tag_id),
    FOREIGN KEY (stock_code) REFERENCES stock_industry_kb(stock_code),
    FOREIGN KEY (concept_tag_id) REFERENCES concept_tag(id)
);
INSERT INTO stock_concept_rel_new SELECT * FROM stock_concept_rel;
DROP TABLE stock_concept_rel;
ALTER TABLE stock_concept_rel_new RENAME TO stock_concept_rel;

-- ============================================
-- 2. stock_industry_kb: add FK on std_industry_id
-- ============================================
CREATE TABLE stock_industry_kb_new (
    stock_code VARCHAR NOT NULL PRIMARY KEY,
    stock_name VARCHAR NOT NULL,
    std_industry_id INTEGER,
    business_desc TEXT,
    area VARCHAR,
    list_date VARCHAR,
    market VARCHAR,
    exchange VARCHAR,
    industry_raw VARCHAR,
    main_business_raw TEXT,
    is_hs VARCHAR,
    enriched_at DATETIME,
    FOREIGN KEY (std_industry_id) REFERENCES industry_tree(id)
);
INSERT INTO stock_industry_kb_new SELECT
    stock_code, stock_name, std_industry_id, business_desc,
    area, list_date, market, exchange, industry_raw,
    main_business_raw, is_hs, enriched_at
FROM stock_industry_kb;
DROP TABLE stock_industry_kb;
ALTER TABLE stock_industry_kb_new RENAME TO stock_industry_kb;

-- ============================================
-- 3. industry_tree: add FK on parent_id
-- ============================================
CREATE TABLE industry_tree_new (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    name VARCHAR NOT NULL,
    parent_id INTEGER DEFAULT 0,
    level INTEGER NOT NULL,
    sort INTEGER DEFAULT 0,
    FOREIGN KEY (parent_id) REFERENCES industry_tree(id)
);
INSERT INTO industry_tree_new SELECT * FROM industry_tree;
DROP TABLE industry_tree;
ALTER TABLE industry_tree_new RENAME TO industry_tree;
"""


def migrate():
    print("Adding foreign key constraints to existing tables...")
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(MIGRATION_SQL)
    conn.commit()

    # Verify FKs are enabled and working
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys")
    fk_enabled = cursor.fetchone()[0]
    print(f"  PRAGMA foreign_keys = {fk_enabled}")

    # Verify table schemas
    for table in ["industry_tree", "stock_industry_kb", "stock_concept_rel"]:
        cursor.execute(f"PRAGMA foreign_key_list({table})")
        fks = cursor.fetchall()
        if fks:
            print(f"  {table} foreign keys:")
            for fk in fks:
                # fk = (id, seq, table, from, to, on_update, on_delete, match)
                print(f"    {fk[3]} -> {fk[2]}.{fk[4]}")
        else:
            print(f"  {table}: no foreign keys found")

    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    migrate()
