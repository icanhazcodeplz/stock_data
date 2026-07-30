from datetime import date, timedelta
from pathlib import Path

from stock_data.io_utils import (
    YAHOO_UNKNOWN_REASON,
    YAHOO_UNKNOWN_RETRY_DAYS,
    SkipRow,
    append_skip_symbols,
    is_expired,
    read_skip_rows,
    read_symbols,
    remove_skip_symbols,
    write_skip_rows,
)

TODAY = date(2026, 7, 30)
FRESH = (TODAY - timedelta(days=YAHOO_UNKNOWN_RETRY_DAYS - 1)).isoformat()
EXPIRED = (TODAY - timedelta(days=YAHOO_UNKNOWN_RETRY_DAYS)).isoformat()


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


class TestReadSkipRows:
    def test_missing_file_yields_no_rows(self, tmp_path):
        assert read_skip_rows(tmp_path / "skip_symbols.csv") == []

    def test_reads_symbol_reason_and_date(self, tmp_path):
        path = tmp_path / "skip_symbols.csv"
        path.write_text(f"symbol,reason,date\nSPY,ETF,\nZZZQ,{YAHOO_UNKNOWN_REASON},{FRESH}\n")

        assert read_skip_rows(path) == [
            SkipRow("SPY", "ETF", ""),
            SkipRow("ZZZQ", YAHOO_UNKNOWN_REASON, FRESH),
        ]

    def test_two_column_file_reads_with_empty_dates(self, tmp_path):
        """Skip lists written before the date column must still load."""
        path = tmp_path / "skip_symbols.csv"
        path.write_text("symbol,reason\nSPY,ETF\nFOO.U,unit\n")

        assert read_skip_rows(path) == [SkipRow("SPY", "ETF", ""), SkipRow("FOO.U", "unit", "")]


class TestWriteSkipRows:
    def test_writes_header_sorted_by_symbol(self, tmp_path):
        path = tmp_path / "skip_symbols.csv"

        write_skip_rows([SkipRow("ZZZ", "ETF"), SkipRow("AAA", "unit")], path)

        assert path.read_text() == "symbol,reason,date\nAAA,unit,\nZZZ,ETF,\n"

    def test_accepts_plain_two_tuples(self, tmp_path):
        """classify() yields (symbol, reason) pairs; they must write cleanly."""
        path = tmp_path / "skip_symbols.csv"

        write_skip_rows([("AAA", "unit")], path)

        assert read_skip_rows(path) == [SkipRow("AAA", "unit", "")]

    def test_round_trips_through_read(self, tmp_path):
        path = tmp_path / "skip_symbols.csv"
        rows = [SkipRow("AAA", "unit", ""), SkipRow("ZZZ", YAHOO_UNKNOWN_REASON, FRESH)]

        write_skip_rows(rows, path)

        assert read_skip_rows(path) == rows


class TestIsExpired:
    def test_structural_rows_never_expire(self):
        assert is_expired(SkipRow("SPY", "ETF", ""), TODAY) is False
        assert is_expired(SkipRow("FOO.U", "unit", EXPIRED), TODAY) is False

    def test_fresh_verdict_is_not_expired(self):
        assert is_expired(SkipRow("ZZZQ", YAHOO_UNKNOWN_REASON, FRESH), TODAY) is False

    def test_verdict_at_the_retry_boundary_is_expired(self):
        assert is_expired(SkipRow("ZZZQ", YAHOO_UNKNOWN_REASON, EXPIRED), TODAY) is True

    def test_undated_verdict_is_expired(self):
        """Rows written before dates were recorded get one retry, which dates them."""
        assert is_expired(SkipRow("ZZZQ", YAHOO_UNKNOWN_REASON, ""), TODAY) is True

    def test_unparseable_date_is_expired(self):
        assert is_expired(SkipRow("ZZZQ", YAHOO_UNKNOWN_REASON, "not-a-date"), TODAY) is True


class TestReadSymbolsExpiry:
    def test_fresh_verdict_keeps_symbol_out(self, tmp_path):
        symbols_path, skip_path = _write_universe(
            tmp_path,
            "AAA\nZZZQ\n",
            f"symbol,reason,date\nZZZQ,{YAHOO_UNKNOWN_REASON},{FRESH}\n",
        )

        assert read_symbols(symbols_path, skip_path, TODAY) == ["AAA"]

    def test_expired_verdict_lets_symbol_back_in(self, tmp_path):
        symbols_path, skip_path = _write_universe(
            tmp_path,
            "AAA\nZZZQ\n",
            f"symbol,reason,date\nZZZQ,{YAHOO_UNKNOWN_REASON},{EXPIRED}\n",
        )

        assert read_symbols(symbols_path, skip_path, TODAY) == ["AAA", "ZZZQ"]

    def test_expiry_does_not_apply_to_structural_rows(self, tmp_path):
        symbols_path, skip_path = _write_universe(
            tmp_path,
            "AAA\nSPY\n",
            f"symbol,reason,date\nSPY,ETF,{EXPIRED}\n",
        )

        assert read_symbols(symbols_path, skip_path, TODAY) == ["AAA"]


class TestAppendSkipSymbols:
    def test_creates_file_when_missing(self, tmp_path):
        path = tmp_path / "skip_symbols.csv"

        added = append_skip_symbols(["ZZZQ"], YAHOO_UNKNOWN_REASON, path, TODAY)

        assert added == ["ZZZQ"]
        assert read_skip_rows(path) == [SkipRow("ZZZQ", YAHOO_UNKNOWN_REASON, TODAY.isoformat())]

    def test_preserves_existing_rows(self, tmp_path):
        path = tmp_path / "skip_symbols.csv"
        path.write_text("symbol,reason,date\nSPY,ETF,\n")

        append_skip_symbols(["ZZZQ"], YAHOO_UNKNOWN_REASON, path, TODAY)

        assert read_skip_rows(path) == [
            SkipRow("SPY", "ETF", ""),
            SkipRow("ZZZQ", YAHOO_UNKNOWN_REASON, TODAY.isoformat()),
        ]

    def test_symbol_under_another_reason_is_left_alone(self, tmp_path):
        path = tmp_path / "skip_symbols.csv"
        path.write_text("symbol,reason,date\nSPY,ETF,\n")

        added = append_skip_symbols(["SPY"], YAHOO_UNKNOWN_REASON, path, TODAY)

        # The existing ETF classification wins; no second SPY row, no date.
        assert added == []
        assert read_skip_rows(path) == [SkipRow("SPY", "ETF", "")]

    def test_reconfirming_resets_the_retry_clock(self, tmp_path):
        """An expired verdict confirmed again must not expire immediately."""
        path = tmp_path / "skip_symbols.csv"
        path.write_text(f"symbol,reason,date\nZZZQ,{YAHOO_UNKNOWN_REASON},{EXPIRED}\n")

        added = append_skip_symbols(["ZZZQ"], YAHOO_UNKNOWN_REASON, path, TODAY)

        assert added == []  # not new, but re-dated
        rows = read_skip_rows(path)
        assert rows == [SkipRow("ZZZQ", YAHOO_UNKNOWN_REASON, TODAY.isoformat())]
        assert is_expired(rows[0], TODAY) is False

    def test_duplicates_within_one_call_collapse(self, tmp_path):
        path = tmp_path / "skip_symbols.csv"

        added = append_skip_symbols(["ZZZQ", "ZZZQ"], YAHOO_UNKNOWN_REASON, path, TODAY)

        assert added == ["ZZZQ"]
        assert len(read_skip_rows(path)) == 1

    def test_appended_symbols_are_filtered_by_read_symbols(self, tmp_path):
        """The whole point: a skip-listed symbol leaves the working universe."""
        symbols_path, skip_path = _write_universe(tmp_path, "AAA\nZZZQ\n")

        append_skip_symbols(["ZZZQ"], YAHOO_UNKNOWN_REASON, skip_path, TODAY)

        assert read_symbols(symbols_path, skip_path, TODAY) == ["AAA"]


class TestRemoveSkipSymbols:
    def test_removes_matching_reason(self, tmp_path):
        path = tmp_path / "skip_symbols.csv"
        path.write_text(f"symbol,reason,date\nZZZQ,{YAHOO_UNKNOWN_REASON},{EXPIRED}\n")

        removed = remove_skip_symbols(["ZZZQ"], YAHOO_UNKNOWN_REASON, path)

        assert removed == ["ZZZQ"]
        assert read_skip_rows(path) == []

    def test_leaves_other_reasons_alone(self, tmp_path):
        path = tmp_path / "skip_symbols.csv"
        path.write_text("symbol,reason,date\nSPY,ETF,\n")

        removed = remove_skip_symbols(["SPY"], YAHOO_UNKNOWN_REASON, path)

        assert removed == []
        assert read_skip_rows(path) == [SkipRow("SPY", "ETF", "")]

    def test_unlisted_symbol_is_a_no_op(self, tmp_path):
        path = tmp_path / "skip_symbols.csv"
        path.write_text("symbol,reason,date\nSPY,ETF,\n")

        assert remove_skip_symbols(["AAA"], YAHOO_UNKNOWN_REASON, path) == []

    def test_missing_file_is_a_no_op(self, tmp_path):
        assert remove_skip_symbols(["AAA"], YAHOO_UNKNOWN_REASON, tmp_path / "skip.csv") == []
