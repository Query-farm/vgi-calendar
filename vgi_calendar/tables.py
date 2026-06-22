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
from .schema_utils import field

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
        name = "supported_countries"
        description = "Every (country, subdivision) the holiday functions support"
        categories = ["calendar", "holidays"]
        examples = [
            FunctionExample(
                sql="SELECT count(DISTINCT country) FROM cal.supported_countries()",
                description="How many countries are supported",
            ),
            FunctionExample(
                sql="SELECT subdivision FROM cal.supported_countries() WHERE country = 'DE'",
                description="German subdivisions (Bundesländer)",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_NoArgs]) -> TableCardinality:
        return TableCardinality(estimate=4000, max=20000)

    @classmethod
    def process(cls, params: ProcessParams[_NoArgs], state: None, out: OutputCollector) -> None:
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
