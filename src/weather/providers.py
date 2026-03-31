"""Weather and Polymarket provider clients for the pilot."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from statistics import mean
from typing import Any

import httpx

from weather.config import WEATHER_USER_AGENT

_EVENT_LINK_RE = re.compile(r'/event/([a-z0-9-]+)', re.IGNORECASE)


def _headers() -> dict[str, str]:
    return {"User-Agent": WEATHER_USER_AGENT}


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except (TypeError, ValueError):
        return None


async def fetch_weather_page_slugs(
    client: httpx.AsyncClient,
    page_url: str,
) -> list[str]:
    response = await client.get(page_url, headers=_headers())
    response.raise_for_status()
    html = response.text

    slugs: list[str] = []
    seen: set[str] = set()
    for match in _EVENT_LINK_RE.finditer(html):
        slug = match.group(1).strip().lower()
        if not slug.startswith("highest-temperature-in-"):
            continue
        if slug in seen:
            continue
        seen.add(slug)
        slugs.append(slug)
    return slugs


async def fetch_polymarket_event_by_slug(
    client: httpx.AsyncClient,
    gamma_api_base: str,
    slug: str,
) -> dict[str, Any] | None:
    response = await client.get(
        f"{gamma_api_base}/events",
        params={"slug": slug},
        headers=_headers(),
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list):
        return payload[0] if payload else None
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data[0] if data else None
        return payload
    return None


async def fetch_station_info(
    client: httpx.AsyncClient,
    station_code: str,
) -> dict[str, Any] | None:
    response = await client.get(
        "https://aviationweather.gov/api/data/stationinfo",
        params={"ids": station_code, "format": "json"},
        headers=_headers(),
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list) and payload:
        return payload[0]
    if isinstance(payload, dict) and payload.get("data"):
        data = payload["data"]
        if isinstance(data, list) and data:
            return data[0]
    return None


async def fetch_metar_observations(
    client: httpx.AsyncClient,
    station_code: str,
    *,
    hours: int = 18,
) -> list[dict[str, Any]]:
    response = await client.get(
        "https://aviationweather.gov/api/data/metar",
        params={"ids": station_code, "format": "json", "hours": hours},
        headers=_headers(),
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and payload.get("data"):
        data = payload["data"]
        if isinstance(data, list):
            return data
    return []


def parse_metar_rows(
    station_code: str,
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in observations:
        observed_at = (
            _safe_datetime(item.get("obsTime"))
            or _safe_datetime(item.get("reportTime"))
            or _safe_datetime(item.get("observation_time"))
        )
        if observed_at is None:
            continue
        cloud_layers = item.get("clouds") or item.get("cldCvg") or item.get("cloud_layers")
        rows.append(
            {
                "station_code": station_code,
                "observed_at": observed_at,
                "temperature": _safe_float(item.get("temp") or item.get("temperature")),
                "dewpoint": _safe_float(item.get("dewp") or item.get("dewpoint")),
                "wind_speed": _safe_float(item.get("wspd") or item.get("wind_speed")),
                "wind_direction": _safe_float(item.get("wdir") or item.get("wind_direction")),
                "wind_gust": _safe_float(item.get("wgst") or item.get("wind_gust")),
                "cloud": cloud_layers,
                "visibility": str(item.get("visib") or item.get("visibility") or "") or None,
                "payload_json": item,
            }
        )
    return rows


async def fetch_open_meteo_ensemble(
    client: httpx.AsyncClient,
    *,
    lat: float,
    lon: float,
    timezone_name: str,
    start_date: date,
    end_date: date,
    unit: str,
) -> dict[str, Any]:
    response = await client.get(
        "https://ensemble-api.open-meteo.com/v1/ensemble",
        params={
            "latitude": lat,
            "longitude": lon,
            "timezone": timezone_name,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": "temperature_2m",
            "temperature_unit": "fahrenheit" if unit == "F" else "celsius",
        },
        headers=_headers(),
    )
    response.raise_for_status()
    return response.json()


def extract_ensemble_member_maxima(payload: dict[str, Any]) -> list[float]:
    hourly = payload.get("hourly") or {}
    maxima: list[float] = []
    for key, values in hourly.items():
        if not str(key).startswith("temperature_2m_member"):
            continue
        series = [_safe_float(value) for value in values or []]
        finite = [value for value in series if value is not None]
        if finite:
            maxima.append(max(finite))
    return maxima


async def fetch_open_meteo_forecast(
    client: httpx.AsyncClient,
    *,
    lat: float,
    lon: float,
    timezone_name: str,
    start_date: date,
    end_date: date,
    unit: str,
) -> dict[str, Any]:
    response = await client.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "timezone": timezone_name,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": ",".join(
                [
                    "temperature_2m",
                    "dew_point_2m",
                    "cloud_cover",
                    "wind_speed_10m",
                    "precipitation_probability",
                ]
            ),
            "temperature_unit": "fahrenheit" if unit == "F" else "celsius",
            "wind_speed_unit": "ms",
        },
        headers=_headers(),
    )
    response.raise_for_status()
    return response.json()


def extract_hourly_series(payload: dict[str, Any], key: str) -> dict[str, Any] | None:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time")
    values = hourly.get(key)
    if not isinstance(times, list) or not isinstance(values, list):
        return None
    return {"time": times, "values": values}


def extract_hourly_max(payload: dict[str, Any], key: str = "temperature_2m") -> float | None:
    series = extract_hourly_series(payload, key)
    if not series:
        return None
    finite = [_safe_float(value) for value in series["values"]]
    values = [value for value in finite if value is not None]
    return max(values) if values else None


async def fetch_nws_hourly_forecast(
    client: httpx.AsyncClient,
    *,
    lat: float,
    lon: float,
) -> dict[str, Any] | None:
    points = await client.get(
        f"https://api.weather.gov/points/{lat},{lon}",
        headers={"User-Agent": WEATHER_USER_AGENT, "Accept": "application/geo+json"},
        follow_redirects=True,
    )
    points.raise_for_status()
    points_payload = points.json()
    forecast_url = (
        points_payload.get("properties", {}).get("forecastHourly")
        if isinstance(points_payload, dict)
        else None
    )
    if not forecast_url:
        return None

    forecast = await client.get(
        forecast_url,
        headers={"User-Agent": WEATHER_USER_AGENT, "Accept": "application/geo+json"},
        follow_redirects=True,
    )
    forecast.raise_for_status()
    return forecast.json()


def summarize_nws_hourly(payload: dict[str, Any]) -> dict[str, Any]:
    periods = payload.get("properties", {}).get("periods") or []
    temps = [_safe_float(period.get("temperature")) for period in periods]
    finite_temps = [value for value in temps if value is not None]
    return {
        "temp_max": max(finite_temps) if finite_temps else None,
        "periods": periods,
    }


def summarize_ensemble_payload(payload: dict[str, Any]) -> dict[str, Any]:
    maxima = extract_ensemble_member_maxima(payload)
    return {
        "temp_max": mean(maxima) if maxima else None,
        "member_maxima": maxima,
        "temp_hourly": payload.get("hourly"),
        "payload_json": payload,
    }
