# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Daily utility that runs each morning to collect stock information, indicators, and recent price/volume history for most US equities (NASDAQ, AMEX, NYSE) via the Alpaca market data API. The user has an Alpaca market data account with unlimited usage.

## Environment

- Python 3.14, managed by `uv`. Dependencies declared in `pyproject.toml`; lockfile is `uv.lock`; venv lives at `.venv/`.
- `uv sync` — install/update dependencies into the venv.
- `uv run <cmd>` — run a command inside the venv (e.g. `uv run python -m stock_data.get_all_stocks`).
- `uv add <pkg>` / `uv remove <pkg>` — manage dependencies (edits `pyproject.toml` + `uv.lock`).

## Configuration

`settings.py` (at the repo root, NOT inside the `stock_data/` package) loads `.env` via `python-dotenv` and exposes credentials on the `ENV` class:

- `ALPACA_KEY` / `ALPACA_SECRET` — live market-data credentials.
- `ALPACA_PAPER_KEY` / `ALPACA_PAPER_SECRET` — paper-trading credentials.

Credentials are read lazily (a descriptor resolves each name from the environment on access), so importing `settings` — e.g. for `REPO_ROOT` — never requires a `.env`; a missing variable raises `RuntimeError` only when actually used.

`REPO_ROOT` is defined as the directory containing `settings.py`. Because `settings.py` sits at the repo root rather than inside the package, importing it requires running from the repo root (or having the repo root on `sys.path`).

## Architecture

- `stock_data/` — main package.
- `stock_data/clients/alpaca.py` — thin wrapper around the `alpaca-py` SDK. Centralizes `TradingClient` construction (paper vs. live, picking the right keys from `settings.ENV`) and exposes typed helpers like `get_active_us_equities(exchange)`. New data-source clients should follow the same pattern: one file per provider under `clients/`.
- `stock_data/clients/yahoo.py` — Yahoo Finance client: the `Financials` dataclass and `get_financials(symbol)` (via `yfinance`). Note: Yahoo does not raise on unknown tickers — it returns a `Financials` with every field `None`.
- `stock_data/get_all_stock_names.py` — fetches active US-equity symbols from NASDAQ, AMEX, and NYSE via the alpaca client. Accepts `exchanges` and `limit_per_exchange` so tests can pull a tiny slice without hitting the full universe. `refresh_symbols_if_stale()` rewrites `data/all_symbols.txt` at most once per day.
- `stock_data/io_utils.py` — `read_symbols()`: the working universe (`all_symbols.txt` minus `skip_symbols.csv`). Prefer this over reading the symbols file directly.
- `stock_data/storage.py` — SQLite layer: `connect()`, `insert_fundamentals()`, `delete_older_fundamentals()` (drop all but a symbol's newest row), `get_latest_per_symbol()` (latest timestamp per symbol), `get_latest_fundamentals()` (latest full row per symbol).
- `stock_data/read_fundamentals.py` — read-side entry point; loads the latest stored fundamentals for the working universe as dicts (or a DataFrame when run as a script).
- `scripts/get_stock_data.py` — the daily entry point (see Storage below). Budgeted: at most `MAX_YAHOO_CALLS_PER_RUN` Yahoo calls per run, missing symbols first, then stalest, skipping anything fresher than `MIN_REFRESH_AGE_DAYS`.
- `scripts/build_skip_symbols.py` — rebuilds `data/skip_symbols.csv` (ETFs, warrants/rights/units, preferreds, when-issued). `rebuild_skip_symbols_if_stale()` is called by the daily run and rebuilds only when the CSV is missing or older than `MAX_SKIP_SYMBOLS_AGE_DAYS`; it must run after the symbols file is refreshed, since classification reads it.
- `tests/` — pytest test modules. Run with `uv run pytest` from the repo root, or target a single file: `uv run pytest tests/test_storage.py`. Tests that hit live APIs (Alpaca, Yahoo) are marked `network` and excluded by default (see `[tool.pytest.ini_options]` in `pyproject.toml`); run them with `uv run pytest -m network`. New tests against external services must carry that marker.

When adding new data-source clients, read credentials from `settings.ENV` rather than `os.environ` directly.

## Storage

- `data/fundamentals.db` (SQLite) — the fundamentals store, keyed by `(symbol, retrieval_datetime)`. A successful refetch replaces the symbol's previous row, so it holds one (latest) row per symbol; a failed fetch leaves the old row in place. Gitignored.
- `data/all_symbols.txt` — the daily symbol snapshot from Alpaca. Gitignored.
- `data/skip_symbols.csv` — committed skip list (`symbol,reason`) consumed by `read_symbols()`.
- Daily run (intended as a cron entry): `uv run python scripts/get_stock_data.py`.
- Backups:
  - Quick copy (safe when no writer active): `cp data/fundamentals.db data/fundamentals.db.bak`
  - Online safe: `sqlite3 data/fundamentals.db ".backup 'data/fundamentals-$(date +%Y%m%d).db'"`
  - Offsite: rsync `data/` elsewhere.

## Style Guide

- Do not add arg-parsing for testing purposes in new or existing scripts. If a script needs a smaller run for manual testing, expose it as a function parameter (e.g. `limit`) rather than a command-line flag.
