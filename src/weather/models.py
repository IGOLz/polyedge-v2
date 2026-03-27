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


def complete_neg_risk_quotes(
    *,
    neg_risk: bool,
    yes_bid: float | None,
    yes_ask: float | None,
    yes_mid: float | None,
    yes_bid_size: float | None,
    yes_ask_size: float | None,
    no_bid: float | None,
    no_ask: float | None,
    no_mid: float | None,
    no_bid_size: float | None,
    no_ask_size: float | None,
) -> dict[str, float | None]:
    if neg_risk:
        if yes_bid is None and no_ask is not None:
            yes_bid = max(0.0, min(1.0, 1.0 - no_ask))
        if yes_ask is None and no_bid is not None:
            yes_ask = max(0.0, min(1.0, 1.0 - no_bid))
        if no_bid is None and yes_ask is not None:
            no_bid = max(0.0, min(1.0, 1.0 - yes_ask))
        if no_ask is None and yes_bid is not None:
            no_ask = max(0.0, min(1.0, 1.0 - yes_bid))
        if yes_mid is None and no_mid is not None:
            yes_mid = max(0.0, min(1.0, 1.0 - no_mid))
        if no_mid is None and yes_mid is not None:
            no_mid = max(0.0, min(1.0, 1.0 - yes_mid))
        if yes_bid_size is None and no_ask_size is not None:
            yes_bid_size = no_ask_size
        if yes_ask_size is None and no_bid_size is not None:
            yes_ask_size = no_bid_size
        if no_bid_size is None and yes_ask_size is not None:
            no_bid_size = yes_ask_size
        if no_ask_size is None and yes_bid_size is not None:
            no_ask_size = yes_bid_size
    if yes_mid is None and yes_bid is not None and yes_ask is not None:
        yes_mid = (yes_bid + yes_ask) / 2.0
    if no_mid is None and no_bid is not None and no_ask is not None:
        no_mid = (no_bid + no_ask) / 2.0
    return {
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "yes_mid": yes_mid,
        "yes_bid_size": yes_bid_size,
        "yes_ask_size": yes_ask_size,
        "no_bid": no_bid,
        "no_ask": no_ask,
        "no_mid": no_mid,
        "no_bid_size": no_bid_size,
        "no_ask_size": no_ask_size,
    }
