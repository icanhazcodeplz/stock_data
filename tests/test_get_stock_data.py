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


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Patch out network and filesystem; record get_financials call order."""
    db_path = tmp_path / "fundamentals.db"
    calls: list[str] = []

    monkeypatch.setattr(gsd, "refresh_symbols_if_stale", lambda: None)
    monkeypatch.setattr(gsd, "connect", lambda: connect(db_path))

    def fake_get_financials(symbol: str) -> Financials:
        calls.append(symbol)
        return _make_financials(symbol)

    monkeypatch.setattr(gsd, "get_financials", fake_get_financials)

    class Env:
        pass

    e = Env()
    e.db_path = db_path
    e.calls = calls
    e.monkeypatch = monkeypatch
    return e


def _set_universe(env, symbols: list[str]) -> None:
    env.monkeypatch.setattr(gsd, "read_symbols", lambda: symbols)


def _seed(env, symbol: str, when: datetime) -> None:
    conn = connect(env.db_path)
    try:
        insert_fundamentals(conn, [_make_financials(symbol)], retrieval_datetime=when)
    finally:
        conn.close()


def _db_rows(env) -> list[tuple[str, str]]:
    conn = connect(env.db_path)
    try:
        return conn.execute(
            "SELECT symbol, retrieval_datetime FROM fundamentals ORDER BY retrieval_datetime"
        ).fetchall()
    finally:
        conn.close()


def test_budget_caps_calls(env):
    universe = [f"SYM{i:03d}" for i in range(200)]
    _set_universe(env, universe)
    env.monkeypatch.setattr(gsd, "MAX_YAHOO_CALLS_PER_RUN", 50)

    gsd.get_stock_data()

    assert len(env.calls) == 50
    assert len(_db_rows(env)) == 50
    # Missing symbols are fetched in sorted order.
    assert env.calls == sorted(universe)[:50]


def test_missing_before_stale(env):
    _set_universe(env, ["AAA", "BBB", "CCC"])
    _seed(env, "BBB", OLD + timedelta(days=2))  # newer of the two stale rows
    _seed(env, "CCC", OLD)  # oldest

    gsd.get_stock_data()

    assert env.calls == ["AAA", "CCC", "BBB"]


def test_stale_oldest_first(env):
    _set_universe(env, ["AAA", "BBB", "CCC"])
    _seed(env, "AAA", OLD + timedelta(days=2))
    _seed(env, "BBB", OLD)
    _seed(env, "CCC", OLD + timedelta(days=1))

    gsd.get_stock_data()

    assert env.calls == ["BBB", "CCC", "AAA"]


def test_fresh_symbols_not_refetched(env):
    _set_universe(env, ["AAA", "BBB"])
    _seed(env, "AAA", OLD)
    _seed(env, "BBB", datetime.now(timezone.utc) - timedelta(days=1))  # fresh

    gsd.get_stock_data()

    assert env.calls == ["AAA"]


def test_delisted_symbols_ignored_history_preserved(env):
    _set_universe(env, ["AAA"])
    _seed(env, "GONE", OLD)  # in the DB but no longer in the universe

    gsd.get_stock_data()

    assert env.calls == ["AAA"]
    assert {row[0] for row in _db_rows(env)} == {"GONE", "AAA"}


def test_all_null_record_not_inserted(env, capsys):
    _set_universe(env, ["ZZZQ"])
    env.monkeypatch.setattr(
        gsd,
        "get_financials",
        lambda symbol: _all_null_financials(symbol),
    )

    gsd.get_stock_data()

    assert _db_rows(env) == []
    out = capsys.readouterr().out
    assert "not stored" in out
    assert "Failed (1): ZZZQ" in out


def test_dotted_symbol_translated(env):
    _set_universe(env, ["BRK.B"])

    gsd.get_stock_data()

    # Yahoo is called with the dash form...
    assert env.calls == ["BRK-B"]
    # ...but the row is stored under the original Alpaca symbol.
    assert [row[0] for row in _db_rows(env)] == ["BRK.B"]


def test_fetch_failure_does_not_stop_run(env, capsys):
    _set_universe(env, ["AAA", "BBB"])

    def flaky(symbol: str) -> Financials:
        env.calls.append(symbol)
        if symbol == "AAA":
            raise RuntimeError("boom")
        return _make_financials(symbol)

    env.monkeypatch.setattr(gsd, "get_financials", flaky)

    gsd.get_stock_data()

    assert env.calls == ["AAA", "BBB"]
    assert [row[0] for row in _db_rows(env)] == ["BBB"]
    assert "Failed (1): AAA" in capsys.readouterr().out


def test_yahoo_symbol_translation():
    """yahoo_symbol only rewrites dots; plain symbols pass through."""
    assert gsd.yahoo_symbol("AAPL") == "AAPL"
    assert gsd.yahoo_symbol("BRK.B") == "BRK-B"
