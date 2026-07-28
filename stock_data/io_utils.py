"""Filesystem helpers for reading the project's symbol lists.

Centralizes reading ``all_symbols.txt`` and ``skip_symbols.csv`` so callers
get a single, already-filtered list of symbols worth fetching.
"""

import csv
from pathlib import Path

from stock_data.get_all_stock_names import DEFAULT_SYMBOLS_FILE

# skip_symbols.csv lives alongside all_symbols.txt (built by
# scripts/build_skip_symbols.py).
DEFAULT_SKIP_SYMBOLS_FILE: Path = DEFAULT_SYMBOLS_FILE.parent / "skip_symbols.csv"


def _read_skip_symbols(path: Path = DEFAULT_SKIP_SYMBOLS_FILE) -> set[str]:
    """Return the set of symbols to skip, read from the skip CSV.

    The CSV has a ``symbol,reason`` header; only the ``symbol`` column is
    used here. A missing file yields an empty set (nothing to skip).
    """
    if not path.exists():
        return set()
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        return {row["symbol"] for row in reader if row.get("symbol")}


def read_symbols(
    symbols_path: Path = DEFAULT_SYMBOLS_FILE,
    skip_path: Path = DEFAULT_SKIP_SYMBOLS_FILE,
) -> list[str]:
    """Read all symbols, minus those listed in the skip CSV.

    Reads ``all_symbols.txt`` (one symbol per line), drops any symbol that
    appears in ``skip_symbols.csv`` (ETFs, warrants/rights/units, preferreds
    — instruments with no equity fundamentals to fetch), and returns the
    remaining symbols in the file's original order.
    """
    symbols = symbols_path.read_text().split()
    skip = _read_skip_symbols(skip_path)
    return [symbol for symbol in symbols if symbol not in skip]
