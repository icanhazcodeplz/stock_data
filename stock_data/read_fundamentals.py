import sqlite3
from pathlib import Path

from stock_data.get_all_stock_names import DEFAULT_SYMBOLS_FILE
from stock_data.storage import DB_PATH, connect


def read_all_symbols(path: Path = DEFAULT_SYMBOLS_FILE) -> list[str]:
    """Read symbols from the symbols file, one per line."""
    return path.read_text().splitlines()


def get_latest_fundamentals(
    conn: sqlite3.Connection,
    symbols: list[str],
) -> list[dict]:
    """Return the most recent fundamentals row for each of ``symbols``.

    Symbols with no rows in the database are simply absent from the result.
    """
    if not symbols:
        return []
    placeholders = ",".join("?" for _ in symbols)
    cursor = conn.execute(
        f"""
        SELECT f.*
        FROM fundamentals f
        INNER JOIN (
            SELECT symbol, MAX(retrieval_datetime) AS max_dt
            FROM fundamentals
            WHERE symbol IN ({placeholders})
            GROUP BY symbol
        ) latest
        ON f.symbol = latest.symbol AND f.retrieval_datetime = latest.max_dt
        """,
        symbols,
    )
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def read_fundamentals_for_all_symbols(
    db_path: Path = DB_PATH,
    symbols_path: Path = DEFAULT_SYMBOLS_FILE,
) -> list[dict]:
    """Read the latest fundamentals row for every symbol in ``symbols_path``."""
    symbols = read_all_symbols(symbols_path)
    conn = connect(db_path)
    try:
        return get_latest_fundamentals(conn, symbols)
    finally:
        conn.close()

if __name__ == "__main__":
    import pandas as pd
    out = read_fundamentals_for_all_symbols()
    out = pd.DataFrame(out)
    print(out)
