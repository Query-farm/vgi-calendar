"""End-to-end tests for the per-row scalar calendar functions.

These spawn ``calendar_worker.py`` as a subprocess via ``vgi.client.Client`` and
call each scalar exactly as DuckDB would after ``ATTACH``, exercising the arity
overloads (``is_holiday(date)`` / ``(date, country)`` / ``(date, country,
subdiv)`` and the like). The ``date`` column travels in the input batch (a
``Param``); only the constant ``country`` / ``subdiv`` arguments go in
``positional``.
"""

from __future__ import annotations

import datetime as dt
import sys
from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pytest
from vgi import Arguments
from vgi.client import Client

_WORKER = str(Path(__file__).resolve().parent.parent / "calendar_worker.py")


@pytest.fixture(scope="module")
def client() -> Iterator[Client]:
    # Use the current interpreter (deps already installed) and worker_limit=1 so
    # output order matches input order for deterministic per-row assertions.
    with Client(f"{sys.executable} {_WORKER}", worker_limit=1) as c:
        yield c


def _scalar(client: Client, name: str, batch: pa.RecordBatch, *, positional: list[pa.Scalar] | None = None) -> list:
    results = list(
        client.scalar_function(
            function_name=name,
            input=iter([batch]),
            arguments=Arguments(positional=positional or []),
        )
    )
    return results[0]["result"].to_pylist()


def _dates(values: list[dt.date]) -> pa.RecordBatch:
    return pa.RecordBatch.from_pydict({"d": pa.array(values, type=pa.date32())})


class TestIsHoliday:
    def test_default_country(self, client: Client) -> None:
        # Christmas is a holiday; the next day (a Saturday in 2026) is not flagged
        # as a holiday by is_holiday (it only checks the holiday calendar).
        out = _scalar(client, "is_holiday", _dates([dt.date(2026, 12, 25), dt.date(2026, 6, 23)]))
        assert out == [True, False]

    def test_explicit_country(self, client: Client) -> None:
        out = _scalar(
            client,
            "is_holiday",
            _dates([dt.date(2026, 12, 25)]),
            positional=[pa.scalar("GB")],
        )
        assert out == [True]

    def test_country_and_subdiv(self, client: Client) -> None:
        # Cesar Chavez Day (Mar 31) is a California holiday, not US-federal.
        d = _dates([dt.date(2026, 3, 31)])
        assert _scalar(client, "is_holiday", d, positional=[pa.scalar("US")]) == [False]
        assert _scalar(client, "is_holiday", d, positional=[pa.scalar("US"), pa.scalar("CA")]) == [True]


class TestHolidayName:
    def test_default_country(self, client: Client) -> None:
        out = _scalar(client, "holiday_name", _dates([dt.date(2026, 12, 25), dt.date(2026, 6, 23)]))
        assert out == ["Christmas Day", None]


class TestIsBusinessDay:
    def test_default_country(self, client: Client) -> None:
        # Sat 2026-06-20, holiday 2026-12-25, plain Tue 2026-06-23.
        out = _scalar(
            client,
            "is_business_day",
            _dates([dt.date(2026, 6, 20), dt.date(2026, 12, 25), dt.date(2026, 6, 23)]),
        )
        assert out == [False, False, True]


class TestAddBusinessDays:
    def test_two_args(self, client: Client) -> None:
        batch = pa.RecordBatch.from_pydict(
            {
                "d": pa.array([dt.date(2026, 12, 24)], type=pa.date32()),
                "n": pa.array([2], type=pa.int32()),
            }
        )
        out = _scalar(client, "add_business_days", batch)
        # +2 business days from Thu 2026-12-24 skips Christmas + weekend -> Tue 29.
        assert out == [dt.date(2026, 12, 29)]

    def test_three_args_country(self, client: Client) -> None:
        batch = pa.RecordBatch.from_pydict(
            {
                "d": pa.array([dt.date(2026, 6, 22)], type=pa.date32()),
                "n": pa.array([1], type=pa.int32()),
            }
        )
        out = _scalar(client, "add_business_days", batch, positional=[pa.scalar("US")])
        assert out == [dt.date(2026, 6, 23)]

    def test_four_args_subdiv(self, client: Client) -> None:
        # +2 business days from Mon 2026-03-30. In plain US the next two working
        # days are Tue 31 + Wed 1 -> Apr 1; in California Tue 31 is Cesar Chavez
        # Day, so the count skips it -> Apr 2. The subdivision overload must honour
        # the regional holiday the country overload misses.
        batch = pa.RecordBatch.from_pydict(
            {
                "d": pa.array([dt.date(2026, 3, 30)], type=pa.date32()),
                "n": pa.array([2], type=pa.int32()),
            }
        )
        assert _scalar(client, "add_business_days", batch, positional=[pa.scalar("US")]) == [dt.date(2026, 4, 1)]
        assert _scalar(client, "add_business_days", batch, positional=[pa.scalar("US"), pa.scalar("CA")]) == [
            dt.date(2026, 4, 2)
        ]


class TestBusinessDaysBetween:
    def test_two_args(self, client: Client) -> None:
        batch = pa.RecordBatch.from_pydict(
            {
                "s": pa.array([dt.date(2026, 6, 22)], type=pa.date32()),
                "e": pa.array([dt.date(2026, 6, 29)], type=pa.date32()),
            }
        )
        out = _scalar(client, "business_days_between", batch)
        assert out == [5]

    def test_four_args_subdiv(self, client: Client) -> None:
        # March 2026 has 22 US business days; California loses Cesar Chavez Day
        # (Mar 31), so its count is 21. Exercises the country/subdivision overload.
        batch = pa.RecordBatch.from_pydict(
            {
                "s": pa.array([dt.date(2026, 3, 1)], type=pa.date32()),
                "e": pa.array([dt.date(2026, 4, 1)], type=pa.date32()),
            }
        )
        assert _scalar(client, "business_days_between", batch, positional=[pa.scalar("US")]) == [22]
        assert _scalar(client, "business_days_between", batch, positional=[pa.scalar("US"), pa.scalar("CA")]) == [21]
