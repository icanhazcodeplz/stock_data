#!/usr/bin/env python
"""Daily entry point.

Refreshes the symbol list (skipping the fetch if it was already updated
today), pulls Yahoo Finance fundamentals for each symbol, and stores the
results in the fundamentals sqlite database.

Symbols containing a "." (Alpaca's notation for share classes, preferred
shares, units, warrants, etc. — e.g. "BRK.B", "ABR.PRD", "AAC.U") are
skipped. Yahoo Finance does not recognize that notation directly (a raw
lookup 404s), and it uses its own dash-based convention that isn't a simple
1:1 translation — e.g. "BRK.B" -> "BRK-B" (dot to dash works), but
"AAC.U" -> "AAC-UN" and "ABR.PRD" -> "ABR-PD" (irregular suffix rewrites,
verified by hand against a few examples). Building a correct suffix-mapping
table is future work; for now these symbols are just logged and skipped.

Usage:
    uv run python scripts/get_stock_data [--limit N]

Run from the repo root so `settings` and `stock_data` are importable.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stock_data.clients.yahoo import get_financials  # noqa: E402
from stock_data.get_all_stock_names import (  # noqa: E402
    DEFAULT_SYMBOLS_FILE,
    refresh_symbols_if_stale,
)
from stock_data.storage import connect, insert_fundamentals  # noqa: E402


def get_stock_data(limit: int | None = None) -> None:
    """Refresh symbols, fetch Yahoo fundamentals, and store them.

    ``limit`` restricts processing to the first N symbols, for quick manual
    testing without hitting the whole universe.
    """
    refresh_symbols_if_stale()
    # Always read back from the symbols file (sorted, one per line) rather
    # than trusting the in-memory return value, so behavior is identical
    # whether this run triggered a refetch or not.
    symbols = DEFAULT_SYMBOLS_FILE.read_text().splitlines()
    if limit is not None:
        symbols = symbols[:limit]

    dotted = [s for s in symbols if "." in s]
    clean_symbols = [s for s in symbols if "." not in s]
    if dotted:
        print(
            f"Skipping {len(dotted)} symbol(s) with '.' in the name "
            f"(no reliable Yahoo mapping): {', '.join(dotted)}"
        )

    conn = connect()
    try:
        fetched = 0
        failed: list[str] = []
        for symbol in clean_symbols:
            try:
                financials = get_financials(symbol)
            except Exception as exc:
                failed.append(symbol)
                print(f"  {symbol}: FAILED to fetch ({exc!r})")
                continue
            insert_fundamentals(conn, [financials])
            fetched += 1
            print(
                f"  {symbol}: sector={financials.sector!r} "
                f"float_shares={financials.float_shares}"
            )
    finally:
        conn.close()

    print(f"\nFetched and stored {fetched}/{len(clean_symbols)} symbols.")
    if dotted:
        print(f"Skipped (dotted): {len(dotted)}")
    if failed:
        print(f"Failed: {', '.join(failed)}")


if __name__ == "__main__":
    get_stock_data(limit=100)
