"""Composed example queries: several ``cal`` objects combined in one realistic query.

Each query is defined exactly once here and referenced from every place that
publishes it:

* the schema-level ``vgi.example_queries`` list (see :mod:`vgi_calendar.worker`);
* the per-object ``vgi.example_queries`` list of every object named in
  :attr:`ComposedExample.attach_to` -- the object that drives the query comes
  first. The vgi-lint agent simulator shows agents only the first five examples
  of a function or table, never the schema-level list, so the worker inserts
  these within that window;
* ``test/sql/composed.test`` and ``tests/test_composed.py``, which pin the rows
  each description promises.

Every query is offline and deterministic (fixed years and dates, no ``now()``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComposedExample:
    """One composed example query.

    Attributes:
        name: Stable slug, used by tests and as the executable-example name.
        description: What the query answers. It must match the rows it returns.
        sql: The catalog-qualified query.
        attach_to: Object names whose per-object example list also carries this
            query. The driving object comes first.
    """

    name: str
    description: str
    sql: str
    attach_to: tuple[str, ...]

    def as_example(self) -> dict[str, str]:
        """Return the ``{"description", "sql"}`` dict used by ``vgi.example_queries``."""
        return {"description": self.description, "sql": self.sql}


PAYMENT_CALENDAR = ComposedExample(
    name="settlement-schedule-following",
    description=(
        "Payment calendar: 1st-of-month 2026 payments from rrule, rolled forward to the next US "
        "business day when the 1st is not one, with the reason: the holiday name, or the weekday "
        "for weekend rolls."
    ),
    sql=(
        "WITH sched AS (SELECT r.seq, CAST(r.occurrence AS DATE) AS due "
        "FROM cal.main.rrule(TIMESTAMP '2026-01-01', 'FREQ=MONTHLY;BYMONTHDAY=1;COUNT=12') AS r) "
        "SELECT due, CASE WHEN cal.main.is_business_day(due) THEN due "
        "ELSE cal.main.add_business_days(due, 1) END AS settles_on, "
        "CASE WHEN NOT cal.main.is_business_day(due) "
        "THEN coalesce(cal.main.holiday_name(due), dayname(due)) END AS rolled_because "
        "FROM sched ORDER BY seq"
    ),
    attach_to=("rrule", "add_business_days"),
)

MONTHLY_CAPACITY = ComposedExample(
    name="monthly-working-days",
    description=(
        "Capacity plan: US business days per month in 2026, with the holidays that fell on a "
        "weekday and so removed a working day (weekend holidays such as Saturday 4 July are "
        "left out)."
    ),
    sql=(
        "WITH bd AS (SELECT date_trunc('month', date) AS month, count(*) AS business_days "
        "FROM cal.main.business_days(DATE '2026-01-01', DATE '2026-12-31', country := 'US') "
        "GROUP BY ALL), "
        "lost AS (SELECT date_trunc('month', date) AS month, count(*) AS weekday_holidays, "
        "string_agg(name, ', ' ORDER BY date) AS holiday_names "
        "FROM cal.main.holidays(2026, country := 'US') WHERE isodow(date) <= 5 GROUP BY ALL) "
        "SELECT strftime(bd.month, '%Y-%m') AS month, bd.business_days, "
        "coalesce(lost.weekday_holidays, 0) AS weekday_holidays, lost.holiday_names "
        "FROM bd LEFT JOIN lost USING (month) ORDER BY bd.month"
    ),
    attach_to=("business_days",),
)

US_GB_OPEN_DAYS = ComposedExample(
    name="us-gb-common-business-days",
    description=(
        "Cross-border settlement window: the days from 21 Dec 2026 to 8 Jan 2027 when both the "
        "US and the UK (GB) are open, i.e. US business days that are also GB business days."
    ),
    sql=(
        "SELECT b.date, dayname(b.date) AS weekday "
        "FROM cal.main.business_days(DATE '2026-12-21', DATE '2027-01-08', country := 'US') AS b "
        "WHERE cal.main.is_business_day(b.date, 'GB') ORDER BY b.date"
    ),
    attach_to=("business_days", "is_business_day"),
)

WEEKLY_CAPACITY = ComposedExample(
    name="business-days-per-iso-week",
    description=(
        "Sprint capacity: US business days in each ISO week from 30 Nov 2026 to 10 Jan 2027, "
        "labelled with iso_year_week (Christmas and New Year's Day cut W52 and W53 to 4 days)."
    ),
    sql=(
        "SELECT cal.main.iso_year_week(b.date) AS iso_week, count(*) AS business_days, "
        "min(b.date) AS first_day, max(b.date) AS last_day "
        "FROM cal.main.business_days(DATE '2026-11-30', DATE '2027-01-10', country := 'US') AS b "
        "GROUP BY ALL ORDER BY iso_week"
    ),
    attach_to=("iso_year_week", "business_days"),
)

HOLIDAY_COUNTDOWN = ComposedExample(
    name="business-days-to-next-holidays",
    description=(
        "Countdown: the US holidays on or after 13 November 2026, with how many US business "
        "days remain until each (business_days_between counts [start, end))."
    ),
    sql=(
        "SELECT h.date, h.name, "
        "cal.main.business_days_between(DATE '2026-11-13', h.date) AS business_days_away "
        "FROM cal.main.holidays(2026, country := 'US') AS h "
        "WHERE h.date >= DATE '2026-11-13' ORDER BY h.date"
    ),
    attach_to=("holidays", "business_days_between"),
)

EASTER_ANCHORED = ComposedExample(
    name="easter-anchored-holidays",
    description=(
        "Moveable feasts: the German holidays whose offset from easter() is the same in 2025, "
        "2026 and 2027, i.e. the Easter-anchored ones, with that offset in days. Fixed-date "
        "holidays such as Labor Day drop out."
    ),
    sql=(
        "WITH h AS (SELECT date, name FROM cal.main.holidays(2025, country := 'DE') "
        "UNION ALL SELECT date, name FROM cal.main.holidays(2026, country := 'DE') "
        "UNION ALL SELECT date, name FROM cal.main.holidays(2027, country := 'DE')) "
        "SELECT name, min(date - cal.main.easter(year(date))) AS days_from_easter FROM h "
        "GROUP BY name HAVING count(*) = 3 "
        "AND count(DISTINCT date - cal.main.easter(year(date))) = 1 "
        "ORDER BY days_from_easter"
    ),
    attach_to=("easter", "holidays"),
)

US_GB_SHARED_CLOSURES = ComposedExample(
    name="us-gb-shared-closures",
    description=(
        "Cross-border closures: the 2026 dates that are a public holiday in both the US and GB, "
        "with each country's holiday name."
    ),
    sql=(
        "SELECT us.date, us.name AS us_holiday, gb.name AS gb_holiday "
        "FROM cal.main.holidays(2026, country := 'US') AS us "
        "JOIN cal.main.holidays(2026, country := 'GB') AS gb ON us.date = gb.date "
        "ORDER BY us.date"
    ),
    attach_to=("holidays",),
)

# Schema-level order: the distinct-object compositions first, the one-function
# self-join (US_GB_SHARED_CLOSURES) last.
COMPOSED_EXAMPLES: tuple[ComposedExample, ...] = (
    PAYMENT_CALENDAR,
    MONTHLY_CAPACITY,
    US_GB_OPEN_DAYS,
    WEEKLY_CAPACITY,
    HOLIDAY_COUNTDOWN,
    EASTER_ANCHORED,
    US_GB_SHARED_CLOSURES,
)
