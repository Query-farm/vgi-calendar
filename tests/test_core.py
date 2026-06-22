"""Unit tests for the pure calendar math in ``vgi_calendar.core``."""

from __future__ import annotations

import datetime as dt

import pytest

from vgi_calendar import core


class TestHolidays:
    def test_christmas_is_us_holiday(self) -> None:
        assert core.is_holiday(dt.date(2026, 12, 25), "US") is True

    def test_random_weekday_is_not_holiday(self) -> None:
        assert core.is_holiday(dt.date(2026, 6, 23), "US") is False

    def test_holiday_name(self) -> None:
        assert core.holiday_name(dt.date(2026, 12, 25), "US") == "Christmas Day"

    def test_holiday_name_none_when_not_holiday(self) -> None:
        assert core.holiday_name(dt.date(2026, 6, 23), "US") is None

    def test_subdivision_specific_holiday(self) -> None:
        # Cesar Chavez Day (Mar 31) is a California holiday, not a US-federal one.
        d = dt.date(2026, 3, 31)
        assert core.is_holiday(d, "US") is False
        assert core.is_holiday(d, "US", "CA") is True

    def test_country_case_insensitive(self) -> None:
        assert core.is_holiday(dt.date(2026, 12, 25), "us") is True

    def test_holidays_in_year_sorted_nonempty(self) -> None:
        rows = core.holidays_in_year(2026, "US")
        assert len(rows) > 0
        dates = [r[0] for r in rows]
        assert dates == sorted(dates)
        assert all(d.year == 2026 for d in dates)
        names = {r[1] for r in rows}
        assert any("Christmas" in n for n in names)


class TestBusinessDays:
    def test_weekend_is_not_business_day(self) -> None:
        # 2026-06-20 is a Saturday.
        assert core.is_business_day(dt.date(2026, 6, 20), "US") is False

    def test_holiday_is_not_business_day(self) -> None:
        assert core.is_business_day(dt.date(2026, 12, 25), "US") is False

    def test_plain_weekday_is_business_day(self) -> None:
        # 2026-06-23 is a Tuesday, not a holiday.
        assert core.is_business_day(dt.date(2026, 6, 23), "US") is True

    def test_add_business_days_skips_holiday_and_weekend(self) -> None:
        # 2026-12-24 (Thu). +1 -> skip Christmas (Fri 25) + weekend -> Mon 28.
        assert core.add_business_days(dt.date(2026, 12, 24), 1, "US") == dt.date(2026, 12, 28)

    def test_add_business_days_zero_is_identity(self) -> None:
        d = dt.date(2026, 12, 25)  # a holiday
        assert core.add_business_days(d, 0, "US") == d

    def test_add_business_days_negative(self) -> None:
        # 2026-12-28 (Mon). -1 business day -> 2026-12-24 (Thu, skipping Christmas + weekend).
        assert core.add_business_days(dt.date(2026, 12, 28), -1, "US") == dt.date(2026, 12, 24)

    def test_business_days_between_same_day_is_zero(self) -> None:
        d = dt.date(2026, 6, 23)
        assert core.business_days_between(d, d, "US") == 0

    def test_business_days_between_one_week(self) -> None:
        # Mon 2026-06-22 .. Mon 2026-06-29 (exclusive) = 5 business days.
        assert core.business_days_between(dt.date(2026, 6, 22), dt.date(2026, 6, 29), "US") == 5

    def test_business_days_between_reversed_is_negative(self) -> None:
        a = core.business_days_between(dt.date(2026, 6, 22), dt.date(2026, 6, 29), "US")
        b = core.business_days_between(dt.date(2026, 6, 29), dt.date(2026, 6, 22), "US")
        assert b == -a

    def test_business_days_in_range_inclusive(self) -> None:
        days = core.business_days_in_range(dt.date(2026, 6, 22), dt.date(2026, 6, 26), "US")
        # Mon..Fri, no holidays that week.
        assert days == [
            dt.date(2026, 6, 22),
            dt.date(2026, 6, 23),
            dt.date(2026, 6, 24),
            dt.date(2026, 6, 25),
            dt.date(2026, 6, 26),
        ]

    def test_business_days_in_range_empty_when_reversed(self) -> None:
        assert core.business_days_in_range(dt.date(2026, 6, 26), dt.date(2026, 6, 22), "US") == []


class TestCalendarMath:
    def test_easter_2026(self) -> None:
        assert core.easter(2026) == dt.date(2026, 4, 5)

    def test_iso_week(self) -> None:
        assert core.iso_week(dt.date(2026, 6, 22)) == 26

    def test_iso_year_week_format(self) -> None:
        assert core.iso_year_week(dt.date(2026, 6, 22)) == "2026-W26"

    def test_iso_year_week_crosses_year_boundary(self) -> None:
        # 2026-12-31 is ISO week 53 of ISO-year 2026.
        assert core.iso_year_week(dt.date(2026, 12, 31)) == "2026-W53"


class TestRrule:
    def test_weekly_count(self) -> None:
        occ = core.expand_rrule(dt.datetime(2026, 1, 1), "FREQ=WEEKLY;COUNT=4")
        assert occ == [
            dt.datetime(2026, 1, 1),
            dt.datetime(2026, 1, 8),
            dt.datetime(2026, 1, 15),
            dt.datetime(2026, 1, 22),
        ]

    def test_full_rrule_prefix(self) -> None:
        occ = core.expand_rrule(dt.datetime(2026, 1, 1), "RRULE:FREQ=DAILY;COUNT=3")
        assert len(occ) == 3

    def test_count_argument_bounds(self) -> None:
        occ = core.expand_rrule(dt.datetime(2026, 1, 1), "FREQ=DAILY", count=5)
        assert len(occ) == 5

    def test_until_argument_bounds(self) -> None:
        occ = core.expand_rrule(
            dt.datetime(2026, 1, 1),
            "FREQ=MONTHLY;BYMONTHDAY=1",
            until=dt.datetime(2026, 12, 31),
        )
        assert len(occ) == 12
        assert occ[0] == dt.datetime(2026, 1, 1)
        assert occ[-1] == dt.datetime(2026, 12, 1)

    def test_unbounded_rule_respects_hard_cap(self) -> None:
        occ = core.expand_rrule(dt.datetime(2026, 1, 1), "FREQ=DAILY", hard_cap=10)
        assert len(occ) == 10

    def test_malformed_freq_raises(self) -> None:
        with pytest.raises(ValueError):
            core.expand_rrule(dt.datetime(2026, 1, 1), "FREQ=BOGUS;COUNT=2")

    def test_garbage_rule_string_raises(self) -> None:
        with pytest.raises(ValueError):
            core.expand_rrule(dt.datetime(2026, 1, 1), "this is not a rule")

    def test_count_one_returns_single(self) -> None:
        assert core.expand_rrule(dt.datetime(2026, 1, 1), "FREQ=DAILY", count=1) == [dt.datetime(2026, 1, 1)]

    def test_until_before_dtstart_is_empty(self) -> None:
        occ = core.expand_rrule(
            dt.datetime(2026, 6, 1),
            "FREQ=DAILY",
            until=dt.datetime(2026, 1, 1),
        )
        assert occ == []


class TestErrorAndEdgeCases:
    def test_unknown_country_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            core.is_holiday(dt.date(2026, 1, 1), "ZZ")

    def test_unknown_country_in_holidays_in_year_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            core.holidays_in_year(2026, "ZZ")

    def test_unknown_subdivision_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            core.is_holiday(dt.date(2026, 1, 1), "US", "ZZ")

    def test_leap_year_feb_29_is_valid_business_day(self) -> None:
        # 2024-02-29 is a Thursday and not a US holiday -> a business day.
        d = dt.date(2024, 2, 29)
        assert d.weekday() == 3
        assert core.is_business_day(d, "US") is True

    def test_business_days_between_start_after_end_is_negative(self) -> None:
        fwd = core.business_days_between(dt.date(2026, 6, 22), dt.date(2026, 6, 29), "US")
        rev = core.business_days_between(dt.date(2026, 6, 29), dt.date(2026, 6, 22), "US")
        assert fwd == 5
        assert rev == -5

    def test_business_days_in_range_empty_range_same_day(self) -> None:
        # A single-day inclusive range over a weekend yields nothing.
        sat = dt.date(2026, 6, 20)
        assert core.business_days_in_range(sat, sat, "US") == []

    def test_add_business_days_across_year_boundary(self) -> None:
        # Wed 2025-12-31 +1 business day -> skip New Year's Day (Thu 2026-01-01)
        # -> Fri 2026-01-02.
        result = core.add_business_days(dt.date(2025, 12, 31), 1, "US")
        assert result == dt.date(2026, 1, 2)

    def test_iso_year_week_year_boundary(self) -> None:
        # 2021-01-01 is ISO week 53 of ISO-year *2020*.
        assert core.iso_year_week(dt.date(2021, 1, 1)) == "2020-W53"

    def test_easter_leap_year(self) -> None:
        assert core.easter(2024) == dt.date(2024, 3, 31)
