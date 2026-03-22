"""Weather enrichment helpers for wallet-forensics."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from datetime import UTC
from typing import Any
from zoneinfo import ZoneInfo

from weather.providers import extract_ensemble_member_maxima

from analysis.wallet_forensics.constants import WEATHER_SLUG_PREFIX
from analysis.wallet_forensics.utils import maybe_json, safe_float


def is_weather_market(row: dict[str, Any]) -> bool:
    slug = str(row.get("event_slug") or row.get("eventSlug") or "").lower()
    title = str(row.get("title") or row.get("question") or "").lower()
    return slug.startswith(WEATHER_SLUG_PREFIX) or "highest temperature in " in title


def enrich_ledger_with_weather(
    ledger_rows: list[dict[str, Any]],
    market_context: dict[str, dict[str, Any]],
    weather_market_rows: dict[str, dict[str, Any]],
    forecast_rows_by_market: dict[str, list[dict[str, Any]]],
    observations_by_station: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in ledger_rows:
        condition_id = str(row.get("condition_id") or "")
        context = market_context.get(condition_id, {})
        weather_row = weather_market_rows.get(condition_id)
        is_weather = bool(weather_row) or is_weather_market(context)
        merged = dict(row)
        merged["is_weather"] = is_weather
        if not is_weather:
            enriched.append(merged)
            continue

        timezone_name = (weather_row or {}).get("timezone") or "UTC"
        try:
            local_tz = ZoneInfo(timezone_name)
        except Exception:
            local_tz = UTC
        occurred_at = row["occurred_at"].astimezone(local_tz)
        merged["weather_city"] = (weather_row or {}).get("city")
        merged["weather_station_code"] = (weather_row or {}).get("station_code")
        merged["weather_local_date"] = (weather_row or {}).get("local_date")
        merged["weather_bucket_label"] = (weather_row or {}).get("bucket_label")
        merged["weather_local_time"] = occurred_at.isoformat()
        end_date = context.get("end_date")
        if end_date:
            merged["hours_to_resolution"] = (end_date - row["occurred_at"]).total_seconds() / 3600.0
        else:
            merged["hours_to_resolution"] = None

        forecasts = forecast_rows_by_market.get(condition_id, [])
        chosen_forecast = latest_forecast_before(forecasts, row["occurred_at"])
        merged["weather_forecast_run_at"] = chosen_forecast.get("run_at") if chosen_forecast else None
        merged["weather_forecast_age_seconds"] = None
        merged["weather_ensemble_dispersion"] = None
        merged["weather_fair_yes_probability"] = None
        if chosen_forecast:
            run_at = chosen_forecast.get("run_at")
            if run_at is not None:
                merged["weather_forecast_age_seconds"] = (row["occurred_at"] - run_at).total_seconds()
            merged["weather_ensemble_dispersion"] = ensemble_dispersion(chosen_forecast)
            bucket_prob = weather_bucket_probability(weather_row or {}, chosen_forecast)
            if bucket_prob is not None:
                merged["weather_fair_yes_probability"] = bucket_prob

        station_code = (weather_row or {}).get("station_code")
        observation_rows = observations_by_station.get(station_code or "", [])
        latest_observation = latest_observation_before(observation_rows, row["occurred_at"])
        if latest_observation:
            merged["weather_observed_at"] = latest_observation.get("observed_at")
            merged["weather_observed_temperature"] = safe_float(latest_observation.get("temperature"))
            merged["weather_observation_age_seconds"] = (
                row["occurred_at"] - latest_observation["observed_at"]
            ).total_seconds()
        else:
            merged["weather_observed_at"] = None
            merged["weather_observed_temperature"] = None
            merged["weather_observation_age_seconds"] = None

        enriched.append(merged)
    return enriched


def latest_forecast_before(rows: list[dict[str, Any]], occurred_at) -> dict[str, Any] | None:
    eligible = [row for row in rows if row.get("run_at") and row["run_at"] <= occurred_at]
    eligible.sort(key=lambda item: (item["run_at"], item.get("captured_at") or item["run_at"]), reverse=True)
    return eligible[0] if eligible else None


def latest_observation_before(rows: list[dict[str, Any]], occurred_at) -> dict[str, Any] | None:
    eligible = [row for row in rows if row.get("observed_at") and row["observed_at"] <= occurred_at]
    eligible.sort(key=lambda item: item["observed_at"], reverse=True)
    return eligible[0] if eligible else None


def ensemble_dispersion(row: dict[str, Any]) -> float | None:
    payload = maybe_json(row.get("payload_json")) or {}
    maxima = extract_ensemble_member_maxima(payload)
    if len(maxima) < 2:
        return None
    mean = sum(maxima) / len(maxima)
    variance = sum((item - mean) ** 2 for item in maxima) / len(maxima)
    return variance ** 0.5


def weather_bucket_probability(weather_row: dict[str, Any], forecast_row: dict[str, Any]) -> float | None:
    payload = maybe_json(forecast_row.get("payload_json")) or {}
    maxima = extract_ensemble_member_maxima(payload)
    if not maxima:
        return None
    low = safe_float(weather_row.get("bucket_low"))
    high = safe_float(weather_row.get("bucket_high"))
    precision = int(weather_row.get("resolution_precision_scale") or 0)
    hits = 0
    for item in maxima:
        rounded = round_half_up(item, precision)
        if contains_bucket(low, high, rounded):
            hits += 1
    return hits / len(maxima)


def contains_bucket(low: float | None, high: float | None, value: float) -> bool:
    if low is None and high is None:
        return False
    if low is None:
        return value <= high
    if high is None:
        return value >= low
    return low <= value <= high


def round_half_up(value: float, precision: int) -> float:
    quantum = Decimal("1").scaleb(-precision)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))
