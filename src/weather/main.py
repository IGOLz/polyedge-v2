"""Weather collector service for the daily-temperature pilot."""

from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from shared.api import fetch_market_resolution, fetch_token_ids_async
from shared.config import POLYMARKET_API
from shared.db import (
    close_pool,
    create_weather_tables,
    deactivate_missing_weather_markets,
    init_pool,
    insert_market_quotes,
    insert_weather_forecast_snapshots,
    upsert_market_outcome,
    upsert_weather_market_catalog_rows,
    upsert_weather_observations,
    upsert_weather_station_map_rows,
)
from shared.http import get_async_http_client
from shared.logging import setup_logger
from shared.ws import QuoteUpdate, run_quote_listener
from weather.config import (
    DISCOVERY_INTERVAL_SECONDS,
    FORECAST_INTERVAL_SECONDS,
    MAX_SLUG_FETCH,
    OBSERVATION_INTERVAL_SECONDS,
    PILOT_MARKET_TYPE,
    RESOLUTION_INTERVAL_SECONDS,
    WEATHER_PAGE_URL,
)
from weather.models import ParsedWeatherEvent, WeatherMarketContext
from weather.parser import parse_weather_event
from weather.providers import (
    extract_hourly_max,
    extract_hourly_series,
    fetch_metar_observations,
    fetch_nws_hourly_forecast,
    fetch_open_meteo_ensemble,
    fetch_open_meteo_forecast,
    fetch_polymarket_event_by_slug,
    fetch_station_info,
    fetch_weather_page_slugs,
    parse_metar_rows,
    summarize_ensemble_payload,
    summarize_nws_hourly,
)
from weather.station_map import seed_station_rows
from weather.storage import (
    fetch_active_weather_contexts,
    fetch_known_weather_token_ids,
    fetch_quote_tracking_assets,
    fetch_station_rows,
)

logger = setup_logger("weather")
TOKEN_ID_FETCH_CONCURRENCY = 8


@dataclass
class AppState:
    shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    quote_reconnect_event: asyncio.Event = field(default_factory=asyncio.Event)
    quote_cache: dict[tuple[str, str], tuple[float | None, float | None, float | None, float | None, str]] = field(default_factory=dict)


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, app_state: AppState) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, app_state.shutdown_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_args: loop.call_soon_threadsafe(app_state.shutdown_event.set))


async def _seed_station_map(http_client: httpx.AsyncClient) -> None:
    await upsert_weather_station_map_rows(seed_station_rows())
    rows = await fetch_station_rows()

    enriched_rows: list[dict[str, Any]] = []
    for city_key, row in rows.items():
        station_code = row.get("station_code")
        if not station_code:
            continue
        if row.get("lat") is not None and row.get("lon") is not None and row.get("station_name"):
            continue
        try:
            station_info = await fetch_station_info(http_client, station_code)
        except Exception as exc:
            logger.warning("Station info fetch failed for %s: %s", station_code, exc)
            continue
        if not station_info:
            continue
        enriched_rows.append(
            {
                "city_key": city_key,
                "city": row["city"],
                "station_code": station_code,
                "station_name": station_info.get("site") or station_info.get("name"),
                "lat": station_info.get("lat"),
                "lon": station_info.get("lon"),
                "timezone": row["timezone"],
                "country_code": row.get("country_code"),
                "observation_provider": row.get("observation_provider"),
                "forecast_provider": row.get("forecast_provider"),
                "verified": bool(row.get("verified", False)),
                "notes": row.get("notes"),
            }
        )
    if enriched_rows:
        await upsert_weather_station_map_rows(enriched_rows)
        logger.info("Enriched %d station mapping row(s)", len(enriched_rows))


async def _fetch_and_parse_event(
    http_client: httpx.AsyncClient,
    slug: str,
    station_rows: dict[str, dict],
) -> ParsedWeatherEvent | None:
    event = await fetch_polymarket_event_by_slug(
        http_client,
        POLYMARKET_API["gamma_api_base"],
        slug,
    )
    if not event:
        return None
    return parse_weather_event(event, station_rows, now=datetime.now(UTC))


async def _hydrate_token_ids(
    http_client: httpx.AsyncClient,
    parsed_event: ParsedWeatherEvent,
) -> ParsedWeatherEvent:
    semaphore = asyncio.Semaphore(TOKEN_ID_FETCH_CONCURRENCY)

    async def _fetch_missing(market_id: str) -> tuple[str, tuple[str, str] | None | Exception]:
        async with semaphore:
            try:
                token_ids = await fetch_token_ids_async(http_client, market_id)
                return market_id, token_ids
            except Exception as exc:  # pragma: no cover
                return market_id, exc

    missing_markets = [
        market
        for market in parsed_event.markets
        if not str(market.yes_token_id or "").strip() or not str(market.no_token_id or "").strip()
    ]
    tasks = [_fetch_missing(market.market_id) for market in missing_markets]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    token_map = {
        market_id: token_ids
        for market_id, token_ids in results
        if not isinstance(token_ids, Exception) and token_ids is not None
    }
    for market in parsed_event.markets:
        token_ids = token_map.get(market.market_id)
        if token_ids is None:
            continue
        market.yes_token_id, market.no_token_id = token_ids
    return parsed_event


async def discovery_loop(app_state: AppState, http_client: httpx.AsyncClient) -> None:
    while not app_state.shutdown_event.is_set():
        try:
            station_rows = await fetch_station_rows()
            slugs = await fetch_weather_page_slugs(http_client, WEATHER_PAGE_URL)
            slugs = slugs[:MAX_SLUG_FETCH]
            if not slugs:
                logger.warning("Weather discovery returned no candidate slugs; keeping current catalog")
            else:
                parsed_results = await asyncio.gather(
                    *[_fetch_and_parse_event(http_client, slug, station_rows) for slug in slugs],
                    return_exceptions=True,
                )
                events: list[ParsedWeatherEvent] = []
                for result in parsed_results:
                    if isinstance(result, Exception):
                        logger.warning("Weather event parse task failed: %s", result)
                        continue
                    if result is not None:
                        events.append(result)

                known_token_ids = await fetch_known_weather_token_ids(
                    [market.market_id for event in events for market in event.markets]
                )
                for event in events:
                    for market in event.markets:
                        known = known_token_ids.get(market.market_id)
                        if not known:
                            continue
                        if known[0]:
                            market.yes_token_id = known[0]
                        if known[1]:
                            market.no_token_id = known[1]

                hydrated = await asyncio.gather(
                    *[_hydrate_token_ids(http_client, event) for event in events],
                    return_exceptions=True,
                )

                catalog_rows: list[dict[str, Any]] = []
                discovered_market_ids: list[str] = []
                for item in hydrated:
                    if isinstance(item, Exception):
                        logger.warning("Token hydration failed: %s", item)
                        continue
                    for market in item.markets:
                        discovered_market_ids.append(market.market_id)
                        catalog_rows.append(
                            {
                                "market_id": market.market_id,
                                "event_id": market.event_id,
                                "event_slug": market.event_slug,
                                "market_slug": market.market_slug,
                                "question": market.question,
                                "city": market.city,
                                "city_key": market.city_key,
                                "station_code": market.station_code,
                                "station_name": market.station_name,
                                "lat": market.lat,
                                "lon": market.lon,
                                "timezone": market.timezone,
                                "local_date": market.local_date,
                                "metric": "temperature_max",
                                "unit": market.unit,
                                "bucket_label": market.bucket_label,
                                "bucket_low": market.bucket_low,
                                "bucket_high": market.bucket_high,
                                "bucket_order": market.bucket_order,
                                "rule_family": market.rule_family,
                                "resolution_source_url": market.resolution_source_url,
                                "resolution_precision_scale": market.resolution_precision_scale,
                                "neg_risk": market.neg_risk,
                                "active": market.active,
                                "eligible": market.eligible,
                                "eligibility_reason": market.eligibility_reason,
                                "yes_token_id": market.yes_token_id,
                                "no_token_id": market.no_token_id,
                                "started_at": market.started_at,
                                "ended_at": market.ended_at,
                            }
                        )
                        await upsert_market_outcome(
                            market_id=market.market_id,
                            market_type=PILOT_MARKET_TYPE,
                            started_at=market.started_at or datetime.now(UTC),
                            ended_at=market.ended_at,
                            resolved=False,
                        )

                if catalog_rows:
                    await upsert_weather_market_catalog_rows(catalog_rows)
                    await deactivate_missing_weather_markets(discovered_market_ids)
                    app_state.quote_reconnect_event.set()
                    eligible_events = sum(1 for event in events if event.eligible)
                    logger.info(
                        "Weather discovery: %d event(s), %d eligible, %d market bucket(s)",
                        len(events),
                        eligible_events,
                        len(catalog_rows),
                    )
        except Exception:
            logger.exception("Weather discovery loop failed")

        try:
            await asyncio.wait_for(app_state.shutdown_event.wait(), timeout=DISCOVERY_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass


async def quote_listener_loop(app_state: AppState) -> None:
    async def get_tracked_assets():
        return await fetch_quote_tracking_assets()

    async def on_connection_state(connected: bool, asset_count: int):
        if connected:
            logger.info("Weather quote socket connected: %d asset(s)", asset_count)
        else:
            logger.warning("Weather quote socket disconnected")

    async def on_quote_update(asset: dict[str, Any], quote: QuoteUpdate):
        market_id = str(asset["market_id"])
        outcome = str(asset["outcome"])
        cache_key = (market_id, outcome)
        new_state = (
            quote.best_bid,
            quote.best_ask,
            quote.best_bid_size,
            quote.best_ask_size,
            quote.source_event_type,
        )
        if app_state.quote_cache.get(cache_key) == new_state:
            return
        app_state.quote_cache[cache_key] = new_state
        await insert_market_quotes(
            [
                {
                    "time": datetime.now(UTC),
                    "market_id": market_id,
                    "outcome": outcome,
                    "asset_id": asset["asset_id"],
                    "best_bid": quote.best_bid,
                    "best_ask": quote.best_ask,
                    "mid": quote.mid,
                    "best_bid_size": quote.best_bid_size,
                    "best_ask_size": quote.best_ask_size,
                    "source_event_type": quote.source_event_type,
                }
            ]
        )

    await run_quote_listener(
        get_tracked_assets=get_tracked_assets,
        on_quote_update=on_quote_update,
        shutdown_event=app_state.shutdown_event,
        reconnect_event=app_state.quote_reconnect_event,
        on_connection_state=on_connection_state,
    )


async def _insert_forecasts_for_context(
    http_client: httpx.AsyncClient,
    context: WeatherMarketContext,
) -> None:
    if context.lat is None or context.lon is None or not context.timezone or context.local_date is None or not context.unit:
        return

    forecast_rows: list[dict[str, Any]] = []

    try:
        ensemble_payload = await fetch_open_meteo_ensemble(
            http_client,
            lat=context.lat,
            lon=context.lon,
            timezone_name=context.timezone,
            start_date=context.local_date,
            end_date=context.local_date,
            unit=context.unit,
        )
        ensemble_summary = summarize_ensemble_payload(ensemble_payload)
        run_at = datetime.now(UTC)
        for market in context.markets:
            forecast_rows.append(
                {
                    "market_id": market.market_id,
                    "provider": "open_meteo",
                    "model": "ensemble",
                    "run_at": run_at,
                    "forecast_for": context.local_date,
                    "temp_max": ensemble_summary["temp_max"],
                    "temp_hourly": ensemble_summary["temp_hourly"],
                    "payload_json": ensemble_summary["payload_json"],
                }
            )
    except Exception as exc:
        logger.warning("Open-Meteo ensemble fetch failed for %s: %s", context.event_slug, exc)

    try:
        deterministic_payload = await fetch_open_meteo_forecast(
            http_client,
            lat=context.lat,
            lon=context.lon,
            timezone_name=context.timezone,
            start_date=context.local_date,
            end_date=context.local_date,
            unit=context.unit,
        )
        run_at = datetime.now(UTC)
        temp_hourly = extract_hourly_series(deterministic_payload, "temperature_2m")
        cloud = extract_hourly_series(deterministic_payload, "cloud_cover")
        wind = extract_hourly_series(deterministic_payload, "wind_speed_10m")
        dewpoint = extract_hourly_series(deterministic_payload, "dew_point_2m")
        precip_prob = extract_hourly_series(deterministic_payload, "precipitation_probability")
        temp_max = extract_hourly_max(deterministic_payload)
        for market in context.markets:
            forecast_rows.append(
                {
                    "market_id": market.market_id,
                    "provider": "open_meteo",
                    "model": "deterministic",
                    "run_at": run_at,
                    "forecast_for": context.local_date,
                    "temp_max": temp_max,
                    "temp_hourly": temp_hourly,
                    "cloud": cloud,
                    "wind": wind,
                    "dewpoint": dewpoint,
                    "precip_prob": precip_prob,
                    "payload_json": deterministic_payload,
                }
            )
    except Exception as exc:
        logger.warning("Open-Meteo deterministic fetch failed for %s: %s", context.event_slug, exc)

    if context.station_code and context.station_code.startswith("K"):
        try:
            nws_payload = await fetch_nws_hourly_forecast(
                http_client,
                lat=context.lat,
                lon=context.lon,
            )
            if nws_payload is not None:
                summary = summarize_nws_hourly(nws_payload)
                run_at = datetime.now(UTC)
                for market in context.markets:
                    forecast_rows.append(
                        {
                            "market_id": market.market_id,
                            "provider": "nws",
                            "model": "hourly",
                            "run_at": run_at,
                            "forecast_for": context.local_date,
                            "temp_max": summary["temp_max"],
                            "payload_json": nws_payload,
                        }
                    )
        except Exception as exc:
            logger.warning("NWS forecast fetch failed for %s: %s", context.event_slug, exc)

    if forecast_rows:
        await insert_weather_forecast_snapshots(forecast_rows)


async def forecast_loop(app_state: AppState, http_client: httpx.AsyncClient) -> None:
    while not app_state.shutdown_event.is_set():
        try:
            contexts = await fetch_active_weather_contexts(eligible_only=True)
            unique_contexts = list({context.event_id: context for context in contexts}.values())
            for context in unique_contexts:
                await _insert_forecasts_for_context(http_client, context)
            if contexts:
                logger.info("Weather forecasts refreshed for %d event(s)", len(unique_contexts))
        except Exception:
            logger.exception("Forecast loop failed")

        try:
            await asyncio.wait_for(app_state.shutdown_event.wait(), timeout=FORECAST_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass


async def observation_loop(app_state: AppState, http_client: httpx.AsyncClient) -> None:
    while not app_state.shutdown_event.is_set():
        try:
            contexts = await fetch_active_weather_contexts(eligible_only=True)
            seen_station_codes: set[str] = set()
            for context in contexts:
                station_code = context.station_code
                if not station_code or station_code in seen_station_codes or station_code in {"HKO", "46692"}:
                    continue
                seen_station_codes.add(station_code)
                try:
                    observations = await fetch_metar_observations(http_client, station_code)
                except Exception as exc:
                    logger.warning("Observation fetch failed for %s: %s", station_code, exc)
                    continue
                rows = parse_metar_rows(station_code, observations)
                if rows:
                    await upsert_weather_observations(rows)
            if seen_station_codes:
                logger.info("Weather observations refreshed for %d station(s)", len(seen_station_codes))
        except Exception:
            logger.exception("Observation loop failed")

        try:
            await asyncio.wait_for(app_state.shutdown_event.wait(), timeout=OBSERVATION_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass


async def resolution_loop(app_state: AppState, http_client: httpx.AsyncClient) -> None:
    while not app_state.shutdown_event.is_set():
        try:
            contexts = await fetch_active_weather_contexts(eligible_only=False, include_ended=True)
            for context in contexts:
                for market in context.markets:
                    if market.ended_at is None or market.ended_at > datetime.now(UTC):
                        continue
                    result = await fetch_market_resolution(http_client, market.market_id)
                    if not result or not result.get("resolved"):
                        continue
                    await upsert_market_outcome(
                        market_id=market.market_id,
                        market_type=PILOT_MARKET_TYPE,
                        started_at=market.started_at or datetime.now(UTC),
                        ended_at=market.ended_at,
                        final_outcome=result.get("winner"),
                        final_up_price=result.get("final_up_price"),
                        total_volume=result.get("total_volume"),
                        resolved=True,
                    )
                    logger.info(
                        "Weather market resolved: %s -> %s",
                        market.market_id[:16],
                        result.get("winner"),
                    )
        except Exception:
            logger.exception("Resolution loop failed")

        try:
            await asyncio.wait_for(app_state.shutdown_event.wait(), timeout=RESOLUTION_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass


async def main() -> None:
    logger.info("Weather collector starting...")
    await init_pool()
    await create_weather_tables()

    app_state = AppState()
    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop, app_state)

    async with get_async_http_client(timeout=30.0) as http_client:
        await _seed_station_map(http_client)

        tasks = [
            asyncio.create_task(discovery_loop(app_state, http_client), name="weather-discovery"),
            asyncio.create_task(quote_listener_loop(app_state), name="weather-quotes"),
            asyncio.create_task(forecast_loop(app_state, http_client), name="weather-forecasts"),
            asyncio.create_task(observation_loop(app_state, http_client), name="weather-observations"),
            asyncio.create_task(resolution_loop(app_state, http_client), name="weather-resolution"),
        ]

        await app_state.shutdown_event.wait()
        logger.info("Weather collector shutting down...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
