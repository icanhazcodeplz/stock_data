"""Offline tests for the daily fetch script.

Everything network-facing is monkeypatched on ``scripts.get_stock_data``:
``refresh_symbols_if_stale`` (Alpaca), ``get_financials`` (Yahoo),
``read_symbols`` (filesystem), and ``connect`` (pointed at a tmp_path DB).
"""

from datetime import datetime, timedelta, timezone

import pytest

import scripts.get_stock_data as gsd
from stock_data.clients.yahoo import Financials
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


class FakeEnvironment:
    """Patched-out world for one test: tmp DB, canned universe, recorded calls."""

    def __init__(self, monkeypatch, db_path):
        self.monkeypatch = monkeypatch
        self.db_path = db_path
        self.calls: list[str] = []

        monkeypatch.setattr(gsd, "refresh_symbols_if_stale", lambda: None)
        monkeypatch.setattr(gsd, "connect", lambda: connect(db_path))
        monkeypatch.setattr(gsd, "get_financials", self._fake_get_financials)

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
        assert "not stored" in out
        assert "Failed (1): ZZZQ" in out

    def test_dotted_symbol_translated(self, env):
        env.set_universe(["BRK.B"])

        gsd.get_stock_data()

        # Yahoo is called with the dash form...
        assert env.calls == ["BRK-B"]
        # ...but the row is stored under the original Alpaca symbol.
        assert [row[0] for row in env.db_rows()] == ["BRK.B"]

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


class TestAlpacaToYahooSymbol:
    """The share-class ticker translation helper."""

    def test_plain_symbol_passes_through(self):
        assert gsd.alpaca_to_yahoo_symbol("AAPL") == "AAPL"

    def test_share_class_dot_becomes_dash(self):
        assert gsd.alpaca_to_yahoo_symbol("BRK.B") == "BRK-B"
