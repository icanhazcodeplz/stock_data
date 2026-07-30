"""Filesystem helpers for reading and writing the project's symbol lists.

Centralizes access to ``all_symbols.txt`` and ``skip_symbols.csv`` so callers
get a single, already-filtered list of symbols worth fetching, and so the
skip CSV has exactly one writer.
"""

import csv
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import NamedTuple

from stock_data.get_all_stock_names import DEFAULT_SYMBOLS_FILE

# skip_symbols.csv lives alongside all_symbols.txt (built by
# scripts/build_skip_symbols.py).
DEFAULT_SKIP_SYMBOLS_FILE: Path = DEFAULT_SYMBOLS_FILE.parent / "skip_symbols.csv"

# Reason recorded for symbols Yahoo has no fundamentals for. Unlike the other
# reasons, these are discovered by the daily run rather than derived from the
# ticker, so a rebuild can't recompute them (see ``carried_yahoo_unknown``).
YAHOO_UNKNOWN_REASON = "yahoo_unknown"

# How long a ``yahoo_unknown`` verdict stands before the symbol is retried.
# Most of these are bonds and ETFs that will never have fundamentals, but a
# few are real companies Yahoo has not indexed yet (a recent IPO, a thinly
# covered small cap), and those must not be excluded forever.
YAHOO_UNKNOWN_RETRY_DAYS = 30


class SkipRow(NamedTuple):
    """One row of the skip CSV.

    ``date`` is the ISO date the row was recorded and is only meaningful for
    ``yahoo_unknown`` rows, which expire; structural rows (ETF, warrant,
    preferred, ...) are permanent and leave it empty.
    """

    symbol: str
    reason: str
    date: str = ""


def read_skip_rows(path: Path = DEFAULT_SKIP_SYMBOLS_FILE) -> list[SkipRow]:
    """Return the rows of the skip CSV.

    A missing file yields an empty list (nothing to skip). A file without the
    ``date`` column reads back with an empty date, so older skip lists load
    unchanged.
    """
    if not path.exists():
        return []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        return [
            SkipRow(row["symbol"], row.get("reason") or "", row.get("date") or "")
            for row in reader
            if row.get("symbol")
        ]


def write_skip_rows(rows: Iterable[SkipRow], path: Path = DEFAULT_SKIP_SYMBOLS_FILE) -> None:
    """Write ``rows`` to ``path`` as a CSV, sorted by symbol."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "reason", "date"])
        writer.writerows(sorted(SkipRow(*row) for row in rows))


def is_expired(
    row: SkipRow,
    today: date | None = None,
    retry_days: int = YAHOO_UNKNOWN_RETRY_DAYS,
) -> bool:
    """True if ``row`` is a ``yahoo_unknown`` verdict old enough to retry.

    Only ``yahoo_unknown`` rows expire. A row with no date — written before
    dates were recorded — counts as expired so it is retried once and then
    carries a date like any other.
    """
    if row.reason != YAHOO_UNKNOWN_REASON:
        return False
    if not row.date:
        return True
    try:
        recorded = date.fromisoformat(row.date)
    except ValueError:
        return True
    return ((today or date.today()) - recorded).days >= retry_days


def append_skip_symbols(
    symbols: Iterable[str],
    reason: str,
    path: Path = DEFAULT_SKIP_SYMBOLS_FILE,
    today: date | None = None,
) -> list[str]:
    """Record ``symbols`` under ``reason``; return the ones newly added.

    A symbol already listed under a *different* reason is left alone, so this
    never overwrites a classification the rebuild owns. A symbol already
    listed under the *same* reason has its date refreshed — that is what
    restarts the retry clock when a symbol is confirmed unknown again — but it
    is not reported as newly added.
    """
    stamp = (today or date.today()).isoformat()
    wanted = set(symbols)
    rows = read_skip_rows(path)

    updated: list[SkipRow] = []
    refreshed = False
    for row in rows:
        if row.symbol in wanted and row.reason == reason:
            updated.append(SkipRow(row.symbol, reason, stamp))
            refreshed = refreshed or row.date != stamp
        else:
            updated.append(row)

    listed = {row.symbol for row in rows}
    added = sorted(wanted - listed)
    updated.extend(SkipRow(symbol, reason, stamp) for symbol in added)

    if added or refreshed:
        write_skip_rows(updated, path)
    return added


def remove_skip_symbols(
    symbols: Iterable[str],
    reason: str,
    path: Path = DEFAULT_SKIP_SYMBOLS_FILE,
) -> list[str]:
    """Drop ``symbols`` listed under ``reason``; return the ones removed.

    Used when a retry succeeds: the symbol has fundamentals after all, so its
    stale verdict must go rather than linger and be carried across rebuilds.
    Rows under any other reason are untouched.
    """
    wanted = set(symbols)
    rows = read_skip_rows(path)
    kept = [row for row in rows if not (row.symbol in wanted and row.reason == reason)]
    removed = sorted({row.symbol for row in rows} - {row.symbol for row in kept})
    if removed:
        write_skip_rows(kept, path)
    return removed


def read_symbols(
    symbols_path: Path = DEFAULT_SYMBOLS_FILE,
    skip_path: Path = DEFAULT_SKIP_SYMBOLS_FILE,
    today: date | None = None,
) -> list[str]:
    """Read all symbols, minus those currently skipped.

    Reads ``all_symbols.txt`` (one symbol per line), drops any symbol listed
    in ``skip_symbols.csv`` (ETFs, warrants/rights/units, preferreds,
    when-issued lines, and symbols Yahoo has no record of — none of which have
    equity fundamentals to fetch), and returns the rest in the file's original
    order.

    A ``yahoo_unknown`` row older than ``YAHOO_UNKNOWN_RETRY_DAYS`` is treated
    as no longer binding, so the symbol re-enters the universe for one more
    attempt.
    """
    symbols = symbols_path.read_text().split()
    skip = {row.symbol for row in read_skip_rows(skip_path) if not is_expired(row, today)}
    return [symbol for symbol in symbols if symbol not in skip]
