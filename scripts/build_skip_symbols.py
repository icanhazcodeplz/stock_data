#!/usr/bin/env python
"""Build ``data/skip_symbols.csv`` — the list of symbols to skip when
collecting Yahoo fundamentals.

Two kinds of symbols never carry the equity fundamentals we collect
(sector, industry, float, short interest) and only waste a Yahoo call:

* **ETFs / funds.** Yahoo reports these with ``quoteType == "ETF"``. A
  fund's ``.info`` has none of the company fields we store. Detected by
  querying Yahoo's batched quote endpoint for every symbol.
* **Warrants / rights / units.** These are derivative listings of an
  underlying company (mostly SPACs). Yahoo reports them as ``EQUITY``
  (or 404s), so ``quoteType`` can't distinguish them — instead they are
  detected from the ticker itself:
    - Alpaca dotted notation: ``FOO.U``/``.UN`` (unit), ``FOO.WS``/``.WT``
      (warrant), ``FOO.R``/``.RT`` (right).
    - NASDAQ 5th-letter convention: a 5+ char symbol ending in ``U``
      (unit), ``W`` (warrant), or ``R`` (right).
* **Preferred shares.** Alpaca writes these as ``FOO.PRx`` (preferred
  series x), which Yahoo doesn't resolve 1:1. A preferred behaves like a
  bond and carries none of the company fundamentals we store. Detected
  from the ticker suffix.
* **When-issued lines.** Alpaca writes these as ``FOO.WI`` — a conditional
  listing that trades between a security's announcement and its actual
  issuance (spinoffs, reorganizations, listing changes). The fundamentals
  belong to the underlying company, not the when-issued line, so Yahoo
  either doesn't know the ticker or returns a near-empty record.

The output CSV has three columns — ``symbol``, ``reason``, ``date`` — where
``reason`` is one of ``ETF``, ``warrant``, ``right``, ``unit``,
``preferred``, ``when-issued``. These are derived from the ticker or from
Yahoo's ``quoteType``, are permanent, and leave ``date`` empty.

``yahoo_unknown`` rows are the exception: they are written by the daily
run, not by this script, carry the date they were recorded, and are carried
across rebuilds because no amount of reclassification can rediscover them
(see ``carried_yahoo_unknown``).

The file is generated, not source — it is gitignored and rebuilt on demand.

The daily run calls ``rebuild_skip_symbols_if_stale()`` itself, so this
script only needs to be run by hand to force an immediate rebuild.

Usage:
    uv run python scripts/build_skip_symbols.py

Run from the repo root so ``settings`` and ``stock_data`` are importable.
"""

import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from yfinance.data import YfData  # noqa: E402

from stock_data.get_all_stock_names import DEFAULT_SYMBOLS_FILE  # noqa: E402
from stock_data.io_utils import (  # noqa: E402
    DEFAULT_SKIP_SYMBOLS_FILE as SKIP_SYMBOLS_FILE,
)
from stock_data.io_utils import (  # noqa: E402
    YAHOO_UNKNOWN_REASON,
    SkipRow,
    read_skip_rows,
    write_skip_rows,
)

QUOTE_URL = "https://query2.finance.yahoo.com/v7/finance/quote"

# The skip list only shifts as listings are created and retired, so a few days
# of drift costs nothing; a rebuild is a full pass over Yahoo's quote endpoint.
MAX_SKIP_SYMBOLS_AGE_DAYS = 3

# Dotted (Alpaca) suffixes -> reason.
_DOTTED_SUFFIXES: dict[str, str] = {
    "U": "unit",
    "UN": "unit",
    "W": "warrant",
    "WS": "warrant",
    "WT": "warrant",
    "WSA": "warrant",
    "WI": "when-issued",
    "R": "right",
    "RT": "right",
}

# NASDAQ 5th-letter code -> reason, for non-dotted symbols.
_LETTER_SUFFIXES: dict[str, str] = {"U": "unit", "W": "warrant", "R": "right"}


def structural_reason(symbol: str) -> str | None:
    """Classify a symbol as a warrant/right/unit/preferred from its ticker
    alone.

    Returns the reason string, or ``None`` if the ticker carries no such
    marker. Yahoo can't distinguish these (it reports the tradable ones as
    EQUITY and 404s on the rest), so the ticker convention is the only
    reliable signal.
    """
    _, dot, suffix = symbol.partition(".")
    if dot:
        suffix = suffix.upper()
        if suffix.startswith("PR"):  # PR, PRA..PRZ -> preferred series
            return "preferred"
        return _DOTTED_SUFFIXES.get(suffix)
    if len(symbol) >= 5:
        return _LETTER_SUFFIXES.get(symbol[-1])
    return None


def fetch_quote_types(symbols: list[str], *, batch_size: int = 100) -> dict[str, str]:
    """Return ``{symbol: quoteType}`` from Yahoo's batched quote endpoint.

    Symbols Yahoo doesn't recognize (e.g. dotted warrant/unit tickers) are
    simply absent from the result. A failing batch is reported and skipped
    rather than aborting the whole run.
    """
    data = YfData()
    quote_types: dict[str, str] = {}
    for i in range(0, len(symbols), batch_size):
        chunk = symbols[i : i + batch_size]
        try:
            resp = data.get(QUOTE_URL, params={"symbols": ",".join(chunk)})
            resp.raise_for_status()
            results = resp.json().get("quoteResponse", {}).get("result", [])
        except Exception as exc:  # noqa: BLE001 - keep going on a bad batch
            print(f"  batch {i}-{i + len(chunk)} FAILED ({exc!r}); skipping")
            continue
        for quote in results:
            sym = quote.get("symbol")
            if sym:
                quote_types[sym] = quote.get("quoteType")
        print(f"  fetched quoteType for {min(i + batch_size, len(symbols))}/{len(symbols)} symbols")
    return quote_types


def classify(symbols: list[str], quote_types: dict[str, str]) -> list[tuple[str, str]]:
    """Return ``(symbol, reason)`` rows for every skippable symbol.

    ETF classification (from Yahoo) takes precedence over the ticker-suffix
    rule, so a fund whose ticker happens to end in U/W/R is still "ETF".
    """
    rows: list[tuple[str, str]] = []
    for symbol in symbols:
        if quote_types.get(symbol) == "ETF":
            rows.append((symbol, "ETF"))
            continue
        reason = structural_reason(symbol)
        if reason is not None:
            rows.append((symbol, reason))
    return rows


def carried_yahoo_unknown(
    symbols: list[str],
    rows: list[tuple[str, str]],
    path: Path = SKIP_SYMBOLS_FILE,
) -> list[SkipRow]:
    """Return the ``yahoo_unknown`` rows a rebuild should carry forward.

    A rebuild recomputes its rows from the ticker and Yahoo's ``quoteType``,
    neither of which can rediscover that Yahoo has no fundamentals for a
    symbol — that is only learned by fetching it. Without carrying them the
    wholesale rewrite would drop those rows and the daily run would spend its
    budget rediscovering them.

    Dropped on the way through: symbols that have left the universe
    (delisted), so the file doesn't accumulate forever, and symbols this
    rebuild already classified some other way, so no symbol appears twice —
    that is how a newly listed ETF, unknown to Yahoo when it was first
    fetched, gets relabelled once Yahoo indexes it.

    Rows keep their recorded date, so a rebuild never restarts the retry
    clock.
    """
    universe = set(symbols)
    classified = {symbol for symbol, *_ in rows}
    return [
        row
        for row in read_skip_rows(path)
        if row.reason == YAHOO_UNKNOWN_REASON and row.symbol in universe and row.symbol not in classified
    ]


def build_skip_symbols(limit: int | None = None, path: Path = SKIP_SYMBOLS_FILE) -> None:
    """Read the symbols file, classify skippable symbols, and write the CSV."""
    symbols = DEFAULT_SYMBOLS_FILE.read_text().split()
    if limit is not None:
        symbols = symbols[:limit]

    print(f"Classifying {len(symbols)} symbols...")
    quote_types = fetch_quote_types(symbols)
    rows = classify(symbols, quote_types)
    rows += carried_yahoo_unknown(symbols, rows, path)
    write_skip_rows(rows, path)

    counts = Counter(reason for _, reason in rows)
    print(f"\nWrote {len(rows)} skip symbol(s) to {path}")
    for reason, count in sorted(counts.items()):
        print(f"  {reason}: {count}")


def skip_file_is_stale(path: Path = SKIP_SYMBOLS_FILE) -> bool:
    """Return True if the skip list is missing or older than the max age."""
    if not path.exists():
        return True
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age > timedelta(days=MAX_SKIP_SYMBOLS_AGE_DAYS)


def rebuild_skip_symbols_if_stale(path: Path = SKIP_SYMBOLS_FILE) -> None:
    """Rebuild the skip list unless it is still fresh.

    Called by the daily run so a missing or aging skip list can't quietly
    send warrants, units, and ETFs into the Yahoo budget. Must run after the
    symbols file is refreshed, since the classification reads it.
    """
    if not skip_file_is_stale(path):
        print(f"{path} is less than {MAX_SKIP_SYMBOLS_AGE_DAYS} days old; skipping rebuild.")
        return
    print(f"{path} is missing or more than {MAX_SKIP_SYMBOLS_AGE_DAYS} days old; rebuilding.")
    build_skip_symbols(path=path)


if __name__ == "__main__":
    build_skip_symbols(limit=None)
