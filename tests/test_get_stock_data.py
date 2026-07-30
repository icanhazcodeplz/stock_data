"""Offline tests for the daily fetch script.

Everything network- and filesystem-facing is monkeypatched on
``scripts.get_stock_data``: ``refresh_symbols_if_stale`` (Alpaca),
``rebuild_skip_symbols_if_stale`` (Yahoo), ``get_financials`` (Yahoo),
``read_symbols``, ``connect`` (pointed at a tmp_path DB), and
``append_skip_symbols`` (pointed at a tmp_path skip CSV, so a test can
never touch the committed ``data/skip_symbols.csv``).
"""

from datetime import date, datetime, timedelta, timezone

import pytest

import scripts.get_stock_data as gsd
from stock_data.clients.yahoo import Financials
from stock_data.io_utils import (
    YAHOO_UNKNOWN_REASON,
    YAHOO_UNKNOWN_RETRY_DAYS,
    SkipRow,
    append_skip_symbols,
    read_skip_rows,
    remove_skip_symbols,
)
from stock_data.storage import connect, insert_fundamentals

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
OLD = NOW - timedelta(days=30)  # comfortably past MIN_REFRESH_AGE_DAYS


def _make_financials(symbol: str) -> Financials:
    return Financials(
        symbol=symbol,
        float_shares=1_000_000,
        short_ratio=1.5,
        short_interest=10_000,
        sector="Technology",
        industry="Software",
        country="United States",
        exchange="NMS",
        short_float=0.05,
    )


def _all_null_financials(symbol: str) -> Financials:
    return Financials(
        symbol=symbol,
        float_shares=None,
        short_ratio=None,
        short_interest=None,
        sector=None,
        industry=None,
        country=None,
        exchange=None,
        short_float=None,
    )


def _exchange_only_financials(symbol: str) -> Financials:
    """What Yahoo returns for a baby bond or a fund: a quote-header exchange
    and nothing else."""
    financials = _all_null_financials(symbol)
    financials.exchange = "NYQ"
    return financials


class FakeEnvironment:
    """Patched-out world for one test: tmp DB, canned universe, recorded calls."""

    def __init__(self, monkeypatch, db_path):
        self.monkeypatch = monkeypatch
        self.db_path = db_path
        self.skip_path = db_path.parent / "skip_symbols.csv"
        self.calls: list[str] = []

        monkeypatch.setattr(gsd, "refresh_symbols_if_stale", lambda: None)
        monkeypatch.setattr(gsd, "rebuild_skip_symbols_if_stale", lambda: None)
        monkeypatch.setattr(gsd, "connect", lambda: connect(db_path))
        monkeypatch.setattr(gsd, "get_financials", self._fake_get_financials)
        monkeypatch.setattr(
            gsd,
            "append_skip_symbols",
            lambda symbols, reason: append_skip_symbols(symbols, reason, self.skip_path),
        )
        monkeypatch.setattr(
            gsd,
            "remove_skip_symbols",
            lambda symbols, reason: remove_skip_symbols(symbols, reason, self.skip_path),
        )

    def _fake_get_financials(self, symbol: str) -> Financials:
        self.calls.append(symbol)
        return _make_financials(symbol)

    def set_universe(self, symbols: list[str]) -> None:
        self.monkeypatch.setattr(gsd, "read_symbols", lambda: symbols)

    def seed_db(self, symbol: str, when: datetime) -> None:
        conn = connect(self.db_path)
        try:
            insert_fundamentals(conn, [_make_financials(symbol)], retrieval_datetime=when)
        finally:
            conn.close()

    def skip_rows(self) -> list[tuple[str, str]]:
        return read_skip_rows(self.skip_path)

    def db_rows(self) -> list[tuple[str, str]]:
        conn = connect(self.db_path)
        try:
            return conn.execute(
                "SELECT symbol, retrieval_datetime FROM fundamentals ORDER BY retrieval_datetime"
            ).fetchall()
        finally:
            conn.close()


@pytest.fixture
def env(monkeypatch, tmp_path) -> FakeEnvironment:
    return FakeEnvironment(monkeypatch, tmp_path / "fundamentals.db")


class TestFetchPrioritization:
    """Which symbols a run selects, and in what order."""

    def test_budget_caps_calls(self, env):
        universe = [f"SYM{i:03d}" for i in range(200)]
        env.set_universe(universe)

        gsd.get_stock_data(max_calls=50)

        assert len(env.calls) == 50
        assert len(env.db_rows()) == 50
        # Missing symbols are fetched in sorted order.
        assert env.calls == sorted(universe)[:50]

    def test_max_calls_defaults_to_daily_budget(self):
        import inspect

        default = inspect.signature(gsd.get_stock_data).parameters["max_calls"].default
        assert default == gsd.MAX_YAHOO_CALLS_PER_RUN

    def test_missing_before_stale(self, env):
        env.set_universe(["AAA", "BBB", "CCC"])
        env.seed_db("BBB", OLD + timedelta(days=2))  # newer of the two stale rows
        env.seed_db("CCC", OLD)  # oldest

        gsd.get_stock_data()

        assert env.calls == ["AAA", "CCC", "BBB"]

    def test_stale_oldest_first(self, env):
        env.set_universe(["AAA", "BBB", "CCC"])
        env.seed_db("AAA", OLD + timedelta(days=2))
        env.seed_db("BBB", OLD)
        env.seed_db("CCC", OLD + timedelta(days=1))

        gsd.get_stock_data()

        assert env.calls == ["BBB", "CCC", "AAA"]

    def test_fresh_symbols_not_refetched(self, env):
        env.set_universe(["AAA", "BBB"])
        env.seed_db("AAA", OLD)
        env.seed_db("BBB", datetime.now(timezone.utc) - timedelta(days=1))  # fresh

        gsd.get_stock_data()

        assert env.calls == ["AAA"]

    def test_delisted_symbols_ignored_history_preserved(self, env):
        env.set_universe(["AAA"])
        env.seed_db("GONE", OLD)  # in the DB but no longer in the universe

        gsd.get_stock_data()

        assert env.calls == ["AAA"]
        assert {row[0] for row in env.db_rows()} == {"GONE", "AAA"}


class TestRecordHandling:
    """What happens to each fetched record on its way into the DB."""

    def test_all_null_record_not_inserted(self, env, capsys):
        env.set_universe(["ZZZQ"])
        env.monkeypatch.setattr(gsd, "get_financials", _all_null_financials)

        gsd.get_stock_data()

        assert env.db_rows() == []
        out = capsys.readouterr().out
        assert "unknown to Yahoo" in out
        assert "Unknown to Yahoo (1): ZZZQ" in out

    def test_exchange_only_record_not_inserted(self, env, capsys):
        env.set_universe(["AFGB"])
        env.monkeypatch.setattr(gsd, "get_financials", _exchange_only_financials)

        gsd.get_stock_data()

        assert env.db_rows() == []
        assert "Unknown to Yahoo (1): AFGB" in capsys.readouterr().out

    def test_partial_record_is_inserted(self, env):
        """A record with any company field populated is real data, even if
        most fields are null."""

        def _float_only(symbol: str) -> Financials:
            financials = _all_null_financials(symbol)
            financials.exchange = "NMS"
            financials.float_shares = 83_824_239
            return financials

        env.set_universe(["ADAMG"])
        env.monkeypatch.setattr(gsd, "get_financials", _float_only)

        gsd.get_stock_data()

        assert [row[0] for row in env.db_rows()] == ["ADAMG"]

    def test_dotted_symbol_translated(self, env):
        env.set_universe(["BRK.B"])

        gsd.get_stock_data()

        # Yahoo is called with the dash form...
        assert env.calls == ["BRK-B"]
        # ...but the row is stored under the original Alpaca symbol.
        assert [row[0] for row in env.db_rows()] == ["BRK.B"]

    def test_refetch_replaces_previous_row(self, env):
        env.set_universe(["AAA"])
        env.seed_db("AAA", OLD)

        gsd.get_stock_data()

        # The stale row is removed; only the fresh row remains.
        rows = env.db_rows()
        assert [row[0] for row in rows] == ["AAA"]
        assert rows[0][1] != OLD.isoformat()

    def test_fetch_failure_does_not_stop_run(self, env, capsys):
        env.set_universe(["AAA", "BBB"])

        def flaky(symbol: str) -> Financials:
            env.calls.append(symbol)
            if symbol == "AAA":
                raise RuntimeError("boom")
            return _make_financials(symbol)

        env.monkeypatch.setattr(gsd, "get_financials", flaky)

        gsd.get_stock_data()

        assert env.calls == ["AAA", "BBB"]
        assert [row[0] for row in env.db_rows()] == ["BBB"]
        assert "Failed (1): AAA" in capsys.readouterr().out


class TestYahooUnknownSkipListing:
    """Symbols Yahoo has no record of are skip-listed so they stop consuming
    the budget. Without a DB row they stay in ``missing`` — at the front of
    the queue — and would be refetched on every future run."""

    def test_unknown_symbol_is_skip_listed_with_todays_date(self, env):
        env.set_universe(["ZZZQ"])
        env.monkeypatch.setattr(gsd, "get_financials", _all_null_financials)

        gsd.get_stock_data()

        assert env.skip_rows() == [SkipRow("ZZZQ", YAHOO_UNKNOWN_REASON, date.today().isoformat())]

    def test_second_run_does_not_refetch_a_skip_listed_symbol(self, env):
        """The regression this exists to prevent: before skip-listing, ZZZQ
        had no row, stayed in ``missing``, and was refetched every run."""

        def fetch(symbol: str) -> Financials:
            env.calls.append(symbol)
            return _all_null_financials(symbol) if symbol == "ZZZQ" else _make_financials(symbol)

        env.monkeypatch.setattr(gsd, "get_financials", fetch)
        env.set_universe(["AAA", "ZZZQ"])

        gsd.get_stock_data()

        assert env.calls == ["AAA", "ZZZQ"]
        assert {row.symbol for row in env.skip_rows()} == {"ZZZQ"}

        # read_symbols applies the skip list in production; emulate that here.
        env.set_universe(["AAA"])
        env.calls.clear()

        gsd.get_stock_data()

        # ZZZQ is skip-listed, and AAA's row is now fresh.
        assert env.calls == []

    def test_fetch_exception_is_not_skip_listed(self, env):
        """A raised fetch is transient — skip-listing it would let one Yahoo
        outage permanently blacklist the universe."""
        env.set_universe(["AAA"])

        def boom(symbol: str) -> Financials:
            raise RuntimeError("connection reset")

        env.monkeypatch.setattr(gsd, "get_financials", boom)

        gsd.get_stock_data()

        assert env.skip_rows() == []

    def test_successful_fetch_is_not_skip_listed(self, env):
        env.set_universe(["AAA"])

        gsd.get_stock_data()

        assert env.skip_rows() == []

    def test_unknown_symbols_are_appended_to_existing_skip_rows(self, env):
        env.skip_path.write_text("symbol,reason,date\nSPY,ETF,\n")
        env.set_universe(["ZZZQ"])
        env.monkeypatch.setattr(gsd, "get_financials", _all_null_financials)

        gsd.get_stock_data()

        assert env.skip_rows() == [
            SkipRow("SPY", "ETF", ""),
            SkipRow("ZZZQ", YAHOO_UNKNOWN_REASON, date.today().isoformat()),
        ]


class TestYahooUnknownRetry:
    """A yahoo_unknown verdict expires so a symbol Yahoo simply had not
    indexed yet — a recent IPO, a thin small cap — is not excluded forever."""

    def _seed_expired(self, env, symbol: str) -> None:
        stale = (date.today() - timedelta(days=YAHOO_UNKNOWN_RETRY_DAYS)).isoformat()
        env.skip_path.write_text(f"symbol,reason,date\n{symbol},{YAHOO_UNKNOWN_REASON},{stale}\n")

    def test_expired_verdict_is_retried_and_recovers(self, env):
        """Yahoo has data this time: the skip entry is dropped and the row stored."""
        self._seed_expired(env, "ALPS")
        env.set_universe(["ALPS"])  # read_symbols lets it back in once expired

        gsd.get_stock_data()

        assert env.calls == ["ALPS"]
        assert [row[0] for row in env.db_rows()] == ["ALPS"]
        assert env.skip_rows() == []

    def test_expired_verdict_still_unknown_resets_the_clock(self, env):
        self._seed_expired(env, "ZZZQ")
        env.set_universe(["ZZZQ"])
        env.monkeypatch.setattr(gsd, "get_financials", _all_null_financials)

        gsd.get_stock_data()

        # Re-dated to today, so it is excluded again for another full window.
        assert env.skip_rows() == [SkipRow("ZZZQ", YAHOO_UNKNOWN_REASON, date.today().isoformat())]
        assert env.db_rows() == []

    def test_recovery_only_clears_yahoo_unknown_rows(self, env):
        """A successful fetch must not delete a structural classification."""
        env.skip_path.write_text("symbol,reason,date\nAAA,ETF,\n")
        env.set_universe(["AAA"])

        gsd.get_stock_data()

        assert env.skip_rows() == [SkipRow("AAA", "ETF", "")]


class TestAlpacaToYahooSymbol:
    """The share-class ticker translation helper."""

    def test_plain_symbol_passes_through(self):
        assert gsd.alpaca_to_yahoo_symbol("AAPL") == "AAPL"

    def test_share_class_dot_becomes_dash(self):
        assert gsd.alpaca_to_yahoo_symbol("BRK.B") == "BRK-B"
