"""Database helpers for weather collector and trading runtime."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from shared.db import get_pool
from weather.config import LOOKAHEAD_HOURS, PILOT_MARKET_TYPE
from weather.models import WeatherBucketMarket, WeatherMarketContext


def _maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _local_market_close(local_date: date | None, timezone_name: str | None) -> datetime | None:
    if local_date is None or not timezone_name:
        return None
    zone = ZoneInfo(str(timezone_name))
    return datetime.combine(local_date, datetime.max.time(), tzinfo=zone).astimezone(UTC)


def _effective_market_close(local_date: date | None, timezone_name: str | None, ended_at: datetime | None) -> datetime | None:
    local_close = _local_market_close(local_date, timezone_name)
    if local_close is None:
        return ended_at
    if ended_at is None:
        return local_close
    return max(ended_at, local_close)


def _eligibility_reason_tokens(reason: Any) -> list[str]:
    text = str(reason or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


def _row_effectively_live(row: Any, *, now: datetime) -> bool:
    effective_close = _effective_market_close(
        row.get("local_date"),
        row.get("timezone"),
        row.get("ended_at"),
    )
    if effective_close is None:
        return True
    return effective_close > now


def _row_effectively_eligible(row: Any, *, now: datetime) -> bool:
    if bool(row.get("eligible")):
        return True
    reasons = _eligibility_reason_tokens(row.get("eligibility_reason"))
    if not reasons:
        return False
    if reasons != [f"outside {LOOKAHEAD_HOURS}h lookahead"]:
        return False
    effective_close = _effective_market_close(
        row.get("local_date"),
        row.get("timezone"),
        row.get("ended_at"),
    )
    if effective_close is None:
        return False
    return now <= effective_close <= now + timedelta(hours=LOOKAHEAD_HOURS)


async def fetch_station_rows() -> dict[str, dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                city_key,
                city,
                station_code,
                station_name,
                lat,
                lon,
                timezone,
                country_code,
                observation_provider,
                forecast_provider,
                verified,
                notes
            FROM weather_station_map
            """
        )
    return {str(row["city_key"]): dict(row) for row in rows}


async def fetch_quote_tracking_assets() -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT market_id, yes_token_id AS asset_id, 'Up' AS outcome
            FROM weather_market_catalog
            WHERE active = TRUE AND yes_token_id IS NOT NULL
            UNION ALL
            SELECT market_id, no_token_id AS asset_id, 'Down' AS outcome
            FROM weather_market_catalog
            WHERE active = TRUE AND no_token_id IS NOT NULL
            """
        )
    return [dict(row) for row in rows]


async def fetch_active_weather_contexts(
    *,
    eligible_only: bool = True,
    include_ended: bool = False,
) -> list[WeatherMarketContext]:
    now = datetime.now(UTC)
    pool = get_pool()
    async with pool.acquire() as conn:
        where_parts = [
            "wmc.active = TRUE",
            "mo.market_type = $1",
            "mo.resolved = FALSE",
        ]
        args: list[Any] = [PILOT_MARKET_TYPE]

        rows = await conn.fetch(
            f"""
            WITH latest_quotes AS (
                SELECT DISTINCT ON (market_id, outcome)
                    market_id,
                    outcome,
                    time,
                    best_bid,
                    best_ask,
                    mid,
                    best_bid_size,
                    best_ask_size
                FROM market_quotes
                ORDER BY market_id, outcome, time DESC
            )
            SELECT
                wmc.market_id,
                wmc.event_id,
                wmc.event_slug,
                wmc.market_slug,
                wmc.question,
                wmc.city,
                wmc.city_key,
                COALESCE(wmc.station_code, wsm.station_code) AS station_code,
                COALESCE(wmc.station_name, wsm.station_name) AS station_name,
                COALESCE(wmc.lat, wsm.lat) AS lat,
                COALESCE(wmc.lon, wsm.lon) AS lon,
                COALESCE(wmc.timezone, wsm.timezone) AS timezone,
                wmc.local_date,
                wmc.unit,
                wmc.bucket_label,
                wmc.bucket_low,
                wmc.bucket_high,
                wmc.bucket_order,
                wmc.rule_family,
                wmc.resolution_source_url,
                wmc.resolution_precision_scale,
                wmc.neg_risk,
                wmc.active,
                wmc.eligible,
                wmc.eligibility_reason,
                wmc.yes_token_id,
                wmc.no_token_id,
                COALESCE(wmc.started_at, mo.started_at) AS started_at,
                COALESCE(wmc.ended_at, mo.ended_at) AS ended_at,
                wsm.verified AS station_verified,
                wsm.observation_provider,
                wsm.forecast_provider,
                q_up.time AS up_quote_time,
                q_up.best_bid AS up_best_bid,
                q_up.best_ask AS up_best_ask,
                q_up.mid AS up_mid,
                q_up.best_bid_size AS up_best_bid_size,
                q_up.best_ask_size AS up_best_ask_size,
                q_down.time AS down_quote_time,
                q_down.best_bid AS down_best_bid,
                q_down.best_ask AS down_best_ask,
                q_down.mid AS down_mid,
                q_down.best_bid_size AS down_best_bid_size,
                q_down.best_ask_size AS down_best_ask_size
            FROM weather_market_catalog wmc
            JOIN market_outcomes mo ON mo.market_id = wmc.market_id
            LEFT JOIN weather_station_map wsm ON wsm.city_key = wmc.city_key
            LEFT JOIN latest_quotes q_up
                ON q_up.market_id = wmc.market_id AND q_up.outcome = 'Up'
            LEFT JOIN latest_quotes q_down
                ON q_down.market_id = wmc.market_id AND q_down.outcome = 'Down'
            WHERE {" AND ".join(where_parts)}
            ORDER BY wmc.event_id, wmc.bucket_order
            """,
            *args,
        )

    filtered_rows = []
    for row in rows:
        if not include_ended and not _row_effectively_live(row, now=now):
            continue
        if eligible_only and not _row_effectively_eligible(row, now=now):
            continue
        filtered_rows.append(row)

    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in filtered_rows:
        grouped[str(row["event_id"])].append(row)

    contexts: list[WeatherMarketContext] = []
    for event_rows in grouped.values():
        first = event_rows[0]
        markets: list[WeatherBucketMarket] = []
        for row in event_rows:
            latest_quote_time = row["up_quote_time"] or row["down_quote_time"]
            markets.append(
                WeatherBucketMarket(
                    market_id=row["market_id"],
                    event_id=row["event_id"],
                    event_slug=row["event_slug"],
                    market_slug=row["market_slug"] or "",
                    question=row["question"],
                    city=row["city"],
                    city_key=row["city_key"],
                    station_code=row["station_code"],
                    station_name=row["station_name"],
                    lat=float(row["lat"]) if row["lat"] is not None else None,
                    lon=float(row["lon"]) if row["lon"] is not None else None,
                    timezone=row["timezone"],
                    local_date=row["local_date"],
                    unit=row["unit"],
                    bucket_label=row["bucket_label"],
                    bucket_low=float(row["bucket_low"]) if row["bucket_low"] is not None else None,
                    bucket_high=float(row["bucket_high"]) if row["bucket_high"] is not None else None,
                    bucket_order=int(row["bucket_order"]),
                    rule_family=row["rule_family"],
                    resolution_source_url=row["resolution_source_url"],
                    resolution_precision_scale=int(row["resolution_precision_scale"] or 0),
                    neg_risk=bool(row["neg_risk"]),
                    active=bool(row["active"]),
                    eligible=bool(row["eligible"]),
                    eligibility_reason=row["eligibility_reason"],
                    yes_token_id=row["yes_token_id"],
                    no_token_id=row["no_token_id"],
                    started_at=row["started_at"],
                    ended_at=row["ended_at"],
                    yes_bid=float(row["up_best_bid"]) if row["up_best_bid"] is not None else None,
                    yes_ask=float(row["up_best_ask"]) if row["up_best_ask"] is not None else None,
                    yes_mid=float(row["up_mid"]) if row["up_mid"] is not None else None,
                    yes_bid_size=float(row["up_best_bid_size"]) if row["up_best_bid_size"] is not None else None,
                    yes_ask_size=float(row["up_best_ask_size"]) if row["up_best_ask_size"] is not None else None,
                    no_bid=float(row["down_best_bid"]) if row["down_best_bid"] is not None else None,
                    no_ask=float(row["down_best_ask"]) if row["down_best_ask"] is not None else None,
                    no_mid=float(row["down_mid"]) if row["down_mid"] is not None else None,
                    no_bid_size=float(row["down_best_bid_size"]) if row["down_best_bid_size"] is not None else None,
                    no_ask_size=float(row["down_best_ask_size"]) if row["down_best_ask_size"] is not None else None,
                    latest_quote_time=latest_quote_time,
                )
            )

        local_date = first["local_date"]
        if local_date is not None:
            title = f"Highest temperature in {first['city']} on {local_date.isoformat()}"
        else:
            title = first["event_slug"].replace("-", " ")

        contexts.append(
            WeatherMarketContext(
                event_id=str(first["event_id"]),
                event_slug=str(first["event_slug"]),
                title=title,
                city=str(first["city"]),
                city_key=str(first["city_key"]),
                station_code=first["station_code"],
                station_name=first["station_name"],
                lat=float(first["lat"]) if first["lat"] is not None else None,
                lon=float(first["lon"]) if first["lon"] is not None else None,
                timezone=first["timezone"],
                local_date=local_date,
                unit=first["unit"],
                rule_family=first["rule_family"],
                resolution_source_url=first["resolution_source_url"],
                verified_station=bool(first["station_verified"]),
                observation_provider=first["observation_provider"],
                forecast_provider=first["forecast_provider"],
                markets=markets,
            )
        )

    return sorted(contexts, key=lambda item: (item.local_date or datetime.now(UTC).date(), item.city))


async def fetch_recent_forecast_rows(
    market_id: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                captured_at,
                market_id,
                provider,
                model,
                run_at,
                forecast_for,
                temp_max,
                temp_hourly,
                cloud,
                wind,
                dewpoint,
                precip_prob,
                payload_json
            FROM weather_forecast_snapshots
            WHERE market_id = $1
            ORDER BY run_at DESC, captured_at DESC
            LIMIT $2
            """,
            market_id,
            limit,
        )
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for key in ("temp_hourly", "cloud", "wind", "dewpoint", "precip_prob", "payload_json"):
            item[key] = _maybe_json(item.get(key))
        result.append(item)
    return result


async def fetch_observation_rows(
    station_code: str,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 72,
) -> list[dict[str, Any]]:
    pool = get_pool()
    start_time = start_time or (datetime.now(UTC) - timedelta(hours=24))
    end_time = end_time or datetime.now(UTC)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                station_code,
                observed_at,
                temperature,
                dewpoint,
                wind_speed,
                wind_direction,
                wind_gust,
                cloud,
                visibility,
                payload_json
            FROM weather_observations
            WHERE station_code = $1
              AND observed_at BETWEEN $2 AND $3
            ORDER BY observed_at DESC
            LIMIT $4
            """,
            station_code,
            start_time,
            end_time,
            limit,
        )
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for key in ("cloud", "payload_json"):
            item[key] = _maybe_json(item.get(key))
        result.append(item)
    return result


async def fetch_quote_near(
    market_id: str,
    outcome: str,
    target: datetime,
    *,
    window_seconds: int = 7200,
) -> dict[str, Any] | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                time,
                market_id,
                outcome,
                best_bid,
                best_ask,
                mid,
                best_bid_size,
                best_ask_size
            FROM market_quotes
            WHERE market_id = $1
              AND outcome = $2
              AND time BETWEEN $3 - ($4 * INTERVAL '1 second') AND $3 + ($4 * INTERVAL '1 second')
            ORDER BY ABS(EXTRACT(EPOCH FROM (time - $3)))
            LIMIT 1
            """,
            market_id,
            outcome,
            target,
            window_seconds,
        )
    return dict(row) if row is not None else None
