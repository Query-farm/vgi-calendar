"""Set-returning trading / exchange-calendar table functions for DuckDB.

These expand to **many rows**, so they are exposed as **table functions** -- the
form that accepts DuckDB ``name := value`` arguments (``exchange``). The
per-row, single-value trading functions (``is_trading_day``, ``market_open``,
...) are *scalars* and live in :mod:`vgi_calendar.trading_scalars`.

    SELECT * FROM cal.trading_sessions(DATE '2026-01-01', DATE '2026-01-31');
    SELECT * FROM cal.trading_schedule(DATE '2026-11-25', DATE '2026-11-30', exchange := 'XNYS');
    SELECT * FROM cal.exchanges();
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Annotated, ClassVar

import pyarrow as pa
from vgi.arguments import Arg
from vgi.metadata import FunctionExample
from vgi.table_function import (
    BindParams,
    ProcessParams,
    TableCardinality,
    TableFunctionGenerator,
    bind_fixed_schema,
    init_single_worker,
)
from vgi_rpc.rpc import OutputCollector

from . import trading
from .schema_utils import field

_TZ_TS = pa.timestamp("us", tz="UTC")
_EXCHANGE = Arg[str](
    "exchange",
    default=trading.DEFAULT_EXCHANGE,
    doc="Exchange MIC code (e.g. 'XNYS', 'XLON'). See cal.exchanges().",
)


# ---------------------------------------------------------------------------
# trading_sessions(start, end, exchange := 'XNYS') -> (date)
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class _TradingSessionsArgs:
    """``trading_sessions(start, end, exchange := ...)``."""

    start: Annotated[_dt.date, Arg(0, arrow_type=pa.date32(), doc="Range start (inclusive).")]
    end: Annotated[_dt.date, Arg(1, arrow_type=pa.date32(), doc="Range end (inclusive).")]
    exchange: Annotated[str, _EXCHANGE]


_TRADING_SESSIONS_SCHEMA = pa.schema(
    [field("date", pa.date32(), "A trading session in the range.", nullable=False)]
)


@init_single_worker
@bind_fixed_schema
class TradingSessionsFunction(TableFunctionGenerator[_TradingSessionsArgs]):
    """Every trading session in an inclusive ``[start, end]`` range, one per row."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _TRADING_SESSIONS_SCHEMA

    class Meta:
        name = "trading_sessions"
        description = "Every trading session in an inclusive [start, end] range"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT * FROM cal.trading_sessions(DATE '2026-01-01', DATE '2026-01-31')",
                description="NYSE sessions in January 2026",
            ),
            FunctionExample(
                sql=(
                    "SELECT * FROM cal.trading_sessions(DATE '2026-01-01', DATE '2026-01-31', "
                    "exchange := 'XLON')"
                ),
                description="London sessions in January 2026",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_TradingSessionsArgs]) -> TableCardinality:
        return TableCardinality(estimate=None, max=None)

    @classmethod
    def process(cls, params: ProcessParams[_TradingSessionsArgs], state: None, out: OutputCollector) -> None:
        a = params.args
        days = trading.trading_sessions_in_range(a.start, a.end, a.exchange)
        out.emit(pa.RecordBatch.from_pydict({"date": days}, schema=params.output_schema))
        out.finish()


# ---------------------------------------------------------------------------
# trading_schedule(start, end, exchange := 'XNYS')
#   -> (session, market_open, market_close, is_early_close)
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class _TradingScheduleArgs:
    """``trading_schedule(start, end, exchange := ...)``."""

    start: Annotated[_dt.date, Arg(0, arrow_type=pa.date32(), doc="Range start (inclusive).")]
    end: Annotated[_dt.date, Arg(1, arrow_type=pa.date32(), doc="Range end (inclusive).")]
    exchange: Annotated[str, _EXCHANGE]


_TRADING_SCHEDULE_SCHEMA = pa.schema(
    [
        field("session", pa.date32(), "Trading session date.", nullable=False),
        field("market_open", _TZ_TS, "UTC market-open instant.", nullable=False),
        field("market_close", _TZ_TS, "UTC market-close instant.", nullable=False),
        field("is_early_close", pa.bool_(), "True if the session closes early.", nullable=False),
    ]
)


@init_single_worker
@bind_fixed_schema
class TradingScheduleFunction(TableFunctionGenerator[_TradingScheduleArgs]):
    """Per-session open / close / early-close schedule over ``[start, end]``."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _TRADING_SCHEDULE_SCHEMA

    class Meta:
        name = "trading_schedule"
        description = "Per-session open/close/early-close schedule for a date range"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT * FROM cal.trading_schedule(DATE '2026-11-25', DATE '2026-11-30')",
                description="NYSE schedule around Thanksgiving (note the early close)",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_TradingScheduleArgs]) -> TableCardinality:
        return TableCardinality(estimate=None, max=None)

    @classmethod
    def process(cls, params: ProcessParams[_TradingScheduleArgs], state: None, out: OutputCollector) -> None:
        a = params.args
        rows = trading.trading_schedule(a.start, a.end, a.exchange)
        out.emit(
            pa.RecordBatch.from_pydict(
                {
                    "session": [r[0] for r in rows],
                    "market_open": [r[1] for r in rows],
                    "market_close": [r[2] for r in rows],
                    "is_early_close": [r[3] for r in rows],
                },
                schema=params.output_schema,
            )
        )
        out.finish()


# ---------------------------------------------------------------------------
# exchanges() -> (code)
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class _NoArgs:
    """``exchanges()`` takes no arguments."""


_EXCHANGES_SCHEMA = pa.schema(
    [field("code", pa.string(), "Exchange MIC code (e.g. 'XNYS').", nullable=False)]
)


@init_single_worker
@bind_fixed_schema
class ExchangesFunction(TableFunctionGenerator[_NoArgs]):
    """Every supported exchange MIC code, one per row."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _EXCHANGES_SCHEMA

    class Meta:
        name = "exchanges"
        description = "List every supported exchange calendar MIC code"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT * FROM cal.exchanges() ORDER BY code",
                description="All supported exchange codes",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_NoArgs]) -> TableCardinality:
        return TableCardinality(estimate=120, max=1000)

    @classmethod
    def process(cls, params: ProcessParams[_NoArgs], state: None, out: OutputCollector) -> None:
        out.emit(pa.RecordBatch.from_pydict({"code": trading.list_exchanges()}, schema=params.output_schema))
        out.finish()


TRADING_TABLE_FUNCTIONS: list[type] = [
    TradingSessionsFunction,
    TradingScheduleFunction,
    ExchangesFunction,
]
