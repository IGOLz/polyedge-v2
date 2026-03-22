"""Configuration and constants for the weather pilot."""

from __future__ import annotations

from shared.config import WEATHER_CONFIG

PILOT_MARKET_TYPE = "weather_temp_daily"
PILOT_METRIC = "temperature_max"

SLIPPAGE_BUFFER = 0.01

W1_MIN_EDGE = 0.08
W1_MIN_NET_EV = 0.06
W1_MAX_SPREAD = 0.05
W1_MAX_DISAGREEMENT_C = 2.0

W2_MIN_FAIR_MOVE = 0.10
W3_MIN_EDGE_AFTER_NOON = 0.05
W4_MIN_PACKAGE_EV = 0.08
W4_MAX_COMBINED_COST = 0.70

WEATHER_PAGE_URL = WEATHER_CONFIG["weather_page_url"]
WEATHER_USER_AGENT = WEATHER_CONFIG["user_agent"]
DISCOVERY_INTERVAL_SECONDS = WEATHER_CONFIG["discovery_interval_seconds"]
FORECAST_INTERVAL_SECONDS = WEATHER_CONFIG["forecast_interval_seconds"]
OBSERVATION_INTERVAL_SECONDS = WEATHER_CONFIG["observation_interval_seconds"]
RESOLUTION_INTERVAL_SECONDS = WEATHER_CONFIG["resolution_interval_seconds"]
LOOKAHEAD_HOURS = WEATHER_CONFIG["lookahead_hours"]
MIN_EVENT_LIQUIDITY = WEATHER_CONFIG["min_event_liquidity"]
MAX_SLUG_FETCH = WEATHER_CONFIG["max_slug_fetch"]
QUOTES_STALE_SECONDS = WEATHER_CONFIG["quotes_stale_seconds"]
FORECAST_STALE_SECONDS = WEATHER_CONFIG["forecast_stale_seconds"]
OBSERVATION_STALE_SECONDS = WEATHER_CONFIG["observation_stale_seconds"]

