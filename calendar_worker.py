# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "vgi-python[http]>=0.9.0",
#     "holidays>=0.50",
#     "python-dateutil>=2.9",
#     "exchange-calendars>=4.5",
# ]
# ///
"""VGI worker exposing calendar / holiday / business-day / recurrence math to SQL.

Assembles the calendar functions in ``vgi_calendar`` into a single ``cal``
catalog and runs the worker over stdio (DuckDB subprocess) or HTTP.

Usage:
    uv run calendar_worker.py           # serve over stdio (DuckDB subprocess)

    INSTALL vgi FROM community; LOAD vgi;
    ATTACH 'cal' (TYPE vgi, LOCATION 'uv run calendar_worker.py');

    SELECT cal.main.is_holiday(DATE '2026-12-25');            -- per-row scalar (defaults to 'US')
    SELECT cal.main.is_holiday(DATE '2026-03-31', 'US', 'CA');
    SELECT * FROM cal.main.holidays(2026, country := 'US', subdiv := 'CA');
    SELECT cal.main.iso_year_week(DATE '2026-06-22');
    SELECT * FROM cal.main.rrule(TIMESTAMP '2026-01-01', 'FREQ=WEEKLY;COUNT=4');

    -- Trading / exchange calendars (default exchange 'XNYS' = NYSE):
    SELECT cal.main.is_trading_day(DATE '2026-01-01');             -- false
    SELECT cal.main.market_close(DATE '2026-11-27', 'XNYS');       -- early close
    SELECT * FROM cal.main.trading_schedule(DATE '2026-11-25', DATE '2026-11-30');
    SELECT * FROM cal.main.exchanges;
"""

from __future__ import annotations

import json

from vgi import Worker
from vgi.catalog import Catalog, Schema, Table

from vgi_calendar.meta import keywords_array
from vgi_calendar.scalars import SCALAR_FUNCTIONS
from vgi_calendar.tables import TABLE_FUNCTIONS, SupportedCountriesFunction
from vgi_calendar.trading_scalars import TRADING_SCALAR_FUNCTIONS
from vgi_calendar.trading_tables import TRADING_TABLE_FUNCTIONS, ExchangesFunction

_FUNCTIONS: list[type] = [
    *SCALAR_FUNCTIONS,
    *TABLE_FUNCTIONS,
    *TRADING_SCALAR_FUNCTIONS,
    *TRADING_TABLE_FUNCTIONS,
]

# VGI413 — the schema's `vgi.categories` registry (see below) requires every
# categorizable object to carry a `vgi.category` naming one of the registry
# entries. Rather than thread a category argument through every function's
# `Meta`, map each function by name and stamp `vgi.category` onto its tags here;
# `vgi.resolve_metadata` reads `Meta.tags` live at discovery time, so mutating it
# before the worker serves is sufficient.
_CATEGORY_BY_NAME: dict[str, str] = {
    # Holiday tests, names, and listings
    "is_holiday": "holidays",
    "holiday_name": "holidays",
    "holidays": "holidays",
    # Business-day tests, arithmetic, and enumeration
    "is_business_day": "business-days",
    "add_business_days": "business-days",
    "business_days_between": "business-days",
    "business_days": "business-days",
    # RFC-5545 recurrence expansion
    "rrule": "recurrence",
    # Calendar labels: Easter and ISO week / year-week
    "easter": "date-parts",
    "iso_week": "date-parts",
    "iso_year_week": "date-parts",
    # Stock-exchange trading calendars
    "is_trading_day": "trading",
    "next_trading_day": "trading",
    "previous_trading_day": "trading",
    "add_trading_days": "trading",
    "trading_days_between": "trading",
    "market_open": "trading",
    "market_close": "trading",
    "is_early_close": "trading",
    "trading_sessions": "trading",
    "trading_schedule": "trading",
    # NB: `supported_countries` / `exchanges` are scan-backed TABLES (see below),
    # not functions, so they carry `vgi.category` on the Table directly and are
    # intentionally absent from this function-name map.
}

for _fn in _FUNCTIONS:
    _meta = _fn.Meta  # type: ignore[attr-defined]  # every registered function class defines Meta
    _meta.tags = {**dict(_meta.tags), "vgi.category": _CATEGORY_BY_NAME[_meta.name]}

_CATALOG_DESCRIPTION_LLM = (
    "Calendar math for SQL: test whether a date is a public holiday or business day and name the "
    "holiday (hundreds of countries and subdivisions via the `holidays` library), advance dates by "
    "business days and count business days between two dates, compute Easter and ISO week / "
    "year-week labels, list a year's holidays, enumerate business days in a range, and expand "
    "RFC-5545 (RRULE) recurrence rules into timestamps. Also covers stock-exchange trading "
    "calendars (default 'XNYS' = NYSE): test trading days, get market open/close instants "
    "(including early closes), list trading sessions and the per-session schedule for a date "
    "range, and enumerate supported exchange MIC codes. Use for holiday, business-day, "
    "recurrence, and market-hours questions in SQL."
)

_CATALOG_DESCRIPTION_MD = (
    "# Calendar, Holiday & Trading-Day Math in SQL\n\n"
    "**`cal` brings public-holiday lookups, business-day arithmetic, RFC-5545 (RRULE) "
    "recurrence expansion, and stock-exchange trading calendars directly into DuckDB SQL — no "
    "ETL, no Python glue, just `SELECT`.** Ask whether a date is a holiday or a working day, name "
    "the holiday, add or count business days, expand a recurrence rule into a series of "
    "timestamps, or check market open/close hours for the NYSE and ~100 other exchanges, all as "
    "ordinary SQL expressions and table functions.\n\n"
    "This VGI worker is for analysts, data engineers, and application developers who need correct "
    "calendar logic close to their data: payment and settlement date math, SLA and business-day "
    "deadlines, payroll and billing cycles, scheduling and reminders, trading-day filtering, and "
    "market-hours analytics. It exposes a single `cal` catalog (schema `main`) over Apache Arrow, "
    "so every function streams results back to DuckDB with native types — `DATE`, `TIMESTAMP`, "
    "and `TIMESTAMPTZ` round-trip cleanly. Coverage is global, not US-centric: hundreds of "
    "countries and their subdivisions are supported, and `'US'` / `'XNYS'` (NYSE) are merely the "
    "default arguments, not limits.\n\n"
    "The holiday and business-day engine is powered by the "
    "[holidays](https://github.com/vacanza/holidays) library "
    "([docs](https://holidays.readthedocs.io/)), which models hundreds of national and "
    "subdivision calendars. Recurrence and Easter math come from "
    "[python-dateutil](https://github.com/dateutil/dateutil) "
    "([docs](https://dateutil.readthedocs.io/)), whose `rrulestr` parser implements the "
    "[RFC-5545](https://datatracker.ietf.org/doc/html/rfc5545) recurrence grammar. Trading "
    "calendars are provided by "
    "[exchange-calendars](https://github.com/gerrymanoim/exchange_calendars), covering roughly a "
    "hundred exchanges including early closes and holiday sessions.\n\n"
    "Per-row questions are answered by scalar functions you can drop straight into a projection "
    "or predicate; set-returning questions — a year's holidays, a range of working days or "
    "trading sessions, an expanded recurrence — are table functions. Country/subdivision and "
    "exchange are ordinary arguments that default to `'US'` and `'XNYS'`. List the schema to "
    "discover the full surface and each function's arguments; a few starting points:\n\n"
    "```sql\n"
    "SELECT cal.main.is_holiday(DATE '2026-12-25');\n"
    "SELECT cal.main.add_business_days(DATE '2026-12-24', 2);\n"
    "SELECT * FROM cal.main.rrule(TIMESTAMP '2026-01-01', 'FREQ=WEEKLY;COUNT=4');\n"
    "```"
)

_SCHEMA_DESCRIPTION_LLM = (
    "Holiday, business-day, recurrence, and trading-calendar functions: holiday/business-day "
    "tests and names, business-day arithmetic, Easter and ISO week labels, holiday and "
    "business-day listings, RFC-5545 recurrence expansion, and stock-exchange trading sessions, "
    "market open/close, and schedules."
)

_SCHEMA_DESCRIPTION_MD = (
    "## Calendar, holiday & trading-day math\n\n"
    "Holiday, business-day, recurrence, and stock-exchange trading-calendar functions over Apache "
    "Arrow, exposed as ordinary DuckDB SQL.\n\n"
    "**Key concepts**\n\n"
    "- Scalar functions answer one question per row and slot into a projection or predicate.\n"
    "- Table functions return sets of rows: a year's holidays, a range of working days or trading "
    "sessions, or an expanded recurrence.\n"
    "- Country/subdivision and exchange are ordinary arguments; `'US'` and `'XNYS'` (NYSE) are "
    "only defaults, not limits — coverage is global.\n"
    "- `DATE`, `TIMESTAMP`, and `TIMESTAMPTZ` round-trip natively over Arrow.\n\n"
    "**When to use it**\n\n"
    "Reach for this schema for holiday and business-day date math (settlement, SLA, payroll, "
    "billing), calendar labels (Easter, ISO week / year-week), RFC-5545 recurrence expansion, and "
    "trading-day / market-hours analytics. List the schema to discover the functions and their "
    "arguments."
)

# VGI506 — representative, catalog-qualified example queries for the schema.
# Every reference is fully qualified (`cal.main.<fn>`) so each line executes as
# written against the attached worker.
_SCHEMA_EXAMPLE_QUERIES = (
    "SELECT cal.main.is_holiday(DATE '2026-12-25');\n"
    "SELECT cal.main.holiday_name(DATE '2026-07-04');\n"
    "SELECT cal.main.is_business_day(DATE '2026-12-25');\n"
    "SELECT cal.main.add_business_days(DATE '2026-12-24', 2);\n"
    "SELECT cal.main.business_days_between(DATE '2026-01-01', DATE '2026-02-01');\n"
    "SELECT cal.main.easter(2026);\n"
    "SELECT cal.main.iso_year_week(DATE '2026-06-22');\n"
    "SELECT * FROM cal.main.holidays(2026, country := 'US', subdiv := 'CA');\n"
    "SELECT * FROM cal.main.rrule(TIMESTAMP '2026-01-01', 'FREQ=WEEKLY;COUNT=4');\n"
    "SELECT cal.main.is_trading_day(DATE '2026-01-01');\n"
    "SELECT cal.main.market_close(DATE '2026-11-27');\n"
    "SELECT * FROM cal.main.trading_schedule(DATE '2026-11-25', DATE '2026-11-30');"
)

# VGI311 — the `supported_countries` and `exchanges` reference datasets always
# return the same rows, so we expose each as a regular scan-backed TABLE: the
# `Table(function=…)` form serves the rows of the backing generator directly,
# letting consumers write `SELECT * FROM cal.main.<name>` (no parentheses) with
# no redundant view-over-a-table-function layer (see vgi-lint VGI145).
_SUPPORTED_COUNTRIES_TABLE = Table(
    name="supported_countries",
    function=SupportedCountriesFunction,
    comment="Discovery table of every (country, subdivision) the holiday/business-day functions accept.",
    # `country` is always populated; `subdivision` is NULL for country-level rows,
    # so the row identity is the (country, subdivision) pair (UNIQUE, not a PK
    # since subdivision is nullable).
    not_null=("country",),
    unique=(("country", "subdivision"),),
    column_comments={
        "country": "ISO-3166 alpha-2 country code (e.g. 'US', 'GB').",
        "subdivision": "Subdivision / state / province code, or NULL for a country-level entry.",
    },
    tags={
        "vgi.title": "Supported Countries (table)",
        "vgi.category": "discovery",
        "vgi.doc_llm": (
            "A ready-to-scan **discovery table** of every `(country, subdivision)` pair the "
            "holiday and business-day functions support, so you can find the codes to pass as "
            "`country` / `subdiv` to `is_holiday`, `holiday_name`, `is_business_day`, `holidays`, "
            "and friends. `country` is an ISO-3166 alpha-2 code; `subdivision` is a state/province "
            "code or `NULL` for a country-level entry. Reference it directly by name (no "
            "parentheses) in a `FROM` clause. Coverage is broad "
            "(hundreds of countries plus subdivisions); `'US'` is merely the default, not a limit."
        ),
        "vgi.doc_md": (
            "## supported_countries (table)\n\n"
            "Every **`(country, subdivision)`** the holiday functions support, as a plain table.\n\n"
            "`country` is ISO-3166 alpha-2; `subdivision` is a state/province code or `NULL`. "
            "Scan it directly by name (no parentheses) to find valid `country`/`subdiv` "
            "arguments; `'US'` is just the default."
        ),
        "vgi.keywords": keywords_array(
            "supported countries, list countries, available countries, subdivisions, "
            "iso-3166, discovery, what countries, jurisdictions, countries table"
        ),
        "domain": "date-and-time",
        "category": "calendar",
        "topic": "supported-countries",
        "vgi.example_queries": (
            '[{"description": "How many countries are supported.", '
            '"sql": "SELECT count(DISTINCT country) FROM cal.main.supported_countries"}, '
            '{"description": "German subdivisions (Bundesländer).", '
            '"sql": "SELECT subdivision FROM cal.main.supported_countries WHERE country = \'DE\'"}]'
        ),
    },
)

_EXCHANGES_TABLE = Table(
    name="exchanges",
    function=ExchangesFunction,
    comment="Discovery table of every supported stock-exchange trading-calendar MIC code.",
    # Each MIC code uniquely identifies one exchange calendar -> natural primary key.
    primary_key=(("code",),),
    column_comments={
        "code": "Exchange MIC code (e.g. 'XNYS' = NYSE, 'XLON' = London).",
    },
    tags={
        "vgi.title": "Supported Exchanges (table)",
        "vgi.category": "discovery",
        "vgi.doc_llm": (
            "A ready-to-scan **discovery table** of every supported stock-exchange trading "
            "calendar, one MIC code per row. These are the codes you pass as the `exchange` "
            "argument to the trading functions (`is_trading_day`, `market_open`, "
            "`trading_schedule`, ...). Reference it directly by name (no parentheses) in a "
            "`FROM` clause. "
            "`'XNYS'` (NYSE) is merely the default; coverage spans roughly a hundred "
            "exchange calendars via `exchange-calendars` (e.g. `'XLON'` London, `'XTKS'` Tokyo, "
            "`'XNAS'` Nasdaq)."
        ),
        "vgi.doc_md": (
            "## exchanges (table)\n\n"
            "Every supported **exchange MIC code**, one per row, as a plain table.\n\n"
            "The valid `exchange` arguments for the trading functions; `'XNYS'` is just the "
            "default. Scan it directly by name (no parentheses). "
            "~100 calendars (`'XLON'`, `'XTKS'`, `'XNAS'`, ...)."
        ),
        "vgi.keywords": keywords_array(
            "exchanges, list exchanges, mic codes, supported exchanges, trading calendars, "
            "discovery, xnys xlon xtks, stock exchange codes, exchanges table"
        ),
        "domain": "date-and-time",
        "category": "calendar",
        "topic": "supported-exchanges",
        "vgi.example_queries": (
            '[{"description": "List all supported exchange MIC codes.", '
            '"sql": "SELECT code FROM cal.main.exchanges ORDER BY code"}, '
            '{"description": "Confirm the NYSE (XNYS) calendar is available.", '
            '"sql": "SELECT count(*) AS n FROM cal.main.exchanges WHERE code = \'XNYS\'"}]'
        ),
    },
)


# VGI413 — the schema's category registry. Ordered; each object's `vgi.category`
# (stamped above / on the views) names one of these. Drives listing navigation
# and SEO sections.
_SCHEMA_CATEGORIES = json.dumps(
    [
        {"name": "holidays", "description": "Public-holiday tests, names, and yearly listings."},
        {
            "name": "business-days",
            "description": "Business/working-day tests, business-day arithmetic, and enumeration.",
        },
        {"name": "recurrence", "description": "RFC-5545 (RRULE) recurrence expansion into timestamps."},
        {"name": "date-parts", "description": "Calendar labels: Easter and ISO week / year-week."},
        {
            "name": "trading",
            "description": "Stock-exchange trading calendars: sessions, market hours, and schedules.",
        },
        {"name": "discovery", "description": "Reference tables of supported countries and exchange codes."},
    ]
)

# VGI152 — the fixed agent-suitability task suite used by `vgi-lint simulate`.
# Each task's `prompt` is all the analyst sees; `reference_sql` is grader-only
# and must be deterministic. Chosen to exercise the main surface (holiday /
# business-day / recurrence scalars + table functions and the trading calendar).
_AGENT_TEST_TASKS = json.dumps(
    [
        {
            "name": "add-five-business-days",
            "prompt": (
                "Using the cal calendar worker, what calendar date is exactly 5 US business days "
                "after 25 November 2026? Business days exclude weekends and US public holidays "
                "(note US Thanksgiving falls in that week). Return a single date."
            ),
            "reference_sql": "SELECT cal.main.add_business_days(DATE '2026-11-25', 5) AS result",
            "ignore_column_names": True,
        },
        {
            "name": "iso-year-week-label",
            "prompt": (
                "Using the cal worker, what is the ISO 8601 year-week label (ISO year and week "
                "number) for 22 June 2026? Return the single label value."
            ),
            "reference_sql": "SELECT cal.main.iso_year_week(DATE '2026-06-22') AS iso_year_week",
            "ignore_column_names": True,
        },
        {
            "name": "japan-golden-week-holiday-name",
            "prompt": (
                "Using the cal worker, what is the name of the public holiday in Japan (country "
                "code 'JP') on 4 May 2026? Return the single holiday name."
            ),
            "reference_sql": "SELECT cal.main.holiday_name(DATE '2026-05-04', 'JP') AS name",
            "ignore_column_names": True,
        },
        {
            "name": "next-nyse-session-after-new-year",
            "prompt": (
                "Using the cal worker, what is the first New York Stock Exchange trading session "
                "strictly after 1 January 2026? Return a single date."
            ),
            "reference_sql": "SELECT cal.main.next_trading_day(DATE '2026-01-01') AS next_session",
            "ignore_column_names": True,
        },
        {
            "name": "add-ten-nyse-sessions",
            "prompt": (
                "Using the cal worker, what calendar date is 10 New York Stock Exchange trading "
                "sessions after 2 January 2026 (skipping weekends and exchange holidays)? Return a "
                "single date."
            ),
            "reference_sql": "SELECT cal.main.add_trading_days(DATE '2026-01-02', 10) AS result",
            "ignore_column_names": True,
        },
        {
            "name": "mon-wed-fri-recurrence",
            "prompt": (
                "Using the cal worker's RFC-5545 recurrence support, list the first six occurrences "
                "of the rule 'FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=6' starting at midnight on "
                "1 January 2026. Return the sequence index and occurrence timestamp, ordered by "
                "sequence."
            ),
            "reference_sql": (
                "SELECT seq, occurrence FROM cal.main.rrule(TIMESTAMP '2026-01-01', "
                "'FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=6') ORDER BY seq"
            ),
            "ignore_column_names": True,
        },
        {
            "name": "nyse-early-close-instant",
            "prompt": (
                "Using the cal worker, at what UTC timestamp does the New York Stock Exchange close "
                "on 27 November 2026 (the day after US Thanksgiving, an early-close half-day)? "
                "Return a single timestamp."
            ),
            "reference_sql": "SELECT cal.main.market_close(DATE '2026-11-27') AS market_close",
            "ignore_column_names": True,
        },
    ]
)


_CALENDAR_CATALOG = Catalog(
    name="cal",
    default_schema="main",
    comment="Holiday, business-day, recurrence, and stock-exchange trading-calendar math for SQL",
    tags={
        "vgi.title": "Calendar, Holiday & Trading-Day Math",
        "vgi.keywords": keywords_array(
            "calendar, holiday, public holiday, business day, working day, banking day, "
            "easter, iso week, year-week, recurrence, rrule, rfc-5545, trading day, "
            "trading calendar, exchange calendar, market open, market close, nyse, lse, "
            "date math, weekday, country, subdivision"
        ),
        "vgi.doc_llm": _CATALOG_DESCRIPTION_LLM,
        "vgi.doc_md": _CATALOG_DESCRIPTION_MD,
        "vgi.author": "Query.Farm",
        "vgi.copyright": "Copyright 2026 Query Farm LLC - https://query.farm",
        "vgi.license": "MIT",
        "vgi.support_contact": "https://github.com/Query-farm/vgi-calendar/issues",
        "vgi.support_policy_url": "https://github.com/Query-farm/vgi-calendar/blob/main/README.md",
        "vgi.agent_test_tasks": _AGENT_TEST_TASKS,
    },
    source_url="https://github.com/Query-farm/vgi-calendar",
    schemas=[
        Schema(
            name="main",
            comment="Holiday, business-day, and recurrence calendar math for SQL",
            tags={
                "vgi.title": "Calendar — main",
                "vgi.keywords": keywords_array(
                    "holiday, business day, trading day, easter, iso week, recurrence, rrule, "
                    "market open, market close, exchange calendar, supported countries, exchanges"
                ),
                # VGI123 classifying tags use BARE keys (not vgi.-namespaced).
                "domain": "date-and-time",
                "category": "calendar",
                "topic": "holidays-business-days-trading-calendars",
                "vgi.categories": _SCHEMA_CATEGORIES,
                "vgi.example_queries": _SCHEMA_EXAMPLE_QUERIES,
                "vgi.doc_llm": _SCHEMA_DESCRIPTION_LLM,
                "vgi.doc_md": _SCHEMA_DESCRIPTION_MD,
            },
            functions=list(_FUNCTIONS),
            tables=[_SUPPORTED_COUNTRIES_TABLE, _EXCHANGES_TABLE],
        ),
    ],
)


class CalendarWorker(Worker):
    """Worker process hosting the ``cal`` calendar catalog."""

    catalog = _CALENDAR_CATALOG


def main() -> None:
    """Run the calendar worker process (stdio or, via flags, HTTP)."""
    CalendarWorker.main()


if __name__ == "__main__":
    main()
