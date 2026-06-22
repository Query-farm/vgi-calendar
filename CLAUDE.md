# CLAUDE.md — vgi-calendar

Contributor/agent notes. User-facing docs live in `README.md`; this is the
"how it's built and where the sharp edges are" companion.

## What this is

A [VGI](https://query.farm) worker exposing calendar / holiday / business-day /
recurrence **and stock-exchange trading-calendar** math to DuckDB/SQL, backed by
`holidays` (MIT), `python-dateutil`, and `exchange-calendars` (Apache-2.0).
`calendar_worker.py` assembles every function into one `cal` catalog (single
`main` schema) over stdio. Companion to the sibling `vgi-crontimes`.

## Layout

```
calendar_worker.py     repo-root stdio entry point; PEP 723 inline deps; main()
vgi_calendar/
  core.py              pure holiday/business-day/recurrence math (holidays + dateutil)
  trading.py           pure trading-calendar math (exchange-calendars); no Arrow/VGI
  scalars.py           per-row holiday/business-day scalars (arity overloads)
  tables.py            holiday tables (named args) + supported_countries()
  trading_scalars.py   per-row trading scalars (arity overloads, exchange default 'XNYS')
  trading_tables.py    trading_sessions / trading_schedule / exchanges()
  schema_utils.py      pa.Field comment / column-doc helper
tests/                 pytest: test_core, test_trading (pure), test_scalars + test_tables (Client RPC)
test/sql/*.test        haybarn-unittest sqllogictest — authoritative E2E
Makefile               test / test-unit / test-sql / lint
```

To add a function: implement the math in `core.py` / `trading.py` (pure), wrap
it as a scalar or table function in the matching module, register it in
`calendar_worker.py`'s `_FUNCTIONS`.

## Coverage is broad — "US-centric" is just the default

The `holidays` library supports **hundreds** of countries (501 entries incl.
subdivisions in 0.99); every holiday/business-day function takes `country` /
`subdiv`. `'US'` is only the default-arity value. `cal.supported_countries()`
enumerates the full matrix; `cal.exchanges()` enumerates the ~100 trading
calendars. Don't "fix" US-centricity by swapping libraries — `holidays` already
has the broadest coverage of any Python option (`workalendar` covers far fewer).

## Scalars vs table functions — THE core convention (read first)

The VGI SDK makes **scalar functions positional-only**: `name := value` named
args are rejected for scalars and only work on table functions. This drove the
whole function-shape split here:

- **Per-row functions are scalars with arity overloads** so they work inline in
  a projection (`SELECT is_holiday(order_date) FROM orders`):
  `is_holiday(date)` / `(date, country)` / `(date, country, subdiv)`; same shape
  for `holiday_name`, `is_business_day`, `add_business_days`,
  `business_days_between`. Defaults are positional (country defaults to `'US'`).
- **Set-returning functions are table functions** and DO use named args:
  `holidays(year, country := ..., subdiv := ...)`, `business_days(start, end,
  country := ...)`, `rrule(dtstart, rule, count := ..., until := ...)`.

If you're tempted to give a scalar a `country :=` arg, you can't — add an
overload instead. (This same constraint shapes every sibling worker.)

## Sharp edges (learned the hard way)

1. **Named-arg Arrow type must be pinned, or a NULL default breaks the wire.**
   A table-function named arg whose Python default is `None` infers Arrow type
   NULL, so a supplied `subdiv := 'CA'` fails at cast time (`VARCHAR -> "NULL"`).
   Pin `arrow_type=pa.string()` on the descriptor. The in-process pytest harness
   did NOT catch this — only the real ATTACH+SELECT E2E did. **Run the SQL suite.**
2. **`haybarn-unittest` skips `require vgi`.** Under haybarn the extension is not
   autoloaded for `require`, so a `.test` using `require vgi` is silently
   SKIPPED. Use an explicit `statement ok` / `LOAD vgi;` instead (the SQL files
   here already do). `LOAD vgi` also works under the locally-built vgi unittest.
3. **DATE ↔ date32, TIMESTAMP ↔ timestamp(us).** Round-trip these correctly;
   `core.py` keeps everything in `datetime.date`/`datetime` and the Arrow
   mapping is in the function wrappers.
4. **TIMESTAMPTZ scalars need an explicit `Returns(arrow_type=...)`.** A
   `pa.TimestampArray` return raises `TimestampArray requires explicit
   arrow_type in Returns()` at class definition unless you pass
   `Returns(arrow_type=pa.timestamp("us", tz="UTC"))` — see `market_open` /
   `market_close`. `exchange-calendars` returns UTC tz-aware instants; the
   worker maps them to DuckDB `TIMESTAMPTZ`. SQL assertions compare against
   `TIMESTAMPTZ '... +00'` literals so they're timezone-independent.
5. **`exchange-calendars` coverage window is bounded** (~20yr back to ~1yr
   ahead). `trading.py` is written bounds-safe via `searchsorted` on
   `cal.sessions`, so out-of-window dates return `None`/empty rather than
   raising. It also pulls in `pandas` + `numpy` — this worker is heavier than
   the pure-`holidays` core; the model/calendar objects are `lru_cache`d per
   process (the state VGI's pooled worker amortizes).

## Testing

```sh
uv run pytest -q              # unit: pure math + Client RPC integration
make test-sql                 # E2E: haybarn-unittest over test/sql/*  (authoritative)
make test                     # both
uv run ruff check . && uv run mypy vgi_calendar/
```

`make test-sql` sets `VGI_CALENDAR_WORKER="uv run --python 3.13
calendar_worker.py"`, puts `~/.local/bin` on PATH, and runs `haybarn-unittest
--test-dir . "test/sql/*"`. Install the runner once with
`uv tool install haybarn-unittest`. **The SQL suite is authoritative** — unit
tests call functions directly and can pass while the RPC path is broken (that's
how edge #1 hid). CI (`.github/workflows/ci.yml`) runs unit + lint + a gated
`e2e` job that installs haybarn-unittest and runs `make test-sql`.

## Conventions

- `holidays` library: `country` is its country code; `subdiv` is a subdivision
  (state/province). Unknown country/subdiv raises — surfaced as a clear error.
- `rrule` is RFC-5545 via `dateutil.rrule.rrulestr`; bound by `count` or `until`.
- Nothing is published or deployed yet; all functions are pure/offline (no model
  downloads, no network), so the suite is fast and hermetic.
