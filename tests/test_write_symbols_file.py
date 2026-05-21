from pathlib import Path

from stock_data.get_all_stock_names import write_symbols_file


def test_writes_sorted_with_trailing_newline(tmp_path: Path):
    target = tmp_path / "symbols.txt"
    symbols = ["MSFT", "AAPL", "GOOG", "AMZN"]

    write_symbols_file(symbols, path=target)

    content = target.read_text()
    assert content.endswith("\n")
    lines = content.splitlines()
    assert lines == ["AAPL", "AMZN", "GOOG", "MSFT"]


def test_creates_parent_directory_if_missing(tmp_path: Path):
    target = tmp_path / "nested" / "deeper" / "symbols.txt"
    assert not target.parent.exists()

    write_symbols_file(["AAA", "BBB"], path=target)

    assert target.parent.is_dir()
    assert target.read_text() == "AAA\nBBB\n"


def test_does_not_mutate_input_list(tmp_path: Path):
    target = tmp_path / "symbols.txt"
    symbols = ["ZZZ", "AAA", "MMM"]
    original = list(symbols)

    write_symbols_file(symbols, path=target)

    assert symbols == original
