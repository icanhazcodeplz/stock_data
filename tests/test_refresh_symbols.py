"""Offline tests for the once-per-day symbols-file refresh."""

import os
import time

import stock_data.get_all_stock_names as gasn
from stock_data.get_all_stock_names import refresh_symbols_if_stale, symbols_file_updated_today


def _age_file(path, days: int) -> None:
    old = time.time() - days * 86400
    os.utime(path, (old, old))


class TestSymbolsFileUpdatedToday:
    def test_missing_file(self, tmp_path):
        assert not symbols_file_updated_today(tmp_path / "all_symbols.txt")

    def test_file_written_today(self, tmp_path):
        path = tmp_path / "all_symbols.txt"
        path.write_text("AAA\n")
        assert symbols_file_updated_today(path)

    def test_file_written_yesterday(self, tmp_path):
        path = tmp_path / "all_symbols.txt"
        path.write_text("AAA\n")
        _age_file(path, days=1)
        assert not symbols_file_updated_today(path)


class TestRefreshSymbolsIfStale:
    def test_fetches_and_writes_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gasn, "get_all_stock_names", lambda: ["BBB", "AAA", "AAA"])
        path = tmp_path / "all_symbols.txt"

        symbols = refresh_symbols_if_stale(path)

        assert symbols == ["AAA", "BBB"]
        assert path.read_text() == "AAA\nBBB\n"

    def test_fetches_when_file_is_stale(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gasn, "get_all_stock_names", lambda: ["CCC"])
        path = tmp_path / "all_symbols.txt"
        path.write_text("AAA\n")
        _age_file(path, days=1)

        symbols = refresh_symbols_if_stale(path)

        assert symbols == ["CCC"]
        assert path.read_text() == "CCC\n"

    def test_skips_fetch_when_file_is_fresh(self, tmp_path, monkeypatch):
        def _explode():
            raise AssertionError("must not hit the API when the file is fresh")

        monkeypatch.setattr(gasn, "get_all_stock_names", _explode)
        path = tmp_path / "all_symbols.txt"
        path.write_text("AAA\nBBB\n")

        assert refresh_symbols_if_stale(path) == ["AAA", "BBB"]
