"""Shared configuration — single source of truth for all services.

Environment variables are read once at import time.
Services import what they need: `from shared.config import DB_CONFIG, POLYMARKET_API`.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    """Return env var value or raise if missing/empty."""
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


def _optional(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _optional_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value.strip())


def _optional_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return float(value.strip())


def _optional_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _optional_csv(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or default


# ── PostgreSQL ──────────────────────────────────────────────────────────

DB_CONFIG = {
    "host": _optional("POSTGRES_HOST", "localhost"),
    "port": int(_optional("POSTGRES_PORT", "5432")),
    "user": _optional("POSTGRES_USER", "polymarket"),
    "password": _optional("POSTGRES_PASSWORD", ""),
    "database": _optional("POSTGRES_DB", "polymarket_tracker"),
}

DB_DSN = (
    f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
)

# ── Polymarket API ──────────────────────────────────────────────────────

POLYMARKET_API = {
    "clob_rest_base": "https://clob.polymarket.com",
    "clob_ws_url": "wss://ws-subscriptions-clob.polymarket.com/ws/market",
    "gamma_api_base": "https://gamma-api.polymarket.com",
}

WEATHER_CONFIG = {
    "weather_page_url": _optional(
        "WEATHER_MARKETS_URL",
        "https://polymarket.com/predictions/weather",
    ),
    "user_agent": _optional(
        "WEATHER_USER_AGENT",
        "polyedge-weather-bot/0.1 (contact: local)",
    ),
    "discovery_interval_seconds": _optional_int(
        "WEATHER_DISCOVERY_INTERVAL_SECONDS", 300
    ),
    "forecast_interval_seconds": _optional_int(
        "WEATHER_FORECAST_INTERVAL_SECONDS", 600
    ),
    "observation_interval_seconds": _optional_int(
        "WEATHER_OBSERVATION_INTERVAL_SECONDS", 300
    ),
    "resolution_interval_seconds": _optional_int(
        "WEATHER_RESOLUTION_INTERVAL_SECONDS", 300
    ),
    "lookahead_hours": _optional_int("WEATHER_LOOKAHEAD_HOURS", 72),
    "min_event_liquidity": _optional_float(
        "WEATHER_MIN_EVENT_LIQUIDITY", 10000.0
    ),
    "max_slug_fetch": _optional_int("WEATHER_MAX_SLUG_FETCH", 80),
    "quotes_stale_seconds": _optional_int("WEATHER_QUOTES_STALE_SECONDS", 600),
    "forecast_stale_seconds": _optional_int(
        "WEATHER_FORECAST_STALE_SECONDS", 10800
    ),
    "observation_stale_seconds": _optional_int(
        "WEATHER_OBSERVATION_STALE_SECONDS", 1800
    ),
}

# €€ Binance market data (used by core collection + live feature consumers) €€€€€€€

BINANCE_CONFIG = {
    "ws_base_url": _optional("BINANCE_WS_URL", "wss://stream.binance.com:9443"),
    "rest_base_url": _optional("BINANCE_REST_BASE_URL", "https://api.binance.com"),
    "tracked_symbols": _optional_csv(
        "BINANCE_TRACKED_SYMBOLS",
        ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"],
    ),
    "backfill_lookback_seconds": _optional_int(
        "BINANCE_BACKFILL_LOOKBACK_SECONDS", 120
    ),
    "stale_data_threshold_seconds": _optional_int(
        "BINANCE_STALE_DATA_THRESHOLD_SECONDS", 3
    ),
}

# ── Timing constants (used by core + trading) ──────────────────────────

TIMING = {
    "market_discovery_interval": 30,     # seconds between REST polls
    "price_record_interval": 1,          # seconds between tick writes
    "volume_poll_interval": 10,          # seconds between market volume refreshes
    "heartbeat_interval": 60,            # seconds between heartbeat logs
    "resolution_poll_interval": 10,      # seconds between resolution checks
    "ws_reconnect_max_backoff": 30,      # max seconds for WS reconnect backoff
}

# ── Core runtime switches ───────────────────────────────────────────────

CORE_RUNTIME = {
    "debug_mode": _optional_bool("CORE_DEBUG_MODE", False),
}

# ── Trading authentication (only loaded when env vars are present) ──────

TRADING_AUTH: dict = {}
_trading_keys = [
    "PRIVATE_KEY", "POLYMARKET_API_KEY", "POLYMARKET_API_SECRET",
    "POLYMARKET_API_PASSPHRASE", "PROXY_WALLET", "EOA_ADDRESS",
]
if all(os.getenv(k, "").strip() for k in _trading_keys):
    TRADING_AUTH = {k.lower(): _require(k) for k in _trading_keys}

PROXY_URL = _optional("PROXY_URL")

# ── Trading parameters ──────────────────────────────────────────────────

CHAIN_ID = 137  # Polygon mainnet

USDC_ADDRESSES = {
    "usdc_e": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
    "usdc_native": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
}
