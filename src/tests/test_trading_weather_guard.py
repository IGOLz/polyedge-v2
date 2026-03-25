from __future__ import annotations

import unittest

from trading_weather import config as weather_config
from trading_weather.main import (
    _candidate_brief,
    _cycle_status_message,
    _entry_invariant_failure,
    _sequence_final_outcome,
    _sequence_realized_pnl,
    _weather_trade_signal_payload,
    build_startup_telemetry,
)
from trading_weather.wallet_guard import audit_wallet_integrity


def _weather_activity(*, market_id: str = "weather-1") -> dict:
    return {
        "conditionId": market_id,
        "question": "Will the highest temperature in Rome be 16C?",
        "slug": "highest-temperature-in-rome-on-march-26-2026-16c",
        "type": "TRADE",
        "side": "BUY",
        "outcome": "Yes",
        "size": 10,
        "price": 0.49,
        "timestamp": 1,
        "transactionHash": "0xweather",
    }


def _crypto_activity() -> dict:
    return {
        "conditionId": "crypto-1",
        "question": "Will BTC go up or down?",
        "slug": "btc-updown-march-26-2026",
        "type": "TRADE",
        "side": "BUY",
        "outcome": "Up",
        "size": 25,
        "price": 0.41,
        "timestamp": 1,
        "transactionHash": "0xcrypto",
    }


def _weather_position(*, market_id: str = "weather-1") -> dict:
    return {
        "market": market_id,
        "title": "Will the highest temperature in Rome be 16C?",
        "slug": "highest-temperature-in-rome-on-march-26-2026-16c",
        "outcome": "Yes",
        "size": 12,
        "avgPrice": 0.49,
        "curPrice": 0.52,
        "cashPnl": 0.2,
        "redeemable": False,
    }


def _crypto_position() -> dict:
    return {
        "market": "crypto-1",
        "title": "Will BTC go up or down?",
        "slug": "btc-updown-march-26-2026",
        "outcome": "Up",
        "size": 15,
        "avgPrice": 0.41,
        "curPrice": 0.0,
        "cashPnl": -2.5,
        "redeemable": False,
    }


class TradingWeatherGuardTests(unittest.TestCase):
    def test_weather_trade_signal_payload_includes_position_and_plan(self):
        plan = {
            "event_id": "282550",
            "event_slug": "highest-temperature-in-rome-on-march-26-2026",
            "city": "rome",
            "local_date": "2026-03-26",
            "bucket_label": "16C or higher",
            "question": "Will the highest temperature in Rome be 16C or higher?",
            "condition_id": "weather-1",
            "yes_token_id": "yes-token",
            "no_token_id": "no-token",
            "first_side": "yes",
            "second_side": "no",
            "target_shares": 10,
            "combined_cost": 0.992,
            "expected_edge_usd": 0.08,
        }
        candidate = {
            "market_id": "weather-1",
            "city": "rome",
            "local_date": "2026-03-26",
            "bucket_label": "16C or higher",
            "combined_cost": 0.992,
            "merge_edge": 0.008,
            "max_mergeable_size": 25,
            "inventory_imbalance_ratio": 0.1,
            "quote_quality_label": "better_than_nearby_trade",
        }

        payload = _weather_trade_signal_payload(position_id=42, candidate=candidate, plan=plan)

        self.assertEqual(payload["weather_position_id"], 42)
        self.assertEqual(payload["city"], "rome")
        self.assertEqual(payload["planned_target_shares"], 10)
        self.assertEqual(payload["candidate"], _candidate_brief(candidate))

    def test_sequence_pnl_and_outcome_use_realized_components(self):
        position = {
            "status": "merged_closed",
            "total_entry_cost": 9.92,
            "merged_collateral_usdc": 10.0,
            "redeemed_collateral_usdc": 0.0,
            "unwind_collateral_usdc": 0.0,
        }

        self.assertAlmostEqual(_sequence_realized_pnl(position), 0.08)
        self.assertEqual(_sequence_final_outcome(position), "take_profit")

    def test_sequence_loss_maps_to_loss_outcome(self):
        position = {
            "status": "partial_unwound",
            "total_entry_cost": 5.00,
            "merged_collateral_usdc": 0.0,
            "redeemed_collateral_usdc": 0.0,
            "unwind_collateral_usdc": 4.65,
        }

        self.assertAlmostEqual(_sequence_realized_pnl(position), -0.35)
        self.assertEqual(_sequence_final_outcome(position), "loss")

    def test_wallet_guard_blocks_foreign_activity_in_lookback(self):
        report = audit_wallet_integrity(
            activity_rows=[_weather_activity(), _crypto_activity()],
            position_rows=[],
            tracked_weather_market_ids={"weather-1"},
            require_clean_wallet=True,
            allow_orphaned_positions=False,
        )

        self.assertFalse(report["ready"])
        self.assertEqual(report["reason"], "foreign_wallet_activity_detected")
        self.assertEqual(report["stats"]["foreign_activity_count"], 1)

    def test_wallet_guard_blocks_foreign_open_positions_first(self):
        report = audit_wallet_integrity(
            activity_rows=[_crypto_activity()],
            position_rows=[_crypto_position()],
            tracked_weather_market_ids={"weather-1"},
            require_clean_wallet=True,
            allow_orphaned_positions=False,
        )

        self.assertFalse(report["ready"])
        self.assertEqual(report["reason"], "foreign_open_positions_detected")
        self.assertEqual(report["stats"]["foreign_open_positions_count"], 1)

    def test_wallet_guard_blocks_orphaned_weather_inventory(self):
        report = audit_wallet_integrity(
            activity_rows=[_weather_activity()],
            position_rows=[_weather_position(market_id="weather-orphan")],
            tracked_weather_market_ids={"weather-1"},
            require_clean_wallet=True,
            allow_orphaned_positions=False,
        )

        self.assertFalse(report["ready"])
        self.assertEqual(report["reason"], "orphaned_weather_inventory_detected")
        self.assertEqual(report["stats"]["orphaned_weather_positions_count"], 1)

    def test_wallet_guard_allows_clean_tracked_weather_wallet(self):
        report = audit_wallet_integrity(
            activity_rows=[_weather_activity()],
            position_rows=[_weather_position()],
            tracked_weather_market_ids={"weather-1"},
            require_clean_wallet=True,
            allow_orphaned_positions=False,
        )

        self.assertTrue(report["ready"])
        self.assertIsNone(report["reason"])
        self.assertEqual(report["stats"]["weather_open_positions_count"], 1)

    def test_entry_invariant_rejects_single_sided_plan(self):
        candidate = {"market_id": "weather-1"}
        plan = {
            "market_id": "weather-1",
            "event_slug": "highest-temperature-in-rome-on-march-26-2026-16c",
            "question": "Will the highest temperature in Rome be 16C?",
            "first_side": "yes",
            "second_side": "yes",
            "yes_token_id": "yes-token",
            "no_token_id": "no-token",
            "condition_id": "weather-1",
            "target_shares": 10,
        }

        self.assertEqual(_entry_invariant_failure(candidate, plan), "entry_not_paired_yes_no")

    def test_startup_telemetry_exposes_caps_and_guard_flags(self):
        telemetry = build_startup_telemetry(
            config_path="/tmp/weather.json",
            dry_run=False,
            bot_config={"strategy_name": "coldmath_inventory_rebalancing_merge_v2"},
        )

        self.assertEqual(telemetry["sequence_budget_usd"], weather_config.DEFAULT_SEQUENCE_BUDGET_USD)
        self.assertEqual(telemetry["max_total_exposure_usd"], weather_config.DEFAULT_MAX_TOTAL_EXPOSURE_USD)
        self.assertEqual(telemetry["daily_loss_limit_usd"], weather_config.DEFAULT_DAILY_LOSS_LIMIT_USD)
        self.assertEqual(telemetry["total_spend_limit_usd"], weather_config.DEFAULT_TOTAL_SPEND_LIMIT_USD)
        self.assertEqual(telemetry["require_clean_wallet"], weather_config.REQUIRE_CLEAN_WALLET)
        self.assertEqual(telemetry["allow_orphaned_positions"], weather_config.ALLOW_ORPHANED_POSITIONS)
        self.assertTrue(telemetry["code_fingerprint"])
        self.assertTrue(telemetry["config_fingerprint"])

    def test_cycle_status_message_includes_wallet_guard_block(self):
        message = _cycle_status_message(
            {
                "balance": 10,
                "daily_realized_pnl": 0,
                "total_spent_usd": 12.5,
                "total_spend_limit_usd": 30,
                "active_positions": 0,
                "active_exposure_usd": 0,
                "context_count": 1,
                "market_count": 5,
                "candidate_count": 0,
                "near_miss_count": 2,
                "entry_attempts": 0,
                "stand_down_reason": "foreign_open_positions_detected",
                "wallet_guard": {
                    "ready": False,
                    "reason": "foreign_open_positions_detected",
                    "stats": {
                        "foreign_open_positions_count": 2,
                        "foreign_activity_count": 7,
                        "orphaned_weather_positions_count": 1,
                    },
                },
            }
        )

        self.assertIn("guard=blocked:foreign_open_positions_detected", message)
        self.assertIn("spent=12.50/30.00", message)
        self.assertIn("foreign_positions=2", message)
        self.assertIn("foreign_activity=7", message)
        self.assertIn("orphaned_weather=1", message)


if __name__ == "__main__":
    unittest.main()
