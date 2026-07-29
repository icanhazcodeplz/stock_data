"""Read-side entry point: load the latest stored fundamentals for the
working universe.

The DB helper itself (``get_latest_fundamentals``) lives in
``stock_data.storage`` next to the other SQL; this module just wires it to
``read_symbols()`` (the skip-list-filtered universe) for interactive use.
"""

from pathlib import Path

from stock_data.io_utils import read_symbols
from stock_data.storage import DB_PATH, connect, get_latest_fundamentals


def read_fundamentals_for_all_symbols(db_path: Path = DB_PATH) -> list[dict]:
    """Read the latest fundamentals row for every symbol in the working
    universe (``all_symbols.txt`` minus ``skip_symbols.csv``)."""
    symbols = read_symbols()
    conn = connect(db_path)
    try:
        return get_latest_fundamentals(conn, symbols)
    finally:
        conn.close()


if __name__ == "__main__":
    import pandas as pd

    out = pd.DataFrame(read_fundamentals_for_all_symbols())
    print(out)
