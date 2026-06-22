"""Calendar table functions for DuckDB.

Two groups, both exposed as **table functions** so they can take DuckDB
``name := value`` arguments (``country``, ``subdiv``) -- VGI scalar functions
bind constants by position only and do not accept named arguments, so any
function that wants an optional, named ``country`` / ``subdiv`` is a table
function here.

* **Single-value answers** -- ``is_holiday``, ``holiday_name``,
  ``is_business_day``, ``add_business_days``, ``business_days_between``. Each
  takes its date(s) as positional ``DATE`` constants plus named ``country`` /
  ``subdiv`` and returns exactly one row with the answer.

* **Set-valued** -- ``holidays(year)``, ``business_days(start, end)``, and
  ``rrule(dtstart, rule)`` expand to many rows.

        SELECT is_holiday FROM cal.is_holiday(DATE '2026-12-25', country := 'US');
        SELECT * FROM cal.holidays(2026, country := 'US', subdiv := 'CA');
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
from .schema_utils import field

# Common named-argument descriptors. ``subdiv`` defaults to NULL; ``country``
# to 'US'. Both are optional and named (string position).
_COUNTRY = Arg[str]("country", default="US", doc="ISO-3166 alpha-2 country code (e.g. 'US', 'GB').")
_SUBDIV = Arg[str | None]("subdiv", default=None, doc="Optional subdivision / state code (e.g. 'CA', 'NY').")


# ===========================================================================
# Single-value answers (date constants in -> one row out)
# ===========================================================================


@dataclass(kw_only=True)
class _DateCountryArgs:
    """A positional ``DATE`` plus optional named ``country`` / ``subdiv``."""

    date: Annotated[_dt.date, Arg(0, arrow_type=pa.date32(), doc="The date to test.")]
    country: Annotated[str, _COUNTRY]
    subdiv: Annotated[str | None, _SUBDIV]


_IS_HOLIDAY_SCHEMA = pa.schema(
    [field("is_holiday", pa.bool_(), "True if the date is a public holiday.", nullable=False)]
)


@init_single_worker
@bind_fixed_schema
class IsHolidayFunction(TableFunctionGenerator[_DateCountryArgs]):
    """Whether a single date is a public holiday."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _IS_HOLIDAY_SCHEMA

    class Meta:
        name = "is_holiday"
        description = "True if a date is a public holiday in a country/subdivision"
        categories = ["calendar", "holidays"]
        examples = [
            FunctionExample(
                sql="SELECT is_holiday FROM cal.is_holiday(DATE '2026-12-25', country := 'US')",
                description="Is Christmas 2026 a US holiday?",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_DateCountryArgs]) -> TableCardinality:
        return TableCardinality(estimate=1, max=1)

    @classmethod
    def process(cls, params: ProcessParams[_DateCountryArgs], state: None, out: OutputCollector) -> None:
        a = params.args
        value = core.is_holiday(a.date, a.country, a.subdiv)
        out.emit(pa.RecordBatch.from_pydict({"is_holiday": [value]}, schema=params.output_schema))
        out.finish()


_HOLIDAY_NAME_SCHEMA = pa.schema(
    [field("holiday_name", pa.string(), "Holiday name, or NULL if not a holiday.", nullable=True)]
)


@init_single_worker
@bind_fixed_schema
class HolidayNameFunction(TableFunctionGenerator[_DateCountryArgs]):
    """The public-holiday name on a date (NULL when not a holiday)."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _HOLIDAY_NAME_SCHEMA

    class Meta:
        name = "holiday_name"
        description = "Public-holiday name on a date, or NULL"
        categories = ["calendar", "holidays"]
        examples = [
            FunctionExample(
                sql="SELECT holiday_name FROM cal.holiday_name(DATE '2026-07-04')",
                description="Name of the US holiday on 2026-07-04",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_DateCountryArgs]) -> TableCardinality:
        return TableCardinality(estimate=1, max=1)

    @classmethod
    def process(cls, params: ProcessParams[_DateCountryArgs], state: None, out: OutputCollector) -> None:
        a = params.args
        value = core.holiday_name(a.date, a.country, a.subdiv)
        out.emit(pa.RecordBatch.from_pydict({"holiday_name": [value]}, schema=params.output_schema))
        out.finish()


_IS_BUSINESS_DAY_SCHEMA = pa.schema(
    [field("is_business_day", pa.bool_(), "True if a weekday and not a holiday.", nullable=False)]
)


@init_single_worker
@bind_fixed_schema
class IsBusinessDayFunction(TableFunctionGenerator[_DateCountryArgs]):
    """Whether a date is a business day (weekday and not a holiday)."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _IS_BUSINESS_DAY_SCHEMA

    class Meta:
        name = "is_business_day"
        description = "True if a date is a weekday and not a public holiday"
        categories = ["calendar", "business-days"]
        examples = [
            FunctionExample(
                sql="SELECT is_business_day FROM cal.is_business_day(DATE '2026-12-25')",
                description="Is Christmas 2026 a business day?",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_DateCountryArgs]) -> TableCardinality:
        return TableCardinality(estimate=1, max=1)

    @classmethod
    def process(cls, params: ProcessParams[_DateCountryArgs], state: None, out: OutputCollector) -> None:
        a = params.args
        value = core.is_business_day(a.date, a.country, a.subdiv)
        out.emit(pa.RecordBatch.from_pydict({"is_business_day": [value]}, schema=params.output_schema))
        out.finish()


@dataclass(kw_only=True)
class _AddBusinessDaysArgs:
    """``add_business_days(date, n, country := ..., subdiv := ...)``."""

    date: Annotated[_dt.date, Arg(0, arrow_type=pa.date32(), doc="Starting date.")]
    n: Annotated[int, Arg(1, arrow_type=pa.int32(), doc="Business days to add (negative goes backwards).")]
    country: Annotated[str, _COUNTRY]
    subdiv: Annotated[str | None, _SUBDIV]


_ADD_BUSINESS_DAYS_SCHEMA = pa.schema([field("date", pa.date32(), "Resulting business day.", nullable=False)])


@init_single_worker
@bind_fixed_schema
class AddBusinessDaysFunction(TableFunctionGenerator[_AddBusinessDaysArgs]):
    """Advance a date by N business days (skipping weekends and holidays)."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _ADD_BUSINESS_DAYS_SCHEMA

    class Meta:
        name = "add_business_days"
        description = "Advance a date by N business days (skips weekends + holidays)"
        categories = ["calendar", "business-days"]
        examples = [
            FunctionExample(
                sql="SELECT date FROM cal.add_business_days(DATE '2026-12-24', 2, country := 'US')",
                description="Two business days after 2026-12-24 (skips Christmas + weekend)",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_AddBusinessDaysArgs]) -> TableCardinality:
        return TableCardinality(estimate=1, max=1)

    @classmethod
    def process(cls, params: ProcessParams[_AddBusinessDaysArgs], state: None, out: OutputCollector) -> None:
        a = params.args
        value = core.add_business_days(a.date, a.n, a.country, a.subdiv)
        out.emit(pa.RecordBatch.from_pydict({"date": [value]}, schema=params.output_schema))
        out.finish()


@dataclass(kw_only=True)
class _BusinessDaysBetweenArgs:
    """``business_days_between(start, end, country := ..., subdiv := ...)``."""

    start: Annotated[_dt.date, Arg(0, arrow_type=pa.date32(), doc="Start date (inclusive).")]
    end: Annotated[_dt.date, Arg(1, arrow_type=pa.date32(), doc="End date (exclusive).")]
    country: Annotated[str, _COUNTRY]
    subdiv: Annotated[str | None, _SUBDIV]


_BUSINESS_DAYS_BETWEEN_SCHEMA = pa.schema(
    [field("business_days", pa.int32(), "Business-day count in [start, end).", nullable=False)]
)


@init_single_worker
@bind_fixed_schema
class BusinessDaysBetweenFunction(TableFunctionGenerator[_BusinessDaysBetweenArgs]):
    """Count business days in the half-open range ``[start, end)``."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _BUSINESS_DAYS_BETWEEN_SCHEMA

    class Meta:
        name = "business_days_between"
        description = "Count business days in [start, end) (start inclusive)"
        categories = ["calendar", "business-days"]
        examples = [
            FunctionExample(
                sql=(
                    "SELECT business_days "
                    "FROM cal.business_days_between(DATE '2026-01-01', DATE '2026-02-01')"
                ),
                description="Business days in January 2026",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_BusinessDaysBetweenArgs]) -> TableCardinality:
        return TableCardinality(estimate=1, max=1)

    @classmethod
    def process(
        cls, params: ProcessParams[_BusinessDaysBetweenArgs], state: None, out: OutputCollector
    ) -> None:
        a = params.args
        value = core.business_days_between(a.start, a.end, a.country, a.subdiv)
        out.emit(pa.RecordBatch.from_pydict({"business_days": [value]}, schema=params.output_schema))
        out.finish()


# ===========================================================================
# Set-valued table functions
# ===========================================================================


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
        name = "holidays"
        description = "All public holidays in a year (date, name, observed)"
        categories = ["calendar", "holidays"]
        examples = [
            FunctionExample(
                sql="SELECT * FROM cal.holidays(2026, country := 'US')",
                description="Every US public holiday in 2026",
            ),
            FunctionExample(
                sql="SELECT * FROM cal.holidays(2026, country := 'US', subdiv := 'CA')",
                description="US + California holidays in 2026",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_HolidaysArgs]) -> TableCardinality:
        return TableCardinality(estimate=40, max=400)

    @classmethod
    def process(cls, params: ProcessParams[_HolidaysArgs], state: None, out: OutputCollector) -> None:
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


_BUSINESS_DAYS_SCHEMA = pa.schema(
    [field("date", pa.date32(), "A business day in the range.", nullable=False)]
)


@init_single_worker
@bind_fixed_schema
class BusinessDaysFunction(TableFunctionGenerator[_BusinessDaysArgs]):
    """Every business day in an inclusive ``[start, end]`` range, one per row."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _BUSINESS_DAYS_SCHEMA

    class Meta:
        name = "business_days"
        description = "Every business day in an inclusive [start, end] range"
        categories = ["calendar", "business-days"]
        examples = [
            FunctionExample(
                sql="SELECT * FROM cal.business_days(DATE '2026-12-21', DATE '2026-12-31', country := 'US')",
                description="Business days over the 2026 year-end week",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_BusinessDaysArgs]) -> TableCardinality:
        return TableCardinality(estimate=None, max=None)

    @classmethod
    def process(cls, params: ProcessParams[_BusinessDaysArgs], state: None, out: OutputCollector) -> None:
        a = params.args
        days = core.business_days_in_range(a.start, a.end, a.country, a.subdiv)
        out.emit(pa.RecordBatch.from_pydict({"date": days}, schema=params.output_schema))
        out.finish()


@dataclass(kw_only=True)
class _RruleArgs:
    """``rrule(dtstart, rule, count := ..., until := ...)``."""

    dtstart: Annotated[
        _dt.datetime, Arg(0, arrow_type=pa.timestamp("us"), doc="Recurrence start (TIMESTAMP).")
    ]
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
        name = "rrule"
        description = "Expand an RFC-5545 recurrence rule (dateutil) into timestamps"
        categories = ["calendar", "recurrence"]
        examples = [
            FunctionExample(
                sql="SELECT * FROM cal.rrule(TIMESTAMP '2026-01-01', 'FREQ=WEEKLY;COUNT=4')",
                description="The first four weekly occurrences from 2026-01-01",
            ),
            FunctionExample(
                sql=(
                    "SELECT * FROM cal.rrule(TIMESTAMP '2026-01-01', 'FREQ=MONTHLY;BYMONTHDAY=1', "
                    "until := TIMESTAMP '2026-12-31')"
                ),
                description="The first of every month in 2026",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_RruleArgs]) -> TableCardinality:
        n = params.args.count
        return (
            TableCardinality(estimate=n, max=n)
            if n is not None
            else TableCardinality(estimate=None, max=None)
        )

    @classmethod
    def process(cls, params: ProcessParams[_RruleArgs], state: None, out: OutputCollector) -> None:
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


TABLE_FUNCTIONS: list[type] = [
    IsHolidayFunction,
    HolidayNameFunction,
    IsBusinessDayFunction,
    AddBusinessDaysFunction,
    BusinessDaysBetweenFunction,
    HolidaysFunction,
    BusinessDaysFunction,
    RruleFunction,
]
