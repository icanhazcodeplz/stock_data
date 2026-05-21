from datetime import datetime, timedelta, timezone

from stock_data.clients.yahoo import Financials
from stock_data.storage import connect, get_latest_per_symbol, insert_fundamentals


def _make_financials(symbol: str) -> Financials:
    return Financials(
        symbol=symbol,
        float_shares=1_000_000,
        short_ratio=1.5,
        short_interest=10_000,
        sector="Technology",
        industry="Software",
        country="United States",
        exchange="NMS",
        short_float=0.05,
    )


def test_insert_and_get_latest_per_symbol_roundtrip(tmp_path):
    db_path = tmp_path / "fundamentals.db"
    conn = connect(db_path)
    try:
        t1 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(days=1)
        t3 = t2 + timedelta(days=1)

        # First retrieval: two symbols
        n = insert_fundamentals(
            conn,
            [_make_financials("AAPL"), _make_financials("MSFT")],
            retrieval_datetime=t1,
        )
        assert n == 2

        # Second retrieval: only AAPL (latest for AAPL should be t2)
        insert_fundamentals(conn, [_make_financials("AAPL")], retrieval_datetime=t2)

        # Third retrieval: a new symbol
        insert_fundamentals(conn, [_make_financials("GOOG")], retrieval_datetime=t3)

        latest_all = get_latest_per_symbol(conn)
        assert latest_all == {"AAPL": t2, "MSFT": t1, "GOOG": t3}

        latest_subset = get_latest_per_symbol(conn, ["AAPL", "MSFT"])
        assert latest_subset == {"AAPL": t2, "MSFT": t1}

        # Unknown symbol filter -> empty
        assert get_latest_per_symbol(conn, ["NOPE"]) == {}

        # Empty iterable -> empty
        assert get_latest_per_symbol(conn, []) == {}
    finally:
        conn.close()


def test_connect_sets_pragmas_and_creates_schema(tmp_path):
    db_path = tmp_path / "fundamentals.db"
    conn = connect(db_path)
    try:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
        assert journal_mode.lower() == "wal"
        # synchronous=NORMAL == 1
        assert synchronous == 1

        # Table exists
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fundamentals'"
        ).fetchone()
        assert row is not None

        # Index exists
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_fundamentals_symbol_retrieval'"
        ).fetchone()
        assert row is not None
    finally:
        conn.close()
