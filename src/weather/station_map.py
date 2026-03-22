"""Curated station mappings for the weather pilot."""

from __future__ import annotations

import re
import unicodedata


def normalize_city_key(city: str) -> str:
    normalized = unicodedata.normalize("NFKD", city).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")

    aliases = {
        "new-york": "nyc",
        "new-york-city": "nyc",
        "sao-paulo": "sao-paulo",
        "sao-paolo": "sao-paulo",
    }
    return aliases.get(normalized, normalized)


CURATED_STATION_MAP: dict[str, dict[str, object]] = {
    "ankara": {"city": "Ankara", "station_code": "LTAC", "timezone": "Europe/Istanbul", "country_code": "TR"},
    "atlanta": {"city": "Atlanta", "station_code": "KATL", "timezone": "America/New_York", "country_code": "US"},
    "austin": {"city": "Austin", "station_code": "KAUS", "timezone": "America/Chicago", "country_code": "US"},
    "chengdu": {"city": "Chengdu", "station_code": "ZUUU", "timezone": "Asia/Shanghai", "country_code": "CN"},
    "chicago": {"city": "Chicago", "station_code": "KORD", "timezone": "America/Chicago", "country_code": "US"},
    "chongqing": {"city": "Chongqing", "station_code": "ZUCK", "timezone": "Asia/Shanghai", "country_code": "CN"},
    "dallas": {"city": "Dallas", "station_code": "KDAL", "timezone": "America/Chicago", "country_code": "US"},
    "denver": {"city": "Denver", "station_code": "KDEN", "timezone": "America/Denver", "country_code": "US"},
    "houston": {"city": "Houston", "station_code": "KHOU", "timezone": "America/Chicago", "country_code": "US"},
    "london": {"city": "London", "station_code": "EGLC", "timezone": "Europe/London", "country_code": "GB"},
    "los-angeles": {"city": "Los Angeles", "station_code": "KLAX", "timezone": "America/Los_Angeles", "country_code": "US"},
    "madrid": {"city": "Madrid", "station_code": "LEMD", "timezone": "Europe/Madrid", "country_code": "ES"},
    "miami": {"city": "Miami", "station_code": "KMIA", "timezone": "America/New_York", "country_code": "US"},
    "nyc": {"city": "NYC", "station_code": "KLGA", "timezone": "America/New_York", "country_code": "US"},
    "paris": {"city": "Paris", "station_code": "LFPG", "timezone": "Europe/Paris", "country_code": "FR"},
    "san-francisco": {"city": "San Francisco", "station_code": "KSFO", "timezone": "America/Los_Angeles", "country_code": "US"},
    "sao-paulo": {"city": "Sao Paulo", "station_code": "SBGR", "timezone": "America/Sao_Paulo", "country_code": "BR"},
    "seattle": {"city": "Seattle", "station_code": "KSEA", "timezone": "America/Los_Angeles", "country_code": "US"},
    "seoul": {"city": "Seoul", "station_code": "RKSI", "timezone": "Asia/Seoul", "country_code": "KR"},
    "shanghai": {"city": "Shanghai", "station_code": "ZSPD", "timezone": "Asia/Shanghai", "country_code": "CN"},
    "shenzhen": {"city": "Shenzhen", "station_code": "ZGSZ", "timezone": "Asia/Shanghai", "country_code": "CN"},
    "tel-aviv": {"city": "Tel Aviv", "station_code": "LLBG", "timezone": "Asia/Jerusalem", "country_code": "IL"},
    "tokyo": {"city": "Tokyo", "station_code": "RJTT", "timezone": "Asia/Tokyo", "country_code": "JP"},
    "toronto": {"city": "Toronto", "station_code": "CYYZ", "timezone": "America/Toronto", "country_code": "CA"},
    "warsaw": {"city": "Warsaw", "station_code": "EPWA", "timezone": "Europe/Warsaw", "country_code": "PL"},
    "wellington": {"city": "Wellington", "station_code": "NZWN", "timezone": "Pacific/Auckland", "country_code": "NZ"},
    "wuhan": {"city": "Wuhan", "station_code": "ZHHH", "timezone": "Asia/Shanghai", "country_code": "CN"},
    "hong-kong": {
        "city": "Hong Kong",
        "station_code": "HKO",
        "timezone": "Asia/Hong_Kong",
        "country_code": "HK",
        "verified": False,
        "notes": "Skipped in pilot because rules resolve to one decimal place.",
    },
    "taipei": {
        "city": "Taipei",
        "station_code": "46692",
        "timezone": "Asia/Taipei",
        "country_code": "TW",
        "verified": False,
        "notes": "Skipped in pilot because rules resolve to one decimal place.",
    },
}


def seed_station_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for city_key, payload in CURATED_STATION_MAP.items():
        rows.append(
            {
                "city_key": city_key,
                "city": payload["city"],
                "station_code": payload.get("station_code"),
                "timezone": payload["timezone"],
                "country_code": payload.get("country_code"),
                "observation_provider": "aviationweather",
                "forecast_provider": "open_meteo",
                "verified": bool(payload.get("verified", True)),
                "notes": payload.get("notes"),
            }
        )
    return rows
