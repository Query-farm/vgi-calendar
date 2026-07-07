<p align="center">
  <img src="https://raw.githubusercontent.com/Query-farm/vgi/main/docs/vgi-logo.png" alt="Vector Gateway Interface (VGI)" width="320">
</p>

<p align="center"><em>A <a href="https://query.farm">Query.Farm</a> VGI worker for DuckDB.</em></p>

# Holidays, Business Days & Recurrence in DuckDB

> **vgi-calendar** · a [Query.Farm](https://query.farm) VGI worker

[![CI](https://github.com/Query-farm/vgi-calendar/actions/workflows/ci.yml/badge.svg)](https://github.com/Query-farm/vgi-calendar/actions/workflows/ci.yml)

A [VGI](https://query.farm) worker that brings **calendar math** into DuckDB/SQL:
public holidays for **hundreds of countries**, business-day arithmetic, ISO week
labels, and RFC-5545 recurrence expansion. Holiday data comes from the
[`holidays`](https://pypi.org/project/holidays/) library (MIT); recurrence and
Easter from [`python-dateutil`](https://pypi.org/project/python-dateutil/).

```sql
INSTALL vgi FROM community; LOAD vgi;
ATTACH 'cal' (TYPE vgi, LOCATION 'uv run calendar_worker.py');

SELECT cal.easter(2026);                                  -- DATE 2026-04-05
SELECT cal.iso_year_week(DATE '2026-06-22');              -- '2026-W26'
SELECT cal.is_holiday(DATE '2026-12-25');                 -- true (country defaults to 'US')
SELECT cal.is_holiday(DATE '2026-07-14', 'FR');           -- true (Bastille Day)
SELECT * FROM cal.holidays(2026, country := 'DE', subdiv := 'BY');  -- Bavaria
SELECT * FROM cal.rrule(TIMESTAMP '2026-01-01', 'FREQ=WEEKLY;COUNT=4');
```

> **Not US-centric.** The `'US'` you see in examples is only a *default*. The
> holiday functions cover **every country `holidays` supports** — run
> `SELECT count(DISTINCT country) FROM cal.supported_countries;` (hundreds).

> **Looking for stock-exchange trading calendars** (sessions, market open/close
> hours, early closes)? Those live in the companion
> [vgi-trading-calendar](https://github.com/Query-farm/vgi-trading-calendar)
> worker.

## Scalars (per-row) vs. table functions (set-returning)

The split follows what the VGI SDK allows for each function shape:

* **Scalars** take **positional** arguments only and resolve overloads by
  *arity* (DuckDB's `name := value` syntax is a table-function/macro feature, not
  a scalar one). Every per-row answer — `is_holiday`, `holiday_name`,
  `is_business_day`, `add_business_days`, `business_days_between`, plus `easter`,
  `iso_week`, `iso_year_week` — is a **scalar**, so it works inline in any
  projection or predicate. Optional `country` / `subdiv` are extra positional
  arity overloads:

  ```sql
  SELECT is_holiday(order_date)                  FROM orders;  -- defaults to 'US'
  SELECT is_holiday(order_date, 'GB')            FROM orders;  -- explicit country
  SELECT is_holiday(order_date, 'US', 'CA')      FROM orders;  -- country + subdivision
  SELECT order_date, add_business_days(order_date, 2) AS due   FROM orders;
  ```

* **Table functions** return *many* rows and therefore accept named `country :=`
  / `subdiv :=` / `count :=` / `until :=` arguments: `holidays`,
  `business_days`, `rrule`.

  ```sql
  SELECT * FROM cal.holidays(2026, country := 'US', subdiv := 'CA') ORDER BY date;
  SELECT * FROM cal.business_days(DATE '2026-12-21', DATE '2026-12-31', country := 'US');
  SELECT * FROM cal.rrule(TIMESTAMP '2026-01-01', 'FREQ=WEEKLY;COUNT=4');
  ```

## Function catalog

| Function | Form | Signature | Returns |
| --- | --- | --- | --- |
| `is_holiday` | scalar | `(date DATE[, country[, subdiv]])` | `BOOLEAN` |
| `holiday_name` | scalar | `(date DATE[, country[, subdiv]])` | `VARCHAR` (NULL if none) |
| `is_business_day` | scalar | `(date DATE[, country[, subdiv]])` | `BOOLEAN` |
| `add_business_days` | scalar | `(date DATE, n INT[, country])` | `DATE` |
| `business_days_between` | scalar | `(start DATE, end DATE[, country])` | `INT` |
| `easter` | scalar | `(year INT)` | `DATE` |
| `iso_week` | scalar | `(date DATE)` | `INT` |
| `iso_year_week` | scalar | `(date DATE)` | `VARCHAR` (e.g. `'2026-W26'`) |
| `holidays` | table | `(year INT, country := 'US', subdiv := NULL)` | `(date DATE, name VARCHAR, observed BOOLEAN)` |
| `business_days` | table | `(start DATE, end DATE, country := 'US', subdiv := NULL)` | `(date DATE)` |
| `rrule` | table | `(dtstart TIMESTAMP, rule VARCHAR, count := NULL, until := NULL)` | `(seq BIGINT, occurrence TIMESTAMP)` |
| `supported_countries` | table | `()` | `(country VARCHAR, subdivision VARCHAR)` |

The `country` default is `'US'`; for `is_holiday` / `holiday_name` /
`is_business_day` a `subdiv` overload selects a state/province calendar. Discover
valid codes with `cal.supported_countries`.

### Holidays & business days

`country` is an ISO-3166 alpha-2 code (`'US'`, `'GB'`, `'DE'`, …) and `subdiv`
selects a state/province calendar (`'CA'`, `'NY'`, …) — both map directly onto
the `holidays` library's country + subdivision API. A date is a **business day**
when it is a weekday (Mon–Fri) *and* not a public holiday.

```sql
-- US federal holidays in 2026, plus California-specific ones
SELECT * FROM cal.holidays(2026, country := 'US', subdiv := 'CA') ORDER BY date;

-- business days in a window, one per row
SELECT * FROM cal.business_days(DATE '2026-12-21', DATE '2026-12-31', country := 'US');

-- "2 business days after an invoice date" — a per-row scalar
SELECT id, add_business_days(invoiced_on, 2, 'US') AS due FROM invoices;
```

`business_days_between(start, end)` counts the half-open range `[start, end)`
(`start` inclusive, `end` exclusive); a reversed range yields a negative count.

### Recurrence (`rrule`)

`rrule` expands an [RFC-5545](https://datatracker.ietf.org/doc/html/rfc5545)
recurrence rule via `dateutil.rrule.rrulestr`. `rule` may be a bare
`FREQ=…;…` body or a full `RRULE:…` string. `count` and `until` are optional,
named bounds *in addition to* any `COUNT`/`UNTIL` inside the rule — the earliest
stop wins. A rule with no bound anywhere is hard-capped (100k rows) so it always
terminates; pair an unbounded rule with `LIMIT`.

```sql
-- the first of every month in 2026
SELECT * FROM cal.rrule(
  TIMESTAMP '2026-01-01', 'FREQ=MONTHLY;BYMONTHDAY=1', until := TIMESTAMP '2026-12-31');

-- every other Tuesday/Thursday, first 10
SELECT * FROM cal.rrule(
  TIMESTAMP '2026-01-06', 'FREQ=WEEKLY;INTERVAL=2;BYDAY=TU,TH', count := 10);
```

## Companion workers

`vgi-calendar` is one of a small scheduling family:

- [vgi-trading-calendar](https://github.com/Query-farm/vgi-trading-calendar) —
  stock-exchange trading calendars: is the market open, next/previous session,
  session arithmetic, and market open/close hours (including early closes) for
  the NYSE and ~100 other exchanges.
- [vgi-crontimes](https://github.com/Query-farm/vgi-crontimes) — cron-style
  firing math (`0 9 * * *` → next fire times).

## Dependencies & licensing

| Component | License |
| --- | --- |
| `vgi-calendar` (this worker) | MIT |
| [`holidays`](https://pypi.org/project/holidays/) | MIT |
| [`python-dateutil`](https://pypi.org/project/python-dateutil/) | Apache-2.0 / BSD-3-Clause |
| [`vgi-python`](https://github.com/Query-farm/vgi-python) | Query Farm Source-Available |

Holiday definitions are only as complete as the `holidays` library's coverage
for a given country / subdivision and year; consult its docs for the
authoritative support matrix.

## Local development

```sh
uv sync --all-extras     # create .venv with vgi-python + holidays + dateutil + dev tools
make test                # pytest (unit + integration) + SQL end-to-end
make test-unit           # pytest only
make test-sql            # DuckDB sqllogictest files via haybarn-unittest
uv run ruff check .      # lint
uv run mypy vgi_calendar/
```

`tests/test_core.py` covers the pure date math (including error / edge cases and
broad, non-US country coverage); `tests/test_tables.py` drives the set-returning
table functions through the real bind→init→process lifecycle in-process;
`tests/test_scalars.py` and `tests/test_client.py` spawn `calendar_worker.py`
over the VGI client/RPC stack exactly as DuckDB would after `ATTACH`. The
`test/sql/*.test` files are DuckDB sqllogictest cases run by
[`haybarn-unittest`](https://pypi.org/project/haybarn-unittest/)
(`uv tool install haybarn-unittest`) against a real `ATTACH` + `SELECT`.

## Layout

```
calendar_worker.py       entry point; assembles the `cal` catalog (inline uv script metadata)
Makefile                 test / test-unit / test-sql targets
vgi_calendar/
  core.py                pure datetime math over holidays + dateutil (no Arrow/VGI)
  scalars.py             per-row holiday/business-day scalars (arity overloads)
  tables.py              named-arg tables: holidays, business_days, rrule, supported_countries
  schema_utils.py        Arrow field/comment helpers
  meta.py                per-object discovery/description metadata helpers
tests/
  harness.py             in-process bind→init→process driver
  test_core.py           pure-math unit + error/edge + coverage tests
  test_tables.py         table-function integration tests
  test_scalars.py        per-row scalar overloads via vgi.client.Client
  test_client.py         end-to-end scalar + table tests via vgi.client.Client
test/sql/
  *.test                 DuckDB sqllogictest end-to-end cases (haybarn-unittest)
```

---

## Authorship & License

Written by [Query.Farm](https://query.farm).

Copyright 2026 Query Farm LLC - https://query.farm
