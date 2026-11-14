# CLAUDE.md — vgi-calendar

Contributor/agent notes. User-facing docs live in `README.md`; this is the
"how it's built and where the sharp edges are" companion.

## What this is

A [VGI](https://query.farm) worker exposing calendar / holiday / business-day /
recurrence math to DuckDB/SQL, backed by `holidays` (MIT) and `python-dateutil`.
`vgi_calendar/worker.py` assembles every function into one `cal` catalog (single
`main` schema); `calendar_worker.py` is the repo-root stdio shim that runs it.
Stock-exchange trading calendars were split out into the sibling
`vgi-trading-calendar`; `vgi-crontimes` is the sibling cron-firing worker.

## Layout

```
calendar_worker.py     repo-root stdio shim; PEP 723 inline deps; calls vgi_calendar.worker.main()
vgi_calendar/
  worker.py            the `cal` catalog: _FUNCTIONS, schema/catalog metadata, examples, agent tasks
  composed.py          composed example queries (defined once, published by worker.py)
  core.py              pure holiday/business-day/recurrence math (holidays + dateutil)
  scalars.py           per-row holiday/business-day scalars (arity overloads)
  tables.py            table functions (named args) + the supported_countries generator
  schema_utils.py      pa.Field comment / column-doc helper
  meta.py              per-object discovery/description tag helpers (vgi-lint strict)
tests/                 pytest: test_core (pure), test_scalars + test_tables + test_client (Client RPC),
                       test_composed (example placement, grader privacy)
test/sql/*.test        haybarn-unittest sqllogictest — authoritative E2E
vgi-agent-tests.yaml   private graders for vgi.agent_test_tasks (VGI416)
vgi-lint.toml          vgi-lint settings (LOCATION, fail_on = info)
Makefile               test / test-unit / test-sql / lint
```

To add a function: implement the math in `core.py` (pure), wrap it as a scalar or
table function in the matching module, register it in `vgi_calendar/worker.py`'s
`_FUNCTIONS` (and give it a `_CATEGORY_BY_NAME` entry).

## Examples and agent tasks

- Per-function examples come from each class's `Meta.examples`; `worker.py`
  re-emits them, deduped by name, as the `vgi.example_queries` tag.
- Composed examples (several `cal` objects in one query) live once in
  `composed.py`. `worker.py` puts each in the schema list and on the per-object
  list of every name in `attach_to`, and fails at import if one lands past an
  object's fifth example: the vgi-lint agent simulator only shows agents the
  first five, never the schema list. `test/sql/composed.test` pins their rows;
  check a description against the actual rows whenever you change one.
- Agent tasks: prompt in `_AGENT_TEST_TASKS`, grader in `vgi-agent-tests.yaml`.
  A grader's SQL must not be published as an example (`test_composed.py`
  enforces this), and the prompt must pin the output columns.

## Coverage is broad — "US-centric" is just the default

The `holidays` library supports about 250 countries (0.108: 250 canonical
alpha-2 codes, 843 `supported_countries` rows with subdivisions); every
holiday/business-day function takes `country` / `subdiv`. The library also
accepts aliases (alpha-3 codes, `'UK'`); they stay valid arguments but are left
out of `supported_countries`, which would otherwise count each country twice.
`'US'` is only the default-arity value. `cal.supported_countries` enumerates the
full matrix. Don't "fix" US-centricity by swapping libraries —
`holidays` already has the broadest coverage of any Python option (`workalendar`
covers far fewer).

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
3. **Holiday names depend on the locale unless pinned.** Without `language=`,
   `holidays` picks the name language from LANGUAGE/LC_ALL/LC_MESSAGES/LANG and
   falls back to each country's own language, so CI (LANG=C.UTF-8) got
   "Karfreitag" where a Mac got "Good Friday". `core._country_holidays` always
   passes `language="en_US"`. The `observed` column compares against an
   `observed=False` calendar instead of looking for "(observed)" in the name,
   because many countries label shifts differently ("Day off for ...").
4. **Scalar integer params: use BIGINT.** DuckDB won't narrow BIGINT to INTEGER
   implicitly, so an INTEGER `easter(year)` rejected `easter(year(d))`.
5. **DATE ↔ date32, TIMESTAMP ↔ timestamp(us).** Round-trip these correctly;
   `core.py` keeps everything in `datetime.date`/`datetime` and the Arrow
   mapping is in the function wrappers.

## Testing

```sh
uv sync --all-extras          # once: dev tools (mypy etc.) are an extra
uv run pytest -q              # unit: pure math + Client RPC integration
make test-sql                 # E2E: haybarn-unittest over test/sql/*  (authoritative)
make test                     # both
make lint                     # ruff format --check, ruff check, mypy, pydoclint (as CI)
uvx --refresh --prerelease allow --from 'vgi-lint-check>=2.5.1' \
  vgi-lint lint --execute --execute-mode run --fail-on info   # metadata gate (reads vgi-lint.toml)
```

`make test-sql` sets `VGI_CALENDAR_WORKER="uv run --python 3.13
calendar_worker.py"`, puts `~/.local/bin` on PATH, and runs `haybarn-unittest
--keep-home --test-dir . "test/sql/*"`. Install the runner once with
`uv tool install --prerelease allow 'haybarn-unittest>=2.0.0rc11,<2.1'` (haybarn 2.0:
only its community `vgi` extension speaks the worker's VGI protocol vgi.v3 /
3.3). **The SQL suite is authoritative** — unit
tests call functions directly and can pass while the RPC path is broken (that's
how edge #1 hid). CI (`.github/workflows/ci.yml`) runs unit tests, lint, the vgi-lint
metadata gate, and an `integration` job that runs the SQL suite through
`ci/run-integration.sh` over the subprocess, http, and unix transports.

## Conventions

- `holidays` library: `country` is its country code; `subdiv` is a subdivision
  (state/province). Unknown country/subdiv raises — surfaced as a clear error.
- `rrule` is RFC-5545 via `dateutil.rrule.rrulestr`; bound by `count` or `until`.
- Released from tags (`v0.5.0` is current) as GitHub releases and a ghcr image;
  never published to PyPI. All functions are pure/offline (no model downloads,
  no network), so the suite is fast and hermetic.
