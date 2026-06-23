"""Pure calendar / holiday / business-day / recurrence math.

No Arrow or VGI dependency lives here -- just :mod:`holidays` and
:mod:`dateutil` over ``datetime``. Keeping the math in one importable,
side-effect-free module means it can be unit-tested directly and reused by the
Arrow-facing function adapters in the sibling modules.

* **Holidays / business days** are backed by the :mod:`holidays` library. A
  ``country`` (ISO-3166 alpha-2, default ``"US"``) plus optional ``subdiv``
  (state / province code) select the calendar. Weekends are Saturday/Sunday.
* **Recurrence** (``rrule``) is RFC-5545 expansion via
  :func:`dateutil.rrule.rrulestr`.
* **Easter** is the Western (Gregorian) computus via :func:`dateutil.easter.easter`.
"""

from __future__ import annotations

import datetime as _dt
import functools

import holidays
from dateutil.easter import easter as _easter
from dateutil.rrule import rrulestr

_WEEKEND = {5, 6}  # Saturday, Sunday (Python weekday(): Mon=0 .. Sun=6)


@functools.lru_cache(maxsize=256)
def _holidays_for(country: str, subdiv: str | None) -> holidays.HolidayBase:
    """A reusable :class:`holidays.HolidayBase` for ``country`` / ``subdiv``.

    The instance lazily expands years on demand and caches them internally, so
    repeated membership tests across many dates stay cheap. Wrapped in an LRU so
    a single worker process keeps one calendar object per (country, subdiv).
    """
    return holidays.country_holidays(country.upper(), subdiv=subdiv)


def is_holiday(date: _dt.date, country: str = "US", subdiv: str | None = None) -> bool:
    """True if ``date`` is a public holiday in ``country`` (optionally ``subdiv``)."""
    return date in _holidays_for(country, subdiv)


def holiday_name(date: _dt.date, country: str = "US", subdiv: str | None = None) -> str | None:
    """The holiday name on ``date``, or ``None`` if it is not a holiday.

    When a date carries multiple observances the library joins them with
    ``"; "``; that combined string is returned unchanged.
    """
    return _holidays_for(country, subdiv).get(date)


def is_business_day(date: _dt.date, country: str = "US", subdiv: str | None = None) -> bool:
    """True if ``date`` is a weekday that is not a public holiday."""
    if date.weekday() in _WEEKEND:
        return False
    return date not in _holidays_for(country, subdiv)


def add_business_days(date: _dt.date, n: int, country: str = "US", subdiv: str | None = None) -> _dt.date:
    """Advance ``date`` by ``n`` business days (negative ``n`` goes backwards).

    ``n == 0`` returns ``date`` unchanged even if it is itself a weekend or
    holiday. Otherwise each step skips weekends and holidays; the result is
    always a business day.
    """
    if n == 0:
        return date
    step = 1 if n > 0 else -1
    remaining = abs(n)
    cur = date
    cal = _holidays_for(country, subdiv)
    while remaining > 0:
        cur = cur + _dt.timedelta(days=step)
        if cur.weekday() in _WEEKEND or cur in cal:
            continue
        remaining -= 1
    return cur


def business_days_between(start: _dt.date, end: _dt.date, country: str = "US", subdiv: str | None = None) -> int:
    """Count business days in ``[start, end)`` -- half-open, ``start`` inclusive.

    Returns a count: ``business_days_between(d, d)`` is ``0``. If ``end`` is
    before ``start`` the count is negative (business days going backwards),
    mirroring how a date difference behaves.
    """
    if start == end:
        return 0
    cal = _holidays_for(country, subdiv)
    sign = 1 if end > start else -1
    lo, hi = (start, end) if end > start else (end, start)
    count = 0
    cur = lo
    while cur < hi:
        if cur.weekday() not in _WEEKEND and cur not in cal:
            count += 1
        cur = cur + _dt.timedelta(days=1)
    return sign * count


def easter(year: int) -> _dt.date:
    """Western (Gregorian) Easter Sunday for ``year``."""
    return _easter(year)


def iso_week(date: _dt.date) -> int:
    """ISO-8601 week number (1..53) for ``date``."""
    return date.isocalendar()[1]


def iso_year_week(date: _dt.date) -> str:
    """ISO-8601 year-week label, e.g. ``"2026-W26"``.

    Uses the *ISO* year (which can differ from the calendar year for dates in
    the first/last days of a year) and zero-pads the week to two digits.
    """
    iso = date.isocalendar()
    return f"{iso[0]:04d}-W{iso[1]:02d}"


def holidays_in_year(year: int, country: str = "US", subdiv: str | None = None) -> list[tuple[_dt.date, str, bool]]:
    """All holidays in ``year`` as ``(date, name, observed)`` triples, date-sorted.

    ``observed`` is ``True`` when the entry is an *observed* shift (the library
    appends ``"(observed)"`` to the name when a holiday falling on a weekend is
    observed on an adjacent weekday).
    """
    cal = holidays.country_holidays(country.upper(), subdiv=subdiv, years=year, observed=True)
    rows: list[tuple[_dt.date, str, bool]] = []
    for d, name in cal.items():
        if d.year != year:
            continue
        rows.append((d, name, "(observed)" in name.lower()))
    rows.sort(key=lambda r: r[0])
    return rows


def supported_countries() -> list[tuple[str, str | None]]:
    """Every ``(country, subdivision)`` pair the :mod:`holidays` library supports.

    Returned sorted by country code. A country with no subdivisions yields a
    single row whose ``subdivision`` is ``None``; a country with subdivisions
    yields one row per subdivision (so ``SELECT DISTINCT country`` still lists
    every supported country). This is how broad the coverage is -- the ``"US"``
    default of the holiday functions is just a default, not a limit.
    """
    out: list[tuple[str, str | None]] = []
    for country, subdivs in sorted(holidays.list_supported_countries().items()):
        if subdivs:
            out.extend((country, s) for s in subdivs)
        else:
            out.append((country, None))
    return out


def business_days_in_range(
    start: _dt.date, end: _dt.date, country: str = "US", subdiv: str | None = None
) -> list[_dt.date]:
    """Every business day in the inclusive range ``[start, end]``, ascending."""
    if end < start:
        return []
    cal = _holidays_for(country, subdiv)
    out: list[_dt.date] = []
    cur = start
    while cur <= end:
        if cur.weekday() not in _WEEKEND and cur not in cal:
            out.append(cur)
        cur = cur + _dt.timedelta(days=1)
    return out


def expand_rrule(
    dtstart: _dt.datetime,
    rule: str,
    count: int | None = None,
    until: _dt.datetime | None = None,
    hard_cap: int = 100_000,
) -> list[_dt.datetime]:
    """Expand an RFC-5545 recurrence ``rule`` from ``dtstart``.

    ``rule`` may be a bare ``"FREQ=...;..."`` body or a full ``"RRULE:..."`` /
    multi-line iCalendar string. ``count`` and ``until`` further bound the set
    *in addition to* any ``COUNT`` / ``UNTIL`` already inside ``rule`` -- the
    earliest stop wins. An unbounded rule (no count/until anywhere) is capped at
    ``hard_cap`` occurrences so it always terminates.
    """
    rr = rrulestr(rule, dtstart=dtstart)

    bounded = count is not None or until is not None or _rule_is_bounded(rule)
    limit = hard_cap if not bounded else None

    out: list[_dt.datetime] = []
    for occ in rr:
        if until is not None and occ > until:
            break
        out.append(occ)
        if count is not None and len(out) >= count:
            break
        if limit is not None and len(out) >= limit:
            break
    return out


def _rule_is_bounded(rule: str) -> bool:
    """Heuristic: does the rule text itself carry a COUNT or UNTIL stop?"""
    upper = rule.upper()
    return "COUNT=" in upper or "UNTIL=" in upper
