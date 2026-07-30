from datetime import datetime, timezone

import pandas as pd

from scripts.load_fundamentals import load_fundamentals
from stock_data.clients.yahoo import Financials
from stock_data.storage import connect, insert_fundamentals

T1 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


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


def _seed(db_path) -> None:
    conn = connect(db_path)
    try:
        insert_fundamentals(conn, [_make_financials("MSFT"), _make_financials("AAPL")], retrieval_datetime=T1)
    finally:
        conn.close()


def test_loads_latest_row_per_symbol_with_parsed_datetimes(tmp_path):
    db_path = tmp_path / "fundamentals.db"
    _seed(db_path)

    df = load_fundamentals(db_path)

    assert len(df) == 2
    assert pd.api.types.is_datetime64_any_dtype(df["retrieval_datetime"])
    # Rows come back sorted by symbol, not in insertion order.
    assert list(df["symbol"]) == ["AAPL", "MSFT"]
    assert df.loc[df["symbol"] == "MSFT", "float_shares"].item() == 1_000_000


def test_empty_database_returns_empty_frame(tmp_path):
    df = load_fundamentals(tmp_path / "fundamentals.db")

    assert df.empty
    assert "symbol" in df.columns
