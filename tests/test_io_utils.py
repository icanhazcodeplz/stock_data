from pathlib import Path

from stock_data.io_utils import read_symbols


def _write_universe(tmp_path: Path, symbols: str, skip_csv: str | None = None) -> tuple[Path, Path]:
    symbols_path = tmp_path / "all_symbols.txt"
    symbols_path.write_text(symbols)
    skip_path = tmp_path / "skip_symbols.csv"
    if skip_csv is not None:
        skip_path.write_text(skip_csv)
    return symbols_path, skip_path


def test_filters_symbols_listed_in_skip_csv(tmp_path):
    symbols_path, skip_path = _write_universe(
        tmp_path,
        "AAA\nBBB\nCCC\n",
        "symbol,reason\nBBB,ETF\n",
    )

    assert read_symbols(symbols_path, skip_path) == ["AAA", "CCC"]


def test_missing_skip_file_returns_all_symbols(tmp_path):
    symbols_path, skip_path = _write_universe(tmp_path, "AAA\nBBB\n")

    assert read_symbols(symbols_path, skip_path) == ["AAA", "BBB"]


def test_preserves_symbols_file_order(tmp_path):
    symbols_path, skip_path = _write_universe(tmp_path, "ZZZ\nAAA\nMMM\n")

    assert read_symbols(symbols_path, skip_path) == ["ZZZ", "AAA", "MMM"]


def test_blank_lines_are_ignored(tmp_path):
    symbols_path, skip_path = _write_universe(tmp_path, "AAA\n\nBBB\n\n")

    assert read_symbols(symbols_path, skip_path) == ["AAA", "BBB"]
