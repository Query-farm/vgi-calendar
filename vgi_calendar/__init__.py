"""Calendar / holiday / business-day / recurrence math as a VGI worker.

The implementation is split so each concern stays focused:

- ``core``     -- pure ``datetime`` math over the ``holidays`` and ``dateutil``
  libraries; no Arrow or VGI dependency, directly unit-testable.
- ``scalars``  -- positional-only calendar functions as VGI scalar functions
  (``easter``, ``iso_week``, ``iso_year_week``).
- ``tables``   -- everything that wants optional, named ``country`` / ``subdiv``
  arguments, exposed as table functions (VGI scalars cannot take named args).

``calendar_worker.py`` at the repo root assembles these into the ``cal``
catalog and runs the worker over stdio (or HTTP).
"""

from __future__ import annotations

__version__ = "0.1.0"
