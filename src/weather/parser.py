"""Weather market parsing and eligibility checks."""

from __future__ import annotations

import calendar
import re
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from weather.config import LOOKAHEAD_HOURS, MIN_EVENT_LIQUIDITY, PILOT_METRIC
from weather.models import ParsedWeatherEvent, WeatherBucketMarket
from weather.station_map import normalize_city_key

_TITLE_RE = re.compile(
    r"^highest temperature in (?P<city>.+?) on (?P<month>[a-z]+) (?P<day>\d{1,2}) (?P<year>\d{4})\??$",
    re.IGNORECASE,
)
_SLUG_RE = re.compile(
    r"^highest-temperature-in-(?P<city>.+)-on-(?P<month>[a-z]+)-(?P<day>\d{1,2})-(?P<year>\d{4})$",
    re.IGNORECASE,
)
_BUCKET_RANGE_RE = re.compile(
    r"^(?P<low>-?\d+(?:\.\d+)?)\s*-\s*(?P<high>-?\d+(?:\.\d+)?)\s*°\s*(?P<unit>[CF])$",
    re.IGNORECASE,
)
_BUCKET_EXACT_RE = re.compile(
    r"^(?P<value>-?\d+(?:\.\d+)?)\s*°\s*(?P<unit>[CF])$",
    re.IGNORECASE,
)
_BUCKET_BELOW_RE = re.compile(
    r"^(?P<value>-?\d+(?:\.\d+)?)\s*°\s*(?P<unit>[CF])\s+or\s+below$",
    re.IGNORECASE,
)
_BUCKET_ABOVE_RE = re.compile(
    r"^(?P<value>-?\d+(?:\.\d+)?)\s*°\s*(?P<unit>[CF])\s+or\s+higher$",
    re.IGNORECASE,
)
_WUNDERGROUND_STATION_RE = re.compile(
    r"wunderground\.com/.+?/daily/([A-Z0-9]{4,6})",
    re.IGNORECASE,
)
_WEATHER_GOV_STATION_RE = re.compile(r"site=([A-Z0-9]{4,6})", re.IGNORECASE)
_CWA_STATION_RE = re.compile(r"\bID=(\d{3,8})\b", re.IGNORECASE)

_MONTHS = {name.lower(): index for index, name in enumerate(calendar.month_name) if name}


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date_parts(month: str, day: str, year: str) -> date | None:
    month_index = _MONTHS.get(month.lower())
    if month_index is None:
        return None
    try:
        return date(int(year), month_index, int(day))
    except ValueError:
        return None


def _event_title(event: dict) -> str:
    return (event.get("title") or event.get("name") or "").strip()


def _event_slug(event: dict) -> str:
    return str(event.get("slug") or "").strip()


def _event_description(event: dict) -> str:
    return str(event.get("description") or "").strip()


def _parse_city_and_date(event: dict) -> tuple[str, str, date | None]:
    title = _event_title(event)
    slug = _event_slug(event)
    match = _TITLE_RE.match(title) or _SLUG_RE.match(slug)
    if not match:
        return "", "", None

    city = re.sub(r"\s+", " ", match.group("city").replace("-", " ")).strip()
    city_key = normalize_city_key(city)
    local_date = _parse_date_parts(match.group("month"), match.group("day"), match.group("year"))
    return city, city_key, local_date


def _parse_rule_family(description: str, resolution_source_url: str | None) -> str | None:
    haystack = " ".join(part for part in [description, resolution_source_url or ""] if part).lower()
    if "wunderground.com" in haystack:
        return "wunderground_daily"
    if "forecast.weather.gov" in haystack or "weather.gov" in haystack:
        return "weather_gov_timeseries"
    if "hko.gov.hk" in haystack or "hong kong observatory" in haystack:
        return "hong_kong_observatory"
    if "cwa.gov.tw" in haystack or "transportdata.e-land.gov.tw" in haystack:
        return "taiwan_cwa"
    return None


def _parse_precision_scale(description: str) -> int | None:
    lowered = description.lower()
    if "one decimal place" in lowered or "1 decimal place" in lowered:
        return 1
    if "nearest whole degree" in lowered or "whole degree" in lowered:
        return 0
    if "rounded to the nearest integer" in lowered:
        return 0
    return None


def _parse_unit(description: str, fallback_label: str | None) -> str | None:
    lowered = description.lower()
    if "fahrenheit" in lowered:
        return "F"
    if "celsius" in lowered:
        return "C"
    if fallback_label:
        bucket = parse_bucket_label(fallback_label)
        if bucket is not None:
            return bucket["unit"]
    return None


def _parse_station_code(description: str, resolution_source_url: str | None) -> str | None:
    haystack = " ".join(part for part in [description, resolution_source_url or ""] if part)

    for pattern in (_WUNDERGROUND_STATION_RE, _WEATHER_GOV_STATION_RE, _CWA_STATION_RE):
        match = pattern.search(haystack)
        if match:
            return match.group(1).upper()

    if "hong kong observatory" in haystack.lower():
        return "HKO"
    return None


def parse_bucket_label(label: str) -> dict[str, float | str | None] | None:
    cleaned = re.sub(r"\s+", " ", str(label or "").strip())
    if not cleaned:
        return None

    match = _BUCKET_RANGE_RE.match(cleaned)
    if match:
        return {
            "bucket_label": cleaned,
            "bucket_low": float(match.group("low")),
            "bucket_high": float(match.group("high")),
            "unit": match.group("unit").upper(),
        }

    match = _BUCKET_EXACT_RE.match(cleaned)
    if match:
        value = float(match.group("value"))
        return {
            "bucket_label": cleaned,
            "bucket_low": value,
            "bucket_high": value,
            "unit": match.group("unit").upper(),
        }

    match = _BUCKET_BELOW_RE.match(cleaned)
    if match:
        value = float(match.group("value"))
        return {
            "bucket_label": cleaned,
            "bucket_low": None,
            "bucket_high": value,
            "unit": match.group("unit").upper(),
        }

    match = _BUCKET_ABOVE_RE.match(cleaned)
    if match:
        value = float(match.group("value"))
        return {
            "bucket_label": cleaned,
            "bucket_low": value,
            "bucket_high": None,
            "unit": match.group("unit").upper(),
        }

    return None


def _market_started_at(event: dict, market: dict, now: datetime) -> datetime:
    raw = (
        market.get("startDate")
        or market.get("start_date")
        or event.get("startDate")
        or event.get("start_date")
        or market.get("createdAt")
        or market.get("created_at")
    )
    if raw:
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(UTC)
        except (TypeError, ValueError):
            pass
    return now


def _market_ended_at(event: dict, market: dict) -> datetime | None:
    raw = (
        market.get("endDate")
        or market.get("end_date")
        or event.get("endDate")
        or event.get("end_date")
    )
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _local_market_close(local_date: date | None, timezone_name: str | None) -> datetime | None:
    if local_date is None or not timezone_name:
        return None
    zone = ZoneInfo(timezone_name)
    return datetime.combine(local_date, datetime.max.time(), tzinfo=zone).astimezone(UTC)


def _effective_market_close(
    local_date: date | None,
    timezone_name: str | None,
    ended_at: datetime | None,
) -> datetime | None:
    local_close = _local_market_close(local_date, timezone_name)
    if local_close is None:
        return ended_at
    if ended_at is None:
        return local_close
    return max(ended_at, local_close)


def _event_liquidity(event: dict) -> float:
    direct = _safe_float(event.get("liquidity"))
    if direct is not None:
        return direct
    total = 0.0
    for market in event.get("markets") or []:
        total += _safe_float(market.get("liquidity")) or 0.0
    return total


def _eligibility_window_ok(
    local_date: date | None,
    timezone_name: str | None,
    ended_at: datetime | None,
    now: datetime,
) -> bool:
    latest_allowed = now + timedelta(hours=LOOKAHEAD_HOURS)
    effective_close = _effective_market_close(local_date, timezone_name, ended_at)
    if effective_close is not None:
        return now <= effective_close <= latest_allowed
    if local_date is None or not timezone_name:
        return False
    zone_now = now.astimezone(ZoneInfo(timezone_name))
    local_close = datetime.combine(local_date, datetime.max.time(), tzinfo=ZoneInfo(timezone_name))
    return zone_now <= local_close <= latest_allowed.astimezone(ZoneInfo(timezone_name))


def parse_weather_event(
    event: dict,
    station_rows: dict[str, dict],
    *,
    now: datetime | None = None,
) -> ParsedWeatherEvent | None:
    current_time = now or datetime.now(UTC)
    title = _event_title(event)
    if not title.lower().startswith("highest temperature in "):
        return None

    city, city_key, local_date = _parse_city_and_date(event)
    if not city or not city_key:
        return None

    station_row = station_rows.get(city_key, {})
    description = _event_description(event)
    resolution_source_url = str(event.get("resolutionSource") or event.get("resolution_source") or "").strip() or None
    rule_family = _parse_rule_family(description, resolution_source_url)
    precision_scale = _parse_precision_scale(description)

    event_liquidity = _event_liquidity(event)
    neg_risk = bool(event.get("negRisk") or event.get("neg_risk"))
    station_code = _parse_station_code(description, resolution_source_url) or station_row.get("station_code")
    station_name = station_row.get("station_name")
    timezone_name = station_row.get("timezone")
    lat = station_row.get("lat")
    lon = station_row.get("lon")
    verified_station = bool(station_row.get("verified", False))

    parsed_markets: list[WeatherBucketMarket] = []
    parse_error = None
    ending_for_window: datetime | None = None
    first_bucket_label: str | None = None

    for index, market in enumerate(event.get("markets") or []):
        market_id = str(market.get("conditionId") or market.get("condition_id") or "").strip()
        if not market_id:
            continue

        bucket_label = (
            str(market.get("groupItemTitle") or market.get("group_item_title") or market.get("title") or "").strip()
            or str(market.get("question") or "").strip()
        )
        if first_bucket_label is None and bucket_label:
            first_bucket_label = bucket_label

        parsed_bucket = parse_bucket_label(bucket_label)
        if parsed_bucket is None:
            parse_error = f"unparseable bucket: {bucket_label}"
            continue

        market_end = _market_ended_at(event, market)
        if market_end is not None and (ending_for_window is None or market_end > ending_for_window):
            ending_for_window = market_end

        parsed_markets.append(
            WeatherBucketMarket(
                market_id=market_id,
                event_id=str(event.get("id") or event.get("eventId") or _event_slug(event)),
                event_slug=_event_slug(event),
                market_slug=str(market.get("slug") or "").strip(),
                question=str(market.get("question") or "").strip(),
                city=city,
                city_key=city_key,
                station_code=station_code,
                station_name=station_name,
                lat=lat,
                lon=lon,
                timezone=timezone_name,
                local_date=local_date,
                unit=str(parsed_bucket["unit"]),
                bucket_label=str(parsed_bucket["bucket_label"]),
                bucket_low=parsed_bucket["bucket_low"],
                bucket_high=parsed_bucket["bucket_high"],
                bucket_order=index,
                rule_family=rule_family,
                resolution_source_url=resolution_source_url,
                resolution_precision_scale=precision_scale if precision_scale is not None else -1,
                neg_risk=neg_risk,
                active=bool(market.get("active", True)),
                eligible=False,
                eligibility_reason=None,
                yes_token_id=None,
                no_token_id=None,
                started_at=_market_started_at(event, market, current_time),
                ended_at=market_end,
            )
        )

    if not parsed_markets:
        return None

    unit = _parse_unit(description, first_bucket_label) or parsed_markets[0].unit

    eligible = True
    reasons: list[str] = []
    if not neg_risk:
        eligible = False
        reasons.append("neg-risk disabled")
    if event_liquidity < MIN_EVENT_LIQUIDITY:
        eligible = False
        reasons.append(f"event liquidity below {MIN_EVENT_LIQUIDITY:.0f}")
    if parse_error is not None:
        eligible = False
        reasons.append(parse_error)
    if precision_scale != 0:
        eligible = False
        reasons.append("resolution is not whole-degree")
    if not timezone_name:
        eligible = False
        reasons.append("missing timezone mapping")
    if not station_code:
        eligible = False
        reasons.append("missing station mapping")
    if not verified_station:
        eligible = False
        reasons.append("station mapping not verified")
    if unit not in {"C", "F"}:
        eligible = False
        reasons.append("missing temperature unit")
    if not _eligibility_window_ok(local_date, timezone_name, ending_for_window, current_time):
        eligible = False
        reasons.append(f"outside {LOOKAHEAD_HOURS}h lookahead")

    reason = "; ".join(reasons) if reasons else None
    for market in parsed_markets:
        market.unit = unit
        market.station_code = station_code
        market.station_name = station_name
        market.rule_family = rule_family
        market.resolution_precision_scale = precision_scale if precision_scale is not None else -1
        market.eligible = eligible
        market.eligibility_reason = reason

    return ParsedWeatherEvent(
        event_id=str(event.get("id") or event.get("eventId") or _event_slug(event)),
        event_slug=_event_slug(event),
        title=title,
        city=city,
        city_key=city_key,
        local_date=local_date,
        timezone=timezone_name,
        station_code=station_code,
        station_name=station_name,
        lat=lat,
        lon=lon,
        unit=unit,
        rule_family=rule_family,
        resolution_source_url=resolution_source_url,
        resolution_precision_scale=precision_scale if precision_scale is not None else -1,
        neg_risk=neg_risk,
        event_liquidity=event_liquidity,
        markets=parsed_markets,
        eligible=eligible,
        eligibility_reason=reason,
    )
