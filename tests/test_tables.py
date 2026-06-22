"""Integration tests for the calendar table functions (in-process harness)."""

from __future__ import annotations

import datetime as dt

import pyarrow as pa

from vgi_calendar.tables import (
    AddBusinessDaysFunction,
    BusinessDaysBetweenFunction,
    BusinessDaysFunction,
    HolidayNameFunction,
    HolidaysFunction,
    IsBusinessDayFunction,
    IsHolidayFunction,
    RruleFunction,
)

from .harness import invoke_table_function


def _date(d: dt.date) -> pa.Scalar:
    return pa.scalar(d, type=pa.date32())


def _ts(d: dt.datetime) -> pa.Scalar:
    return pa.scalar(d, type=pa.timestamp("us"))


class TestIsHoliday:
    def test_christmas_us(self) -> None:
        table = invoke_table_function(
            IsHolidayFunction,
            positional=(_date(dt.date(2026, 12, 25)),),
            named={"country": pa.scalar("US")},
        )
        assert table.column("is_holiday").to_pylist() == [True]

    def test_non_holiday(self) -> None:
        table = invoke_table_function(
            IsHolidayFunction,
            positional=(_date(dt.date(2026, 6, 23)),),
        )
        assert table.column("is_holiday").to_pylist() == [False]

    def test_subdivision(self) -> None:
        table = invoke_table_function(
            IsHolidayFunction,
            positional=(_date(dt.date(2026, 3, 31)),),
            named={"country": pa.scalar("US"), "subdiv": pa.scalar("CA")},
        )
        assert table.column("is_holiday").to_pylist() == [True]


class TestHolidayName:
    def test_name(self) -> None:
        table = invoke_table_function(
            HolidayNameFunction,
            positional=(_date(dt.date(2026, 12, 25)),),
        )
        assert table.column("holiday_name").to_pylist() == ["Christmas Day"]

    def test_null_when_not_holiday(self) -> None:
        table = invoke_table_function(
            HolidayNameFunction,
            positional=(_date(dt.date(2026, 6, 23)),),
        )
        assert table.column("holiday_name").to_pylist() == [None]


class TestIsBusinessDay:
    def test_holiday_is_not_business_day(self) -> None:
        table = invoke_table_function(
            IsBusinessDayFunction,
            positional=(_date(dt.date(2026, 12, 25)),),
        )
        assert table.column("is_business_day").to_pylist() == [False]

    def test_weekday_is_business_day(self) -> None:
        table = invoke_table_function(
            IsBusinessDayFunction,
            positional=(_date(dt.date(2026, 6, 23)),),
        )
        assert table.column("is_business_day").to_pylist() == [True]


class TestAddBusinessDays:
    def test_skips_holiday_and_weekend(self) -> None:
        table = invoke_table_function(
            AddBusinessDaysFunction,
            positional=(_date(dt.date(2026, 12, 24)), pa.scalar(1, type=pa.int32())),
            named={"country": pa.scalar("US")},
        )
        assert table.column("date").to_pylist() == [dt.date(2026, 12, 28)]


class TestBusinessDaysBetween:
    def test_one_week(self) -> None:
        table = invoke_table_function(
            BusinessDaysBetweenFunction,
            positional=(_date(dt.date(2026, 6, 22)), _date(dt.date(2026, 6, 29))),
        )
        assert table.column("business_days").to_pylist() == [5]


class TestHolidaysTable:
    def test_us_2026(self) -> None:
        table = invoke_table_function(
            HolidaysFunction,
            positional=(pa.scalar(2026, type=pa.int32()),),
            named={"country": pa.scalar("US")},
        )
        assert table.num_rows > 0
        assert table.column_names == ["date", "name", "observed"]
        names = table.column("name").to_pylist()
        assert any("Christmas" in n for n in names)
        dates = table.column("date").to_pylist()
        assert dates == sorted(dates)
        assert all(d.year == 2026 for d in dates)

    def test_subdiv_adds_holidays(self) -> None:
        us = invoke_table_function(
            HolidaysFunction,
            positional=(pa.scalar(2026, type=pa.int32()),),
            named={"country": pa.scalar("US")},
        ).num_rows
        ca = invoke_table_function(
            HolidaysFunction,
            positional=(pa.scalar(2026, type=pa.int32()),),
            named={"country": pa.scalar("US"), "subdiv": pa.scalar("CA")},
        ).num_rows
        assert ca >= us


class TestBusinessDaysTable:
    def test_inclusive_range(self) -> None:
        table = invoke_table_function(
            BusinessDaysFunction,
            positional=(_date(dt.date(2026, 6, 22)), _date(dt.date(2026, 6, 26))),
        )
        assert table.column("date").to_pylist() == [
            dt.date(2026, 6, 22),
            dt.date(2026, 6, 23),
            dt.date(2026, 6, 24),
            dt.date(2026, 6, 25),
            dt.date(2026, 6, 26),
        ]


class TestRrule:
    def test_weekly_count(self) -> None:
        table = invoke_table_function(
            RruleFunction,
            positional=(_ts(dt.datetime(2026, 1, 1)), pa.scalar("FREQ=WEEKLY;COUNT=4")),
        )
        assert table.column("seq").to_pylist() == [0, 1, 2, 3]
        assert table.column("occurrence").to_pylist() == [
            dt.datetime(2026, 1, 1),
            dt.datetime(2026, 1, 8),
            dt.datetime(2026, 1, 15),
            dt.datetime(2026, 1, 22),
        ]

    def test_until_named_arg(self) -> None:
        table = invoke_table_function(
            RruleFunction,
            positional=(_ts(dt.datetime(2026, 1, 1)), pa.scalar("FREQ=MONTHLY;BYMONTHDAY=1")),
            named={"until": _ts(dt.datetime(2026, 12, 31))},
        )
        assert table.num_rows == 12

    def test_count_named_arg(self) -> None:
        table = invoke_table_function(
            RruleFunction,
            positional=(_ts(dt.datetime(2026, 1, 1)), pa.scalar("FREQ=DAILY")),
            named={"count": pa.scalar(3, type=pa.int32())},
        )
        assert table.num_rows == 3
