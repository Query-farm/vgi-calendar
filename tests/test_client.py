"""End-to-end tests driving the worker over the real VGI client/RPC stack.

These spawn ``calendar_worker.py`` as a subprocess via ``vgi.client.Client`` and
exercise the wire protocol, exactly as DuckDB would after ``ATTACH``. They are
slower than the in-process harness tests, so we keep coverage here to one
representative scalar and one table function.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pyarrow as pa
import pytest
from vgi import Arguments
from vgi.client import Client

_WORKER = str(Path(__file__).resolve().parent.parent / "calendar_worker.py")


@pytest.fixture(scope="module")
def client() -> Client:
    with Client(f"uv run {_WORKER}") as c:
        yield c


def test_easter_scalar(client: Client) -> None:
    batch = pa.RecordBatch.from_pydict({"year": pa.array([2026, 2027], type=pa.int32())})
    results = list(
        client.scalar_function(
            function_name="easter",
            input=iter([batch]),
            arguments=Arguments(positional=()),
        )
    )
    assert results[0]["result"].to_pylist() == [dt.date(2026, 4, 5), dt.date(2027, 3, 28)]


def test_iso_year_week_scalar(client: Client) -> None:
    batch = pa.RecordBatch.from_pydict({"d": pa.array([dt.date(2026, 6, 22)], type=pa.date32())})
    results = list(
        client.scalar_function(
            function_name="iso_year_week",
            input=iter([batch]),
            arguments=Arguments(positional=()),
        )
    )
    assert results[0]["result"].to_pylist() == ["2026-W26"]


def test_holidays_table_function(client: Client) -> None:
    results = list(
        client.table_function(
            function_name="holidays",
            arguments=Arguments(
                positional=(pa.scalar(2026, type=pa.int32()),),
                named={"country": pa.scalar("US")},
            ),
        )
    )
    table = pa.Table.from_batches(results)
    names = table.column("name").to_pylist()
    assert any("Christmas" in n for n in names)
    assert table.num_rows > 0
