"""Pure scalar functions: one value in, one value out, no named arguments.

These are the calendar functions whose whole signature is positional, so they
map cleanly onto a VGI :class:`~vgi.scalar_function.ScalarFunction` (which binds
``Param`` columns by position and ``ConstParam`` constants by position; VGI
scalar functions do not support DuckDB ``name := value`` arguments -- those live
in :mod:`vgi_calendar.tables`).

    SELECT cal.easter(2026);                 -- DATE 2026-04-05
    SELECT cal.iso_week(d), cal.iso_year_week(d) FROM events;
"""

from __future__ import annotations

from typing import Annotated

import pyarrow as pa
from vgi.arguments import Param, Returns
from vgi.metadata import FunctionExample
from vgi.scalar_function import ScalarFunction

from . import core


class EasterFunction(ScalarFunction):
    """Western (Gregorian) Easter Sunday for a given year."""

    class Meta:
        name = "easter"
        description = "Western (Gregorian) Easter Sunday for a year"
        categories = ["calendar"]
        examples = [
            FunctionExample(sql="SELECT cal.easter(2026)", description="Easter Sunday in 2026"),
        ]

    @classmethod
    def compute(
        cls,
        year: Annotated[pa.Int32Array, Param(doc="Year (e.g. 2026)")],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Map each year to its Easter Sunday date (NULLs pass through)."""
        out = [None if y is None else core.easter(int(y)) for y in year.to_pylist()]
        return pa.array(out, type=pa.date32())


class IsoWeekFunction(ScalarFunction):
    """ISO-8601 week number (1..53) for a date."""

    class Meta:
        name = "iso_week"
        description = "ISO-8601 week number (1..53) for a date"
        categories = ["calendar"]
        examples = [
            FunctionExample(sql="SELECT cal.iso_week(DATE '2026-06-22')", description="ISO week of a date"),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to inspect")],
    ) -> Annotated[pa.Int32Array, Returns()]:
        """Map each date to its ISO week number."""
        out = [None if d is None else core.iso_week(d) for d in date.to_pylist()]
        return pa.array(out, type=pa.int32())


class IsoYearWeekFunction(ScalarFunction):
    """ISO-8601 year-week label such as ``'2026-W26'``."""

    class Meta:
        name = "iso_year_week"
        description = "ISO-8601 year-week label, e.g. '2026-W26'"
        categories = ["calendar"]
        examples = [
            FunctionExample(
                sql="SELECT cal.iso_year_week(DATE '2026-06-22')",
                description="ISO year-week label of a date",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to inspect")],
    ) -> Annotated[pa.StringArray, Returns()]:
        """Map each date to its ISO year-week string."""
        out = [None if d is None else core.iso_year_week(d) for d in date.to_pylist()]
        return pa.array(out, type=pa.string())


SCALAR_FUNCTIONS: list[type] = [
    EasterFunction,
    IsoWeekFunction,
    IsoYearWeekFunction,
]
