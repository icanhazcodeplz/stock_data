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

The output CSV has two columns, ``symbol`` and ``reason``, where
``reason`` is one of ``ETF``, ``warrant``, ``right``, ``unit``,
``preferred``, ``when-issued``. It is committed so downstream jobs can
skip these symbols without re-querying Yahoo.

Usage:
    uv run python scripts/build_skip_symbols.py

Run from the repo root so ``settings`` and ``stock_data`` are importable.
"""

import csv
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from yfinance.data import YfData  # noqa: E402

from stock_data.get_all_stock_names import DEFAULT_SYMBOLS_FILE  # noqa: E402
from stock_data.io_utils import (  # noqa: E402
    DEFAULT_SKIP_SYMBOLS_FILE as SKIP_SYMBOLS_FILE,
)

QUOTE_URL = "https://query2.finance.yahoo.com/v7/finance/quote"

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


def write_skip_file(rows: list[tuple[str, str]], path: Path = SKIP_SYMBOLS_FILE) -> None:
    """Write ``rows`` to ``path`` as a two-column CSV, sorted by symbol."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "reason"])
        writer.writerows(sorted(rows))


def build_skip_symbols(limit: int | None = None) -> None:
    """Read the symbols file, classify skippable symbols, and write the CSV."""
    symbols = DEFAULT_SYMBOLS_FILE.read_text().split()
    if limit is not None:
        symbols = symbols[:limit]

    print(f"Classifying {len(symbols)} symbols...")
    quote_types = fetch_quote_types(symbols)
    rows = classify(symbols, quote_types)
    write_skip_file(rows)

    counts = Counter(reason for _, reason in rows)
    print(f"\nWrote {len(rows)} skip symbol(s) to {SKIP_SYMBOLS_FILE}")
    for reason, count in sorted(counts.items()):
        print(f"  {reason}: {count}")


if __name__ == "__main__":
    build_skip_symbols(limit=None)
