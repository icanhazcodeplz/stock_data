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

`REPO_ROOT` is defined as the directory containing `settings.py`. Because `settings.py` sits at the repo root rather than inside the package, importing it requires running from the repo root (or having the repo root on `sys.path`).

## Architecture

- `stock_data/` — main package.
- `stock_data/clients/alpaca.py` — thin wrapper around the `alpaca-py` SDK. Centralizes `TradingClient` construction (paper vs. live, picking the right keys from `settings.ENV`) and exposes typed helpers like `get_active_us_equities(exchange)`. New data-source clients should follow the same pattern: one file per provider under `clients/`.
- `stock_data/get_all_stock_names.py` — fetches active US-equity symbols from NASDAQ, AMEX, and NYSE via the alpaca client. Accepts `exchanges` and `limit_per_exchange` so tests can pull a tiny slice without hitting the full universe.
- `tests/` — unittest test modules. Run with `uv run python -m unittest discover` from the repo root, or target a single module: `uv run python -m unittest tests.test_get_all_stock_names`.

When adding new data-source clients, read credentials from `settings.ENV` rather than `os.environ` directly.
