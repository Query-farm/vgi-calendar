# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "vgi-python[http]>=0.8.5",
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

    SELECT cal.is_holiday(DATE '2026-12-25');            -- per-row scalar (defaults to 'US')
    SELECT cal.is_holiday(DATE '2026-03-31', 'US', 'CA');
    SELECT * FROM cal.holidays(2026, country := 'US', subdiv := 'CA');
    SELECT cal.iso_year_week(DATE '2026-06-22');
    SELECT * FROM cal.rrule(TIMESTAMP '2026-01-01', 'FREQ=WEEKLY;COUNT=4');

    -- Trading / exchange calendars (default exchange 'XNYS' = NYSE):
    SELECT cal.is_trading_day(DATE '2026-01-01');             -- false
    SELECT cal.market_close(DATE '2026-11-27', 'XNYS');       -- early close
    SELECT * FROM cal.trading_schedule(DATE '2026-11-25', DATE '2026-11-30');
    SELECT * FROM cal.exchanges();
"""

from __future__ import annotations

from vgi import Worker
from vgi.catalog import Catalog, Schema, View

from vgi_calendar.meta import keywords_array
from vgi_calendar.scalars import SCALAR_FUNCTIONS
from vgi_calendar.tables import TABLE_FUNCTIONS
from vgi_calendar.trading_scalars import TRADING_SCALAR_FUNCTIONS
from vgi_calendar.trading_tables import TRADING_TABLE_FUNCTIONS

_FUNCTIONS: list[type] = [
    *SCALAR_FUNCTIONS,
    *TABLE_FUNCTIONS,
    *TRADING_SCALAR_FUNCTIONS,
    *TRADING_TABLE_FUNCTIONS,
]

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
    "# cal\n\n"
    "Holiday, business-day, recurrence, and stock-exchange trading-calendar math for DuckDB via "
    "VGI, backed by `holidays`, `python-dateutil`, and `exchange-calendars`.\n\n"
    "**Scalars:** `easter`, `iso_week`, `iso_year_week`, `is_holiday`, `holiday_name`, "
    "`is_business_day`, `add_business_days`, `business_days_between`, `is_trading_day`, "
    "`market_open`, `market_close`.\n\n"
    "**Table functions:** `holidays`, `business_days`, `rrule`, `supported_countries`, "
    "`trading_sessions`, `trading_schedule`, `exchanges`.\n\n"
    "Country/subdivision and exchange are arguments; `'US'` / `'XNYS'` are only defaults. See "
    "`cal.supported_countries()` and `cal.exchanges()` for coverage."
)

_SCHEMA_DESCRIPTION_LLM = (
    "Holiday, business-day, recurrence, and trading-calendar functions: holiday/business-day "
    "tests and names, business-day arithmetic, Easter and ISO week labels, holiday and "
    "business-day listings, RFC-5545 recurrence expansion, and stock-exchange trading sessions, "
    "market open/close, and schedules."
)

_SCHEMA_DESCRIPTION_MD = (
    "Holiday, business-day, recurrence, and stock-exchange trading-calendar functions over Apache "
    "Arrow. Scalars test and name public holidays, test business days, do business-day arithmetic, "
    "compute Easter and ISO week / year-week labels, and answer trading-day, market-open/close, and "
    "early-close questions. Table functions list a year's holidays, enumerate business days or "
    "trading sessions in a range, expand RFC-5545 (RRULE) recurrences, and enumerate supported "
    "countries and exchange MIC codes. Country/subdivision and exchange are arguments; `'US'` and "
    "`'XNYS'` are only defaults."
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

# VGI311 — the parameterless table functions `supported_countries()` and
# `exchanges()` always return the same rows, so we also expose each as a regular
# VIEW of the same name. That lets consumers write `SELECT * FROM cal.main.<name>`
# (no parentheses); the view simply scans the backing table function.
_SUPPORTED_COUNTRIES_VIEW = View(
    name="supported_countries",
    definition="SELECT country, subdivision FROM cal.main.supported_countries()",
    comment="Discovery table of every (country, subdivision) the holiday/business-day functions accept.",
    column_comments={
        "country": "ISO-3166 alpha-2 country code (e.g. 'US', 'GB').",
        "subdivision": "Subdivision / state / province code, or NULL for a country-level entry.",
    },
    tags={
        "vgi.title": "Supported Countries (table)",
        "vgi.doc_llm": (
            "A ready-to-scan **discovery table** of every `(country, subdivision)` pair the "
            "holiday and business-day functions support, so you can find the codes to pass as "
            "`country` / `subdiv` to `is_holiday`, `holiday_name`, `is_business_day`, `holidays`, "
            "and friends. `country` is an ISO-3166 alpha-2 code; `subdivision` is a state/province "
            "code or `NULL` for a country-level entry. This is the no-argument table form of the "
            "`supported_countries()` table function -- query it directly with "
            "`SELECT * FROM cal.main.supported_countries` (no parentheses). Coverage is broad "
            "(hundreds of countries plus subdivisions); `'US'` is merely the default, not a limit."
        ),
        "vgi.doc_md": (
            "## supported_countries (view)\n\n"
            "Every **`(country, subdivision)`** the holiday functions support, as a plain table.\n\n"
            "`country` is ISO-3166 alpha-2; `subdivision` is a state/province code or `NULL`. The "
            "no-argument table form of `supported_countries()` -- scan it with "
            "`SELECT * FROM cal.main.supported_countries`. Use it to find valid `country`/`subdiv` "
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

_EXCHANGES_VIEW = View(
    name="exchanges",
    definition="SELECT code FROM cal.main.exchanges()",
    comment="Discovery table of every supported stock-exchange trading-calendar MIC code.",
    column_comments={
        "code": "Exchange MIC code (e.g. 'XNYS' = NYSE, 'XLON' = London).",
    },
    tags={
        "vgi.title": "Supported Exchanges (table)",
        "vgi.doc_llm": (
            "A ready-to-scan **discovery table** of every supported stock-exchange trading "
            "calendar, one MIC code per row. These are the codes you pass as the `exchange` "
            "argument to the trading functions (`is_trading_day`, `market_open`, "
            "`trading_schedule`, ...). This is the no-argument table form of the `exchanges()` "
            "table function -- query it directly with `SELECT * FROM cal.main.exchanges` (no "
            "parentheses). `'XNYS'` (NYSE) is merely the default; coverage spans roughly a hundred "
            "exchange calendars via `exchange-calendars` (e.g. `'XLON'` London, `'XTKS'` Tokyo, "
            "`'XNAS'` Nasdaq)."
        ),
        "vgi.doc_md": (
            "## exchanges (view)\n\n"
            "Every supported **exchange MIC code**, one per row, as a plain table.\n\n"
            "The valid `exchange` arguments for the trading functions; `'XNYS'` is just the "
            "default. The no-argument table form of `exchanges()` -- scan it with "
            "`SELECT * FROM cal.main.exchanges`. ~100 calendars (`'XLON'`, `'XTKS'`, `'XNAS'`, ...)."
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
                "vgi.example_queries": _SCHEMA_EXAMPLE_QUERIES,
                "vgi.doc_llm": _SCHEMA_DESCRIPTION_LLM,
                "vgi.doc_md": _SCHEMA_DESCRIPTION_MD,
            },
            functions=list(_FUNCTIONS),
            views=[_SUPPORTED_COUNTRIES_VIEW, _EXCHANGES_VIEW],
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
