from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from trading_weather.clone_config import normalize_clone_bot_config
from trading_weather.clone_engine import build_clone_runtime, plan_paired_entry
from trading_weather.paper_runtime import (
    _paper_build_equity_snapshot,
    _paper_candidate_signature,
    _paper_candidate_enabled,
    _paper_fill_quote,
    _paper_fill_shares,
    _paper_position_mark_value,
    _paper_resolution_side,
)
from trading_weather.main import run_clone


class TradingWeatherPaperTests(unittest.TestCase):
    def test_normalize_clone_config_adds_paper_defaults(self):
        config = normalize_clone_bot_config(
            {
                "mode": "coldmath_weather_clone",
                "strategy_name": "paper-test",
                "execution_mode": "paper_live",
                "playbooks": {
                    "paired_under_par": {
                        "enabled": True,
                        "shadow_enabled": True,
                        "live_enabled": True,
                    }
                },
            }
        )

        self.assertEqual(config["execution_mode"], "paper_live")
        self.assertEqual(config["paper"]["fill_model"], "touch_realistic")
        self.assertGreater(config["paper"]["snapshot_interval_seconds"], 0.0)
        self.assertFalse(config["paper"]["execute_shadow_playbooks"])

    def test_paper_fill_shares_caps_to_top_of_book(self):
        self.assertEqual(_paper_fill_shares(target_shares=25, available_size=10.9), 10)
        self.assertEqual(_paper_fill_shares(target_shares=8, available_size=25.0), 8)
        self.assertEqual(_paper_fill_shares(target_shares=8, available_size=None), 8)

    def test_paper_fill_quote_uses_generic_directional_price_and_size(self):
        plan = {
            "side": "yes",
            "price": 0.001,
            "available_size": 3000.0,
            "quote_snapshot": {
                "yes_ask": 0.001,
                "yes_ask_size": 3000.0,
            },
        }

        price, available_size = _paper_fill_quote(plan, side="yes")

        self.assertEqual(price, 0.001)
        self.assertEqual(available_size, 3000.0)

    def test_paper_candidate_enabled_defaults_to_live_only(self):
        config = normalize_clone_bot_config(
            {
                "mode": "coldmath_weather_clone",
                "strategy_name": "paper-test",
                "execution_mode": "paper_live",
                "playbooks": {
                    "asymmetric_paired_accumulation": {
                        "enabled": True,
                        "shadow_enabled": True,
                        "live_enabled": False,
                    }
                },
            }
        )

        self.assertFalse(_paper_candidate_enabled(config, "asymmetric_paired_accumulation"))

    def test_paper_candidate_enabled_can_opt_into_shadow_playbooks(self):
        config = normalize_clone_bot_config(
            {
                "mode": "coldmath_weather_clone",
                "strategy_name": "paper-test",
                "execution_mode": "paper_live",
                "paper": {
                    "execute_shadow_playbooks": True,
                },
                "playbooks": {
                    "asymmetric_paired_accumulation": {
                        "enabled": True,
                        "shadow_enabled": True,
                        "live_enabled": False,
                    }
                },
            }
        )

        self.assertTrue(_paper_candidate_enabled(config, "asymmetric_paired_accumulation"))

    def test_paper_candidate_signature_prefers_selected_candidate(self):
        report = {
            "candidates": [
                {
                    "playbook_key": "paired_under_par",
                    "market_id": "m1",
                    "candidate_score": 10.0,
                    "combined_cost": 1.01,
                },
                {
                    "playbook_key": "asymmetric_paired_accumulation",
                    "market_id": "m2",
                    "candidate_score": 999.0,
                    "combined_cost": 1.001,
                    "paper_eligible": True,
                },
            ]
        }

        signature = _paper_candidate_signature(report)

        self.assertIsNotNone(signature)
        self.assertIn("asymmetric_paired_accumulation", signature)
        self.assertIn("m2", signature)

    def test_asymmetric_pair_plan_allows_small_complement_leg(self):
        config = normalize_clone_bot_config(
            {
                "mode": "coldmath_weather_clone",
                "strategy_name": "paper-test",
                "execution_mode": "paper_live",
                "runtime": {
                    "sequence_budget_usd": 8.0,
                    "max_total_exposure_usd": 30.0,
                    "min_expected_edge_usd": 0.03,
                },
                "playbooks": {
                    "asymmetric_paired_accumulation": {
                        "enabled": True,
                        "shadow_enabled": True,
                        "live_enabled": True,
                        "sequence_budget_usd": 8.0,
                        "synthetic_pair_cost_lte": 1.02,
                        "dominant_leg_budget_fraction": 0.94,
                    }
                },
            }
        )
        runtime = build_clone_runtime(config, dry_run=False)
        candidate = {
            "playbook_key": "asymmetric_paired_accumulation",
            "market_id": "m1",
            "event_id": "e1",
            "event_slug": "event",
            "city": "dallas",
            "local_date": "2026-04-01",
            "bucket_label": "72-73F",
            "combined_cost": 1.001,
            "yes_ask": 0.002,
            "no_ask": 0.999,
            "yes_ask_size": 4289.2,
            "no_ask_size": 3403.95,
            "candidate_score": 83313.378225,
            "yes_token_id": "yes",
            "no_token_id": "no",
        }

        plan = plan_paired_entry(candidate, runtime, active_exposure_usd=0.0)

        self.assertIsNotNone(plan)
        self.assertGreater(plan["yes_target_shares"], plan["no_target_shares"])
        self.assertGreater(plan["no_target_shares"], 0)

    def test_paper_position_mark_value_marks_pairs_at_par_and_residual_at_bid(self):
        market_lookup = {
            "m1": SimpleNamespace(
                yes_bid=0.72,
                yes_mid=0.74,
                no_bid=0.21,
                no_mid=0.24,
            )
        }
        position = {
            "market_id": "m1",
            "yes_shares": 10.0,
            "no_shares": 8.0,
        }

        value = _paper_position_mark_value(position, market_lookup)

        self.assertAlmostEqual(value, 8.0 + (2.0 * 0.72), places=6)

    def test_paper_equity_snapshot_uses_realized_plus_open_marks(self):
        market_lookup = {
            "m1": SimpleNamespace(
                yes_bid=0.60,
                yes_mid=0.61,
                no_bid=0.38,
                no_mid=0.39,
            )
        }
        positions = [
            {
                "market_id": "m1",
                "yes_shares": 4.0,
                "no_shares": 2.0,
                "realized_exit_value_usd": 2.0,
                "total_entry_cost": 4.5,
            }
        ]

        snapshot = _paper_build_equity_snapshot(
            positions,
            market_lookup,
            realized_pnl_usd=1.25,
            entry_notional_usd=4.5,
            exit_notional_usd=2.0,
        )

        self.assertAlmostEqual(snapshot["unrealized_pnl_usd"], 0.7, places=6)
        self.assertAlmostEqual(snapshot["equity_pnl_usd"], 1.95, places=6)

    def test_paper_resolution_side_maps_yes_no(self):
        self.assertEqual(_paper_resolution_side({"final_outcome": "Yes"}), "yes")
        self.assertEqual(_paper_resolution_side({"final_outcome": "No"}), "no")
        self.assertIsNone(_paper_resolution_side({"final_outcome": "maybe"}))

    def test_run_clone_routes_paper_live_to_paper_runtime(self):
        config_path = Path(__file__).resolve().parents[1] / "results" / "wallet_forensics" / "coldmath_resume_smoke_v3" / "wallet_coldmath_clone_paper_bot_config.json"
        mocked = AsyncMock()
        with patch("trading_weather.paper_runtime.run_clone_paper", mocked):
            asyncio.run(run_clone(config_path=str(config_path), dry_run=False, once=True))
        mocked.assert_awaited_once()
