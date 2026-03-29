"""ColdMath-style weather clone config normalization."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from trading_weather import config as runtime_config

DEFAULT_CLONE_MODE = "coldmath_weather_clone"
PLAYBOOK_ORDER = (
    "paired_under_par",
    "asymmetric_paired_accumulation",
    "neg_risk_basket",
    "cheap_bucket_accumulation",
    "tail_bucket_accumulation",
    "high_prob_bucket_accumulation",
    "inventory_exit_and_closeout",
)

PAIR_PLAYBOOK_KEYS = frozenset({"paired_under_par", "asymmetric_paired_accumulation"})


def is_clone_bot_config(raw_config: dict[str, Any] | None) -> bool:
    config = raw_config or {}
    mode = str(config.get("mode") or "").strip().lower()
    return mode == DEFAULT_CLONE_MODE or isinstance(config.get("playbooks"), dict)


def normalize_clone_bot_config(raw_config: dict[str, Any] | None) -> dict[str, Any]:
    config = deepcopy(raw_config or {})
    if is_clone_bot_config(config):
        return _normalize_explicit_clone_config(config)
    return _convert_merge_config_to_clone(config)


def playbook_enabled(config: dict[str, Any], playbook_key: str, *, live: bool) -> bool:
    playbook = ((config.get("playbooks") or {}).get(playbook_key) or {})
    if not bool(playbook.get("enabled", False)):
        return False
    flag_key = "live_enabled" if live else "shadow_enabled"
    return bool(playbook.get(flag_key, False))


def _normalize_explicit_clone_config(config: dict[str, Any]) -> dict[str, Any]:
    result = {
        "mode": DEFAULT_CLONE_MODE,
        "strategy_name": str(config.get("strategy_name") or "coldmath_weather_clone_v1"),
        "execution_mode": str(config.get("execution_mode") or "shadow_only"),
        "profile_name": config.get("profile_name"),
        "proxy_wallet": config.get("proxy_wallet"),
        "playbooks": {},
        "runtime": _normalize_runtime(config.get("runtime") or {}),
        "health": _normalize_health(config.get("health") or {}),
        "parity": _normalize_parity(config.get("parity") or {}),
        "deployment": _normalize_deployment(config.get("deployment") or {}),
    }
    playbooks = config.get("playbooks") or {}
    for playbook_key in PLAYBOOK_ORDER:
        playbook_config = (
            playbooks.get(playbook_key)
            if playbook_key in playbooks
            else {"enabled": False, "shadow_enabled": False, "live_enabled": False}
        ) or {}
        result["playbooks"][playbook_key] = _normalize_playbook(
            playbook_key,
            playbook_config,
        )
    return result


def _convert_merge_config_to_clone(config: dict[str, Any]) -> dict[str, Any]:
    entry_rule = config.get("entry_rule") or {}
    inventory_rule = config.get("inventory_balancing_rule") or {}
    exit_rule = config.get("exit_rule") or {}
    strategy_name = str(config.get("strategy_name") or "coldmath_inventory_rebalancing_merge_v2")
    return {
        "mode": DEFAULT_CLONE_MODE,
        "strategy_name": strategy_name.replace("merge", "clone"),
        "execution_mode": "shadow_only",
        "profile_name": config.get("profile_name"),
        "proxy_wallet": config.get("proxy_wallet"),
        "playbooks": {
            "paired_under_par": _normalize_playbook(
                "paired_under_par",
                {
                    "enabled": True,
                    "shadow_enabled": True,
                    "live_enabled": True,
                    "rolling_window_seconds": 60,
                    "synthetic_pair_cost_lte": entry_rule.get("complete_set_cost_lte", 0.995),
                    "min_mergeable_size": entry_rule.get("min_matched_size", 0.0),
                    "max_inventory_imbalance_ratio": inventory_rule.get("max_inventory_imbalance_ratio", 0.473218),
                    "max_quote_age_seconds": 120.0,
                    "max_leg_spread": 0.08,
                    "allow_stale_pair_recovery": True,
                    "shadow_requires_full_quote_pair": False,
                    "live_requires_full_quote_pair": False,
                    "midpoint_confirmation_required": False,
                    "sequence_budget_usd": config.get("sizing_rule", {}).get("max_sequence_buy_usdc", runtime_config.DEFAULT_SEQUENCE_BUDGET_USD or 8.0),
                    "max_ask_size_fraction": 1.0,
                    "reentry_scale": 1.0,
                },
            ),
            "asymmetric_paired_accumulation": _normalize_playbook(
                "asymmetric_paired_accumulation",
                {
                    "enabled": True,
                    "shadow_enabled": True,
                    "live_enabled": False,
                    "rolling_window_seconds": 60,
                    "synthetic_pair_cost_lte": min(1.02, float(entry_rule.get("complete_set_cost_lte", 0.995)) + 0.025),
                    "min_mergeable_size": 0.0,
                    "max_inventory_imbalance_ratio": inventory_rule.get("max_inventory_imbalance_ratio", 0.491617),
                    "max_quote_age_seconds": 120.0,
                    "max_leg_spread": 0.08,
                    "min_leg_price_gte": 0.0,
                    "max_leg_price_lte": 1.0,
                    "dominant_leg_price_gte": 0.90,
                    "complementary_leg_price_lte": 0.10,
                    "dominant_leg_budget_fraction": 0.94,
                    "allow_active_market_reentry": True,
                    "allow_stale_pair_recovery": True,
                    "shadow_requires_full_quote_pair": False,
                    "live_requires_full_quote_pair": False,
                    "midpoint_confirmation_required": False,
                    "sequence_budget_usd": config.get("sizing_rule", {}).get("max_sequence_buy_usdc", runtime_config.DEFAULT_SEQUENCE_BUDGET_USD or 8.0),
                    "max_ask_size_fraction": 1.0,
                    "reentry_scale": 1.0,
                },
            ),
            "neg_risk_basket": _normalize_playbook(
                "neg_risk_basket",
                {
                    "enabled": True,
                    "shadow_enabled": True,
                    "live_enabled": False,
                    "rolling_window_seconds": 60,
                    "sequence_budget_usd": 25.0,
                    "synthetic_basket_cost_lte": 0.99,
                    "min_distinct_conditions": 3,
                    "max_unmatched_ratio": 0.317073,
                    "max_quote_age_seconds": 120.0,
                    "require_sibling_coverage": True,
                    "force_flatten_minutes_before_end": 120,
                    "max_ask_size_fraction": 1.0,
                    "reentry_scale": 1.0,
                },
            ),
            "tail_bucket_accumulation": _normalize_playbook(
                "tail_bucket_accumulation",
                {
                    "enabled": True,
                    "shadow_enabled": True,
                    "live_enabled": False,
                    "directional_price_lte": 0.05,
                    "target_sides": ["yes", "no"],
                    "rolling_window_seconds": 60,
                    "sequence_budget_usd": 5.0,
                    "profit_take_price": 0.12,
                    "force_flatten_minutes_before_end": 120,
                    "max_ask_size_fraction": 1.0,
                    "reentry_scale": 1.0,
                },
            ),
            "cheap_bucket_accumulation": _normalize_playbook(
                "cheap_bucket_accumulation",
                {
                    "enabled": True,
                    "shadow_enabled": True,
                    "live_enabled": False,
                    "directional_price_lte": 0.06,
                    "complementary_price_gte": 0.94,
                    "target_sides": ["yes", "no"],
                    "rolling_window_seconds": 60,
                    "sequence_budget_usd": 3.0,
                    "profit_take_price": 0.12,
                    "force_flatten_minutes_before_end": 120,
                    "max_ask_size_fraction": 1.0,
                    "reentry_scale": 1.0,
                },
            ),
            "high_prob_bucket_accumulation": _normalize_playbook(
                "high_prob_bucket_accumulation",
                {
                    "enabled": True,
                    "shadow_enabled": True,
                    "live_enabled": False,
                    "directional_price_gte": 0.94,
                    "directional_price_lte": 0.995,
                    "complementary_price_lte": 0.06,
                    "require_dominant_bucket": False,
                    "target_sides": ["yes", "no"],
                    "rolling_window_seconds": 60,
                    "sequence_budget_usd": 5.0,
                    "profit_take_price": 0.985,
                    "force_flatten_minutes_before_end": 120,
                    "max_ask_size_fraction": 1.0,
                    "reentry_scale": 1.0,
                },
            ),
            "inventory_exit_and_closeout": _normalize_playbook(
                "inventory_exit_and_closeout",
                {
                    "enabled": True,
                    "shadow_enabled": True,
                    "live_enabled": True,
                    "partial_repair_window_seconds": runtime_config.DEFAULT_PARTIAL_REPAIR_WINDOW_SECONDS,
                    "max_merge_delay_minutes": exit_rule.get("max_merge_delay_minutes", 240.0),
                    "force_flatten_minutes_before_end": 120,
                    "directional_take_profit_buffer": 0.01,
                },
            ),
        },
        "runtime": _normalize_runtime(
            {
                "summary_interval_seconds": runtime_config.DEFAULT_SUMMARY_INTERVAL_SECONDS,
                "loop_interval_seconds": runtime_config.DEFAULT_LOOP_INTERVAL_SECONDS,
                "sequence_budget_usd": runtime_config.DEFAULT_SEQUENCE_BUDGET_USD,
                "max_total_exposure_usd": runtime_config.DEFAULT_MAX_TOTAL_EXPOSURE_USD,
                "daily_loss_limit_usd": runtime_config.DEFAULT_DAILY_LOSS_LIMIT_USD,
                "daily_spend_limit_usd": runtime_config.DEFAULT_TOTAL_SPEND_LIMIT_USD,
                "min_expected_edge_usd": runtime_config.DEFAULT_MIN_EXPECTED_EDGE_USD,
                "max_concurrent_positions": runtime_config.DEFAULT_MAX_CONCURRENT_POSITIONS,
                "min_target_shares": runtime_config.DEFAULT_MIN_TARGET_SHARES,
                "repeat_entry_cooldown_seconds": 15.0,
            }
        ),
        "health": _normalize_health({}),
        "parity": _normalize_parity({}),
        "deployment": _normalize_deployment({}),
    }


def _normalize_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "loop_interval_seconds": float(runtime.get("loop_interval_seconds") or runtime_config.DEFAULT_LOOP_INTERVAL_SECONDS),
        "summary_interval_seconds": float(runtime.get("summary_interval_seconds") or runtime_config.DEFAULT_SUMMARY_INTERVAL_SECONDS),
        "sequence_budget_usd": float(runtime.get("sequence_budget_usd") or runtime_config.DEFAULT_SEQUENCE_BUDGET_USD or 8.0),
        "max_total_exposure_usd": float(runtime.get("max_total_exposure_usd") or runtime_config.DEFAULT_MAX_TOTAL_EXPOSURE_USD or 24.0),
        "daily_loss_limit_usd": float(runtime.get("daily_loss_limit_usd") or runtime_config.DEFAULT_DAILY_LOSS_LIMIT_USD or 12.0),
        "daily_spend_limit_usd": float(runtime.get("daily_spend_limit_usd") or runtime_config.DEFAULT_TOTAL_SPEND_LIMIT_USD or 30.0),
        "min_expected_edge_usd": float(runtime.get("min_expected_edge_usd") or runtime_config.DEFAULT_MIN_EXPECTED_EDGE_USD),
        "max_concurrent_positions": int(runtime.get("max_concurrent_positions") or runtime_config.DEFAULT_MAX_CONCURRENT_POSITIONS or 2),
        "max_entry_attempts": int(runtime.get("max_entry_attempts") or runtime_config.DEFAULT_MAX_ENTRY_ATTEMPTS or 1),
        "min_target_shares": int(runtime.get("min_target_shares") or runtime_config.DEFAULT_MIN_TARGET_SHARES),
        "repeat_entry_cooldown_seconds": float(runtime.get("repeat_entry_cooldown_seconds") or 0.0),
    }


def _normalize_health(health: dict[str, Any]) -> dict[str, Any]:
    return {
        "require_execution_auth_for_live": bool(health.get("require_execution_auth_for_live", True)),
        "allow_shadow_when_auth_unhealthy": bool(health.get("allow_shadow_when_auth_unhealthy", True)),
        "direct_quote_fallback_enabled": bool(health.get("direct_quote_fallback_enabled", True)),
        "direct_quote_cache_seconds": float(health.get("direct_quote_cache_seconds") or 10.0),
        "direct_quote_max_age_seconds": float(health.get("direct_quote_max_age_seconds") or 20.0),
        "direct_quote_timeout_seconds": float(health.get("direct_quote_timeout_seconds") or 8.0),
        "max_direct_quote_markets_per_cycle": int(health.get("max_direct_quote_markets_per_cycle") or 120),
        "min_quote_coverage_ratio": float(health.get("min_quote_coverage_ratio") or 0.4),
        "persist_all_scans": bool(health.get("persist_all_scans", True)),
        "persist_all_market_rows": bool(health.get("persist_all_market_rows", True)),
        "max_persisted_market_rows_per_cycle": int(health.get("max_persisted_market_rows_per_cycle") or 250),
        "max_persisted_sequences_per_cycle": int(health.get("max_persisted_sequences_per_cycle") or 400),
        "persist_timeout_seconds": float(health.get("persist_timeout_seconds") or 5.0),
    }


def _normalize_parity(parity: dict[str, Any]) -> dict[str, Any]:
    return {
        "signal_match_window_seconds": float(parity.get("signal_match_window_seconds") or 15.0),
        "lookback_hours": int(parity.get("lookback_hours") or 24),
        "high_confidence_playbooks": parity.get("high_confidence_playbooks") or ["paired_under_par"],
        "required_under_par_pair_matches": int(parity.get("required_under_par_pair_matches") or 21),
        "enable_live_when_matched_trade_ratio_gte": float(parity.get("enable_live_when_matched_trade_ratio_gte") or 0.25),
        "holdout_condition_side_match_rate_gte": float(parity.get("holdout_condition_side_match_rate_gte") or 0.70),
        "holdout_playbook_match_rate_gte": float(parity.get("holdout_playbook_match_rate_gte") or 0.60),
        "holdout_median_entry_delta_seconds_lte": float(parity.get("holdout_median_entry_delta_seconds_lte") or 45.0),
        "holdout_median_size_error_ratio_lte": float(parity.get("holdout_median_size_error_ratio_lte") or 0.35),
        "holdout_replay_pnl_proxy_ratio_gte": float(parity.get("holdout_replay_pnl_proxy_ratio_gte") or 0.75),
        "holdout_pair_replay_pnl_proxy_ratio_gte": float(parity.get("holdout_pair_replay_pnl_proxy_ratio_gte") or 0.85),
        "notional_miss_bucket_min_usd": float(parity.get("notional_miss_bucket_min_usd") or 25.0),
    }


def _normalize_deployment(deployment: dict[str, Any]) -> dict[str, Any]:
    return {
        "approved_parity_artifact": str(deployment.get("approved_parity_artifact") or "").strip() or None,
        "release_gate_status": str(deployment.get("release_gate_status") or "replay_pending"),
        "require_approved_parity_for_live": bool(deployment.get("require_approved_parity_for_live", True)),
    }


def build_clone_size_model(config: dict[str, Any]) -> dict[str, Any]:
    runtime = config.get("runtime") or {}
    playbooks = config.get("playbooks") or {}
    size_model = {
        "repeat_entry_cooldown_seconds": float(runtime.get("repeat_entry_cooldown_seconds") or 0.0),
        "per_playbook": {},
    }
    for playbook_key in PLAYBOOK_ORDER:
        playbook = (playbooks.get(playbook_key) or {})
        size_model["per_playbook"][playbook_key] = {
            "sequence_budget_usd": float(playbook.get("sequence_budget_usd") or runtime.get("sequence_budget_usd") or 0.0),
            "max_ask_size_fraction": float(playbook.get("max_ask_size_fraction") or 1.0),
            "reentry_scale": float(playbook.get("reentry_scale") or 1.0),
            "dominant_leg_budget_fraction": (
                float(playbook.get("dominant_leg_budget_fraction"))
                if playbook.get("dominant_leg_budget_fraction") is not None
                else None
            ),
        }
    return size_model


def apply_clone_size_model(config: dict[str, Any], size_model: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(config)
    runtime = result.setdefault("runtime", {})
    playbooks = result.setdefault("playbooks", {})
    runtime["repeat_entry_cooldown_seconds"] = float(size_model.get("repeat_entry_cooldown_seconds") or 0.0)
    per_playbook = size_model.get("per_playbook") or {}
    for playbook_key, settings in per_playbook.items():
        playbook = playbooks.setdefault(playbook_key, _normalize_playbook(playbook_key, {}))
        if settings.get("sequence_budget_usd") is not None:
            playbook["sequence_budget_usd"] = float(settings.get("sequence_budget_usd") or 0.0)
        playbook["max_ask_size_fraction"] = float(settings.get("max_ask_size_fraction") or 1.0)
        playbook["reentry_scale"] = float(settings.get("reentry_scale") or 1.0)
        if settings.get("dominant_leg_budget_fraction") is not None:
            playbook["dominant_leg_budget_fraction"] = float(settings.get("dominant_leg_budget_fraction"))
    return result


def _normalize_playbook(playbook_key: str, config: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "enabled": True,
        "shadow_enabled": True,
        "live_enabled": False,
        "rolling_window_seconds": 60.0,
        "sequence_budget_usd": 5.0,
        "target_sides": ["yes", "no"],
        "max_ask_size_fraction": 1.0,
        "reentry_scale": 1.0,
    }
    if playbook_key == "paired_under_par":
        defaults.update(
            {
                "live_enabled": True,
                "synthetic_pair_cost_lte": 0.995,
                "min_mergeable_size": 0.0,
                "max_inventory_imbalance_ratio": 0.473218,
                "max_quote_age_seconds": 120.0,
                "max_leg_spread": 0.08,
                "min_leg_price_gte": 0.0,
                "max_leg_price_lte": 1.0,
                "allow_active_market_reentry": True,
                "allow_stale_pair_recovery": True,
                "shadow_requires_full_quote_pair": False,
                "live_requires_full_quote_pair": False,
                "midpoint_confirmation_required": False,
            }
        )
    elif playbook_key == "asymmetric_paired_accumulation":
        defaults.update(
            {
                "synthetic_pair_cost_lte": 1.02,
                "min_mergeable_size": 0.0,
                "max_inventory_imbalance_ratio": 0.80,
                "max_quote_age_seconds": 120.0,
                "max_leg_spread": 0.08,
                "min_leg_price_gte": 0.0,
                "max_leg_price_lte": 1.0,
                "dominant_leg_price_gte": 0.90,
                "complementary_leg_price_lte": 0.10,
                "dominant_leg_budget_fraction": 0.94,
                "allow_active_market_reentry": True,
                "allow_stale_pair_recovery": True,
                "shadow_requires_full_quote_pair": False,
                "live_requires_full_quote_pair": False,
                "midpoint_confirmation_required": False,
            }
        )
    elif playbook_key == "neg_risk_basket":
        defaults.update(
            {
                "synthetic_basket_cost_lte": 0.99,
                "min_distinct_conditions": 3,
                "max_unmatched_ratio": 0.317073,
                "max_quote_age_seconds": 120.0,
                "require_sibling_coverage": True,
                "force_flatten_minutes_before_end": 120,
            }
        )
    elif playbook_key == "tail_bucket_accumulation":
        defaults.update(
            {
                "directional_price_lte": 0.05,
                "profit_take_price": 0.12,
                "force_flatten_minutes_before_end": 120,
                "minimum_hold_seconds": 300.0,
                "min_quote_age_seconds": 0.0,
            }
        )
    elif playbook_key == "cheap_bucket_accumulation":
        defaults.update(
            {
                "directional_price_lte": 0.06,
                "complementary_price_gte": 0.94,
                "profit_take_price": 0.12,
                "force_flatten_minutes_before_end": 120,
                "minimum_hold_seconds": 300.0,
                "min_quote_age_seconds": 0.0,
            }
        )
    elif playbook_key == "high_prob_bucket_accumulation":
        defaults.update(
            {
                "directional_price_gte": 0.94,
                "directional_price_lte": 0.995,
                "complementary_price_lte": 0.06,
                "require_dominant_bucket": False,
                "profit_take_price": 0.985,
                "force_flatten_minutes_before_end": 120,
                "minimum_hold_seconds": 300.0,
                "min_quote_age_seconds": 0.0,
            }
        )
    elif playbook_key == "inventory_exit_and_closeout":
        defaults.update(
            {
                "shadow_enabled": True,
                "live_enabled": True,
                "partial_repair_window_seconds": runtime_config.DEFAULT_PARTIAL_REPAIR_WINDOW_SECONDS,
                "max_merge_delay_minutes": 240.0,
                "force_flatten_minutes_before_end": 120,
                "directional_take_profit_buffer": 0.01,
            }
        )

    normalized = {**defaults, **(config or {})}
    normalized["enabled"] = bool(normalized.get("enabled", True))
    normalized["shadow_enabled"] = bool(normalized.get("shadow_enabled", True))
    normalized["live_enabled"] = bool(normalized.get("live_enabled", False))
    normalized["rolling_window_seconds"] = float(normalized.get("rolling_window_seconds") or 60.0)
    normalized["sequence_budget_usd"] = float(normalized.get("sequence_budget_usd") or 5.0)
    normalized["target_sides"] = [str(side).lower() for side in normalized.get("target_sides") or ["yes", "no"]]
    return normalized
