#!/usr/bin/env python
"""Daily entry point.

Refreshes the symbol list (skipping the fetch if it was already updated
today), pulls Yahoo Finance fundamentals for a budgeted batch of symbols,
and stores the results in the fundamentals sqlite database. A successful
refetch replaces the symbol's previous row, so the database holds one row
per symbol (the latest); a failed fetch leaves the old row in place.

Each run spends at most ``MAX_YAHOO_CALLS_PER_RUN`` Yahoo calls: symbols
never fetched come first (alphabetically), then previously fetched symbols
whose latest row is older than ``MIN_REFRESH_AGE_DAYS``, oldest first.
Symbols already fresher than that are left alone, so a rerun on the same
day picks up where the previous run stopped instead of repeating it.

Symbols listed in ``data/skip_symbols.csv`` (ETFs, warrants/rights/units,
preferreds, when-issued lines) are dropped by ``read_symbols()``; that
file is rebuilt at the top of the run whenever it is missing or more than
``MAX_SKIP_SYMBOLS_AGE_DAYS`` old. The dotted symbols that
remain are share classes (e.g. "BRK.B"), which Yahoo writes with a dash
("BRK-B"); the ticker is translated for the Yahoo call but the row is
stored under the original Alpaca symbol so the database stays keyed
consistently with ``all_symbols.txt``.

Yahoo does not raise on a ticker it has no fundamentals for — it returns a
record with every company field ``None`` — so those records are counted as
failures and never inserted, otherwise their fresh ``retrieval_datetime``
would permanently hide the symbol from future runs. ``exchange`` does not
count as data here: Yahoo fills it in from the quote header even for
exchange-traded debt (baby bonds, senior notes) and for ETFs it reports as
``EQUITY``, none of which carry the company fields we collect.

Usage:
    uv run python scripts/get_stock_data.py

Run from the repo root so `settings` and `stock_data` are importable.
"""

import sys
from dataclasses import fields as dataclass_fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_skip_symbols import rebuild_skip_symbols_if_stale  # noqa: E402
from stock_data.clients.yahoo import Financials, get_financials  # noqa: E402
from stock_data.get_all_stock_names import refresh_symbols_if_stale  # noqa: E402
from stock_data.io_utils import read_symbols  # noqa: E402
from stock_data.storage import (  # noqa: E402
    connect,
    delete_older_fundamentals,
    get_latest_per_symbol,
    insert_fundamentals,
)

# Cap on Yahoo lookups per run. At ~6,300 symbols in the working universe,
# 500/day completes a full pass in ~13 days while staying well under Yahoo's
# unofficial throttling threshold for sequential .info calls.
MAX_YAHOO_CALLS_PER_RUN = 500

# A symbol whose latest row is younger than this is not refetched. Yahoo's
# short-interest fields update roughly biweekly, so weekly refresh already
# out-paces the data; this also makes same-day reruns cheap no-ops once the
# universe is caught up.
MIN_REFRESH_AGE_DAYS = 7


def alpaca_to_yahoo_symbol(symbol: str) -> str:
    """Translate Alpaca share-class notation to Yahoo's (``BRK.B`` -> ``BRK-B``).

    Only single-letter share-class suffixes survive the skip list, and for
    those the dot-to-dash rewrite is exact. (Warrant/unit/preferred suffixes,
    where the rewrite is irregular, are already dropped via
    ``skip_symbols.csv``.)
    """
    return symbol.replace(".", "-")


# Fields that carry no information about whether Yahoo actually knows the
# ticker: ``symbol`` is ours, and ``exchange`` comes off the quote header,
# which Yahoo fills in even for listings it has no fundamentals for.
_UNINFORMATIVE_FIELDS = frozenset({"symbol", "exchange"})


def _is_all_null(financials: Financials) -> bool:
    """True if Yahoo returned no fundamentals at all for this ticker.

    Exchange-traded debt (baby bonds, senior/subordinated notes) and some
    ETFs come back with every company field ``None`` but a populated
    ``exchange``, so ``exchange`` is excluded from the test — otherwise
    those records look "partial" and get stored.
    """
    return all(
        getattr(financials, field.name) is None
        for field in dataclass_fields(financials)
        if field.name not in _UNINFORMATIVE_FIELDS
    )


def get_stock_data(max_calls: int = MAX_YAHOO_CALLS_PER_RUN) -> None:
    """Refresh symbols, fetch a budgeted batch of Yahoo fundamentals, store them.

    ``max_calls`` caps the Yahoo lookups for this run; the default is the
    daily budget, and manual runs can pass something smaller.
    """
    refresh_symbols_if_stale()
    rebuild_skip_symbols_if_stale()

    symbols = read_symbols()

    conn = connect()
    try:
        latest = get_latest_per_symbol(conn, symbols)
        cutoff = datetime.now(timezone.utc) - timedelta(days=MIN_REFRESH_AGE_DAYS)
        missing = sorted(set(symbols) - latest.keys())
        stale = sorted((s for s in latest if latest[s] < cutoff), key=lambda s: latest[s])
        to_fetch = (missing + stale)[:max_calls]
        print(
            f"Universe: {len(symbols)} symbols "
            f"({len(missing)} missing, {len(stale)} stale, "
            f"{len(latest) - len(stale)} fresh); fetching {len(to_fetch)}."
        )

        fetched = 0
        failed: list[str] = []
        for symbol in to_fetch:
            try:
                financials = get_financials(alpaca_to_yahoo_symbol(symbol))
            except Exception as exc:
                failed.append(symbol)
                print(f"  {symbol}: FAILED to fetch ({exc!r})")
                continue
            if _is_all_null(financials):
                failed.append(symbol)
                print(f"  {symbol}: all fields null (unknown to Yahoo); not stored")
                continue
            # Store under the Alpaca symbol so DB keys match all_symbols.txt.
            financials.symbol = symbol
            insert_fundamentals(conn, [financials])
            delete_older_fundamentals(conn, symbol)
            fetched += 1
            print(f"  {symbol}: sector={financials.sector!r} float_shares={financials.float_shares}")
    finally:
        conn.close()

    print(f"\nFetched and stored {fetched}/{len(to_fetch)} symbols.")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed)}")


if __name__ == "__main__":
    get_stock_data()
