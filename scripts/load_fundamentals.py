#!/usr/bin/env python
"""Load the fundamentals database into a pandas DataFrame.

``load_fundamentals()`` returns the stored fundamentals from
``data/fundamentals.db`` — one row per symbol, since the daily fetch replaces
a symbol's previous row on every successful refetch. ``retrieval_datetime``
is parsed to a timezone-aware pandas datetime column.

For the skip-list-filtered working universe (as dicts rather than a
DataFrame), see ``stock_data.read_fundamentals``.

Usage:
    uv run python scripts/load_fundamentals.py

Run from the repo root so ``settings`` and ``stock_data`` are importable.
"""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stock_data.storage import DB_PATH, connect  # noqa: E402


def load_fundamentals(db_path: Path = DB_PATH) -> pd.DataFrame:
    """Return the fundamentals table as a DataFrame, sorted by symbol.

    The ``retrieval_datetime`` column is parsed to timezone-aware datetimes.
    """
    conn = connect(db_path)
    try:
        df = pd.read_sql_query("SELECT * FROM fundamentals", conn)
    finally:
        conn.close()

    df["retrieval_datetime"] = pd.to_datetime(df["retrieval_datetime"], format="ISO8601")
    return df.sort_values("symbol").reset_index(drop=True)


if __name__ == "__main__":
    frame = load_fundamentals()
    print(frame)
    print(f"\n{len(frame)} rows, {frame['symbol'].nunique()} symbols")
