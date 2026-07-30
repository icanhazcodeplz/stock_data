# stock_data

Daily utility that collects fundamentals (sector, industry, float, short
interest) for most US equities. The symbol universe comes from Alpaca
(NASDAQ, AMEX, NYSE); fundamentals come from Yahoo Finance; the latest row
per symbol is stored in a local SQLite database.

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

## Skip-list rebuild

`data/skip_symbols.csv` lists ETFs, warrants, rights, units, preferred
shares, and when-issued lines — none of which carry the equity fundamentals
we collect. The daily run rebuilds it automatically whenever it is missing
or more than `MAX_SKIP_SYMBOLS_AGE_DAYS` (3) old, so no separate schedule is
needed. To force a rebuild now:

```sh
uv run python scripts/build_skip_symbols.py
```

The file is generated and gitignored; a fresh clone builds it on the first
run.

### `yahoo_unknown` and the retry window

The daily run also appends a `yahoo_unknown` row for any symbol Yahoo
returns no fundamentals for. Most are exchange-traded debt (baby bonds,
subordinated notes, trust preferreds) and freshly listed ETFs Yahoo has not
classified yet — none of which will ever have a sector or a float.

These rows carry the date they were recorded and expire after
`YAHOO_UNKNOWN_RETRY_DAYS` (30). On expiry the symbol re-enters the universe
for one more attempt: if it returns data the skip entry is dropped, and if
it is still unknown the clock resets. That keeps a genuinely new listing —
a recent IPO, a thinly covered small cap — from being excluded forever,
while costing only a handful of calls a month.

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
| `data/fundamentals.db` | no | SQLite store; latest row per symbol, keyed by `(symbol, retrieval_datetime)` |
| `data/all_symbols.txt` | no | Daily symbol snapshot from Alpaca, one symbol per line |
| `data/skip_symbols.csv` | no | `symbol,reason,date` skip list consumed by `read_symbols()`; written by the rebuild and appended to by the daily run |

Backups: `sqlite3 data/fundamentals.db ".backup 'data/fundamentals-$(date +%Y%m%d).db'"`
is safe while a writer is active; a plain `cp` is fine when nothing is writing.

## Tests

```sh
uv run pytest              # offline suite (default)
uv run pytest -m network   # tests that hit live Alpaca/Yahoo APIs
```
