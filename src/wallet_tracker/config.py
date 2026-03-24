"""Configuration for the wallet tracker service."""

from __future__ import annotations

from shared.config import POLYMARKET_API, _optional, _optional_int

WALLET_TRACKER_PROFILE = _optional("WALLET_TRACKER_PROFILE", "ColdMath")
WALLET_TRACKER_INTERVAL_SECONDS = _optional_int("WALLET_TRACKER_INTERVAL_SECONDS", 1800)
WALLET_TRACKER_PAGE_LIMIT = _optional_int("WALLET_TRACKER_PAGE_LIMIT", 500)
WALLET_TRACKER_TIMEOUT_SECONDS = _optional_int("WALLET_TRACKER_TIMEOUT_SECONDS", 30)

DATA_API_BASE = "https://data-api.polymarket.com"
GAMMA_API_BASE = POLYMARKET_API["gamma_api_base"]
