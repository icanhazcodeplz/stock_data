"""Offline tests for the skip-list classifier (pure functions only; the
Yahoo quoteType fetch is exercised separately by the weekly run itself)."""

import pytest

from scripts.build_skip_symbols import classify, structural_reason


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
