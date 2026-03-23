"""Runtime configuration for the dedicated weather merge bot."""

from __future__ import annotations

import os
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


SRC_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOT_CONFIG_PATH = (
    SRC_ROOT
    / "results"
    / "wallet_forensics"
    / "coldmath_resume_smoke_v3"
    / "wallet_inventory_rebalancing_merge_backtest_bot_config.json"
)

DEFAULT_SEQUENCE_BUDGET_USD = _env_float("WEATHER_MERGE_SEQUENCE_BUDGET_USD", 0.0)
DEFAULT_MAX_TOTAL_EXPOSURE_USD = _env_float("WEATHER_MERGE_MAX_TOTAL_EXPOSURE_USD", 0.0)
DEFAULT_DAILY_LOSS_LIMIT_USD = _env_float("WEATHER_MERGE_DAILY_LOSS_LIMIT_USD", 0.0)
DEFAULT_MIN_EXPECTED_EDGE_USD = _env_float("WEATHER_MERGE_MIN_EXPECTED_EDGE_USD", 0.03)
DEFAULT_MAX_CONCURRENT_POSITIONS = _env_int("WEATHER_MERGE_MAX_CONCURRENT_POSITIONS", 0)
DEFAULT_LOOP_INTERVAL_SECONDS = _env_float("WEATHER_MERGE_LOOP_INTERVAL_SECONDS", 60.0)
DEFAULT_PARTIAL_REPAIR_WINDOW_SECONDS = _env_float("WEATHER_MERGE_PARTIAL_REPAIR_WINDOW_SECONDS", 30.0)
DEFAULT_MAX_ENTRY_ATTEMPTS = _env_int("WEATHER_MERGE_MAX_ENTRY_ATTEMPTS", 0)
DEFAULT_MIN_TARGET_SHARES = _env_int("WEATHER_MERGE_MIN_TARGET_SHARES", 5)
AUTO_APPROVE = _env_bool("WEATHER_MERGE_AUTO_APPROVE", True)
AUTO_MERGE = _env_bool("WEATHER_MERGE_AUTO_MERGE", True)
SETTLEMENT_WAIT_SECONDS = _env_float("WEATHER_MERGE_SETTLEMENT_WAIT_SECONDS", 5.0)
