"""Weather strategy evaluation for the pilot."""

from __future__ import annotations
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from statistics import pstdev
from typing import Any
from zoneinfo import ZoneInfo

from shared.strategies import Signal
from weather.config import (
    FORECAST_STALE_SECONDS,
    OBSERVATION_STALE_SECONDS,
    QUOTES_STALE_SECONDS,
    SLIPPAGE_BUFFER,
    W1_MAX_DISAGREEMENT_C,
    W1_MAX_SPREAD,
    W1_MIN_EDGE,
    W1_MIN_NET_EV,
    W2_MIN_FAIR_MOVE,
    W3_MIN_EDGE_AFTER_NOON,
    W4_MAX_COMBINED_COST,
    W4_MIN_PACKAGE_EV,
)
from weather.models import WeatherBucketMarket, WeatherDecision, WeatherSnapshot
from weather.providers import extract_ensemble_member_maxima

MIN_EXECUTABLE_ENTRY_PRICE = 0.02
MAX_EXECUTABLE_ENTRY_PRICE = 0.98


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_celsius(value: float, unit: str | None) -> float:
    if unit == "F":
        return (value - 32.0) * 5.0 / 9.0
    return value


def _round_half_up(value: float, precision_scale: int) -> float:
    quant = Decimal("1") if precision_scale <= 0 else Decimal("1").scaleb(-precision_scale)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def _contains_bucket(market: WeatherBucketMarket, rounded_temp: float) -> bool:
    if market.bucket_low is None and market.bucket_high is None:
        return False
    if market.bucket_low is None:
        return rounded_temp <= float(market.bucket_high)
    if market.bucket_high is None:
        return rounded_temp >= float(market.bucket_low)
    return float(market.bucket_low) <= rounded_temp <= float(market.bucket_high)


def _normalize_probabilities(probabilities: dict[str, float]) -> dict[str, float]:
    total = sum(probabilities.values())
    if total <= 0:
        return probabilities
    return {market_id: value / total for market_id, value in probabilities.items()}


def _extract_latest_forecast(snapshot: WeatherSnapshot, provider: str, model: str) -> dict[str, Any] | None:
    candidates = [
        row
        for row in snapshot.forecasts
        if row.get("provider") == provider and row.get("model") == model
    ]
    candidates.sort(key=lambda row: (row.get("run_at"), row.get("captured_at")), reverse=True)
    return candidates[0] if candidates else None


def _extract_previous_ensemble(snapshot: WeatherSnapshot) -> dict[str, Any] | None:
    candidates = [
        row
        for row in snapshot.recent_forecasts
        if row.get("provider") == "open_meteo" and row.get("model") == "ensemble"
    ]
    candidates.sort(key=lambda row: (row.get("run_at"), row.get("captured_at")), reverse=True)
    if len(candidates) < 2:
        return None
    latest_run = candidates[0].get("run_at")
    for row in candidates[1:]:
        if row.get("run_at") != latest_run:
            return row
    return None


def _forecast_is_stale(row: dict[str, Any] | None, captured_at: datetime) -> bool:
    if row is None:
        return True
    run_at = row.get("run_at")
    if not isinstance(run_at, datetime):
        return True
    return (captured_at - run_at.astimezone(UTC)).total_seconds() > FORECAST_STALE_SECONDS


def _observation_is_stale(snapshot: WeatherSnapshot) -> bool:
    if not snapshot.observations:
        return True
    latest = snapshot.observations[0].get("observed_at")
    if not isinstance(latest, datetime):
        return True
    return (snapshot.captured_at - latest.astimezone(UTC)).total_seconds() > OBSERVATION_STALE_SECONDS


def _quote_is_stale(market: WeatherBucketMarket, captured_at: datetime) -> bool:
    if market.latest_quote_time is None:
        return True
    return (captured_at - market.latest_quote_time.astimezone(UTC)).total_seconds() > QUOTES_STALE_SECONDS


def _current_ensemble_probabilities(snapshot: WeatherSnapshot) -> tuple[dict[str, float], list[float]]:
    row = _extract_latest_forecast(snapshot, "open_meteo", "ensemble")
    if row is None:
        return {}, []
    payload = row.get("payload_json") or {}
    maxima = extract_ensemble_member_maxima(payload)
    if not maxima:
        return {}, []

    rounded = [
        _round_half_up(
            value,
            snapshot.context.markets[0].resolution_precision_scale,
        )
        for value in maxima
    ]
    probabilities: dict[str, float] = {}
    for market in snapshot.context.markets:
        hits = sum(1 for value in rounded if _contains_bucket(market, value))
        probabilities[market.market_id] = hits / len(rounded)
    return _normalize_probabilities(probabilities), maxima


def _member_disagreement_c(maxima: list[float], unit: str | None) -> float:
    if len(maxima) < 2:
        return 0.0
    converted = [_to_celsius(value, unit) for value in maxima]
    return float(pstdev(converted))


def _event_local_hour(snapshot: WeatherSnapshot) -> int | None:
    timezone_name = snapshot.context.timezone
    if not timezone_name:
        return None
    return snapshot.captured_at.astimezone(ZoneInfo(timezone_name)).hour


def _remaining_hourly_temperatures(snapshot: WeatherSnapshot) -> list[float]:
    row = _extract_latest_forecast(snapshot, "open_meteo", "deterministic")
    if row is None:
        return []
    hourly = row.get("temp_hourly") or {}
    times = hourly.get("time")
    values = hourly.get("values")
    if not isinstance(times, list) or not isinstance(values, list):
        return []

    remaining: list[float] = []
    for time_str, value in zip(times, values, strict=False):
        try:
            point = datetime.fromisoformat(str(time_str))
        except ValueError:
            continue
        numeric = _safe_float(value)
        if numeric is None:
            continue
        if point >= snapshot.captured_at.astimezone(point.tzinfo or UTC):
            remaining.append(numeric)
    return remaining


def _quote_spread(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None:
        return None
    return ask - bid


def _entry_price_is_executable(price: float | None) -> bool:
    if price is None:
        return False
    return MIN_EXECUTABLE_ENTRY_PRICE <= price <= MAX_EXECUTABLE_ENTRY_PRICE


def _build_signal(
    *,
    strategy_name: str,
    market: WeatherBucketMarket,
    direction: str,
    entry_price: float,
    fair_probability: float,
    edge: float,
    net_ev: float,
    decision_reason: str,
    extra_data: dict[str, Any] | None = None,
) -> Signal:
    stop_loss = max(0.01, round(entry_price - 0.12, 4))
    take_profit = min(0.99, round(entry_price + 0.18, 4))
    if stop_loss >= entry_price or take_profit <= entry_price:
        raise ValueError(f"non-viable exits for entry price {entry_price:.4f}")
    signal_data = {
        "market_id": market.market_id,
        "event_id": market.event_id,
        "event_slug": market.event_slug,
        "city": market.city,
        "local_date": market.local_date.isoformat() if market.local_date else None,
        "market_bucket_label": market.bucket_label,
        "rule_family": market.rule_family,
        "station_code": market.station_code,
        "fair_probability": round(fair_probability, 4),
        "edge": round(edge, 4),
        "net_ev": round(net_ev, 4),
        "spread": round(
            _quote_spread(market.yes_bid, market.yes_ask)
            if direction == "Up"
            else _quote_spread(market.no_bid, market.no_ask)
            or 0.0,
            4,
        ),
        "decision_reason": decision_reason,
        "bet_cost": 5.0,
        "allow_stage_3": False,
        "price_min": 0.01,
        "price_max": 0.99,
        "stop_loss_price": stop_loss,
        "take_profit_price": take_profit,
    }
    if extra_data:
        signal_data.update(extra_data)
    return Signal(
        direction=direction,
        strategy_name=strategy_name,
        entry_price=round(entry_price, 4),
        signal_data=signal_data,
    )


def _evaluate_yes_trade(
    market: WeatherBucketMarket,
    fair_yes: float,
    strategy_name: str,
    reason: str,
    *,
    min_edge: float,
    min_net_ev: float,
    max_spread: float,
    extra_data: dict[str, Any] | None = None,
) -> Signal | None:
    if market.yes_ask is None or market.yes_bid is None or market.yes_ask_size in (None, 0):
        return None
    if not _entry_price_is_executable(market.yes_ask):
        return None
    spread = market.yes_ask - market.yes_bid
    edge = fair_yes - market.yes_ask
    net_ev = fair_yes - (market.yes_ask + SLIPPAGE_BUFFER)
    if spread > max_spread or edge < min_edge or net_ev < min_net_ev:
        return None
    return _build_signal(
        strategy_name=strategy_name,
        market=market,
        direction="Up",
        entry_price=float(market.yes_ask),
        fair_probability=fair_yes,
        edge=edge,
        net_ev=net_ev,
        decision_reason=reason,
        extra_data=extra_data,
    )


def _evaluate_no_trade(
    market: WeatherBucketMarket,
    fair_yes: float,
    strategy_name: str,
    reason: str,
    *,
    min_edge: float,
    min_net_ev: float,
    max_spread: float,
    extra_data: dict[str, Any] | None = None,
) -> Signal | None:
    fair_no = 1.0 - fair_yes
    if market.no_ask is None or market.no_bid is None or market.no_ask_size in (None, 0):
        return None
    if not _entry_price_is_executable(market.no_ask):
        return None
    spread = market.no_ask - market.no_bid
    edge = fair_no - market.no_ask
    net_ev = fair_no - (market.no_ask + SLIPPAGE_BUFFER)
    if spread > max_spread or edge < min_edge or net_ev < min_net_ev:
        return None
    return _build_signal(
        strategy_name=strategy_name,
        market=market,
        direction="Down",
        entry_price=float(market.no_ask),
        fair_probability=fair_no,
        edge=edge,
        net_ev=net_ev,
        decision_reason=reason,
        extra_data=extra_data,
    )


def _w1_ensemble_fair_value(
    snapshot: WeatherSnapshot,
    fair_probabilities: dict[str, float],
    maxima: list[float],
) -> WeatherDecision | None:
    ensemble_row = _extract_latest_forecast(snapshot, "open_meteo", "ensemble")
    if _forecast_is_stale(ensemble_row, snapshot.captured_at):
        return WeatherDecision(
            strategy_name="W1_ensemble_fair_value",
            reason="stale_forecast",
            fair_probabilities=fair_probabilities,
            skip_reasons=["ensemble forecast stale or missing"],
        )

    disagreement = _member_disagreement_c(maxima, snapshot.context.unit)
    if disagreement > W1_MAX_DISAGREEMENT_C:
        return WeatherDecision(
            strategy_name="W1_ensemble_fair_value",
            reason="high_model_disagreement",
            fair_probabilities=fair_probabilities,
            skip_reasons=[f"ensemble disagreement {disagreement:.2f}C > {W1_MAX_DISAGREEMENT_C:.2f}C"],
        )

    candidates: list[Signal] = []
    for market in snapshot.context.markets:
        if _quote_is_stale(market, snapshot.captured_at):
            continue
        fair_yes = fair_probabilities.get(market.market_id, 0.0)
        extra = {"model_disagreement_c": round(disagreement, 4)}
        yes_signal = _evaluate_yes_trade(
            market,
            fair_yes,
            "W1_ensemble_fair_value",
            "ensemble fair value",
            min_edge=W1_MIN_EDGE,
            min_net_ev=W1_MIN_NET_EV,
            max_spread=W1_MAX_SPREAD,
            extra_data=extra,
        )
        no_signal = _evaluate_no_trade(
            market,
            fair_yes,
            "W1_ensemble_fair_value",
            "ensemble fair value",
            min_edge=W1_MIN_EDGE,
            min_net_ev=W1_MIN_NET_EV,
            max_spread=W1_MAX_SPREAD,
            extra_data=extra,
        )
        for signal in (yes_signal, no_signal):
            if signal is not None:
                candidates.append(signal)

    if not candidates:
        return WeatherDecision(
            strategy_name="W1_ensemble_fair_value",
            reason="no_edge",
            fair_probabilities=fair_probabilities,
            skip_reasons=["no market passed edge, EV, spread, and quote-depth checks"],
        )

    best = max(candidates, key=lambda signal: float(signal.signal_data["net_ev"]))
    return WeatherDecision(
        strategy_name="W1_ensemble_fair_value",
        reason="edge_found",
        fair_probabilities=fair_probabilities,
        signals=[best],
    )


def _w2_forecast_update_reaction(
    snapshot: WeatherSnapshot,
    fair_probabilities: dict[str, float],
) -> WeatherDecision | None:
    current_row = _extract_latest_forecast(snapshot, "open_meteo", "ensemble")
    previous_row = _extract_previous_ensemble(snapshot)
    if current_row is None or previous_row is None:
        return WeatherDecision(
            strategy_name="W2_forecast_update_reaction",
            reason="missing_history",
            fair_probabilities=fair_probabilities,
            skip_reasons=["missing current or previous ensemble run"],
        )

    previous_payload = previous_row.get("payload_json") or {}
    previous_maxima = extract_ensemble_member_maxima(previous_payload)
    if not previous_maxima:
        return WeatherDecision(
            strategy_name="W2_forecast_update_reaction",
            reason="missing_previous_distribution",
            fair_probabilities=fair_probabilities,
            skip_reasons=["previous ensemble run has no member maxima"],
        )

    rounded_previous = [
        _round_half_up(value, snapshot.context.markets[0].resolution_precision_scale)
        for value in previous_maxima
    ]
    previous_probs: dict[str, float] = {}
    for market in snapshot.context.markets:
        hits = sum(1 for value in rounded_previous if _contains_bucket(market, value))
        previous_probs[market.market_id] = hits / len(rounded_previous)
    previous_probs = _normalize_probabilities(previous_probs)

    candidates: list[Signal] = []
    for market in snapshot.context.markets:
        if _quote_is_stale(market, snapshot.captured_at):
            continue
        fair_yes = fair_probabilities.get(market.market_id, 0.0)
        prev_yes = previous_probs.get(market.market_id, 0.0)
        fair_yes_move = fair_yes - prev_yes

        historical = snapshot.quote_history.get(market.market_id, {})
        past_yes_mid = _safe_float((historical.get("Up") or {}).get("mid"))
        past_no_mid = _safe_float((historical.get("Down") or {}).get("mid"))
        current_yes_mid = market.yes_mid
        current_no_mid = market.no_mid

        yes_market_move = (
            current_yes_mid - past_yes_mid
            if current_yes_mid is not None and past_yes_mid is not None
            else 0.0
        )
        no_market_move = (
            current_no_mid - past_no_mid
            if current_no_mid is not None and past_no_mid is not None
            else 0.0
        )
        fair_no = 1.0 - fair_yes
        prev_no = 1.0 - prev_yes
        fair_no_move = fair_no - prev_no

        if fair_yes_move - yes_market_move >= W2_MIN_FAIR_MOVE:
            signal = _evaluate_yes_trade(
                market,
                fair_yes,
                "W2_forecast_update_reaction",
                "forecast update underreaction",
                min_edge=W1_MIN_EDGE,
                min_net_ev=W1_MIN_NET_EV,
                max_spread=W1_MAX_SPREAD,
                extra_data={
                    "fair_move": round(fair_yes_move, 4),
                    "market_move": round(yes_market_move, 4),
                    "previous_fair_probability": round(prev_yes, 4),
                },
            )
            if signal is not None:
                candidates.append(signal)

        if fair_no_move - no_market_move >= W2_MIN_FAIR_MOVE:
            signal = _evaluate_no_trade(
                market,
                fair_yes,
                "W2_forecast_update_reaction",
                "forecast update underreaction",
                min_edge=W1_MIN_EDGE,
                min_net_ev=W1_MIN_NET_EV,
                max_spread=W1_MAX_SPREAD,
                extra_data={
                    "fair_move": round(fair_no_move, 4),
                    "market_move": round(no_market_move, 4),
                    "previous_fair_probability": round(prev_no, 4),
                },
            )
            if signal is not None:
                candidates.append(signal)

    if not candidates:
        return WeatherDecision(
            strategy_name="W2_forecast_update_reaction",
            reason="no_underreaction",
            fair_probabilities=fair_probabilities,
            skip_reasons=["no bucket showed a >=10 point forecast move with market lag"],
        )

    best = max(candidates, key=lambda signal: float(signal.signal_data["net_ev"]))
    return WeatherDecision(
        strategy_name="W2_forecast_update_reaction",
        reason="underreaction_found",
        fair_probabilities=fair_probabilities,
        signals=[best],
    )


def _w3_intraday_nowcast(snapshot: WeatherSnapshot) -> WeatherDecision | None:
    if _event_local_hour(snapshot) is None or _event_local_hour(snapshot) < 12:
        return WeatherDecision(
            strategy_name="W3_intraday_observation_nowcast",
            reason="before_noon",
            fair_probabilities={},
            skip_reasons=["intraday nowcast activates only after local noon"],
        )

    deterministic_row = _extract_latest_forecast(snapshot, "open_meteo", "deterministic")
    if _forecast_is_stale(deterministic_row, snapshot.captured_at):
        return WeatherDecision(
            strategy_name="W3_intraday_observation_nowcast",
            reason="stale_deterministic",
            fair_probabilities={},
            skip_reasons=["deterministic forecast stale or missing"],
        )
    if _observation_is_stale(snapshot):
        return WeatherDecision(
            strategy_name="W3_intraday_observation_nowcast",
            reason="stale_observation",
            fair_probabilities={},
            skip_reasons=["station observations stale or missing"],
        )

    observed_temps = [
        _safe_float(row.get("temperature"))
        for row in snapshot.observations
        if row.get("temperature") is not None
    ]
    observed_values = [value for value in observed_temps if value is not None]
    if not observed_values:
        return WeatherDecision(
            strategy_name="W3_intraday_observation_nowcast",
            reason="missing_temperature_obs",
            fair_probabilities={},
            skip_reasons=["no usable observed temperatures"],
        )

    observed_max = max(observed_values)
    remaining = _remaining_hourly_temperatures(snapshot)
    projected_cap = max([observed_max, *remaining]) if remaining else observed_max
    rounded_observed = _round_half_up(observed_max, snapshot.context.markets[0].resolution_precision_scale)
    rounded_cap = _round_half_up(projected_cap, snapshot.context.markets[0].resolution_precision_scale)

    candidates: list[Signal] = []
    fair_probabilities: dict[str, float] = {}
    for market in snapshot.context.markets:
        if _quote_is_stale(market, snapshot.captured_at):
            continue

        fair_yes = 0.5
        if market.bucket_high is not None and rounded_observed > market.bucket_high:
            fair_yes = 0.0
        elif market.bucket_low is not None and rounded_cap < market.bucket_low:
            fair_yes = 0.0
        elif _contains_bucket(market, rounded_observed) and _contains_bucket(market, rounded_cap):
            fair_yes = 0.95

        fair_probabilities[market.market_id] = fair_yes
        signal: Signal | None = None
        if fair_yes >= 0.9:
            signal = _evaluate_yes_trade(
                market,
                fair_yes,
                "W3_intraday_observation_nowcast",
                "observation-constrained bucket",
                min_edge=W3_MIN_EDGE_AFTER_NOON,
                min_net_ev=W3_MIN_EDGE_AFTER_NOON,
                max_spread=W1_MAX_SPREAD,
                extra_data={
                    "observed_max": round(observed_max, 3),
                    "projected_cap": round(projected_cap, 3),
                },
            )
        elif fair_yes <= 0.05:
            signal = _evaluate_no_trade(
                market,
                fair_yes,
                "W3_intraday_observation_nowcast",
                "observation-constrained bucket",
                min_edge=W3_MIN_EDGE_AFTER_NOON,
                min_net_ev=W3_MIN_EDGE_AFTER_NOON,
                max_spread=W1_MAX_SPREAD,
                extra_data={
                    "observed_max": round(observed_max, 3),
                    "projected_cap": round(projected_cap, 3),
                },
            )
        if signal is not None:
            candidates.append(signal)

    if not candidates:
        return WeatherDecision(
            strategy_name="W3_intraday_observation_nowcast",
            reason="no_nowcast_edge",
            fair_probabilities=fair_probabilities,
            skip_reasons=["observations constrained the range, but no executable edge cleared the threshold"],
        )

    best = max(candidates, key=lambda signal: float(signal.signal_data["net_ev"]))
    return WeatherDecision(
        strategy_name="W3_intraday_observation_nowcast",
        reason="nowcast_edge_found",
        fair_probabilities=fair_probabilities,
        signals=[best],
    )


def _w4_cross_bucket_structure(
    snapshot: WeatherSnapshot,
    fair_probabilities: dict[str, float],
) -> WeatherDecision | None:
    ordered = sorted(snapshot.context.markets, key=lambda market: market.bucket_order)
    best_pair: tuple[WeatherBucketMarket, WeatherBucketMarket] | None = None
    best_package_ev = 0.0

    for left, right in zip(ordered, ordered[1:], strict=False):
        if _quote_is_stale(left, snapshot.captured_at) or _quote_is_stale(right, snapshot.captured_at):
            continue
        if left.yes_ask is None or right.yes_ask is None:
            continue
        if left.yes_bid is None or right.yes_bid is None:
            continue
        if not _entry_price_is_executable(left.yes_ask) or not _entry_price_is_executable(right.yes_ask):
            continue
        spread_left = left.yes_ask - left.yes_bid
        spread_right = right.yes_ask - right.yes_bid
        if spread_left > W1_MAX_SPREAD or spread_right > W1_MAX_SPREAD:
            continue

        combined_cost = left.yes_ask + right.yes_ask + (2 * SLIPPAGE_BUFFER)
        combined_fair = fair_probabilities.get(left.market_id, 0.0) + fair_probabilities.get(right.market_id, 0.0)
        package_ev = combined_fair - combined_cost
        if combined_cost <= W4_MAX_COMBINED_COST and package_ev >= W4_MIN_PACKAGE_EV and package_ev > best_package_ev:
            best_pair = (left, right)
            best_package_ev = package_ev

    if best_pair is None:
        return WeatherDecision(
            strategy_name="W4_cross_bucket_structure",
            reason="no_package",
            fair_probabilities=fair_probabilities,
            skip_reasons=["no adjacent bucket package cleared combined cost and EV thresholds"],
        )

    left, right = best_pair
    package_id = f"{snapshot.context.event_id}:{left.market_id}:{right.market_id}"
    signals = [
        _build_signal(
            strategy_name="W4_cross_bucket_structure",
            market=left,
            direction="Up",
            entry_price=float(left.yes_ask),
            fair_probability=fair_probabilities.get(left.market_id, 0.0),
            edge=fair_probabilities.get(left.market_id, 0.0) - left.yes_ask,
            net_ev=best_package_ev,
            decision_reason="adjacent bucket package",
            extra_data={
                "package_group": package_id,
                "package_market_ids": [left.market_id, right.market_id],
                "package_combined_ev": round(best_package_ev, 4),
                "package_combined_cost": round(left.yes_ask + right.yes_ask, 4),
            },
        ),
        _build_signal(
            strategy_name="W4_cross_bucket_structure",
            market=right,
            direction="Up",
            entry_price=float(right.yes_ask),
            fair_probability=fair_probabilities.get(right.market_id, 0.0),
            edge=fair_probabilities.get(right.market_id, 0.0) - right.yes_ask,
            net_ev=best_package_ev,
            decision_reason="adjacent bucket package",
            extra_data={
                "package_group": package_id,
                "package_market_ids": [left.market_id, right.market_id],
                "package_combined_ev": round(best_package_ev, 4),
                "package_combined_cost": round(left.yes_ask + right.yes_ask, 4),
            },
        ),
    ]
    return WeatherDecision(
        strategy_name="W4_cross_bucket_structure",
        reason="package_found",
        fair_probabilities=fair_probabilities,
        signals=signals,
    )


def evaluate_weather_decision(snapshot: WeatherSnapshot) -> WeatherDecision:
    fair_probabilities, maxima = _current_ensemble_probabilities(snapshot)
    if not fair_probabilities:
        return WeatherDecision(
            strategy_name="weather_skip",
            reason="missing_ensemble_distribution",
            fair_probabilities={},
            skip_reasons=["missing usable ensemble forecast"],
        )

    for evaluator in (
        lambda: _w2_forecast_update_reaction(snapshot, fair_probabilities),
        lambda: _w3_intraday_nowcast(snapshot),
        lambda: _w1_ensemble_fair_value(snapshot, fair_probabilities, maxima),
        lambda: _w4_cross_bucket_structure(snapshot, fair_probabilities),
    ):
        decision = evaluator()
        if decision is not None and decision.signals:
            return decision
    return WeatherDecision(
        strategy_name="weather_skip",
        reason="no_strategy_fired",
        fair_probabilities=fair_probabilities,
        skip_reasons=["all weather strategies passed on this snapshot"],
    )


def evaluate_weather_strategies(snapshot: WeatherSnapshot) -> list[Signal]:
    return evaluate_weather_decision(snapshot).signals
