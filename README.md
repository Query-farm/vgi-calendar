# vgi-calendar

[![CI](https://github.com/Query-farm/vgi-calendar/actions/workflows/ci.yml/badge.svg)](https://github.com/Query-farm/vgi-calendar/actions/workflows/ci.yml)

A [VGI](https://query.farm) worker that brings **calendar math** into DuckDB/SQL:
public holidays, business-day arithmetic, ISO week labels, and RFC-5545
recurrence expansion. Holiday data comes from the
[`holidays`](https://pypi.org/project/holidays/) library (MIT); recurrence and
Easter from [`python-dateutil`](https://pypi.org/project/python-dateutil/).

```sql
INSTALL vgi FROM community; LOAD vgi;
ATTACH 'cal' (TYPE vgi, LOCATION 'uv run calendar_worker.py');

SELECT cal.easter(2026);                                              -- DATE 2026-04-05
SELECT cal.iso_year_week(DATE '2026-06-22');                          -- '2026-W26'
SELECT is_holiday FROM cal.is_holiday(DATE '2026-12-25', country := 'US');   -- true
SELECT * FROM cal.holidays(2026, country := 'US', subdiv := 'CA');
SELECT * FROM cal.rrule(TIMESTAMP '2026-01-01', 'FREQ=WEEKLY;COUNT=4');
```

## Scalars vs. table functions (why some answers are tables)

VGI **scalar** functions bind their constant arguments by *position* only — they
do not accept DuckDB `name := value` arguments. So any calendar function that
wants an optional, named `country` / `subdiv` is exposed as a **table function**
that takes its date(s) positionally and returns a single-row answer:

```sql
-- named country/subdiv -> table function, one row out
SELECT is_holiday FROM cal.is_holiday(DATE '2026-12-25', country := 'US');
SELECT holiday_name FROM cal.holiday_name(DATE '2026-07-04', country := 'US');
SELECT date FROM cal.add_business_days(DATE '2026-12-24', 2, country := 'US');
```

The three functions whose entire signature is positional are true **scalars**
(usable inline in any expression):

```sql
SELECT cal.easter(year), cal.iso_week(d), cal.iso_year_week(d) FROM events;
```

This is the same convention the companion [vgi-crontimes](https://github.com/Query-farm/vgi-crontimes)
worker uses for its named `"end" :=` argument.

## Function catalog

| Function | Form | Signature | Returns |
| --- | --- | --- | --- |
| `is_holiday` | table | `(date DATE, country := 'US', subdiv := NULL)` | `is_holiday BOOLEAN` |
| `holiday_name` | table | `(date DATE, country := 'US', subdiv := NULL)` | `holiday_name VARCHAR` (NULL if none) |
| `is_business_day` | table | `(date DATE, country := 'US', subdiv := NULL)` | `is_business_day BOOLEAN` |
| `add_business_days` | table | `(date DATE, n INT, country := 'US', subdiv := NULL)` | `date DATE` |
| `business_days_between` | table | `(start DATE, end DATE, country := 'US', subdiv := NULL)` | `business_days INT` |
| `holidays` | table | `(year INT, country := 'US', subdiv := NULL)` | `(date DATE, name VARCHAR, observed BOOLEAN)` |
| `business_days` | table | `(start DATE, end DATE, country := 'US', subdiv := NULL)` | `(date DATE)` |
| `rrule` | table | `(dtstart TIMESTAMP, rule VARCHAR, count := NULL, until := NULL)` | `(seq BIGINT, occurrence TIMESTAMP)` |
| `easter` | scalar | `(year INT)` | `DATE` |
| `iso_week` | scalar | `(date DATE)` | `INT` |
| `iso_year_week` | scalar | `(date DATE)` | `VARCHAR` (e.g. `'2026-W26'`) |

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

-- "2 business days after an invoice date" join
SELECT i.id, ab.date AS due
FROM invoices i, cal.add_business_days(i.invoiced_on, 2, country := 'US') ab;
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

For **cron**-style firing math (`0 9 * * *` → next fire times), see the companion
worker [vgi-crontimes](https://github.com/Query-farm/vgi-crontimes); `vgi-calendar`
covers the holiday / business-day / iCalendar-recurrence side of scheduling.

## Dependencies & licensing

| Component | License |
| --- | --- |
| `vgi-calendar` (this worker) | MIT |
| [`holidays`](https://pypi.org/project/holidays/) | MIT |
| [`python-dateutil`](https://pypi.org/project/python-dateutil/) | Apache-2.0 / BSD-3-Clause |
| [`vgi-python`](https://github.com/Query-farm/vgi-python) | Query Farm Source-Available |

Holiday definitions are only as complete as the `holidays` library's coverage
for a given country/subdivision and year; consult its docs for the authoritative
support matrix.

## Local development

```sh
uv sync --all-extras     # create .venv with vgi-python + holidays + dateutil + dev tools
uv run pytest -q         # unit + in-process + end-to-end client tests
uv run ruff check .      # lint
uv run mypy vgi_calendar/
```

`tests/test_core.py` covers the pure date math; `tests/test_tables.py` drives the
table functions through the real bind→init→process lifecycle in-process; and
`tests/test_client.py` spawns `calendar_worker.py` over the VGI client/RPC stack
exactly as DuckDB would after `ATTACH`.

## Layout

```
calendar_worker.py       entry point; assembles the `cal` catalog (inline uv script metadata)
vgi_calendar/
  core.py                pure datetime math over holidays + dateutil (no Arrow/VGI)
  scalars.py             positional-only scalars: easter, iso_week, iso_year_week
  tables.py              named-arg table functions: holidays, business days, rrule, ...
  schema_utils.py        Arrow field/comment helpers
tests/
  harness.py             in-process bind→init→process driver
  test_core.py           pure-math unit tests
  test_tables.py         table-function integration tests
  test_client.py         end-to-end tests via vgi.client.Client
```
