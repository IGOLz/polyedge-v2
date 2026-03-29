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
REPO_ROOT = SRC_ROOT.parent
DEFAULT_MERGE_BOT_CONFIG_PATH = (
    SRC_ROOT
    / "results"
    / "wallet_forensics"
    / "coldmath_resume_smoke_v3"
    / "wallet_inventory_rebalancing_merge_backtest_bot_config.json"
)
DEFAULT_CLONE_BOT_CONFIG_PATH = (
    SRC_ROOT
    / "results"
    / "wallet_forensics"
    / "coldmath_resume_smoke_v3"
    / "wallet_coldmath_clone_bot_config.json"
)
DEFAULT_BOT_CONFIG_PATH = DEFAULT_CLONE_BOT_CONFIG_PATH

DEFAULT_SEQUENCE_BUDGET_USD = _env_float("WEATHER_MERGE_SEQUENCE_BUDGET_USD", 5.0)
DEFAULT_MAX_TOTAL_EXPOSURE_USD = _env_float("WEATHER_MERGE_MAX_TOTAL_EXPOSURE_USD", 10.0)
DEFAULT_DAILY_LOSS_LIMIT_USD = _env_float("WEATHER_MERGE_DAILY_LOSS_LIMIT_USD", 5.0)
DEFAULT_TOTAL_SPEND_LIMIT_USD = _env_float("WEATHER_MERGE_TOTAL_SPEND_LIMIT_USD", 30.0)
DEFAULT_MIN_EXPECTED_EDGE_USD = _env_float("WEATHER_MERGE_MIN_EXPECTED_EDGE_USD", 0.03)
DEFAULT_MAX_CONCURRENT_POSITIONS = _env_int("WEATHER_MERGE_MAX_CONCURRENT_POSITIONS", 1)
DEFAULT_LOOP_INTERVAL_SECONDS = _env_float("WEATHER_MERGE_LOOP_INTERVAL_SECONDS", 30.0)
DEFAULT_SUMMARY_INTERVAL_SECONDS = _env_float("WEATHER_MERGE_SUMMARY_INTERVAL_SECONDS", 60.0)
DEFAULT_PARTIAL_REPAIR_WINDOW_SECONDS = _env_float("WEATHER_MERGE_PARTIAL_REPAIR_WINDOW_SECONDS", 30.0)
DEFAULT_MAX_ENTRY_ATTEMPTS = _env_int("WEATHER_MERGE_MAX_ENTRY_ATTEMPTS", 1)
DEFAULT_MIN_TARGET_SHARES = _env_int("WEATHER_MERGE_MIN_TARGET_SHARES", 5)
DEFAULT_NEAR_MISS_LIMIT = _env_int("WEATHER_MERGE_NEAR_MISS_LIMIT", 5)
REQUIRE_CLEAN_WALLET = _env_bool("WEATHER_MERGE_REQUIRE_CLEAN_WALLET", True)
ACTIVITY_LOOKBACK_MINUTES = _env_int("WEATHER_MERGE_ACTIVITY_LOOKBACK_MINUTES", 60)
ALLOW_ORPHANED_POSITIONS = _env_bool("WEATHER_MERGE_ALLOW_ORPHANED_POSITIONS", False)
DEFAULT_HISTORY_PATH = Path(
    os.getenv(
        "WEATHER_MERGE_HISTORY_PATH",
        str(REPO_ROOT / "logs" / "trading-weather" / "weather_merge_cycle_history.jsonl"),
    )
).expanduser()
DEFAULT_CLONE_HISTORY_PATH = Path(
    os.getenv(
        "WEATHER_CLONE_HISTORY_PATH",
        str(REPO_ROOT / "logs" / "trading-weather" / "weather_clone_cycle_history.jsonl"),
    )
).expanduser()
DEFAULT_PAPER_HISTORY_PATH = Path(
    os.getenv(
        "WEATHER_PAPER_HISTORY_PATH",
        str(REPO_ROOT / "logs" / "trading-weather-paper" / "weather_paper_cycle_history.jsonl"),
    )
).expanduser()
CLONE_LIVE_ENABLED = _env_bool("WEATHER_CLONE_ENABLE_LIVE", True)
AUTO_APPROVE = _env_bool("WEATHER_MERGE_AUTO_APPROVE", True)
AUTO_MERGE = _env_bool("WEATHER_MERGE_AUTO_MERGE", True)
SETTLEMENT_WAIT_SECONDS = _env_float("WEATHER_MERGE_SETTLEMENT_WAIT_SECONDS", 5.0)
