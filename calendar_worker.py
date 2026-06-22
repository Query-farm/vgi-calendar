# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "vgi-python",
#     "holidays>=0.50",
#     "python-dateutil>=2.9",
# ]
#
# [tool.uv.sources]
# vgi-python = { path = "../vgi-python" }
# ///
"""VGI worker exposing calendar / holiday / business-day / recurrence math to SQL.

Assembles the calendar functions in ``vgi_calendar`` into a single ``cal``
catalog and runs the worker over stdio (DuckDB subprocess) or HTTP.

Usage:
    uv run calendar_worker.py           # serve over stdio (DuckDB subprocess)

    INSTALL vgi FROM community; LOAD vgi;
    ATTACH 'cal' (TYPE vgi, LOCATION 'uv run calendar_worker.py');

    SELECT cal.is_holiday(DATE '2026-12-25');            -- per-row scalar (defaults to 'US')
    SELECT cal.is_holiday(DATE '2026-03-31', 'US', 'CA');
    SELECT * FROM cal.holidays(2026, country := 'US', subdiv := 'CA');
    SELECT cal.iso_year_week(DATE '2026-06-22');
    SELECT * FROM cal.rrule(TIMESTAMP '2026-01-01', 'FREQ=WEEKLY;COUNT=4');
"""

from __future__ import annotations

from vgi import Worker
from vgi.catalog import Catalog, Schema

from vgi_calendar.scalars import SCALAR_FUNCTIONS
from vgi_calendar.tables import TABLE_FUNCTIONS

_FUNCTIONS: list[type] = [*SCALAR_FUNCTIONS, *TABLE_FUNCTIONS]

_CALENDAR_CATALOG = Catalog(
    name="cal",
    default_schema="main",
    schemas=[
        Schema(
            name="main",
            comment="Holiday, business-day, and recurrence calendar math for SQL",
            functions=list(_FUNCTIONS),
        ),
    ],
)


class CalendarWorker(Worker):
    """Worker process hosting the ``cal`` calendar catalog."""

    catalog = _CALENDAR_CATALOG


def main() -> None:
    """Run the calendar worker process (stdio or, via flags, HTTP)."""
    CalendarWorker.main()


if __name__ == "__main__":
    main()
