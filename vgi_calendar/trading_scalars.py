"""Per-row scalar trading / exchange-calendar functions.

Every function here is a true DuckDB **scalar** -- one value per row in, one out
-- so it works inline in a projection or predicate:

    SELECT is_trading_day(trade_date)            FROM fills;
    SELECT trade_date, market_close(trade_date, 'XLON') FROM fills;

As with the holiday scalars (see :mod:`vgi_calendar.scalars`), scalars take
**positional** arguments and resolve overloads by *arity* -- ``name := value``
is a table-function feature. So the optional ``exchange`` argument is exposed as
a second arity overload that shares the function name; it defaults to ``'XNYS'``
(New York Stock Exchange):

    is_trading_day(date)            -- exchange defaults to 'XNYS'
    is_trading_day(date, exchange)  -- explicit exchange MIC code

Set-returning trading functions (``trading_sessions``, ``trading_schedule``,
``exchanges``) take named arguments and live in
:mod:`vgi_calendar.trading_tables`.
"""

from __future__ import annotations

from typing import Annotated

import pyarrow as pa
from vgi.arguments import ConstParam, Param, Returns
from vgi.metadata import FunctionExample
from vgi.scalar_function import ScalarFunction

from . import trading

_DEFAULT = trading.DEFAULT_EXCHANGE
_TZ_TS = pa.timestamp("us", tz="UTC")
_EXCHANGE_DOC = "Exchange MIC code, e.g. 'XNYS', 'XNAS', 'XLON'. See cal.exchanges()."


# ---------------------------------------------------------------------------
# is_trading_day(date[, exchange]) -> BOOLEAN
# ---------------------------------------------------------------------------


def _is_trading_day_column(date: pa.Date32Array, *, exchange: str) -> pa.BooleanArray:
    out = [None if d is None else trading.is_trading_day(d, exchange) for d in date.to_pylist()]
    return pa.array(out, type=pa.bool_())


class IsTradingDayFunction(ScalarFunction):
    """``is_trading_day(date)`` -- True if the date is an NYSE trading session."""

    class Meta:
        """Function metadata."""

        name = "is_trading_day"
        description = "True if a date is a trading session (exchange defaults to 'XNYS')"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT is_trading_day(DATE '2026-01-01')",
                description="New Year's Day is not an NYSE session",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to test.")],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Compute the result column for each input row."""
        return _is_trading_day_column(date, exchange=_DEFAULT)


class IsTradingDayExchangeFunction(ScalarFunction):
    """``is_trading_day(date, exchange)`` -- True if a session on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "is_trading_day"
        description = "True if a date is a trading session on an exchange"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT is_trading_day(DATE '2026-12-28', 'XLON')",
                description="Is 2026-12-28 a London Stock Exchange session?",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to test.")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC)],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Compute the result column for each input row."""
        return _is_trading_day_column(date, exchange=exchange)


# ---------------------------------------------------------------------------
# next_trading_day(date[, exchange]) -> DATE
# ---------------------------------------------------------------------------


def _next_trading_day_column(date: pa.Date32Array, *, exchange: str) -> pa.Date32Array:
    out = [None if d is None else trading.next_trading_day(d, exchange) for d in date.to_pylist()]
    return pa.array(out, type=pa.date32())


class NextTradingDayFunction(ScalarFunction):
    """``next_trading_day(date)`` -- first session strictly after ``date``."""

    class Meta:
        """Function metadata."""

        name = "next_trading_day"
        description = "First trading session strictly after a date (exchange 'XNYS')"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT next_trading_day(DATE '2026-01-01')",
                description="Next NYSE session after New Year's Day",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Reference date.")],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Compute the result column for each input row."""
        return _next_trading_day_column(date, exchange=_DEFAULT)


class NextTradingDayExchangeFunction(ScalarFunction):
    """``next_trading_day(date, exchange)`` -- next session on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "next_trading_day"
        description = "First trading session strictly after a date on an exchange"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT next_trading_day(DATE '2026-01-01', 'XTKS')",
                description="Next Tokyo session after New Year's Day",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Reference date.")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC)],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Compute the result column for each input row."""
        return _next_trading_day_column(date, exchange=exchange)


# ---------------------------------------------------------------------------
# previous_trading_day(date[, exchange]) -> DATE
# ---------------------------------------------------------------------------


def _previous_trading_day_column(date: pa.Date32Array, *, exchange: str) -> pa.Date32Array:
    out = [None if d is None else trading.previous_trading_day(d, exchange) for d in date.to_pylist()]
    return pa.array(out, type=pa.date32())


class PreviousTradingDayFunction(ScalarFunction):
    """``previous_trading_day(date)`` -- last session strictly before ``date``."""

    class Meta:
        """Function metadata."""

        name = "previous_trading_day"
        description = "Last trading session strictly before a date (exchange 'XNYS')"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT previous_trading_day(DATE '2026-01-01')",
                description="Last NYSE session before New Year's Day",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Reference date.")],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Compute the result column for each input row."""
        return _previous_trading_day_column(date, exchange=_DEFAULT)


class PreviousTradingDayExchangeFunction(ScalarFunction):
    """``previous_trading_day(date, exchange)`` -- previous session on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "previous_trading_day"
        description = "Last trading session strictly before a date on an exchange"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT previous_trading_day(DATE '2026-01-01', 'XLON')",
                description="Last London session before New Year's Day",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Reference date.")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC)],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Compute the result column for each input row."""
        return _previous_trading_day_column(date, exchange=exchange)


# ---------------------------------------------------------------------------
# add_trading_days(date, n[, exchange]) -> DATE
# ---------------------------------------------------------------------------


def _add_trading_days_column(date: pa.Date32Array, n: pa.Int32Array, *, exchange: str) -> pa.Date32Array:
    out = [
        None if d is None or k is None else trading.add_trading_days(d, int(k), exchange)
        for d, k in zip(date.to_pylist(), n.to_pylist(), strict=True)
    ]
    return pa.array(out, type=pa.date32())


class AddTradingDaysFunction(ScalarFunction):
    """``add_trading_days(date, n)`` -- advance by N NYSE sessions."""

    class Meta:
        """Function metadata."""

        name = "add_trading_days"
        description = "Advance a date by N trading sessions, skipping non-sessions (exchange 'XNYS')"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT add_trading_days(DATE '2026-01-02', 5)",
                description="Five NYSE sessions after 2026-01-02",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Starting date.")],
        n: Annotated[pa.Int32Array, Param(doc="Sessions to add (negative goes backwards).")],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Compute the result column for each input row."""
        return _add_trading_days_column(date, n, exchange=_DEFAULT)


class AddTradingDaysExchangeFunction(ScalarFunction):
    """``add_trading_days(date, n, exchange)`` -- advance by N sessions on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "add_trading_days"
        description = "Advance a date by N trading sessions on an exchange"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT add_trading_days(DATE '2026-01-02', 5, 'XLON')",
                description="Five London sessions after 2026-01-02",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Starting date.")],
        n: Annotated[pa.Int32Array, Param(doc="Sessions to add (negative goes backwards).")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC)],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Compute the result column for each input row."""
        return _add_trading_days_column(date, n, exchange=exchange)


# ---------------------------------------------------------------------------
# trading_days_between(start, end[, exchange]) -> INT
# ---------------------------------------------------------------------------


def _trading_days_between_column(start: pa.Date32Array, end: pa.Date32Array, *, exchange: str) -> pa.Int32Array:
    out = [
        None if s is None or e is None else trading.trading_days_between(s, e, exchange)
        for s, e in zip(start.to_pylist(), end.to_pylist(), strict=True)
    ]
    return pa.array(out, type=pa.int32())


class TradingDaysBetweenFunction(ScalarFunction):
    """``trading_days_between(start, end)`` -- count sessions in ``[start, end)``."""

    class Meta:
        """Function metadata."""

        name = "trading_days_between"
        description = "Count trading sessions in [start, end), start inclusive (exchange 'XNYS')"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT trading_days_between(DATE '2026-01-01', DATE '2026-02-01')",
                description="NYSE sessions in January 2026",
            ),
        ]

    @classmethod
    def compute(
        cls,
        start: Annotated[pa.Date32Array, Param(doc="Start date (inclusive).")],
        end: Annotated[pa.Date32Array, Param(doc="End date (exclusive).")],
    ) -> Annotated[pa.Int32Array, Returns()]:
        """Compute the result column for each input row."""
        return _trading_days_between_column(start, end, exchange=_DEFAULT)


class TradingDaysBetweenExchangeFunction(ScalarFunction):
    """``trading_days_between(start, end, exchange)`` -- count on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "trading_days_between"
        description = "Count trading sessions in [start, end) on an exchange (start inclusive)"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT trading_days_between(DATE '2026-01-01', DATE '2026-02-01', 'XLON')",
                description="London sessions in January 2026",
            ),
        ]

    @classmethod
    def compute(
        cls,
        start: Annotated[pa.Date32Array, Param(doc="Start date (inclusive).")],
        end: Annotated[pa.Date32Array, Param(doc="End date (exclusive).")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC)],
    ) -> Annotated[pa.Int32Array, Returns()]:
        """Compute the result column for each input row."""
        return _trading_days_between_column(start, end, exchange=exchange)


# ---------------------------------------------------------------------------
# market_open / market_close(date[, exchange]) -> TIMESTAMPTZ (UTC)
# ---------------------------------------------------------------------------


def _market_open_column(date: pa.Date32Array, *, exchange: str) -> pa.TimestampArray:
    out = [None if d is None else trading.market_open(d, exchange) for d in date.to_pylist()]
    return pa.array(out, type=_TZ_TS)


def _market_close_column(date: pa.Date32Array, *, exchange: str) -> pa.TimestampArray:
    out = [None if d is None else trading.market_close(d, exchange) for d in date.to_pylist()]
    return pa.array(out, type=_TZ_TS)


class MarketOpenFunction(ScalarFunction):
    """``market_open(date)`` -- UTC open instant, or NULL if not a session."""

    class Meta:
        """Function metadata."""

        name = "market_open"
        description = "UTC market-open instant for a date, NULL if not a session (exchange 'XNYS')"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT market_open(DATE '2026-01-02')",
                description="NYSE open on 2026-01-02 (14:30 UTC)",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Session date.")],
    ) -> Annotated[pa.TimestampArray, Returns(arrow_type=_TZ_TS)]:
        """Compute the result column for each input row."""
        return _market_open_column(date, exchange=_DEFAULT)


class MarketOpenExchangeFunction(ScalarFunction):
    """``market_open(date, exchange)`` -- UTC open instant on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "market_open"
        description = "UTC market-open instant for a date on an exchange, NULL if not a session"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT market_open(DATE '2026-01-02', 'XLON')",
                description="London open on 2026-01-02",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Session date.")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC)],
    ) -> Annotated[pa.TimestampArray, Returns(arrow_type=_TZ_TS)]:
        """Compute the result column for each input row."""
        return _market_open_column(date, exchange=exchange)


class MarketCloseFunction(ScalarFunction):
    """``market_close(date)`` -- UTC close instant, or NULL if not a session."""

    class Meta:
        """Function metadata."""

        name = "market_close"
        description = "UTC market-close instant for a date, NULL if not a session (exchange 'XNYS')"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT market_close(DATE '2026-11-27')",
                description="NYSE early close the day after Thanksgiving (18:00 UTC)",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Session date.")],
    ) -> Annotated[pa.TimestampArray, Returns(arrow_type=_TZ_TS)]:
        """Compute the result column for each input row."""
        return _market_close_column(date, exchange=_DEFAULT)


class MarketCloseExchangeFunction(ScalarFunction):
    """``market_close(date, exchange)`` -- UTC close instant on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "market_close"
        description = "UTC market-close instant for a date on an exchange, NULL if not a session"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT market_close(DATE '2026-01-02', 'XLON')",
                description="London close on 2026-01-02",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Session date.")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC)],
    ) -> Annotated[pa.TimestampArray, Returns(arrow_type=_TZ_TS)]:
        """Compute the result column for each input row."""
        return _market_close_column(date, exchange=exchange)


# ---------------------------------------------------------------------------
# is_early_close(date[, exchange]) -> BOOLEAN
# ---------------------------------------------------------------------------


def _is_early_close_column(date: pa.Date32Array, *, exchange: str) -> pa.BooleanArray:
    out = [None if d is None else trading.is_early_close(d, exchange) for d in date.to_pylist()]
    return pa.array(out, type=pa.bool_())


class IsEarlyCloseFunction(ScalarFunction):
    """``is_early_close(date)`` -- True if the session closes early."""

    class Meta:
        """Function metadata."""

        name = "is_early_close"
        description = "True if a date is a session that closes early (exchange 'XNYS')"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT is_early_close(DATE '2026-11-27')",
                description="The day after US Thanksgiving is an early close",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to test.")],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Compute the result column for each input row."""
        return _is_early_close_column(date, exchange=_DEFAULT)


class IsEarlyCloseExchangeFunction(ScalarFunction):
    """``is_early_close(date, exchange)`` -- early-close session on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "is_early_close"
        description = "True if a date is a session that closes early on an exchange"
        categories = ["calendar", "trading"]
        examples = [
            FunctionExample(
                sql="SELECT is_early_close(DATE '2026-12-24', 'XLON')",
                description="Christmas Eve is an early close on the LSE",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Date to test.")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC)],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Compute the result column for each input row."""
        return _is_early_close_column(date, exchange=exchange)


TRADING_SCALAR_FUNCTIONS: list[type] = [
    IsTradingDayFunction,
    IsTradingDayExchangeFunction,
    NextTradingDayFunction,
    NextTradingDayExchangeFunction,
    PreviousTradingDayFunction,
    PreviousTradingDayExchangeFunction,
    AddTradingDaysFunction,
    AddTradingDaysExchangeFunction,
    TradingDaysBetweenFunction,
    TradingDaysBetweenExchangeFunction,
    MarketOpenFunction,
    MarketOpenExchangeFunction,
    MarketCloseFunction,
    MarketCloseExchangeFunction,
    IsEarlyCloseFunction,
    IsEarlyCloseExchangeFunction,
]
