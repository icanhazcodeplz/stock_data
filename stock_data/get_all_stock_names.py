import time
from collections import Counter
from collections.abc import Iterable
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


if __name__ == "__main__":
    by_exchange: dict[AssetExchange, list[str]] = {}
    timings: dict[AssetExchange, float] = {}

    overall_start = time.perf_counter()
    for exchange in DEFAULT_EXCHANGES:
        start = time.perf_counter()
        assets = get_active_us_equities(exchange)
        timings[exchange] = time.perf_counter() - start
        by_exchange[exchange] = [a.symbol for a in assets]
    overall_elapsed = time.perf_counter() - overall_start

    print(f"Total fetch time: {overall_elapsed:.2f}s\n")
    print(f"{'Exchange':<10} {'Symbols':>8} {'Dotted':>8} {'Time (s)':>10}")
    print("-" * 40)
    for exchange in DEFAULT_EXCHANGES:
        symbols = by_exchange[exchange]
        dotted = [s for s in symbols if "." in s]
        print(
            f"{exchange.value:<10} {len(symbols):>8} {len(dotted):>8} "
            f"{timings[exchange]:>10.2f}"
        )

    counts = Counter(s for symbols in by_exchange.values() for s in symbols)
    duplicates = {sym: c for sym, c in counts.items() if c > 1}
    print(f"\nSymbols appearing in multiple exchanges: {len(duplicates)}")
    if duplicates:
        for sym, count in list(duplicates.items())[:10]:
            exchanges_with = [
                ex.value for ex, symbols in by_exchange.items() if sym in symbols
            ]
            print(f"  {sym} ({count}x): {', '.join(exchanges_with)}")
