"""Integration tests for the calendar set-returning table functions.

Drives ``holidays``, ``business_days`` and ``rrule`` through the real
bind -> init -> process lifecycle in-process (no worker subprocess). The
single-value, per-row functions are *scalars* now and are covered in
``test_scalars.py``.
"""

from __future__ import annotations

import datetime as dt

import pyarrow as pa
import pytest

from vgi_calendar.tables import (
    BusinessDaysFunction,
    HolidaysFunction,
    RruleFunction,
)

from .harness import invoke_table_function


def _date(d: dt.date) -> pa.Scalar:
    return pa.scalar(d, type=pa.date32())


def _ts(d: dt.datetime) -> pa.Scalar:
    return pa.scalar(d, type=pa.timestamp("us"))


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

    def test_observed_shift_flagged(self) -> None:
        # 2027-12-25 (Christmas) falls on a Saturday; the US calendar observes it
        # on Friday 2027-12-24 and flags that row observed=True.
        table = invoke_table_function(
            HolidaysFunction,
            positional=(pa.scalar(2027, type=pa.int32()),),
            named={"country": pa.scalar("US")},
        )
        observed_flags = table.column("observed").to_pylist()
        assert any(observed_flags), "expected at least one observed-shift row in 2027"

    def test_other_country(self) -> None:
        table = invoke_table_function(
            HolidaysFunction,
            positional=(pa.scalar(2026, type=pa.int32()),),
            named={"country": pa.scalar("GB")},
        )
        assert table.num_rows > 0
        assert all(d.year == 2026 for d in table.column("date").to_pylist())


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

    def test_reversed_range_is_empty(self) -> None:
        table = invoke_table_function(
            BusinessDaysFunction,
            positional=(_date(dt.date(2026, 6, 26)), _date(dt.date(2026, 6, 22))),
        )
        assert table.num_rows == 0


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

    def test_malformed_rule_raises(self) -> None:
        with pytest.raises(ValueError):
            invoke_table_function(
                RruleFunction,
                positional=(_ts(dt.datetime(2026, 1, 1)), pa.scalar("FREQ=BOGUS;COUNT=2")),
            )
