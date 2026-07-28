import time
from collections import Counter
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from alpaca.trading.enums import AssetExchange

from settings import REPO_ROOT
from stock_data.clients.alpaca import get_active_us_equities

DEFAULT_EXCHANGES: tuple[AssetExchange, ...] = (
    AssetExchange.NASDAQ,
    AssetExchange.AMEX,
    AssetExchange.NYSE,
)

DEFAULT_SYMBOLS_FILE: Path = REPO_ROOT / "data" / "all_symbols.txt"


def get_all_stock_names(
    exchanges: Iterable[AssetExchange] = DEFAULT_EXCHANGES,
    *,
    limit_per_exchange: int | None = None,
    paper: bool = True,
) -> list[str]:
    symbols: list[str] = []
    for exchange in exchanges:
        assets = get_active_us_equities(exchange, paper=paper)
        if limit_per_exchange is not None:
            assets = assets[:limit_per_exchange]
        symbols.extend(asset.symbol for asset in assets)
    return symbols


def write_symbols_file(
    symbols: list[str],
    path: Path = DEFAULT_SYMBOLS_FILE,
) -> None:
    """Write ``symbols`` to ``path``, one per line, sorted, with a trailing newline.

    Ensures the parent directory exists before writing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_symbols = sorted(symbols)
    path.write_text("\n".join(sorted_symbols) + "\n")


def symbols_file_updated_today(path: Path = DEFAULT_SYMBOLS_FILE) -> bool:
    """Return True if ``path`` exists and was last modified today."""
    if not path.exists():
        return False
    return date.fromtimestamp(path.stat().st_mtime) == date.today()


def fetch_and_write_all_symbols() -> list[str]:
    """Fetch all symbols with the defaults, write them to the symbols file,
    and print a summary of what was fetched."""
    start = time.perf_counter()
    symbols = get_all_stock_names()
    elapsed = time.perf_counter() - start

    write_symbols_file(symbols)

    dotted = [s for s in symbols if "." in s]
    counts = Counter(symbols)
    duplicates = {sym: c for sym, c in counts.items() if c > 1}

    print(f"Total fetch time: {elapsed:.2f}s")
    print(f"Symbols fetched: {len(symbols)}")
    print(f"Dotted symbols: {len(dotted)}")
    print(f"Symbols appearing in multiple exchanges: {len(duplicates)}")
    if duplicates:
        for sym, count in list(duplicates.items())[:10]:
            print(f"  {sym} ({count}x)")
    print(f"Wrote {len(symbols)} symbols to {DEFAULT_SYMBOLS_FILE}")

    return symbols


def refresh_symbols_if_stale() -> list[str]:
    """Refetch and rewrite the symbols file unless it was already updated today.

    Returns the symbols either way: fresh from the API, or read back from the
    existing file when the fetch is skipped.
    """
    if symbols_file_updated_today():
        print(f"{DEFAULT_SYMBOLS_FILE} was already updated today; skipping refetch.")
        return DEFAULT_SYMBOLS_FILE.read_text().splitlines()
    print(f"{DEFAULT_SYMBOLS_FILE} was not updated today; refetching symbols.")
    return fetch_and_write_all_symbols()


if __name__ == "__main__":
    refresh_symbols_if_stale()
