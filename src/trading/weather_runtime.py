"""Weather strategy runtime for the live trading bot."""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from shared.db import create_weather_tables
from trading import config
from trading import db as trading_db
from trading.balance import get_usdc_balance
from trading.db import MarketInfo
from trading.executor import execute_trade
from trading.utils import debug_log, log
from weather.config import PILOT_MARKET_TYPE
from weather.models import WeatherMarketContext, WeatherSnapshot
from weather.storage import (
    fetch_active_weather_contexts,
    fetch_observation_rows,
    fetch_quote_near,
    fetch_recent_forecast_rows,
)
from weather.strategies import evaluate_weather_decision

WEATHER_LOOP_INTERVAL_SECONDS = 60
WEATHER_MARKET_PREFIX = "weather_%"
SHADOW_LOG_INTERVAL_SECONDS = 300

_shadow_cache: dict[str, tuple[str, datetime]] = {}


def _get_live_bool(live_config: dict[str, str], key: str, fallback: bool) -> bool:
    raw = live_config.get(key)
    if raw is None:
        return fallback
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_live_float(live_config: dict[str, str], key: str, fallback: float) -> float:
    raw = live_config.get(key)
    if raw is None:
        return fallback
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def _get_live_int(live_config: dict[str, str], key: str, fallback: int) -> int:
    raw = live_config.get(key)
    if raw is None:
        return fallback
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


def _latest_forecasts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: (item.get("run_at"), item.get("captured_at")), reverse=True):
        key = (str(row.get("provider")), str(row.get("model")))
        latest.setdefault(key, row)
    return list(latest.values())


def _observation_window(context: WeatherMarketContext, captured_at: datetime) -> tuple[datetime, datetime]:
    if context.local_date is None or not context.timezone:
        return captured_at - timedelta(hours=24), captured_at
    zone = ZoneInfo(context.timezone)
    start_local = datetime.combine(context.local_date, datetime.min.time(), tzinfo=zone)
    end_local = datetime.combine(context.local_date, datetime.max.time(), tzinfo=zone)
    return start_local.astimezone(UTC), min(end_local.astimezone(UTC), captured_at)


async def _build_snapshot(context: WeatherMarketContext) -> WeatherSnapshot:
    captured_at = datetime.now(UTC)
    anchor_market_id = context.markets[0].market_id
    recent_forecasts = await fetch_recent_forecast_rows(anchor_market_id, limit=16)
    forecasts = _latest_forecasts(recent_forecasts)

    observations: list[dict[str, Any]] = []
    if context.station_code:
        start_time, end_time = _observation_window(context, captured_at)
        observations = await fetch_observation_rows(
            context.station_code,
            start_time=start_time,
            end_time=end_time,
            limit=96,
        )

    quote_history: dict[str, dict[str, Any]] = {}
    ensemble_rows = [
        row
        for row in recent_forecasts
        if row.get("provider") == "open_meteo" and row.get("model") == "ensemble"
    ]
    ensemble_rows.sort(key=lambda row: (row.get("run_at"), row.get("captured_at")), reverse=True)
    previous_run_at = None
    if ensemble_rows:
        latest_run = ensemble_rows[0].get("run_at")
        for row in ensemble_rows[1:]:
            if row.get("run_at") != latest_run:
                previous_run_at = row.get("run_at")
                break

    if isinstance(previous_run_at, datetime):
        lookup_tasks: list[asyncio.Future] = []
        keys: list[tuple[str, str]] = []
        for market in context.markets:
            for outcome in ("Up", "Down"):
                keys.append((market.market_id, outcome))
                lookup_tasks.append(
                    fetch_quote_near(
                        market.market_id,
                        outcome,
                        previous_run_at,
                        window_seconds=3600,
                    )
                )
        quote_results = await asyncio.gather(*lookup_tasks, return_exceptions=True)
        for (market_id, outcome), row in zip(keys, quote_results, strict=False):
            if isinstance(row, Exception) or row is None:
                continue
            quote_history.setdefault(market_id, {})[outcome] = row

    return WeatherSnapshot(
        context=context,
        captured_at=captured_at,
        forecasts=forecasts,
        recent_forecasts=recent_forecasts,
        observations=observations,
        quote_history=quote_history,
    )


def _populate_probe_execution(
    signal,
    *,
    probe_bet_size: float,
    balance: float,
) -> None:
    bet_size = max(
        probe_bet_size,
        config.MIN_LIVE_BET_SIZE_USD,
        round(signal.entry_price * config.MIN_ENTRY_SHARES, 2),
    )
    shares = max(math.floor(bet_size / signal.entry_price), config.MIN_ENTRY_SHARES)
    actual_cost = shares * signal.entry_price
    while actual_cost + 1e-9 < config.MIN_LIVE_BET_SIZE_USD:
        shares += 1
        actual_cost = shares * signal.entry_price

    signal.locked_shares = shares
    signal.locked_cost = round(actual_cost, 4)
    signal.locked_balance = round(balance, 2)
    signal.locked_bet_size = round(bet_size, 2)
    signal.signal_data.update(
        {
            "bet_cost": round(actual_cost, 4),
            "shares": shares,
            "actual_cost": round(actual_cost, 2),
            "bet_size": round(bet_size, 2),
            "current_balance": round(balance, 2),
            "balance_at_signal": round(balance, 2),
        }
    )


def _shadow_signature(decision, context: WeatherMarketContext) -> str:
    signal_part = ",".join(
        f"{signal.strategy_name}:{signal.direction}:{signal.signal_data.get('market_id')}:{signal.signal_data.get('edge')}"
        for signal in decision.signals
    )
    fair_part = ",".join(
        f"{market_id}:{round(prob, 4)}"
        for market_id, prob in sorted(decision.fair_probabilities.items())
    )
    skip_part = ",".join(decision.skip_reasons)
    return "|".join([context.event_id, decision.strategy_name, decision.reason, signal_part, fair_part, skip_part])


async def _log_shadow_decision(
    context: WeatherMarketContext,
    decision,
    *,
    risk_skip_reason: str | None = None,
) -> None:
    now = datetime.now(UTC)
    signature = _shadow_signature(decision, context)
    previous = _shadow_cache.get(context.event_id)
    if previous is not None:
        previous_signature, previous_at = previous
        if previous_signature == signature and (now - previous_at).total_seconds() < SHADOW_LOG_INTERVAL_SECONDS:
            return

    fair_by_bucket = {
        market.bucket_label: round(decision.fair_probabilities.get(market.market_id, 0.0), 4)
        for market in context.markets
    }
    market_by_bucket = {
        market.bucket_label: {
            "yes_mid": round(market.yes_mid, 4) if market.yes_mid is not None else None,
            "yes_ask": round(market.yes_ask, 4) if market.yes_ask is not None else None,
            "no_mid": round(market.no_mid, 4) if market.no_mid is not None else None,
            "no_ask": round(market.no_ask, 4) if market.no_ask is not None else None,
        }
        for market in context.markets
    }
    await trading_db.log_event(
        "weather_shadow",
        f"Weather shadow valuation for {context.city} ({context.event_slug}) - {decision.strategy_name}/{decision.reason}",
        {
            "event_id": context.event_id,
            "event_slug": context.event_slug,
            "city": context.city,
            "strategy_name": decision.strategy_name,
            "reason": decision.reason,
            "risk_skip_reason": risk_skip_reason,
            "signals": [signal.signal_data for signal in decision.signals],
            "skip_reasons": decision.skip_reasons,
            "fair_probabilities": fair_by_bucket,
            "market_probabilities": market_by_bucket,
        },
        echo=False,
    )
    _shadow_cache[context.event_id] = (signature, now)


def _market_info_for_signal(context: WeatherMarketContext, signal) -> MarketInfo | None:
    market_id = signal.signal_data.get("market_id")
    market = next((item for item in context.markets if item.market_id == market_id), None)
    if market is None or market.ended_at is None:
        return None
    return MarketInfo(
        market_id=market.market_id,
        market_type=PILOT_MARKET_TYPE,
        started_at=market.started_at or datetime.now(UTC),
        ended_at=market.ended_at,
        up_token_id=market.yes_token_id,
        down_token_id=market.no_token_id,
    )


async def _run_weather_cycle(clob) -> None:
    live_config = await trading_db.get_live_config()
    if not _get_live_bool(live_config, "weather_enabled", True):
        return

    contexts = await fetch_active_weather_contexts(eligible_only=True)
    if not contexts:
        debug_log.info("[WEATHER] No active eligible weather contexts")
        return

    balance = await get_usdc_balance()
    probe_bet_size = _get_live_float(
        live_config,
        "weather_probe_bet_size_usd",
        max(config.MIN_LIVE_BET_SIZE_USD, 5.0),
    )
    weather_daily_limit = _get_live_float(live_config, "weather_daily_loss_limit", 10.0)
    max_concurrent_events = _get_live_int(live_config, "weather_max_concurrent_events", 2)
    shadow_only = _get_live_bool(live_config, "weather_shadow_only", False)

    weather_net = await trading_db.get_daily_resolved_net_pnl_for_market_prefix(WEATHER_MARKET_PREFIX)
    weather_loss = max(0.0, -weather_net)
    open_positions = await trading_db.get_open_position_rows_for_market_prefix(WEATHER_MARKET_PREFIX)
    open_events: dict[str, list[dict[str, Any]]] = {}
    for position in open_positions:
        signal_data = position.get("signal_data") or {}
        event_id = signal_data.get("event_id")
        if event_id:
            open_events.setdefault(str(event_id), []).append(position)

    execution_live_config = dict(live_config)
    execution_live_config["daily_loss_limit"] = "1000000"

    def _context_end(context: WeatherMarketContext) -> datetime:
        endings = [market.ended_at for market in context.markets if market.ended_at is not None]
        return min(endings) if endings else datetime.max.replace(tzinfo=UTC)

    for context in sorted(contexts, key=_context_end):
        snapshot = await _build_snapshot(context)
        decision = evaluate_weather_decision(snapshot)

        risk_skip_reason: str | None = None
        if weather_loss >= weather_daily_limit:
            risk_skip_reason = f"weather daily loss limit reached ({weather_loss:.2f} / {weather_daily_limit:.2f})"
        elif context.event_id in open_events:
            risk_skip_reason = "event already has an open weather position"
        elif len(open_events) >= max_concurrent_events:
            risk_skip_reason = f"max concurrent weather events reached ({max_concurrent_events})"
        elif balance >= 0 and balance < probe_bet_size * 2:
            risk_skip_reason = f"insufficient bankroll (${balance:.2f})"
        elif shadow_only:
            risk_skip_reason = "weather shadow-only mode enabled"

        await _log_shadow_decision(context, decision, risk_skip_reason=risk_skip_reason)

        if risk_skip_reason is not None or not decision.signals:
            continue

        if len(decision.signals) > 1 and any(context.event_id in open_events for _signal in decision.signals):
            continue

        executed_any = False
        for signal in decision.signals:
            market = _market_info_for_signal(context, signal)
            if market is None:
                continue
            if await trading_db.already_traded_this_market(market.market_id):
                continue

            _populate_probe_execution(signal, probe_bet_size=probe_bet_size, balance=balance)
            await execute_trade(clob, market, signal, execution_live_config)
            executed_any = True

        if executed_any:
            open_events.setdefault(context.event_id, []).append({"event_id": context.event_id})
            if len(open_events) >= max_concurrent_events:
                break


async def weather_loop(clob) -> None:
    await create_weather_tables()
    while True:
        try:
            await _run_weather_cycle(clob)
        except Exception:
            log.exception("[WEATHER] Weather runtime cycle failed")
        await asyncio.sleep(WEATHER_LOOP_INTERVAL_SECONDS)
