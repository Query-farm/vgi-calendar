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
from .meta import object_tags

_SRC = "scalars.py"

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
        tags = object_tags(
            "Easter Sunday Date",
            "Return the date of Western (Gregorian) **Easter Sunday** for a given calendar year. "
            "Easter is a *movable feast* whose date is derived from the ecclesiastical lunar "
            "calendar, so it cannot be computed with ordinary date arithmetic. Pass an integer "
            "year (e.g. `2026`) and get back a `DATE`; `NULL` years pass through as `NULL`. Useful "
            "for anchoring Easter-relative observances such as Good Friday (Easter - 2 days), "
            "Easter Monday (Easter + 1), Ascension, or Pentecost. This is the Gregorian/Western "
            "computus only -- Orthodox (Julian) Easter is not returned.",
            "## easter\n\n"
            "Western (Gregorian) **Easter Sunday** for a year.\n\n"
            "Easter is a movable feast, so it needs the computus rather than plain date math. "
            "`easter(2026)` returns `DATE '2026-04-05'`.\n\n"
            "Derive related days arithmetically: Good Friday is `easter(y) - 2`, Easter Monday is "
            "`easter(y) + 1`. Returns the Western/Gregorian date only.",
            "easter, easter sunday, computus, movable feast, good friday, easter monday, gregorian easter, paschal",
            _SRC,
        )
        examples = [
            FunctionExample(sql="SELECT cal.main.easter(2026)", description="Easter Sunday in 2026"),
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
        tags = object_tags(
            "ISO-8601 Week Number",
            "Return the **ISO-8601 week number** (1..53) for a date. Under ISO-8601, weeks start "
            "on Monday and week 1 is the week containing the first Thursday of the year, so the "
            "first few days of January can belong to week 52/53 of the *previous* ISO year (and "
            "the last days of December to week 1 of the *next*). This returns only the week "
            "component; pair it with `iso_year_week` when you need the disambiguating year. "
            "`NULL` dates pass through as `NULL`.",
            "## iso_week\n\n"
            "**ISO-8601 week number** (1..53) for a date.\n\n"
            "ISO weeks start on Monday and week 1 holds the year's first Thursday, so early-January "
            "and late-December dates can land in a neighbouring ISO year's week. This returns the "
            "week number alone -- use `iso_year_week` for the `YYYY-Www` label.",
            "iso week, iso-8601, week number, week of year, calendar week, kw, weeknum",
            _SRC,
        )
        examples = [
            FunctionExample(sql="SELECT cal.main.iso_week(DATE '2026-06-22')", description="ISO week of a date"),
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
        tags = object_tags(
            "ISO-8601 Year-Week Label",
            "Return the **ISO-8601 year-week label** such as `'2026-W26'` for a date. This combines "
            "the ISO week-numbering *year* with the ISO week number, which is the correct, "
            "unambiguous way to label a week: because ISO week 1 is anchored to the first Thursday, "
            "the ISO year can differ from the calendar year for dates near the year boundary (e.g. "
            "`2027-01-01` may be labelled `'2026-W53'`). Returns a `VARCHAR`; `NULL` dates pass "
            "through. Ideal for grouping rows by week (`GROUP BY iso_year_week(ts)`).",
            "## iso_year_week\n\n"
            "**ISO-8601 year-week label** like `'2026-W26'`.\n\n"
            "Combines the ISO week-numbering year with the zero-padded week so the label is "
            "unambiguous across year boundaries (a January date can be `'2025-W52'`). Returns a "
            "string -- handy as a `GROUP BY` key for weekly rollups.",
            "iso year week, year-week, yyyy-www, week label, weekly bucket, group by week, iso-8601 week",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT cal.main.iso_year_week(DATE '2026-06-22')",
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
        tags = object_tags(
            "Is Public Holiday",
            "Test whether a date is a **public holiday**. This one-argument overload uses the "
            "default country `'US'`; for other jurisdictions use `is_holiday(date, country)` or "
            "`is_holiday(date, country, subdiv)`. Returns `BOOLEAN` per row (`NULL` in -> `NULL` "
            "out), so it works inline in a `SELECT` projection or a `WHERE` predicate over a date "
            "column. Holiday coverage comes from the `holidays` library (hundreds of countries). "
            "Note this tests *holidays only* -- it does not consider weekends; use "
            "`is_business_day` if you need 'weekday and not a holiday'.",
            "## is_holiday(date)\n\n"
            "True if `date` is a **public holiday** (defaults to country `'US'`).\n\n"
            "Per-row `BOOLEAN`; usable inline in projections and predicates. Tests holidays only "
            "(weekends are not holidays) -- see `is_business_day` for the combined test, and the "
            "two- and three-argument overloads for other countries/subdivisions.",
            "is holiday, holiday check, public holiday, bank holiday, statutory holiday, "
            "day off, observance, us holiday",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT cal.main.is_holiday(DATE '2026-12-25')",
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
        tags = object_tags(
            "Is Public Holiday In Country",
            "Test whether a date is a **public holiday in a specific country**. Pass an ISO-3166 "
            "alpha-2 country code (e.g. `'GB'`, `'DE'`, `'JP'`) as the second argument; this is the "
            "country overload of `is_holiday`. Returns `BOOLEAN` per row (`NULL` date -> `NULL`). "
            "Coverage is from the `holidays` library; call `cal.supported_countries()` to discover "
            "valid codes. For a state/province-specific test add a subdivision: "
            "`is_holiday(date, country, subdiv)`. An unknown country code raises a clear error.",
            "## is_holiday(date, country)\n\n"
            "True if `date` is a **public holiday in `country`** (ISO-3166 alpha-2, e.g. `'GB'`).\n\n"
            "Per-row `BOOLEAN`. See `cal.supported_countries()` for codes and the three-argument "
            "overload for subdivision-level holidays.",
            "is holiday, country holiday, public holiday, iso country, gb holiday, national holiday, bank holiday",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT cal.main.is_holiday(DATE '2026-12-25', 'GB')",
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
        tags = object_tags(
            "Is Public Holiday In Subdivision",
            "Test whether a date is a **public holiday in a country subdivision** (state, "
            "province, or region). Pass the ISO-3166 country code plus a subdivision code (e.g. "
            "`'US','CA'` for California, `'DE','BY'` for Bavaria). This three-argument overload "
            "catches *regional* holidays that the national overload misses -- e.g. Cesar Chavez "
            "Day is observed in California but is not a US-wide federal holiday. Returns `BOOLEAN` "
            "per row (`NULL` date -> `NULL`). Discover valid country/subdivision pairs with "
            "`cal.supported_countries()`; an unknown code raises a clear error.",
            "## is_holiday(date, country, subdiv)\n\n"
            "True if `date` is a **holiday in a subdivision** (e.g. `'US','CA'`).\n\n"
            "Catches region-only holidays national tests miss. Per-row `BOOLEAN`; see "
            "`cal.supported_countries()` for valid `(country, subdiv)` pairs.",
            "is holiday, subdivision holiday, state holiday, provincial holiday, regional holiday, "
            "cesar chavez day, california holiday",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT cal.main.is_holiday(DATE '2026-03-31', 'US', 'CA')",
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
        tags = object_tags(
            "Public Holiday Name",
            "Return the **name of the public holiday** falling on a date, or `NULL` if the date is "
            "not a holiday. This one-argument overload uses the default country `'US'` (so "
            "`2026-07-04` -> `'Independence Day'`). Returns `VARCHAR` per row, so it doubles as a "
            "holiday test: a non-`NULL` result means it's a holiday. For other jurisdictions use "
            "`holiday_name(date, country)` or `holiday_name(date, country, subdiv)`. Names come "
            "from the `holidays` library and are localized to that library's defaults.",
            "## holiday_name(date)\n\n"
            "**Name** of the US public holiday on `date`, else `NULL`.\n\n"
            "Per-row `VARCHAR`; a non-`NULL` value also signals 'is a holiday'. See the country "
            "and subdivision overloads for other jurisdictions.",
            "holiday name, name of holiday, what holiday, holiday label, observance name, "
            "independence day, us holiday name",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT cal.main.holiday_name(DATE '2026-07-04')",
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
        tags = object_tags(
            "Public Holiday Name In Country",
            "Return the **name of the public holiday** on a date for a specific country, or `NULL` "
            "if not a holiday there. Pass an ISO-3166 alpha-2 country code as the second argument "
            "(e.g. `'GB'`, `'FR'`). This is the country overload of `holiday_name`; the result is "
            "`VARCHAR` per row and is `NULL` for non-holidays. Use `cal.supported_countries()` to "
            "find valid codes, and add a subdivision argument for region-specific holiday names. "
            "An unknown country code raises a clear error.",
            "## holiday_name(date, country)\n\n"
            "**Name** of the holiday on `date` in `country` (e.g. `'GB'`), else `NULL`.\n\n"
            "Per-row `VARCHAR`. See `cal.supported_countries()` for codes and the subdivision "
            "overload for regional names.",
            "holiday name, country holiday name, name of holiday, what holiday, observance, uk holiday name",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT cal.main.holiday_name(DATE '2026-12-25', 'GB')",
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
        tags = object_tags(
            "Public Holiday Name In Subdivision",
            "Return the **name of the public holiday** on a date for a country subdivision "
            "(state/province/region), or `NULL`. Pass the ISO-3166 country code plus a subdivision "
            "code (e.g. `'US','CA'`). This three-argument overload surfaces *regional* holiday "
            "names the national overload would miss -- e.g. `2026-03-31` in `'US','CA'` is "
            "`'Cesar Chavez Day'`. Result is `VARCHAR` per row, `NULL` for non-holidays. "
            "Discover valid `(country, subdiv)` pairs via `cal.supported_countries()`.",
            "## holiday_name(date, country, subdiv)\n\n"
            "**Name** of the holiday in a subdivision (e.g. `'US','CA'`), else `NULL`.\n\n"
            "Surfaces region-only holiday names. Per-row `VARCHAR`; see "
            "`cal.supported_countries()` for valid pairs.",
            "holiday name, subdivision holiday name, state holiday name, regional holiday, "
            "cesar chavez day, california holiday name",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT cal.main.holiday_name(DATE '2026-03-31', 'US', 'CA')",
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
        tags = object_tags(
            "Is Business Day",
            "Test whether a date is a **business (working) day** -- i.e. a Monday-Friday weekday "
            "that is *not* a public holiday. This one-argument overload uses the default country "
            "`'US'`. Unlike `is_holiday`, this combines the weekend test with the holiday test, so "
            "Saturdays/Sundays return `false` even when they are not holidays. Returns `BOOLEAN` "
            "per row (`NULL` date -> `NULL`); use it inline to filter rows to working days "
            "(`WHERE is_business_day(order_date)`). For other jurisdictions use the country / "
            "subdivision overloads.",
            "## is_business_day(date)\n\n"
            "True if `date` is a **weekday and not a public holiday** (country `'US'`).\n\n"
            "Combines the weekend and holiday tests -- weekends are `false` regardless. Per-row "
            "`BOOLEAN`; great as a `WHERE` filter. See the country/subdivision overloads.",
            "is business day, working day, business day check, weekday, banking day, "
            "trading-free, not weekend not holiday",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT cal.main.is_business_day(DATE '2026-12-25')",
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
        tags = object_tags(
            "Is Business Day In Country",
            "Test whether a date is a **business (working) day in a specific country** -- a weekday "
            "that is not a public holiday there. Pass an ISO-3166 alpha-2 country code (e.g. "
            "`'GB'`, `'DE'`) as the second argument. The weekend test is Monday-Friday; the "
            "holiday set is the country's. Returns `BOOLEAN` per row (`NULL` date -> `NULL`). "
            "Discover codes with `cal.supported_countries()`; add a subdivision for region-aware "
            "business days. An unknown country code raises a clear error.",
            "## is_business_day(date, country)\n\n"
            "True if `date` is a **working day in `country`** (weekday, not a holiday there).\n\n"
            "Per-row `BOOLEAN`. See `cal.supported_countries()` for codes and the subdivision "
            "overload for regional calendars.",
            "is business day, working day, country business day, banking day, weekday, uk business day, gb working day",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT cal.main.is_business_day(DATE '2026-12-25', 'GB')",
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
        tags = object_tags(
            "Is Business Day In Subdivision",
            "Test whether a date is a **business (working) day in a country subdivision** "
            "(state/province/region) -- a weekday that is not a holiday under that subdivision's "
            "calendar. Pass the ISO-3166 country code plus a subdivision code (e.g. `'US','CA'`). "
            "Regional holidays count: `2026-03-31` is a weekday but, in California, it is Cesar "
            "Chavez Day and so is *not* a business day there. Returns `BOOLEAN` per row (`NULL` "
            "date -> `NULL`); see `cal.supported_countries()` for valid pairs.",
            "## is_business_day(date, country, subdiv)\n\n"
            "True if `date` is a **working day in a subdivision** (e.g. `'US','CA'`).\n\n"
            "Honours region-only holidays. Per-row `BOOLEAN`; see `cal.supported_countries()` for "
            "valid `(country, subdiv)` pairs.",
            "is business day, subdivision business day, state working day, regional holiday, "
            "california business day, banking day",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT cal.main.is_business_day(DATE '2026-03-31', 'US', 'CA')",
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
        tags = object_tags(
            "Add Business Days",
            "Advance a date by **N business days**, skipping weekends and public holidays. This "
            "two-argument overload uses the default country `'US'`. `N` may be negative to step "
            "*backwards*; weekends and holidays are not counted, so the result is always itself a "
            "business day. Returns `DATE` per row (`NULL` date or `NULL` n -> `NULL`). Typical for "
            "SLA/settlement math like 'invoice due 2 business days after issue'. For other "
            "jurisdictions use the country / subdivision overloads.",
            "## add_business_days(date, n)\n\n"
            "Advance `date` by **`n` business days**, skipping weekends + US holidays.\n\n"
            "`n` can be negative to go backwards; the result is always a business day. Per-row "
            "`DATE`. Use for settlement / SLA due-date math; see the country/subdivision overloads.",
            "add business days, business day offset, due date, settlement date, working days, "
            "next business day, sla, skip weekends holidays",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT cal.main.add_business_days(DATE '2026-12-24', 2)",
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
        tags = object_tags(
            "Add Business Days In Country",
            "Advance a date by **N business days in a specific country**, skipping weekends and "
            "that country's public holidays. Pass an ISO-3166 alpha-2 country code (e.g. `'GB'`) "
            "as the third argument. `N` may be negative to step backwards; the result is always a "
            "business day. Returns `DATE` per row (`NULL` inputs -> `NULL`). Discover codes with "
            "`cal.supported_countries()`. An unknown country code raises a clear error.",
            "## add_business_days(date, n, country)\n\n"
            "Advance `date` by **`n` business days in `country`** (e.g. `'GB'`).\n\n"
            "Skips weekends + that country's holidays; `n` can be negative. Per-row `DATE`. See "
            "`cal.supported_countries()` for codes.",
            "add business days, country business days, due date, settlement, working days, "
            "uk business days, banking days",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT cal.main.add_business_days(DATE '2026-12-24', 2, 'GB')",
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
        tags = object_tags(
            "Count Business Days Between",
            "Count the number of **business days in the half-open interval `[start, end)`** -- "
            "`start` inclusive, `end` exclusive -- skipping weekends and public holidays. This "
            "two-argument overload uses the default country `'US'`. Returns `INTEGER` per row "
            "(`NULL` if either bound is `NULL`); the count is negative if `end` precedes `start`. "
            "Use it to measure working-day durations such as turnaround time or aging. For other "
            "jurisdictions use the country overload.",
            "## business_days_between(start, end)\n\n"
            "Count **business days in `[start, end)`** (start inclusive, end exclusive) for US.\n\n"
            "Skips weekends + holidays; negative if `end < start`. Per-row `INTEGER`. Use for "
            "working-day durations; see the country overload for other jurisdictions.",
            "business days between, count business days, working day count, turnaround, "
            "duration in business days, aging, banking days",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT cal.main.business_days_between(DATE '2026-01-01', DATE '2026-02-01')",
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
        tags = object_tags(
            "Count Business Days Between In Country",
            "Count the number of **business days in `[start, end)` for a specific country** -- "
            "`start` inclusive, `end` exclusive -- skipping weekends and that country's public "
            "holidays. Pass an ISO-3166 alpha-2 country code (e.g. `'GB'`) as the third argument. "
            "Returns `INTEGER` per row (`NULL` if a bound is `NULL`); negative if `end` precedes "
            "`start`. Discover codes with `cal.supported_countries()`.",
            "## business_days_between(start, end, country)\n\n"
            "Count **business days in `[start, end)`** for `country` (e.g. `'GB'`).\n\n"
            "Skips weekends + that country's holidays; negative if reversed. Per-row `INTEGER`. "
            "See `cal.supported_countries()` for codes.",
            "business days between, country business days, working day count, turnaround, "
            "uk business days, banking days, duration",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT cal.main.business_days_between(DATE '2026-01-01', DATE '2026-02-01', 'GB')",
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
