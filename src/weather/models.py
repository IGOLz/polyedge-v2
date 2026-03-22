"""Shared weather pilot dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from shared.strategies import Signal


@dataclass(slots=True)
class WeatherBucketMarket:
    market_id: str
    event_id: str
    event_slug: str
    market_slug: str
    question: str
    city: str
    city_key: str
    station_code: str | None
    station_name: str | None
    lat: float | None
    lon: float | None
    timezone: str | None
    local_date: date | None
    unit: str | None
    bucket_label: str
    bucket_low: float | None
    bucket_high: float | None
    bucket_order: int
    rule_family: str | None
    resolution_source_url: str | None
    resolution_precision_scale: int
    neg_risk: bool
    active: bool
    eligible: bool
    eligibility_reason: str | None
    yes_token_id: str | None
    no_token_id: str | None
    started_at: datetime | None
    ended_at: datetime | None
    yes_bid: float | None = None
    yes_ask: float | None = None
    yes_mid: float | None = None
    yes_bid_size: float | None = None
    yes_ask_size: float | None = None
    no_bid: float | None = None
    no_ask: float | None = None
    no_mid: float | None = None
    no_bid_size: float | None = None
    no_ask_size: float | None = None
    latest_quote_time: datetime | None = None


@dataclass(slots=True)
class ParsedWeatherEvent:
    event_id: str
    event_slug: str
    title: str
    city: str
    city_key: str
    local_date: date | None
    timezone: str | None
    station_code: str | None
    station_name: str | None
    lat: float | None
    lon: float | None
    unit: str | None
    rule_family: str | None
    resolution_source_url: str | None
    resolution_precision_scale: int
    neg_risk: bool
    event_liquidity: float
    markets: list[WeatherBucketMarket]
    eligible: bool
    eligibility_reason: str | None


@dataclass(slots=True)
class WeatherMarketContext:
    event_id: str
    event_slug: str
    title: str
    city: str
    city_key: str
    station_code: str | None
    station_name: str | None
    lat: float | None
    lon: float | None
    timezone: str | None
    local_date: date | None
    unit: str | None
    rule_family: str | None
    resolution_source_url: str | None
    verified_station: bool
    observation_provider: str | None
    forecast_provider: str | None
    markets: list[WeatherBucketMarket] = field(default_factory=list)


@dataclass(slots=True)
class WeatherSnapshot:
    context: WeatherMarketContext
    captured_at: datetime
    forecasts: list[dict[str, Any]] = field(default_factory=list)
    recent_forecasts: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    recent_quotes: dict[str, dict[str, Any]] = field(default_factory=dict)
    quote_history: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class WeatherDecision:
    strategy_name: str
    reason: str
    fair_probabilities: dict[str, float]
    signals: list[Signal] = field(default_factory=list)
    skip_reasons: list[str] = field(default_factory=list)
