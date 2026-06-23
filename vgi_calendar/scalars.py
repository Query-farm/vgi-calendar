"""Per-row scalar calendar functions.

Every function here is a true DuckDB **scalar** -- one value (per row) in, one
value out -- so it can be used inline in any projection or predicate:

    SELECT is_holiday(order_date)            FROM orders;
    SELECT order_date, holiday_name(order_date, 'US', 'CA') FROM orders;
    SELECT cal.easter(2026);                 -- DATE 2026-04-05

A note on argument syntax
-------------------------
VGI / DuckDB *scalar* functions take **positional** arguments and resolve
overloads by *arity* (the ``name := value`` named-argument syntax is a property
of table functions and macros, not scalars). The constant ``country`` /
``subdiv`` arguments therefore cannot have Python-style defaults on a single
class; instead each optional trailing argument is exposed as its own arity
overload that shares the function ``name`` -- the same idiom the sibling
``vgi-translate`` worker uses for ``translate(text, to)`` /
``translate(text, to, from)``. So, e.g.:

    is_holiday(date)                  -- country defaults to 'US'
    is_holiday(date, country)         -- explicit country
    is_holiday(date, country, subdiv) -- explicit country + subdivision

Set-returning calendar functions (``holidays``, ``business_days``, ``rrule``)
*do* take named arguments and live in :mod:`vgi_calendar.tables`.
"""

from __future__ import annotations

from typing import Annotated

import pyarrow as pa
from vgi.arguments import ConstParam, Param, Returns
from vgi.metadata import FunctionExample
from vgi.scalar_function import ScalarFunction

from . import core

_DEFAULT_COUNTRY = "US"


# ---------------------------------------------------------------------------
# easter / iso_week / iso_year_week -- whole signature is positional already.
# ---------------------------------------------------------------------------


class EasterFunction(ScalarFunction):
    """Western (Gregorian) Easter Sunday for a given year."""

    class Meta:
        """Function metadata."""

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
        """Function metadata."""

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
        """Function metadata."""

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


# ---------------------------------------------------------------------------
# is_holiday(date[, country[, subdiv]]) -- per-row, arity overloads.
# ---------------------------------------------------------------------------


def _is_holiday_column(date: pa.Date32Array, *, country: str, subdiv: str | None) -> pa.BooleanArray:
    out = [None if d is None else core.is_holiday(d, country, subdiv) for d in date.to_pylist()]
    return pa.array(out, type=pa.bool_())


class IsHolidayFunction(ScalarFunction):
    """``is_holiday(date)`` -- True if the date is a US public holiday."""

    class Meta:
        """Function metadata."""

        name = "is_holiday"
        description = "True if a date is a public holiday (country defaults to 'US')"
        categories = ["calendar", "holidays"]
        examples = [
            FunctionExample(
                sql="SELECT is_holiday(DATE '2026-12-25')",
                description="Is Christmas 2026 a (US) holiday?",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to test.")],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Compute the result column for each input row."""
        return _is_holiday_column(date, country=_DEFAULT_COUNTRY, subdiv=None)


class IsHolidayCountryFunction(ScalarFunction):
    """``is_holiday(date, country)`` -- True if the date is a holiday in ``country``."""

    class Meta:
        """Function metadata."""

        name = "is_holiday"
        description = "True if a date is a public holiday in a country"
        categories = ["calendar", "holidays"]
        examples = [
            FunctionExample(
                sql="SELECT is_holiday(DATE '2026-12-25', 'GB')",
                description="Is Christmas 2026 a UK holiday?",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to test.")],
        country: Annotated[str, ConstParam("ISO-3166 alpha-2 country code, e.g. 'US', 'GB'.")],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Compute the result column for each input row."""
        return _is_holiday_column(date, country=country, subdiv=None)


class IsHolidaySubdivFunction(ScalarFunction):
    """``is_holiday(date, country, subdiv)`` -- holiday in a country + subdivision."""

    class Meta:
        """Function metadata."""

        name = "is_holiday"
        description = "True if a date is a public holiday in a country/subdivision"
        categories = ["calendar", "holidays"]
        examples = [
            FunctionExample(
                sql="SELECT is_holiday(DATE '2026-03-31', 'US', 'CA')",
                description="Cesar Chavez Day is a California holiday",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to test.")],
        country: Annotated[str, ConstParam("ISO-3166 alpha-2 country code, e.g. 'US', 'GB'.")],
        subdiv: Annotated[str, ConstParam("Subdivision / state code, e.g. 'CA', 'NY'.")],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Compute the result column for each input row."""
        return _is_holiday_column(date, country=country, subdiv=subdiv)


# ---------------------------------------------------------------------------
# holiday_name(date[, country[, subdiv]]) -- per-row, arity overloads.
# ---------------------------------------------------------------------------


def _holiday_name_column(date: pa.Date32Array, *, country: str, subdiv: str | None) -> pa.StringArray:
    out = [None if d is None else core.holiday_name(d, country, subdiv) for d in date.to_pylist()]
    return pa.array(out, type=pa.string())


class HolidayNameFunction(ScalarFunction):
    """``holiday_name(date)`` -- the US holiday name on a date, or NULL."""

    class Meta:
        """Function metadata."""

        name = "holiday_name"
        description = "Public-holiday name on a date, or NULL (country defaults to 'US')"
        categories = ["calendar", "holidays"]
        examples = [
            FunctionExample(
                sql="SELECT holiday_name(DATE '2026-07-04')",
                description="Name of the US holiday on 2026-07-04",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to test.")],
    ) -> Annotated[pa.StringArray, Returns()]:
        """Compute the result column for each input row."""
        return _holiday_name_column(date, country=_DEFAULT_COUNTRY, subdiv=None)


class HolidayNameCountryFunction(ScalarFunction):
    """``holiday_name(date, country)`` -- holiday name in ``country``, or NULL."""

    class Meta:
        """Function metadata."""

        name = "holiday_name"
        description = "Public-holiday name on a date in a country, or NULL"
        categories = ["calendar", "holidays"]
        examples = [
            FunctionExample(
                sql="SELECT holiday_name(DATE '2026-12-25', 'GB')",
                description="Name of the UK holiday on Christmas 2026",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to test.")],
        country: Annotated[str, ConstParam("ISO-3166 alpha-2 country code, e.g. 'US', 'GB'.")],
    ) -> Annotated[pa.StringArray, Returns()]:
        """Compute the result column for each input row."""
        return _holiday_name_column(date, country=country, subdiv=None)


class HolidayNameSubdivFunction(ScalarFunction):
    """``holiday_name(date, country, subdiv)`` -- name in a country + subdivision."""

    class Meta:
        """Function metadata."""

        name = "holiday_name"
        description = "Public-holiday name on a date in a country/subdivision, or NULL"
        categories = ["calendar", "holidays"]
        examples = [
            FunctionExample(
                sql="SELECT holiday_name(DATE '2026-03-31', 'US', 'CA')",
                description="Name of the California holiday on 2026-03-31",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to test.")],
        country: Annotated[str, ConstParam("ISO-3166 alpha-2 country code, e.g. 'US', 'GB'.")],
        subdiv: Annotated[str, ConstParam("Subdivision / state code, e.g. 'CA', 'NY'.")],
    ) -> Annotated[pa.StringArray, Returns()]:
        """Compute the result column for each input row."""
        return _holiday_name_column(date, country=country, subdiv=subdiv)


# ---------------------------------------------------------------------------
# is_business_day(date[, country[, subdiv]]) -- per-row, arity overloads.
# ---------------------------------------------------------------------------


def _is_business_day_column(date: pa.Date32Array, *, country: str, subdiv: str | None) -> pa.BooleanArray:
    out = [None if d is None else core.is_business_day(d, country, subdiv) for d in date.to_pylist()]
    return pa.array(out, type=pa.bool_())


class IsBusinessDayFunction(ScalarFunction):
    """``is_business_day(date)`` -- weekday and not a US holiday."""

    class Meta:
        """Function metadata."""

        name = "is_business_day"
        description = "True if a date is a weekday and not a public holiday (country defaults to 'US')"
        categories = ["calendar", "business-days"]
        examples = [
            FunctionExample(
                sql="SELECT is_business_day(DATE '2026-12-25')",
                description="Is Christmas 2026 a business day?",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to test.")],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Compute the result column for each input row."""
        return _is_business_day_column(date, country=_DEFAULT_COUNTRY, subdiv=None)


class IsBusinessDayCountryFunction(ScalarFunction):
    """``is_business_day(date, country)`` -- weekday and not a holiday in ``country``."""

    class Meta:
        """Function metadata."""

        name = "is_business_day"
        description = "True if a date is a weekday and not a public holiday in a country"
        categories = ["calendar", "business-days"]
        examples = [
            FunctionExample(
                sql="SELECT is_business_day(DATE '2026-12-25', 'GB')",
                description="Is Christmas 2026 a UK business day?",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to test.")],
        country: Annotated[str, ConstParam("ISO-3166 alpha-2 country code, e.g. 'US', 'GB'.")],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Compute the result column for each input row."""
        return _is_business_day_column(date, country=country, subdiv=None)


class IsBusinessDaySubdivFunction(ScalarFunction):
    """``is_business_day(date, country, subdiv)`` -- in a country + subdivision."""

    class Meta:
        """Function metadata."""

        name = "is_business_day"
        description = "True if a date is a weekday and not a public holiday in a country/subdivision"
        categories = ["calendar", "business-days"]
        examples = [
            FunctionExample(
                sql="SELECT is_business_day(DATE '2026-03-31', 'US', 'CA')",
                description="Is Cesar Chavez Day a California business day?",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to test.")],
        country: Annotated[str, ConstParam("ISO-3166 alpha-2 country code, e.g. 'US', 'GB'.")],
        subdiv: Annotated[str, ConstParam("Subdivision / state code, e.g. 'CA', 'NY'.")],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Compute the result column for each input row."""
        return _is_business_day_column(date, country=country, subdiv=subdiv)


# ---------------------------------------------------------------------------
# add_business_days(date, n[, country[, subdiv]]) -- per-row, arity overloads.
# ---------------------------------------------------------------------------


def _add_business_days_column(
    date: pa.Date32Array, n: pa.Int32Array, *, country: str, subdiv: str | None
) -> pa.Date32Array:
    out = [
        None if d is None or k is None else core.add_business_days(d, int(k), country, subdiv)
        for d, k in zip(date.to_pylist(), n.to_pylist(), strict=True)
    ]
    return pa.array(out, type=pa.date32())


class AddBusinessDaysFunction(ScalarFunction):
    """``add_business_days(date, n)`` -- advance by N US business days."""

    class Meta:
        """Function metadata."""

        name = "add_business_days"
        description = "Advance a date by N business days, skipping weekends + holidays (country 'US')"
        categories = ["calendar", "business-days"]
        examples = [
            FunctionExample(
                sql="SELECT add_business_days(DATE '2026-12-24', 2)",
                description="Two business days after 2026-12-24 (skips Christmas + weekend)",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Starting date.")],
        n: Annotated[pa.Int32Array, Param(doc="Business days to add (negative goes backwards).")],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Compute the result column for each input row."""
        return _add_business_days_column(date, n, country=_DEFAULT_COUNTRY, subdiv=None)


class AddBusinessDaysCountryFunction(ScalarFunction):
    """``add_business_days(date, n, country)`` -- advance by N business days in ``country``."""

    class Meta:
        """Function metadata."""

        name = "add_business_days"
        description = "Advance a date by N business days in a country, skipping weekends + holidays"
        categories = ["calendar", "business-days"]
        examples = [
            FunctionExample(
                sql="SELECT add_business_days(DATE '2026-12-24', 2, 'GB')",
                description="Two UK business days after 2026-12-24",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Starting date.")],
        n: Annotated[pa.Int32Array, Param(doc="Business days to add (negative goes backwards).")],
        country: Annotated[str, ConstParam("ISO-3166 alpha-2 country code, e.g. 'US', 'GB'.")],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Compute the result column for each input row."""
        return _add_business_days_column(date, n, country=country, subdiv=None)


# ---------------------------------------------------------------------------
# business_days_between(start, end[, country[, subdiv]]) -- per-row overloads.
# ---------------------------------------------------------------------------


def _business_days_between_column(
    start: pa.Date32Array, end: pa.Date32Array, *, country: str, subdiv: str | None
) -> pa.Int32Array:
    out = [
        None if s is None or e is None else core.business_days_between(s, e, country, subdiv)
        for s, e in zip(start.to_pylist(), end.to_pylist(), strict=True)
    ]
    return pa.array(out, type=pa.int32())


class BusinessDaysBetweenFunction(ScalarFunction):
    """``business_days_between(start, end)`` -- count business days in ``[start, end)``."""

    class Meta:
        """Function metadata."""

        name = "business_days_between"
        description = "Count business days in [start, end) (start inclusive; country defaults to 'US')"
        categories = ["calendar", "business-days"]
        examples = [
            FunctionExample(
                sql="SELECT business_days_between(DATE '2026-01-01', DATE '2026-02-01')",
                description="Business days in January 2026",
            ),
        ]

    @classmethod
    def compute(
        cls,
        start: Annotated[pa.Date32Array, Param(doc="Start date (inclusive).")],
        end: Annotated[pa.Date32Array, Param(doc="End date (exclusive).")],
    ) -> Annotated[pa.Int32Array, Returns()]:
        """Compute the result column for each input row."""
        return _business_days_between_column(start, end, country=_DEFAULT_COUNTRY, subdiv=None)


class BusinessDaysBetweenCountryFunction(ScalarFunction):
    """``business_days_between(start, end, country)`` -- count in ``country``."""

    class Meta:
        """Function metadata."""

        name = "business_days_between"
        description = "Count business days in [start, end) for a country (start inclusive)"
        categories = ["calendar", "business-days"]
        examples = [
            FunctionExample(
                sql="SELECT business_days_between(DATE '2026-01-01', DATE '2026-02-01', 'GB')",
                description="UK business days in January 2026",
            ),
        ]

    @classmethod
    def compute(
        cls,
        start: Annotated[pa.Date32Array, Param(doc="Start date (inclusive).")],
        end: Annotated[pa.Date32Array, Param(doc="End date (exclusive).")],
        country: Annotated[str, ConstParam("ISO-3166 alpha-2 country code, e.g. 'US', 'GB'.")],
    ) -> Annotated[pa.Int32Array, Returns()]:
        """Compute the result column for each input row."""
        return _business_days_between_column(start, end, country=country, subdiv=None)


SCALAR_FUNCTIONS: list[type] = [
    EasterFunction,
    IsoWeekFunction,
    IsoYearWeekFunction,
    IsHolidayFunction,
    IsHolidayCountryFunction,
    IsHolidaySubdivFunction,
    HolidayNameFunction,
    HolidayNameCountryFunction,
    HolidayNameSubdivFunction,
    IsBusinessDayFunction,
    IsBusinessDayCountryFunction,
    IsBusinessDaySubdivFunction,
    AddBusinessDaysFunction,
    AddBusinessDaysCountryFunction,
    BusinessDaysBetweenFunction,
    BusinessDaysBetweenCountryFunction,
]
