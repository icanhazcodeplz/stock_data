# stock_data

Daily utility that collects fundamentals (sector, industry, float, short
interest) for most US equities. The symbol universe comes from Alpaca
(NASDAQ, AMEX, NYSE); fundamentals come from Yahoo Finance; everything is
stored as append-only history in a local SQLite database.

## Setup

Requires [uv](https://docs.astral.sh/uv/) (Python 3.14 is managed for you):

```sh
uv sync
```

Create a `.env` at the repo root with your Alpaca market-data credentials:

```
ALPACA_KEY=...
ALPACA_SECRET=...
ALPACA_PAPER_KEY=...
ALPACA_PAPER_SECRET=...
```

Credentials are read lazily — only code paths that talk to Alpaca need them,
so reading the database or running the offline tests works without a `.env`.

## Daily run

```sh
uv run python scripts/get_stock_data.py
```

Each run refreshes the symbol universe (at most once per day), then spends a
budget of up to 500 Yahoo calls: symbols never fetched first
(alphabetically), then previously fetched symbols whose latest row is older
than 7 days, oldest first. A rerun on the same day continues where the last
run stopped instead of repeating it, so the job is safe to cron:

```cron
30 6 * * 1-5 cd /path/to/stock_data && uv run python scripts/get_stock_data.py >> logs/daily.log 2>&1
```

## Weekly skip-list rebuild

```sh
uv run python scripts/build_skip_symbols.py
```

Rebuilds `data/skip_symbols.csv` — ETFs, warrants, rights, units, and
preferred shares, none of which carry the equity fundamentals we collect.
The CSV is committed; intended cadence is weekly.

## Reading the data

```sh
uv run python -m stock_data.read_fundamentals
```

Prints the latest stored row per symbol as a DataFrame. From code, use
`stock_data.read_fundamentals.read_fundamentals_for_all_symbols()` or the
lower-level helpers in `stock_data.storage`.

## Data files

| File | Committed | Purpose |
| --- | --- | --- |
| `data/fundamentals.db` | no | SQLite store; append-only history keyed by `(symbol, retrieval_datetime)` |
| `data/all_symbols.txt` | no | Daily symbol snapshot from Alpaca, one symbol per line |
| `data/skip_symbols.csv` | yes | `symbol,reason` skip list consumed by `read_symbols()` |

Backups: `sqlite3 data/fundamentals.db ".backup 'data/fundamentals-$(date +%Y%m%d).db'"`
is safe while a writer is active; a plain `cp` is fine when nothing is writing.

## Tests

```sh
uv run pytest              # offline suite (default)
uv run pytest -m network   # tests that hit live Alpaca/Yahoo APIs
```
