import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from settings import REPO_ROOT
from stock_data.clients.yahoo import Financials

DB_PATH = REPO_ROOT / "data" / "fundamentals.db"


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS fundamentals (
    symbol TEXT NOT NULL,
    retrieval_datetime TEXT NOT NULL,
    float_shares INTEGER,
    short_ratio REAL,
    short_interest INTEGER,
    sector TEXT,
    industry TEXT,
    country TEXT,
    exchange TEXT,
    short_float REAL
)
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_fundamentals_symbol_retrieval
    ON fundamentals (symbol, retrieval_datetime)
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    """Open a sqlite connection, set PRAGMAs, and ensure schema exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(_CREATE_TABLE_SQL)
    conn.execute(_CREATE_INDEX_SQL)
    conn.commit()
    return conn


def insert_fundamentals(
    conn: sqlite3.Connection,
    records: Iterable[Financials],
    retrieval_datetime: datetime | None = None,
) -> int:
    """Insert Financials records. Returns the number of rows inserted."""
    if retrieval_datetime is None:
        retrieval_datetime = datetime.now(timezone.utc)
    ts = retrieval_datetime.isoformat()
    rows = [
        (
            r.symbol,
            ts,
            r.float_shares,
            r.short_ratio,
            r.short_interest,
            r.sector,
            r.industry,
            r.country,
            r.exchange,
            r.short_float,
        )
        for r in records
    ]
    cursor = conn.executemany(
        """
        INSERT INTO fundamentals (
            symbol, retrieval_datetime, float_shares, short_ratio,
            short_interest, sector, industry, country, exchange, short_float
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return cursor.rowcount


def get_latest_per_symbol(
    conn: sqlite3.Connection,
    symbols: Iterable[str] | None = None,
) -> dict[str, datetime]:
    """Return {symbol: latest retrieval_datetime} for given (or all) symbols."""
    if symbols is None:
        cursor = conn.execute(
            "SELECT symbol, MAX(retrieval_datetime) FROM fundamentals GROUP BY symbol"
        )
    else:
        symbols_list = list(symbols)
        if not symbols_list:
            return {}
        placeholders = ",".join("?" for _ in symbols_list)
        cursor = conn.execute(
            f"SELECT symbol, MAX(retrieval_datetime) FROM fundamentals "
            f"WHERE symbol IN ({placeholders}) GROUP BY symbol",
            symbols_list,
        )
    return {symbol: datetime.fromisoformat(ts) for symbol, ts in cursor.fetchall()}
