# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "vgi-python[http]>=0.14.0",
#     "holidays>=0.50",
#     "python-dateutil>=2.9",
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

For stock-exchange trading calendars (sessions, market hours, schedules), see the
companion worker vgi-trading-calendar.
"""

from __future__ import annotations

import json

from vgi import Worker
from vgi.catalog import Catalog, Schema, Table

from vgi_calendar.meta import keywords_array
from vgi_calendar.scalars import SCALAR_FUNCTIONS
from vgi_calendar.tables import TABLE_FUNCTIONS, SupportedCountriesFunction

_FUNCTIONS: list[type] = [
    *SCALAR_FUNCTIONS,
    *TABLE_FUNCTIONS,
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
    # NB: `supported_countries` is a scan-backed TABLE (see below), not a
    # function, so it carries `vgi.category` on the Table directly and is
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
    "RFC-5545 (RRULE) recurrence rules into timestamps. Use for holiday, business-day, "
    "recurrence, and calendar-label questions in SQL. For stock-exchange trading calendars "
    "(sessions, market hours, schedules), see the companion vgi-trading-calendar worker."
)

_CATALOG_DESCRIPTION_MD = (
    "# Calendar, Holiday & Recurrence Math in SQL\n\n"
    "**`cal` brings public-holiday lookups, business-day arithmetic, and RFC-5545 (RRULE) "
    "recurrence expansion directly into DuckDB SQL — no ETL, no Python glue, just `SELECT`.** Ask "
    "whether a date is a holiday or a working day, name the holiday, add or count business days, "
    "or expand a recurrence rule into a series of timestamps, all as ordinary SQL expressions and "
    "table functions.\n\n"
    "This VGI worker is for analysts, data engineers, and application developers who need correct "
    "calendar logic close to their data: payment and settlement date math, SLA and business-day "
    "deadlines, payroll and billing cycles, and scheduling and reminders. It exposes a single "
    "`cal` catalog (schema `main`) over Apache Arrow, so every function streams results back to "
    "DuckDB with native types — `DATE`, `TIMESTAMP`, and `TIMESTAMPTZ` round-trip cleanly. "
    "Coverage is global, not US-centric: hundreds of countries and their subdivisions are "
    "supported, and `'US'` is merely the default argument, not a limit.\n\n"
    "The holiday and business-day engine is powered by the "
    "[holidays](https://github.com/vacanza/holidays) library "
    "([docs](https://holidays.readthedocs.io/)), which models hundreds of national and "
    "subdivision calendars. Recurrence and Easter math come from "
    "[python-dateutil](https://github.com/dateutil/dateutil) "
    "([docs](https://dateutil.readthedocs.io/)), whose `rrulestr` parser implements the "
    "[RFC-5545](https://datatracker.ietf.org/doc/html/rfc5545) recurrence grammar. For "
    "stock-exchange trading calendars (sessions, market hours, and schedules), see the companion "
    "[vgi-trading-calendar](https://github.com/Query-farm/vgi-trading-calendar) worker.\n\n"
    "Per-row questions are answered by scalar functions you can drop straight into a projection "
    "or predicate; set-returning questions — a year's holidays, a range of working days, an "
    "expanded recurrence — are table functions. Country/subdivision are ordinary arguments that "
    "default to `'US'`. List the schema to discover the full surface and each function's "
    "arguments, and browse the worker's runnable example queries for ready-to-copy starting "
    "points that cover holiday and business-day tests, business-day arithmetic, calendar labels, "
    "and recurrence expansion."
)

_SCHEMA_DESCRIPTION_LLM = (
    "Holiday, business-day, and recurrence functions: holiday/business-day tests and names, "
    "business-day arithmetic, Easter and ISO week labels, holiday and business-day listings, and "
    "RFC-5545 recurrence expansion."
)

_SCHEMA_DESCRIPTION_MD = (
    "## Calendar, holiday & recurrence math\n\n"
    "Holiday, business-day, and recurrence functions over Apache Arrow, exposed as ordinary "
    "DuckDB SQL.\n\n"
    "**Key concepts**\n\n"
    "- Scalar functions answer one question per row and slot into a projection or predicate.\n"
    "- Table functions return sets of rows: a year's holidays, a range of working days, or an "
    "expanded recurrence.\n"
    "- Country/subdivision are ordinary arguments; `'US'` is only a default, not a limit — "
    "coverage is global.\n"
    "- `DATE`, `TIMESTAMP`, and `TIMESTAMPTZ` round-trip natively over Arrow.\n\n"
    "**When to use it**\n\n"
    "Reach for this schema for holiday and business-day date math (settlement, SLA, payroll, "
    "billing), calendar labels (Easter, ISO week / year-week), and RFC-5545 recurrence expansion. "
    "List the schema to discover the functions and their arguments."
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
    "SELECT * FROM cal.main.business_days(DATE '2026-12-21', DATE '2026-12-31');\n"
    "SELECT * FROM cal.main.supported_countries ORDER BY country;"
)

# VGI311 — the `supported_countries` reference dataset always returns the same
# rows, so we expose it as a regular scan-backed TABLE: the `Table(function=…)`
# form serves the rows of the backing generator directly, letting consumers
# write `SELECT * FROM cal.main.supported_countries` (no parentheses) with no
# redundant view-over-a-table-function layer (see vgi-lint VGI145).
_SUPPORTED_COUNTRIES_TABLE = Table(
    name="supported_countries",
    function=SupportedCountriesFunction,
    comment="Discovery table of every (country, subdivision) the holiday/business-day functions accept.",
    # Row identity is the `(country, subdivision)` pair. A country-level entry
    # carries an empty-string subdivision (never NULL — see the generator), so
    # both columns are NOT NULL and the pair is a real composite PRIMARY KEY
    # (VGI805/VGI807). The holiday functions accept an empty-string `subdiv` as
    # country-level, so the primary-key value is also a valid argument.
    not_null=("country", "subdivision"),
    primary_key=(("country", "subdivision"),),
    column_comments={
        "country": "ISO-3166 alpha-2 country code (e.g. 'US', 'GB').",
        "subdivision": "Subdivision / state / province code, or the empty string for a country-level entry.",
    },
    tags={
        "vgi.title": "Supported Countries (table)",
        "vgi.category": "discovery",
        "vgi.doc_llm": (
            "A ready-to-scan **discovery table** of every `(country, subdivision)` pair the "
            "holiday and business-day functions support, so you can find the codes to pass as "
            "`country` / `subdiv` to `is_holiday`, `holiday_name`, `is_business_day`, `holidays`, "
            "and friends. `country` is an ISO-3166 alpha-2 code; `subdivision` is a state/province "
            "code, or the empty string for a country-level entry. Reference it directly by name (no "
            "parentheses) in a query. Coverage is broad "
            "(hundreds of countries plus subdivisions); `'US'` is merely the default, not a limit."
        ),
        "vgi.doc_md": (
            "## supported_countries (table)\n\n"
            "Every **`(country, subdivision)`** the holiday functions support, as a plain table.\n\n"
            "`country` is ISO-3166 alpha-2; `subdivision` is a state/province code, or the empty "
            "string for a country-level entry. Scan it directly by name (no parentheses) to find "
            "valid `country`/`subdiv` arguments; `'US'` is just the default."
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

# VGI413 — the schema's category registry. Ordered; each object's `vgi.category`
# (stamped above / on the table) names one of these. Drives listing navigation
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
        {"name": "discovery", "description": "Reference table of supported countries."},
    ]
)

# VGI509 — at least one guaranteed-runnable example at the catalog level. Each is
# fully catalog-qualified and offline/deterministic so it runs as written.
_EXECUTABLE_EXAMPLES = json.dumps(
    [
        {
            "name": "is-christmas-a-holiday",
            "description": "Whether 25 December 2026 is a US public holiday.",
            "sql": "SELECT cal.main.is_holiday(DATE '2026-12-25') AS is_holiday",
        },
        {
            "name": "add-business-days",
            "description": "Two US business days after 24 December 2026 (skips Christmas + weekend).",
            "sql": "SELECT cal.main.add_business_days(DATE '2026-12-24', 2) AS due",
        },
        {
            "name": "weekly-recurrence",
            "description": "The first four weekly occurrences from 1 January 2026.",
            "sql": "SELECT seq, occurrence FROM cal.main.rrule(TIMESTAMP '2026-01-01', 'FREQ=WEEKLY;COUNT=4') ORDER BY seq",
        },
    ]
)

# VGI152 — the fixed agent-suitability task suite used by `vgi-lint simulate`.
# Each task's `prompt` is all the analyst sees; `reference_sql` is grader-only
# and must be deterministic. Chosen to exercise the main surface (holiday /
# business-day / recurrence scalars + table functions).
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
            "name": "is-us-independence-day-a-holiday",
            "prompt": (
                "Using the cal calendar worker, is 4 July 2026 a public holiday in the United States "
                "(country code 'US')? Return a single boolean value."
            ),
            "reference_sql": "SELECT cal.main.is_holiday(DATE '2026-07-04') AS is_holiday",
            "ignore_column_names": True,
        },
        {
            "name": "is-christmas-a-business-day",
            "prompt": (
                "Using the cal worker, is 25 December 2026 a US business day — that is, a weekday "
                "that is not a public holiday? Return a single boolean value."
            ),
            "reference_sql": "SELECT cal.main.is_business_day(DATE '2026-12-25') AS is_business_day",
            "ignore_column_names": True,
        },
        {
            "name": "count-business-days-year-end",
            "prompt": (
                "Using the cal worker's business_days_between function, how many US business days "
                "does it count between 21 December 2026 and 31 December 2026 (its interval is "
                "start-inclusive, end-exclusive)? Return a single integer."
            ),
            "reference_sql": ("SELECT cal.main.business_days_between(DATE '2026-12-21', DATE '2026-12-31') AS n"),
            "ignore_column_names": True,
        },
        {
            "name": "easter-sunday-2026",
            "prompt": (
                "Using the cal worker, on what calendar date does Western (Gregorian) Easter Sunday "
                "fall in 2026? Return a single date."
            ),
            "reference_sql": "SELECT cal.main.easter(2026) AS easter_date",
            "ignore_column_names": True,
        },
        {
            "name": "iso-week-number",
            "prompt": (
                "Using the cal worker, what is the ISO-8601 week number (a value from 1 to 53) that "
                "contains 22 June 2026? Return a single integer."
            ),
            "reference_sql": "SELECT cal.main.iso_week(DATE '2026-06-22') AS week",
            "ignore_column_names": True,
        },
        {
            "name": "count-us-holidays-2026",
            "prompt": (
                "Using the cal worker's holidays table function, how many public-holiday rows does "
                "it return for the United States (country code 'US') in the calendar year 2026? "
                "Return a single count."
            ),
            "reference_sql": "SELECT count(*) AS n FROM cal.main.holidays(2026, country := 'US')",
            "ignore_column_names": True,
        },
        {
            "name": "count-business-days-table",
            "prompt": (
                "Using the cal worker's business_days table function, how many US business days does "
                "it enumerate for the inclusive date range 21 December 2026 through 31 December "
                "2026? Return a single count."
            ),
            "reference_sql": (
                "SELECT count(*) AS n FROM cal.main.business_days(DATE '2026-12-21', "
                "DATE '2026-12-31', country := 'US')"
            ),
            "ignore_column_names": True,
        },
        {
            "name": "count-supported-countries",
            "prompt": (
                "Using the cal worker's supported_countries table, how many distinct countries does "
                "it cover? Return a single count."
            ),
            "reference_sql": ("SELECT count(DISTINCT country) AS n FROM cal.main.supported_countries"),
            "ignore_column_names": True,
        },
    ]
)


_CALENDAR_CATALOG = Catalog(
    name="cal",
    default_schema="main",
    comment="Holiday, business-day, and recurrence calendar math for SQL",
    tags={
        "vgi.title": "Calendar, Holiday & Recurrence Math",
        "vgi.keywords": keywords_array(
            "calendar, holiday, public holiday, business day, working day, banking day, "
            "easter, iso week, year-week, recurrence, rrule, rfc-5545, "
            "date math, weekday, country, subdivision"
        ),
        "vgi.doc_llm": _CATALOG_DESCRIPTION_LLM,
        "vgi.doc_md": _CATALOG_DESCRIPTION_MD,
        "vgi.author": "Query.Farm",
        "vgi.copyright": "Copyright 2026 Query Farm LLC - https://query.farm",
        "vgi.license": "MIT",
        "vgi.support_contact": "https://github.com/Query-farm/vgi-calendar/issues",
        "vgi.support_policy_url": "https://github.com/Query-farm/vgi-calendar/blob/main/README.md",
        "vgi.executable_examples": _EXECUTABLE_EXAMPLES,
        "vgi.agent_test_tasks": _AGENT_TEST_TASKS,
    },
    source_url="https://github.com/Query-farm/vgi-calendar",
    schemas=[
        Schema(
            name="main",
            comment="Holiday, business-day, and recurrence functions plus the supported-countries table",
            tags={
                "vgi.title": "Calendar — main",
                "vgi.keywords": keywords_array(
                    "holiday, business day, easter, iso week, year-week, recurrence, rrule, "
                    "holidays, business days, supported countries"
                ),
                # VGI123 classifying tags use BARE keys (not vgi.-namespaced).
                "domain": "date-and-time",
                "category": "calendar",
                "topic": "holidays-business-days-recurrence",
                "vgi.categories": _SCHEMA_CATEGORIES,
                "vgi.example_queries": _SCHEMA_EXAMPLE_QUERIES,
                "vgi.doc_llm": _SCHEMA_DESCRIPTION_LLM,
                "vgi.doc_md": _SCHEMA_DESCRIPTION_MD,
            },
            functions=list(_FUNCTIONS),
            tables=[_SUPPORTED_COUNTRIES_TABLE],
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
