"""Trading strategy adapter for shared live strategies.

Converts live ``list[Tick]`` values into :class:`MarketSnapshot`, attaches
live crypto feature series when required, evaluates shared strategies, and
populates the execution fields expected by the trading bot.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from shared import db as shared_db
from shared.config import BINANCE_CONFIG
from shared.crypto_features import (
    SUPPORTED_LIVE_FEATURE_COLUMNS,
    build_live_feature_series,
    latest_bar_is_fresh,
)
from shared.strategies import MarketSnapshot, Signal
from trading.balance import get_usdc_balance
from trading.constants import BET_SIZING
from trading.db import MarketInfo, Tick, already_traded_this_market
from trading.live_profile import get_live_strategies
from trading.strategies import calculate_dynamic_bet_size, calculate_shares
from trading.utils import debug_log, log


def ticks_to_snapshot(market: MarketInfo, ticks: list[Tick]) -> MarketSnapshot:
    """Convert live ticks to a :class:`MarketSnapshot`."""
    total_seconds = int((market.ended_at - market.started_at).total_seconds())
    elapsed_seconds = (datetime.now(timezone.utc) - market.started_at).total_seconds()
    current_second = max(0, min(total_seconds - 1, int(elapsed_seconds)))
    prices = np.full(current_second + 1, np.nan)
    for tick in ticks:
        second = int((tick.time - market.started_at).total_seconds())
        if 0 <= second <= current_second:
            prices[second] = tick.up_price

    parts = market.market_type.split("_")
    asset = parts[0] if parts else ""
    duration_minutes = 0
    if len(parts) >= 2 and parts[1].endswith("m"):
        try:
            duration_minutes = int(parts[1].replace("m", ""))
        except ValueError:
            duration_minutes = 0

    return MarketSnapshot(
        market_id=market.market_id,
        market_type=market.market_type,
        prices=prices,
        total_seconds=total_seconds,
        elapsed_seconds=current_second,
        metadata={
            "asset": asset,
            "hour": market.started_at.hour,
            "started_at": market.started_at,
            "duration_minutes": duration_minutes,
        },
    )


async def _attach_live_feature_series(
    market: MarketInfo,
    snapshot: MarketSnapshot,
    strategies,
) -> str | None:
    """Attach DB-backed live crypto features when any strategy requires them."""
    required_columns = {
        column
        for strategy in strategies
        for column in strategy.required_feature_columns()
    }
    if not required_columns:
        return None

    unsupported = sorted(required_columns - SUPPORTED_LIVE_FEATURE_COLUMNS)
    if unsupported:
        return f"unsupported feature columns: {', '.join(unsupported)}"

    asset = str(snapshot.metadata.get("asset", "")).upper()
    if not asset:
        return "missing market asset"

    symbol = f"{asset}USDT"
    tracked_symbols = {
        tracked_symbol.upper()
        for tracked_symbol in BINANCE_CONFIG["tracked_symbols"]
    }
    if symbol not in tracked_symbols:
        return f"unsupported crypto symbol {symbol}"

    stale_threshold = BINANCE_CONFIG["stale_data_threshold_seconds"]
    latest_bar_time = await shared_db.get_latest_crypto_bar_time(symbol)
    if not latest_bar_is_fresh(
        latest_bar_time,
        threshold_seconds=stale_threshold,
    ):
        return f"stale crypto data for {symbol}"

    if len(snapshot.prices) == 0:
        return "empty price history"

    end_time = market.started_at + timedelta(seconds=len(snapshot.prices) - 1)
    crypto_rows = await shared_db.fetch_crypto_price_bars(
        symbol,
        market.started_at,
        end_time,
    )
    if not crypto_rows:
        return f"missing crypto bars for {symbol}"

    snapshot.feature_series = build_live_feature_series(
        prices=snapshot.prices,
        crypto_rows=crypto_rows,
        started_at=market.started_at,
    )
    return None


def _populate_execution_fields(
    signal: Signal,
    market: MarketInfo,
    snapshot: MarketSnapshot,
    balance: float,
) -> Signal | None:
    """Fill executor-required ``locked_*`` and ``signal_data`` fields."""
    bet_size = calculate_dynamic_bet_size(balance)
    shares = calculate_shares(signal.entry_price, bet_size)
    actual_cost = shares * signal.entry_price

    if actual_cost > balance * BET_SIZING["max_single_trade_pct"]:
        debug_log.info(
            "[ADAPTER] Bet too large for %s: $%.2f > %.0f%% of $%.2f",
            signal.strategy_name,
            actual_cost,
            BET_SIZING["max_single_trade_pct"] * 100,
            balance,
        )
        return None

    signal.locked_shares = shares
    signal.locked_cost = round(actual_cost, 4)
    signal.locked_balance = round(balance, 2)
    signal.locked_bet_size = round(bet_size, 2)

    thesis_parts = [
        f"Strategy {signal.strategy_name} detected {signal.direction} opportunity",
    ]
    if "spike_direction" in signal.signal_data:
        thesis_parts.append(f"(spike: {signal.signal_data['spike_direction']})")
    if "reversion_second" in signal.signal_data:
        thesis_parts.append(f"at second {signal.signal_data['reversion_second']}")
    thesis_parts.append(
        f"- entry ${signal.entry_price:.4f}, "
        f"cost ${actual_cost:.2f}, "
        f"{round(snapshot.total_seconds - snapshot.elapsed_seconds, 0):.0f}s remaining"
    )
    profitability_thesis = " ".join(thesis_parts)

    signal.signal_data.update(
        {
            "bet_cost": round(actual_cost, 4),
            "shares": shares,
            "actual_cost": round(actual_cost, 2),
            "price_min": 0.01,
            "price_max": 0.99,
            "stop_loss_price": signal.signal_data.get("stop_loss_price"),
            "take_profit_price": signal.signal_data.get("take_profit_price"),
            "profitability_thesis": profitability_thesis,
            "balance_at_signal": round(balance, 2),
            "current_balance": round(balance, 2),
            "bet_size": round(bet_size, 2),
            "seconds_elapsed": round(snapshot.elapsed_seconds, 1),
            "seconds_remaining": round(
                snapshot.total_seconds - snapshot.elapsed_seconds,
                1,
            ),
        }
    )

    return signal


async def evaluate_strategies(
    market: MarketInfo,
    ticks: list[Tick],
) -> list[Signal]:
    """Evaluate all shared live strategies against a market."""
    if len(ticks) < 2:
        debug_log.info(
            "[ADAPTER] %s - skipping: not enough ticks (%d < 2)",
            market.market_id[:16],
            len(ticks),
        )
        return []

    strategies = get_live_strategies()
    snapshot = ticks_to_snapshot(market, ticks)

    balance = await get_usdc_balance()
    if balance <= 0:
        log.warning(
            "[ADAPTER] Could not fetch balance for %s (got %.2f), skipping",
            market.market_id[:16],
            balance,
        )
        return []

    feature_skip_reason = await _attach_live_feature_series(
        market,
        snapshot,
        strategies,
    )
    if feature_skip_reason is not None and any(
        strategy.required_feature_columns() for strategy in strategies
    ):
        logger = log.warning if "stale crypto data" in feature_skip_reason else debug_log.info
        logger(
            "[ADAPTER] Crypto features unavailable for %s: %s. Feature strategies will be skipped.",
            market.market_id[:16],
            feature_skip_reason,
        )

    signals: list[Signal] = []
    market_context = {
        "asset": snapshot.metadata.get("asset"),
        "duration_minutes": snapshot.metadata.get("duration_minutes"),
        "feature_series": snapshot.feature_series,
    }

    for strategy in strategies:
        required_columns = strategy.required_feature_columns()
        if required_columns and feature_skip_reason is not None:
            debug_log.info(
                "[ADAPTER] %s - skipping %s: %s",
                market.market_id[:16],
                strategy.config.strategy_name,
                feature_skip_reason,
            )
            continue

        if not strategy.market_is_eligible(market_context):
            debug_log.info(
                "[ADAPTER] %s - skipping %s: market not eligible",
                market.market_id[:16],
                strategy.config.strategy_name,
            )
            continue

        try:
            if await already_traded_this_market(
                market.market_id,
                strategy.config.strategy_name,
            ):
                debug_log.info(
                    "[ADAPTER] %s - already traded with %s, skipping",
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

        try:
            signal = strategy.evaluate(snapshot)
        except Exception as exc:
            debug_log.info(
                "[ADAPTER] Strategy %s raised during evaluate: %s",
                strategy.config.strategy_id,
                exc,
            )
            continue

        if signal is None:
            continue

        populated = _populate_execution_fields(signal, market, snapshot, balance)
        if populated is None:
            continue

        signals.append(populated)

    if signals:
        log.info(
            "[ADAPTER] %d signal(s) for %s: %s",
            len(signals),
            market.market_id[:16],
            [signal.strategy_name for signal in signals],
        )
    else:
        debug_log.info(
            "[ADAPTER] No signals for %s (%d strategies evaluated)",
            market.market_id[:16],
            len(strategies),
        )

    return signals
