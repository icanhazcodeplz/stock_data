"""Offline tests for the skip-list classifier and its staleness check (pure
functions only; the Yahoo quoteType fetch is exercised by the real run)."""

import os
import time

import pytest

from scripts import build_skip_symbols as bss
from scripts.build_skip_symbols import (
    MAX_SKIP_SYMBOLS_AGE_DAYS,
    classify,
    rebuild_skip_symbols_if_stale,
    skip_file_is_stale,
    structural_reason,
)


class TestStructuralReason:
    @pytest.mark.parametrize("symbol", ["AAPL", "F", "GOOG"])
    def test_plain_symbol_is_kept(self, symbol):
        assert structural_reason(symbol) is None

    @pytest.mark.parametrize("symbol", ["BRK.B", "BF.A", "MKC.V"])
    def test_share_class_is_kept(self, symbol):
        assert structural_reason(symbol) is None

    @pytest.mark.parametrize(
        ("symbol", "reason"),
        [
            ("FOO.U", "unit"),
            ("FOO.UN", "unit"),
            ("FOO.W", "warrant"),
            ("FOO.WS", "warrant"),
            ("FOO.WT", "warrant"),
            ("FOO.WSA", "warrant"),
            ("FOO.R", "right"),
            ("FOO.RT", "right"),
        ],
    )
    def test_dotted_derivative_suffixes(self, symbol, reason):
        assert structural_reason(symbol) == reason

    @pytest.mark.parametrize("symbol", ["FOO.PR", "FOO.PRA", "FOO.PRD"])
    def test_preferred_series(self, symbol):
        assert structural_reason(symbol) == "preferred"

    @pytest.mark.parametrize("symbol", ["ADIG.WI", "REZI.WI"])
    def test_when_issued(self, symbol):
        # ".WI" is a conditional pre-issuance listing; Yahoo either doesn't
        # know it or returns a near-empty record, so it must be skipped.
        assert structural_reason(symbol) == "when-issued"

    @pytest.mark.parametrize(
        ("symbol", "reason"),
        [("ABCDU", "unit"), ("ABCDW", "warrant"), ("ABCDR", "right")],
    )
    def test_nasdaq_fifth_letter_convention(self, symbol, reason):
        assert structural_reason(symbol) == reason

    @pytest.mark.parametrize("symbol", ["SNOW", "BLDR", "SU"])
    def test_short_symbols_ending_in_marker_letter_are_kept(self, symbol):
        # The 5th-letter rule only applies to symbols of 5+ characters.
        assert structural_reason(symbol) is None


class TestClassify:
    def test_etf_takes_precedence_over_suffix_rule(self):
        rows = classify(["ABCDU"], {"ABCDU": "ETF"})
        assert rows == [("ABCDU", "ETF")]

    def test_equity_without_marker_is_not_skipped(self):
        assert classify(["AAPL"], {"AAPL": "EQUITY"}) == []

    def test_symbol_unknown_to_yahoo_falls_back_to_ticker_rule(self):
        assert classify(["FOO.U"], {}) == [("FOO.U", "unit")]

    def test_mixed_universe(self):
        rows = classify(
            ["AAPL", "SPY", "FOO.PRA", "ABCDW", "BRK.B"],
            {"AAPL": "EQUITY", "SPY": "ETF", "BRK.B": "EQUITY"},
        )
        assert rows == [("SPY", "ETF"), ("FOO.PRA", "preferred"), ("ABCDW", "warrant")]


def _write_aged(path, age_days: float):
    """Write a skip file and backdate its mtime by ``age_days``."""
    path.write_text("symbol,reason\nSPY,ETF\n")
    mtime = time.time() - age_days * 86400
    os.utime(path, (mtime, mtime))
    return path


class TestSkipFileIsStale:
    def test_missing_file_is_stale(self, tmp_path):
        assert skip_file_is_stale(tmp_path / "skip_symbols.csv") is True

    def test_fresh_file_is_not_stale(self, tmp_path):
        path = _write_aged(tmp_path / "skip_symbols.csv", age_days=0)
        assert skip_file_is_stale(path) is False

    def test_file_just_under_max_age_is_not_stale(self, tmp_path):
        path = _write_aged(tmp_path / "skip_symbols.csv", age_days=MAX_SKIP_SYMBOLS_AGE_DAYS - 0.1)
        assert skip_file_is_stale(path) is False

    def test_file_past_max_age_is_stale(self, tmp_path):
        path = _write_aged(tmp_path / "skip_symbols.csv", age_days=MAX_SKIP_SYMBOLS_AGE_DAYS + 0.1)
        assert skip_file_is_stale(path) is True


class TestRebuildSkipSymbolsIfStale:
    def test_rebuilds_when_missing(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(bss, "build_skip_symbols", lambda **kwargs: calls.append(kwargs))
        path = tmp_path / "skip_symbols.csv"

        rebuild_skip_symbols_if_stale(path)

        assert calls == [{"path": path}]

    def test_skips_rebuild_when_fresh(self, tmp_path, monkeypatch):
        def fail(**kwargs):
            raise AssertionError("should not rebuild a fresh skip file")

        monkeypatch.setattr(bss, "build_skip_symbols", fail)
        path = _write_aged(tmp_path / "skip_symbols.csv", age_days=0)

        rebuild_skip_symbols_if_stale(path)
