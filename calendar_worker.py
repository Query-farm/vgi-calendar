# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "vgi-python[http]>=0.8.4",
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
from vgi.catalog import Catalog, Schema

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
    "Holiday, business-day, recurrence, and stock-exchange trading-calendar functions over Apache Arrow."
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

_CALENDAR_CATALOG = Catalog(
    name="cal",
    default_schema="main",
    comment="Holiday, business-day, recurrence, and stock-exchange trading-calendar math for SQL",
    tags={
        "vgi.title": "Calendar, Holiday & Trading-Day Math",
        "vgi.keywords": (
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
                "vgi.keywords": (
                    "holiday, business day, trading day, easter, iso week, recurrence, rrule, "
                    "market open, market close, exchange calendar, supported countries, exchanges"
                ),
                # VGI123 classifying tags use BARE keys (not vgi.-namespaced).
                "domain": "date-and-time",
                "category": "calendar",
                "topic": "holidays-business-days-trading-calendars",
                "vgi.source_url": ("https://github.com/Query-farm/vgi-calendar/blob/main/calendar_worker.py"),
                "vgi.example_queries": _SCHEMA_EXAMPLE_QUERIES,
                "vgi.doc_llm": _SCHEMA_DESCRIPTION_LLM,
                "vgi.doc_md": _SCHEMA_DESCRIPTION_MD,
            },
            functions=list(_FUNCTIONS),
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
