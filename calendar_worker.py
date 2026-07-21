# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "vgi-python[http]>=0.16.0",
#     "holidays>=0.50",
#     "python-dateutil>=2.9",
# ]
# ///
"""Repo-root PEP 723 entry point for the vgi-calendar worker.

Thin shim over :mod:`vgi_calendar.worker`, which holds the ``cal`` catalog, the
:class:`~vgi_calendar.worker.CalendarWorker`, and ``main()``. Keeping the catalog
and worker inside the importable ``vgi_calendar`` package means the built wheel
(``vgi-calendar``) contains everything needed to serve, while this script keeps
``uv run calendar_worker.py`` working unchanged for the Makefile,
``ci/run-integration.sh``, the pytest suite, and DuckDB ``ATTACH``.

Usage:
    uv run calendar_worker.py           # serve over stdio (DuckDB subprocess)

    INSTALL vgi FROM community; LOAD vgi;
    ATTACH 'cal' (TYPE vgi, LOCATION 'uv run calendar_worker.py');

    SELECT cal.main.is_holiday(DATE '2026-12-25');            -- per-row scalar (defaults to 'US')
    SELECT * FROM cal.main.holidays(2026, country := 'US', subdiv := 'CA');
    SELECT * FROM cal.main.rrule(TIMESTAMP '2026-01-01', 'FREQ=WEEKLY;COUNT=4');

For stock-exchange trading calendars (sessions, market hours, schedules), see the
companion worker vgi-trading-calendar.
"""

from __future__ import annotations

from vgi_calendar.worker import CalendarWorker, main

__all__ = ["CalendarWorker", "main"]


if __name__ == "__main__":
    main()
