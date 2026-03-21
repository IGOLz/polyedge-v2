"""Validated live strategy profile for the trading bot."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from shared.strategies.S10.config import S10Config, get_candidate_config as get_s10_candidate_config
from shared.strategies.S10.strategy import S10Strategy
from shared.strategies.S13.config import S13Config, get_candidate_config as get_s13_candidate_config
from shared.strategies.S13.strategy import S13Strategy
from shared.strategies.S14.config import S14Config, get_candidate_config as get_s14_candidate_config
from shared.strategies.S14.strategy import S14Strategy
from shared.strategies.S5.config import S5Config
from shared.strategies.S5.strategy import S5Strategy
from shared.strategies.S9.config import S9Config
from shared.strategies.S9.strategy import S9Strategy
from shared.strategies.base import BaseStrategy


# Toggle validated live strategies here.
LIVE_STRATEGY_ENABLED: dict[str, bool] = {
    "S5": True,
    "S9": True,
    "S10": True,
    "S13": True,
    "S14": True,
}


def _parse_market_type(market_type: str) -> tuple[str, int]:
    parts = market_type.lower().split("_")
    asset = parts[0] if parts else ""
    duration_minutes = 0
    if len(parts) >= 2 and parts[1].endswith("m"):
        try:
            duration_minutes = int(parts[1][:-1])
        except ValueError:
            duration_minutes = 0
    return asset, duration_minutes


def build_live_s5_config() -> S5Config:
    """Return the exact validated S5 live config."""
    return S5Config(
        strategy_id="S5",
        strategy_name="S5_time_phase_midpoint_reclaim",
        entry_window_start=45,
        entry_window_end=180,
        allowed_hours=[18, 19, 20, 21, 22, 23],
        allowed_assets=["eth", "sol"],
        allowed_durations_minutes=[5],
        price_range_low=0.45,
        price_range_high=0.60,
        approach_lookback=12,
        cross_buffer=0.02,
        confirmation_lookback=5,
        confirmation_min_move=0.01,
        min_cross_move=0.04,
        live_stop_loss_price=0.35,
        live_take_profit_price=0.70,
    )


def build_live_s10_config() -> S10Config:
    """Return the live-tested S10 candidate with crypto market scope."""
    candidate = get_s10_candidate_config()
    candidate.allowed_assets = ["btc", "eth", "sol", "xrp"]
    candidate.allowed_durations_minutes = [5, 15]
    return candidate


def build_live_s9_config() -> S9Config:
    """Return the validated S9 live candidate config."""
    return S9Config(
        strategy_id="S9",
        strategy_name="S9_compression_breakout",
        allowed_assets=["btc", "eth", "sol", "xrp"],
        allowed_durations_minutes=[5],
        compression_window=20,
        compression_max_std=0.008,
        compression_max_range=0.03,
        trigger_scan_start=30,
        trigger_scan_end=180,
        breakout_distance=0.03,
        momentum_lookback=15,
        efficiency_min=0.55,
        live_stop_loss_price=0.40,
        live_take_profit_price=0.70,
    )


def build_live_s13_config() -> S13Config:
    """Return the validated S13 live candidate config."""
    candidate = get_s13_candidate_config()
    candidate.allowed_assets = ["btc", "eth", "sol", "xrp"]
    candidate.allowed_durations_minutes = [5]
    return candidate


def build_live_s14_config() -> S14Config:
    """Return the validated S14 live candidate config."""
    candidate = get_s14_candidate_config()
    candidate.allowed_assets = ["btc", "eth", "sol", "xrp"]
    return candidate


def _build_strategy(strategy_id: str) -> BaseStrategy:
    if strategy_id == "S5":
        return S5Strategy(build_live_s5_config())
    if strategy_id == "S9":
        return S9Strategy(build_live_s9_config())
    if strategy_id == "S10":
        return S10Strategy(build_live_s10_config())
    if strategy_id == "S13":
        return S13Strategy(build_live_s13_config())
    if strategy_id == "S14":
        return S14Strategy(build_live_s14_config())
    raise ValueError(f"Unsupported live strategy id: {strategy_id}")


@lru_cache(maxsize=1)
def get_live_strategies() -> tuple[BaseStrategy, ...]:
    """Instantiate the live strategy set used by the trading bot."""
    return tuple(
        _build_strategy(strategy_id)
        for strategy_id, enabled in LIVE_STRATEGY_ENABLED.items()
        if enabled
    )


def market_in_live_scope(market_type: str, started_at: Any | None = None) -> bool:
    """Return whether a market belongs to the active live trading basket."""
    asset, duration_minutes = _parse_market_type(market_type)
    hour = getattr(started_at, "hour", None)

    for strategy in get_live_strategies():
        cfg = strategy.config
        allowed_assets = getattr(cfg, "allowed_assets", None)
        allowed_durations = getattr(cfg, "allowed_durations_minutes", None)
        allowed_hours = getattr(cfg, "allowed_hours", None)

        if allowed_assets is not None:
            if asset not in {value.lower() for value in allowed_assets}:
                continue

        if allowed_durations is not None:
            if duration_minutes not in allowed_durations:
                continue

        if allowed_hours is not None and hour is not None:
            if hour not in allowed_hours:
                continue

        return True

    return False


def _summarize_strategy(strategy: BaseStrategy) -> str:
    cfg = strategy.config

    if cfg.strategy_id == "S5":
        return (
            f"{cfg.strategy_id} "
            f"enabled={LIVE_STRATEGY_ENABLED.get(cfg.strategy_id, False)} "
            f"assets={cfg.allowed_assets} "
            f"durations={cfg.allowed_durations_minutes} "
            f"hours={cfg.allowed_hours} "
            f"window={cfg.entry_window_start}-{cfg.entry_window_end} "
            f"range={cfg.price_range_low}-{cfg.price_range_high} "
            f"lookbacks={cfg.approach_lookback}/{cfg.confirmation_lookback} "
            f"cross={cfg.cross_buffer}/{cfg.min_cross_move} "
            f"confirmation_move={cfg.confirmation_min_move} "
            f"sl_tp={cfg.live_stop_loss_price}/{cfg.live_take_profit_price}"
        )

    if cfg.strategy_id == "S9":
        return (
            f"{cfg.strategy_id} "
            f"enabled={LIVE_STRATEGY_ENABLED.get(cfg.strategy_id, False)} "
            f"assets={cfg.allowed_assets} "
            f"durations={cfg.allowed_durations_minutes} "
            f"hours={cfg.allowed_hours or 'all'} "
            f"compression={cfg.compression_window}/{cfg.compression_max_std}/{cfg.compression_max_range} "
            f"trigger={cfg.trigger_scan_start}-{cfg.trigger_scan_end} "
            f"breakout={cfg.breakout_distance} "
            f"momentum={cfg.momentum_lookback} "
            f"efficiency={cfg.efficiency_min} "
            f"sl_tp={cfg.live_stop_loss_price}/{cfg.live_take_profit_price}"
        )

    if cfg.strategy_id == "S10":
        return (
            f"{cfg.strategy_id} "
            f"enabled={LIVE_STRATEGY_ENABLED.get(cfg.strategy_id, False)} "
            f"assets={cfg.allowed_assets} "
            f"durations={cfg.allowed_durations_minutes} "
            f"hours={cfg.allowed_hours or 'all'} "
            f"impulse={cfg.impulse_start}-{cfg.impulse_end}@{cfg.impulse_threshold} "
            f"retrace={cfg.retrace_window}/{cfg.retrace_min}-{cfg.retrace_max} "
            f"reaccel={cfg.reacceleration_threshold} "
            f"eff={cfg.impulse_efficiency_min} "
            f"sl_tp={cfg.live_stop_loss_price}/{cfg.live_take_profit_price}"
        )

    if cfg.strategy_id == "S13":
        return (
            f"{cfg.strategy_id} "
            f"enabled={LIVE_STRATEGY_ENABLED.get(cfg.strategy_id, False)} "
            f"assets={cfg.allowed_assets} "
            f"durations={cfg.allowed_durations_minutes} "
            f"feature={cfg.feature_window} "
            f"window={cfg.entry_window_start}-{cfg.entry_window_end} "
            f"underlying={cfg.min_underlying_return} "
            f"confirm={cfg.min_market_confirmation}-{cfg.max_market_delta} "
            f"mid={cfg.max_price_distance_from_mid} "
            f"vol={cfg.max_underlying_vol} "
            f"sl_tp={cfg.live_stop_loss_price}/{cfg.live_take_profit_price}"
        )

    if cfg.strategy_id == "S14":
        return (
            f"{cfg.strategy_id} "
            f"enabled={LIVE_STRATEGY_ENABLED.get(cfg.strategy_id, False)} "
            f"assets={cfg.allowed_assets} "
            f"durations={cfg.allowed_durations_minutes} "
            f"feature={cfg.feature_window} "
            f"window={cfg.entry_window_start}-{cfg.entry_window_end} "
            f"delta={cfg.min_market_delta_abs} "
            f"underlying={cfg.max_underlying_return_abs} "
            f"extremes={cfg.extreme_price_low}/{cfg.extreme_price_high} "
            f"mismatch={cfg.require_direction_mismatch} "
            f"sl_tp={cfg.live_stop_loss_price}/{cfg.live_take_profit_price}"
        )

    return f"{cfg.strategy_id} enabled={LIVE_STRATEGY_ENABLED.get(cfg.strategy_id, False)}"


def live_profile_summary() -> str:
    """Human-readable summary for logs/startup reporting."""
    strategies = get_live_strategies()
    if not strategies:
        return "no live strategies enabled"
    return " | ".join(_summarize_strategy(strategy) for strategy in strategies)
