"""Trading strategy adapter — bridges shared strategies into the trading bot.

Converts live ``list[Tick]`` to :class:`MarketSnapshot`, evaluates strategies
via the shared registry, and populates all executor-required fields on the
returned :class:`Signal` objects.  Exports :func:`evaluate_strategies` with
the same ``async (market, ticks) -> list[Signal]`` signature as the function
it replaces in ``trading/strategies.py``.

**Relationship to trading/strategies.py:**
``trading/strategies.py`` remains in place (D007) and contains the pure
helper functions :func:`calculate_dynamic_bet_size` and
:func:`calculate_shares` which this module imports.  The hardcoded M3/M4
evaluation functions in ``strategies.py`` are superseded by the shared
strategy framework — the main loop simply imports ``evaluate_strategies``
from here instead.

**Composition pattern (D008):**
Same as ``analysis/backtest_strategies.py`` — composes ``shared.strategies``
with existing infrastructure (``trading.balance``, ``trading.db``,
``trading.constants``) without modifying either side.

Usage::

    from trading.strategy_adapter import evaluate_strategies
    signals = await evaluate_strategies(market, ticks)
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from shared.strategies import MarketSnapshot, Signal, discover_strategies, get_strategy
from trading.balance import get_usdc_balance
from trading.constants import BET_SIZING
from trading.db import MarketInfo, Tick, already_traded_this_market
from trading.strategies import calculate_dynamic_bet_size, calculate_shares
from trading.utils import debug_log, log


# ── Tick-to-snapshot conversion ─────────────────────────────────────


def ticks_to_snapshot(market: MarketInfo, ticks: list[Tick]) -> MarketSnapshot:
    """Convert live ticks to a :class:`MarketSnapshot`.

    In live context, ``elapsed_seconds`` reflects real elapsed time since
    market start — *not* ``total_seconds``.  This is the key difference from
    the backtest adapter in S02, where ``elapsed_seconds == total_seconds``
    because the full price series is available.

    ``prices`` is a numpy array indexed by elapsed second, with ``NaN`` for
    seconds without tick data.  Multiple ticks in the same second use
    last-write-wins.
    """
    total_seconds = int((market.ended_at - market.started_at).total_seconds())
    elapsed_seconds = (datetime.now(timezone.utc) - market.started_at).total_seconds()

    prices = np.full(total_seconds, np.nan)
    for tick in ticks:
        second = int((tick.time - market.started_at).total_seconds())
        if 0 <= second < total_seconds:
            prices[second] = tick.up_price  # last-write-wins for same second

    return MarketSnapshot(
        market_id=market.market_id,
        market_type=market.market_type,
        prices=prices,
        total_seconds=total_seconds,
        elapsed_seconds=elapsed_seconds,
        metadata={"started_at": market.started_at},
    )


# ── Execution field population ──────────────────────────────────────


def _populate_execution_fields(
    signal: Signal,
    market: MarketInfo,
    snapshot: MarketSnapshot,
    balance: float,
) -> Signal | None:
    """Fill executor-required ``locked_*`` and ``signal_data`` keys.

    Returns the mutated *signal* on success, or *None* if the trade is too
    large relative to the current balance.
    """
    bet_size = calculate_dynamic_bet_size(balance)
    shares = calculate_shares(signal.entry_price, bet_size)
    actual_cost = shares * signal.entry_price

    # Risk guard: don't risk more than max_single_trade_pct of balance
    if actual_cost > balance * BET_SIZING["max_single_trade_pct"]:
        debug_log.info(
            "[ADAPTER] Bet too large for %s: $%.2f > %.0f%% of $%.2f",
            signal.strategy_name,
            actual_cost,
            BET_SIZING["max_single_trade_pct"] * 100,
            balance,
        )
        return None

    # Locked fields (calculated at signal time, never recalculated)
    signal.locked_shares = shares
    signal.locked_cost = round(actual_cost, 4)
    signal.locked_balance = round(balance, 2)
    signal.locked_bet_size = round(bet_size, 2)

    # Build profitability thesis from signal_data context
    thesis_parts = [
        f"Strategy {signal.strategy_name} detected {signal.direction} opportunity",
    ]
    if "spike_direction" in signal.signal_data:
        thesis_parts.append(
            f"(spike: {signal.signal_data['spike_direction']})"
        )
    if "reversion_second" in signal.signal_data:
        thesis_parts.append(
            f"at second {signal.signal_data['reversion_second']}"
        )
    thesis_parts.append(
        f"— entry ${signal.entry_price:.4f}, "
        f"cost ${actual_cost:.2f}, "
        f"{round(snapshot.total_seconds - snapshot.elapsed_seconds, 0):.0f}s remaining"
    )
    profitability_thesis = " ".join(thesis_parts)

    # Merge execution keys into signal_data
    signal.signal_data.update(
        {
            "bet_cost": round(actual_cost, 4),
            "shares": shares,
            "actual_cost": round(actual_cost, 2),
            "price_min": 0.01,
            "price_max": 0.99,
            "stop_loss_price": None,
            "profitability_thesis": profitability_thesis,
            "balance_at_signal": round(balance, 2),
            "current_balance": round(balance, 2),
            "bet_size": round(bet_size, 2),
            "seconds_elapsed": round(snapshot.elapsed_seconds, 1),
            "seconds_remaining": round(
                snapshot.total_seconds - snapshot.elapsed_seconds, 1
            ),
        }
    )

    return signal


# ── Main entry point ────────────────────────────────────────────────


async def evaluate_strategies(
    market: MarketInfo, ticks: list[Tick]
) -> list[Signal]:
    """Evaluate all shared strategies against a live market.

    Drop-in replacement for ``trading.strategies.evaluate_strategies`` with
    the same async signature.  Converts ticks to :class:`MarketSnapshot`,
    runs each discovered strategy synchronously (D001), populates executor-
    required fields, and returns the list of actionable signals.

    Guards:
    - Empty ticks (< 2) → ``[]``
    - Balance fetch failure (≤ 0) → ``[]`` with warning
    - Already-traded check per strategy → skip
    - Bet-too-large check → skip with debug log
    - Strategy evaluation exception → catch, log, continue
    """
    if len(ticks) < 2:
        debug_log.info(
            "[ADAPTER] %s — skipping: not enough ticks (%d < 2)",
            market.market_id[:16],
            len(ticks),
        )
        return []

    snapshot = ticks_to_snapshot(market, ticks)

    balance = await get_usdc_balance()
    if balance <= 0:
        log.warning(
            "[ADAPTER] Could not fetch balance for %s (got %.2f), skipping",
            market.market_id[:16],
            balance,
        )
        return []

    signals: list[Signal] = []
    strategy_classes = discover_strategies()

    for strategy_id, strategy_cls in strategy_classes.items():
        try:
            strategy = get_strategy(strategy_id)
        except Exception as exc:
            debug_log.info(
                "[ADAPTER] Failed to instantiate strategy %s: %s",
                strategy_id,
                exc,
            )
            continue

        # Already-traded guard (async DB check)
        try:
            if await already_traded_this_market(
                market.market_id, strategy.config.strategy_name
            ):
                debug_log.info(
                    "[ADAPTER] %s — already traded with %s, skipping",
                    market.market_id[:16],
                    strategy.config.strategy_name,
                )
                continue
        except Exception as exc:
            debug_log.info(
                "[ADAPTER] already_traded check failed for %s/%s: %s",
                market.market_id[:16],
                strategy.config.strategy_name,
                exc,
            )
            continue

        # Synchronous evaluation (D001)
        try:
            signal = strategy.evaluate(snapshot)
        except Exception as exc:
            debug_log.info(
                "[ADAPTER] Strategy %s raised during evaluate: %s",
                strategy_id,
                exc,
            )
            continue

        if signal is None:
            continue

        # Populate executor-required fields
        populated = _populate_execution_fields(signal, market, snapshot, balance)
        if populated is None:
            continue

        signals.append(populated)

    # Log signal count per market (matching existing M3/M4 log pattern)
    if signals:
        log.info(
            "[ADAPTER] %d signal(s) for %s: %s",
            len(signals),
            market.market_id[:16],
            [s.strategy_name for s in signals],
        )
    else:
        debug_log.info(
            "[ADAPTER] No signals for %s (%d strategies evaluated)",
            market.market_id[:16],
            len(strategy_classes),
        )

    return signals
