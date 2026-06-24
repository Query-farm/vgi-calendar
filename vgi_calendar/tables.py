"""Set-returning calendar table functions for DuckDB.

These expand to **many rows**, so they are exposed as **table functions** -- the
form that accepts DuckDB ``name := value`` arguments (``country``, ``subdiv``,
``count``, ``until``). The per-row, single-value calendar functions
(``is_holiday``, ``holiday_name``, ``is_business_day``, ``add_business_days``,
``business_days_between``) are *scalars* and live in
:mod:`vgi_calendar.scalars`, so they can be used inline in a projection.

        SELECT * FROM cal.holidays(2026, country := 'US', subdiv := 'CA');
        SELECT * FROM cal.business_days(DATE '2026-12-21', DATE '2026-12-31', country := 'US');
        SELECT * FROM cal.rrule(TIMESTAMP '2026-01-01', 'FREQ=WEEKLY;COUNT=4');
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Annotated, ClassVar

import pyarrow as pa
from vgi.arguments import Arg
from vgi.metadata import FunctionExample
from vgi.table_function import (
    BindParams,
    ProcessParams,
    TableCardinality,
    TableFunctionGenerator,
    bind_fixed_schema,
    init_single_worker,
)
from vgi_rpc.rpc import OutputCollector

from . import core
from .meta import object_tags
from .schema_utils import field

_SRC = "tables.py"

# VGI509 -- guaranteed-runnable, catalog-qualified examples. Each `sql` is
# self-contained and re-runnable against an attached `cal` worker. We omit
# `expected_result` deliberately: the linter only needs each query to execute.
_HOLIDAYS_EXECUTABLE_EXAMPLES = (
    '[{"description": "Every US public holiday in 2026.", '
    '"sql": "SELECT * FROM cal.main.holidays(2026, country := \'US\') ORDER BY date"}, '
    '{"description": "US + California holidays in 2026.", '
    "\"sql\": \"SELECT date, name FROM cal.main.holidays(2026, country := 'US', subdiv := 'CA') "
    'ORDER BY date"}, '
    '{"description": "Count the US public holidays in 2026.", '
    '"sql": "SELECT count(*) AS n FROM cal.main.holidays(2026, country := \'US\')"}]'
)

# Common named-argument descriptors. ``subdiv`` defaults to NULL; ``country``
# to 'US'. Both are optional and named (string position).
_COUNTRY = Arg[str]("country", default="US", doc="ISO-3166 alpha-2 country code (e.g. 'US', 'GB').")
# Explicit ``arrow_type`` so a supplied VARCHAR ``subdiv`` is bound as a string;
# without it the ``None`` default makes the SDK infer a NULL Arrow type and the
# cast of a provided value fails (VARCHAR -> NULL). ``None`` still means "no
# subdivision" and reaches ``core`` unchanged.
_SUBDIV = Arg[str | None](
    "subdiv",
    default=None,
    arrow_type=pa.string(),
    doc="Optional subdivision / state code (e.g. 'CA', 'NY').",
)


@dataclass(kw_only=True)
class _HolidaysArgs:
    """``holidays(year, country := ..., subdiv := ...)``."""

    year: Annotated[int, Arg(0, arrow_type=pa.int32(), doc="Calendar year (e.g. 2026).")]
    country: Annotated[str, _COUNTRY]
    subdiv: Annotated[str | None, _SUBDIV]


_HOLIDAYS_SCHEMA = pa.schema(
    [
        field("date", pa.date32(), "Holiday date.", nullable=False),
        field("name", pa.string(), "Holiday name.", nullable=False),
        field("observed", pa.bool_(), "True if this is an observed-day shift.", nullable=False),
    ]
)


@init_single_worker
@bind_fixed_schema
class HolidaysFunction(TableFunctionGenerator[_HolidaysArgs]):
    """All public holidays in a year as ``(date, name, observed)`` rows."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _HOLIDAYS_SCHEMA

    class Meta:
        """Function metadata."""

        name = "holidays"
        description = "All public holidays in a year (date, name, observed)"
        categories = ["calendar", "holidays"]
        tags = {
            **object_tags(
                "Holidays In A Year",
                "List **every public holiday in a calendar year** as `(date, name, observed)` rows. "
                "Takes the year as a positional argument and optional named `country` (default "
                "`'US'`) and `subdiv` (state/province) arguments. The `observed` column is `true` "
                "when the row is an *observed-day shift* -- e.g. a holiday that falls on a weekend "
                "and is observed on the adjacent weekday. Coverage spans hundreds of countries via "
                "the `holidays` library; call `cal.supported_countries()` to discover valid "
                "`country`/`subdiv` codes. Use it to build a holiday lookup table, join against "
                "transactions, or audit a jurisdiction's calendar.",
                "## holidays(year, country := ..., subdiv := ...)\n\n"
                "All **public holidays in a year** as `(date, name, observed)` rows.\n\n"
                "`country` defaults to `'US'`; add `subdiv` for regional holidays. `observed` flags "
                "weekend-shift observances. See `cal.supported_countries()` for valid codes.",
                "holidays, list holidays, holiday calendar, public holidays, bank holidays, "
                "observed, holiday table, year holidays",
                _SRC,
            ),
            "vgi.executable_examples": _HOLIDAYS_EXECUTABLE_EXAMPLES,
            "vgi.result_columns_md": (
                "| column | type | description |\n"
                "| --- | --- | --- |\n"
                "| `date` | DATE | Holiday date. |\n"
                "| `name` | VARCHAR | Holiday name. |\n"
                "| `observed` | BOOLEAN | True if this row is an observed-day shift. |\n"
            ),
        }
        examples = [
            FunctionExample(
                sql="SELECT * FROM cal.main.holidays(2026, country := 'US')",
                description="Every US public holiday in 2026",
            ),
            FunctionExample(
                sql="SELECT * FROM cal.main.holidays(2026, country := 'US', subdiv := 'CA')",
                description="US + California holidays in 2026",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_HolidaysArgs]) -> TableCardinality:
        """Estimate the output row count for the query planner."""
        return TableCardinality(estimate=40, max=400)

    @classmethod
    def process(cls, params: ProcessParams[_HolidaysArgs], state: None, out: OutputCollector) -> None:
        """Emit the function's output rows into the collector."""
        a = params.args
        rows = core.holidays_in_year(a.year, a.country, a.subdiv)
        out.emit(
            pa.RecordBatch.from_pydict(
                {
                    "date": [r[0] for r in rows],
                    "name": [r[1] for r in rows],
                    "observed": [r[2] for r in rows],
                },
                schema=params.output_schema,
            )
        )
        out.finish()


@dataclass(kw_only=True)
class _BusinessDaysArgs:
    """``business_days(start, end, country := ..., subdiv := ...)``."""

    start: Annotated[_dt.date, Arg(0, arrow_type=pa.date32(), doc="Range start (inclusive).")]
    end: Annotated[_dt.date, Arg(1, arrow_type=pa.date32(), doc="Range end (inclusive).")]
    country: Annotated[str, _COUNTRY]
    subdiv: Annotated[str | None, _SUBDIV]


_BUSINESS_DAYS_SCHEMA = pa.schema([field("date", pa.date32(), "A business day in the range.", nullable=False)])


@init_single_worker
@bind_fixed_schema
class BusinessDaysFunction(TableFunctionGenerator[_BusinessDaysArgs]):
    """Every business day in an inclusive ``[start, end]`` range, one per row."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _BUSINESS_DAYS_SCHEMA

    class Meta:
        """Function metadata."""

        name = "business_days"
        description = "Every business day in an inclusive [start, end] range"
        categories = ["calendar", "business-days"]
        tags = {
            **object_tags(
                "Business Days In Range",
                "Enumerate **every business (working) day in an inclusive `[start, end]` date "
                "range**, one per row -- weekdays that are not public holidays. Takes `start` and "
                "`end` positionally plus optional named `country` (default `'US'`) and `subdiv`. "
                "Both bounds are inclusive. Use it to expand a range into a working-day series you "
                "can join against, count, or window over (e.g. allocate workload across business "
                "days). For other jurisdictions pass `country`/`subdiv`; see "
                "`cal.supported_countries()` for valid codes.",
                "## business_days(start, end, country := ..., subdiv := ...)\n\n"
                "Every **business day in the inclusive `[start, end]` range**, one per row.\n\n"
                "Weekdays minus holidays; both bounds inclusive. `country` defaults to `'US'`. "
                "Expand a range into a working-day series for joins/counts.",
                "business days, working days, list business days, workday series, banking days, "
                "weekdays excluding holidays, date range",
                _SRC,
            ),
            "vgi.result_columns_md": (
                "| column | type | description |\n"
                "| --- | --- | --- |\n"
                "| `date` | DATE | A business day in the range. |\n"
            ),
        }
        examples = [
            FunctionExample(
                sql="SELECT * FROM cal.main.business_days(DATE '2026-12-21', DATE '2026-12-31', country := 'US')",
                description="Business days over the 2026 year-end week",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_BusinessDaysArgs]) -> TableCardinality:
        """Estimate the output row count for the query planner."""
        return TableCardinality(estimate=None, max=None)

    @classmethod
    def process(cls, params: ProcessParams[_BusinessDaysArgs], state: None, out: OutputCollector) -> None:
        """Emit the function's output rows into the collector."""
        a = params.args
        days = core.business_days_in_range(a.start, a.end, a.country, a.subdiv)
        out.emit(pa.RecordBatch.from_pydict({"date": days}, schema=params.output_schema))
        out.finish()


@dataclass(kw_only=True)
class _RruleArgs:
    """``rrule(dtstart, rule, count := ..., until := ...)``."""

    dtstart: Annotated[_dt.datetime, Arg(0, arrow_type=pa.timestamp("us"), doc="Recurrence start (TIMESTAMP).")]
    rule: Annotated[str, Arg(1, arrow_type=pa.string(), doc="RFC-5545 RRULE body or full string.")]
    count: Annotated[int | None, Arg("count", default=None, arrow_type=pa.int32(), doc="Max occurrences.")]
    until: Annotated[
        _dt.datetime | None,
        Arg("until", default=None, arrow_type=pa.timestamp("us"), doc="Upper bound (inclusive)."),
    ]


_RRULE_SCHEMA = pa.schema(
    [
        field("seq", pa.int64(), "0-based occurrence index.", nullable=False),
        field("occurrence", pa.timestamp("us"), "Occurrence timestamp.", nullable=False),
    ]
)


@init_single_worker
@bind_fixed_schema
class RruleFunction(TableFunctionGenerator[_RruleArgs]):
    """Expand an RFC-5545 recurrence rule into ``(seq, occurrence)`` rows."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _RRULE_SCHEMA

    class Meta:
        """Function metadata."""

        name = "rrule"
        description = "Expand an RFC-5545 recurrence rule (dateutil) into timestamps"
        categories = ["calendar", "recurrence"]
        tags = {
            **object_tags(
                "Expand Recurrence Rule",
                "Expand an **RFC-5545 (iCalendar) recurrence rule** into concrete timestamps as "
                "`(seq, occurrence)` rows. Takes a `dtstart` timestamp and an RRULE string "
                "(e.g. `'FREQ=WEEKLY;COUNT=4'` or a full `'RRULE:...'`) positionally, plus optional "
                "named `count` and `until` bounds. Because an RRULE can be infinite, you **must** "
                "bound it -- either inside the rule (`COUNT=`/`UNTIL=`) or via the `count`/`until` "
                "arguments -- or it will not terminate. `seq` is the 0-based occurrence index. "
                "Parsing is via `dateutil.rrule`. Use it to materialize schedules: meetings, "
                "billing cycles, reminders, cron-like calendar events.",
                "## rrule(dtstart, rule, count := ..., until := ...)\n\n"
                "Expand an **RFC-5545 RRULE** into `(seq, occurrence)` timestamp rows.\n\n"
                "Always bound the rule (`COUNT`/`UNTIL` in the string, or the `count`/`until` "
                "args) -- recurrences can be infinite. `seq` is the 0-based index. Backed by "
                "`dateutil.rrule`.",
                "rrule, recurrence, rfc-5545, icalendar, recurring event, schedule expansion, "
                "freq weekly monthly, repeat, ical",
                _SRC,
            ),
            "vgi.result_columns_md": (
                "| column | type | description |\n"
                "| --- | --- | --- |\n"
                "| `seq` | BIGINT | 0-based occurrence index. |\n"
                "| `occurrence` | TIMESTAMP | Occurrence timestamp. |\n"
            ),
        }
        examples = [
            FunctionExample(
                sql="SELECT * FROM cal.main.rrule(TIMESTAMP '2026-01-01', 'FREQ=WEEKLY;COUNT=4')",
                description="The first four weekly occurrences from 2026-01-01",
            ),
            FunctionExample(
                sql=(
                    "SELECT * FROM cal.main.rrule(TIMESTAMP '2026-01-01', 'FREQ=MONTHLY;BYMONTHDAY=1', "
                    "until := TIMESTAMP '2026-12-31')"
                ),
                description="The first of every month in 2026",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_RruleArgs]) -> TableCardinality:
        """Estimate the output row count for the query planner."""
        n = params.args.count
        return TableCardinality(estimate=n, max=n) if n is not None else TableCardinality(estimate=None, max=None)

    @classmethod
    def process(cls, params: ProcessParams[_RruleArgs], state: None, out: OutputCollector) -> None:
        """Emit the function's output rows into the collector."""
        a = params.args
        occ = core.expand_rrule(a.dtstart, a.rule, count=a.count, until=a.until)
        out.emit(
            pa.RecordBatch.from_pydict(
                {
                    "seq": list(range(len(occ))),
                    "occurrence": occ,
                },
                schema=params.output_schema,
            )
        )
        out.finish()


@dataclass(kw_only=True)
class _NoArgs:
    """``supported_countries()`` takes no arguments."""


_SUPPORTED_COUNTRIES_SCHEMA = pa.schema(
    [
        field("country", pa.string(), "ISO-3166 country code.", nullable=False),
        field("subdivision", pa.string(), "Subdivision/state code, or NULL.", nullable=True),
    ]
)


@init_single_worker
@bind_fixed_schema
class SupportedCountriesFunction(TableFunctionGenerator[_NoArgs]):
    """Every ``(country, subdivision)`` the holiday functions support.

    Coverage is broad (hundreds of countries + subdivisions); the ``'US'``
    default of ``is_holiday`` / ``holidays`` / ``business_days`` is only a
    default. Use this to discover the code to pass as ``country`` / ``subdiv``.
    """

    FIXED_SCHEMA: ClassVar[pa.Schema] = _SUPPORTED_COUNTRIES_SCHEMA

    class Meta:
        """Function metadata."""

        name = "supported_countries"
        description = "Every (country, subdivision) the holiday functions support"
        categories = ["calendar", "holidays"]
        tags = {
            **object_tags(
                "Supported Countries Catalog",
                "List every **`(country, subdivision)` pair the holiday/business-day functions "
                "support**, so you can discover which codes to pass as `country` / `subdiv` to "
                "`is_holiday`, `holiday_name`, `is_business_day`, `holidays`, and friends. "
                "`country` is an ISO-3166 alpha-2 code; `subdivision` is a state/province code or "
                "`NULL` for a country-level entry. Coverage is broad (hundreds of countries plus "
                "subdivisions); `'US'` is merely the default, not a limit. This is a discovery "
                "table -- query, filter, or `count` it to explore the supported jurisdictions.",
                "## supported_countries()\n\n"
                "Every **`(country, subdivision)`** the holiday functions support.\n\n"
                "`country` is ISO-3166 alpha-2; `subdivision` is a state/province code or `NULL`. "
                "Use it to find valid `country`/`subdiv` arguments -- `'US'` is just the default.",
                "supported countries, list countries, available countries, subdivisions, "
                "iso-3166, discovery, what countries, jurisdictions",
                _SRC,
            ),
            "vgi.result_columns_md": (
                "| column | type | description |\n"
                "| --- | --- | --- |\n"
                "| `country` | VARCHAR | ISO-3166 alpha-2 country code. |\n"
                "| `subdivision` | VARCHAR | Subdivision / state code, or NULL. |\n"
            ),
        }
        examples = [
            FunctionExample(
                sql="SELECT count(DISTINCT country) FROM cal.main.supported_countries()",
                description="How many countries are supported",
            ),
            FunctionExample(
                sql="SELECT subdivision FROM cal.main.supported_countries() WHERE country = 'DE'",
                description="German subdivisions (Bundesländer)",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_NoArgs]) -> TableCardinality:
        """Estimate the output row count for the query planner."""
        return TableCardinality(estimate=4000, max=20000)

    @classmethod
    def process(cls, params: ProcessParams[_NoArgs], state: None, out: OutputCollector) -> None:
        """Emit the function's output rows into the collector."""
        rows = core.supported_countries()
        out.emit(
            pa.RecordBatch.from_pydict(
                {
                    "country": [r[0] for r in rows],
                    "subdivision": [r[1] for r in rows],
                },
                schema=params.output_schema,
            )
        )
        out.finish()


TABLE_FUNCTIONS: list[type] = [
    HolidaysFunction,
    BusinessDaysFunction,
    RruleFunction,
    SupportedCountriesFunction,
]
