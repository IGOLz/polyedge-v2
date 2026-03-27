from __future__ import annotations

import unittest
from datetime import UTC, date, datetime

from analysis.coldmath_public_parity import (
    _apply_size_model,
    _classify_miss_bucket,
    _clip_covered_window,
    _compare_replay_to_public,
    _deployment_gate_result,
    _group_public_trade_sequences,
    _infer_public_sequence_label,
    _requested_window,
)


class ColdMathPublicParityTests(unittest.TestCase):
    def test_clip_covered_window_intersects_requested_and_recorded_ranges(self):
        requested_start = datetime(2026, 3, 25, 0, 0, tzinfo=UTC)
        requested_end = datetime(2026, 3, 27, 0, 0, tzinfo=UTC)
        coverage_start = datetime(2026, 3, 25, 8, 40, tzinfo=UTC)
        coverage_end = datetime(2026, 3, 26, 23, 43, tzinfo=UTC)

        clipped = _clip_covered_window(
            requested_start=requested_start,
            requested_end=requested_end,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
        )

        self.assertEqual(clipped["covered_start_utc"], coverage_start)
        self.assertEqual(clipped["covered_end_utc"], coverage_end)

    def test_group_public_trade_sequences_splits_on_gap_and_condition(self):
        rows = [
            {
                "timestamp_utc": datetime(2026, 3, 25, 22, 0, 0, tzinfo=UTC),
                "condition_id": "cond-1",
                "event_slug": "highest-temperature-in-rome-on-march-25-2026",
                "city": "Rome",
                "local_date": "2026-03-25",
                "trade_type": "buy",
                "outcome": "yes",
                "price": 0.04,
                "size": 10.0,
            },
            {
                "timestamp_utc": datetime(2026, 3, 25, 22, 1, 0, tzinfo=UTC),
                "condition_id": "cond-1",
                "event_slug": "highest-temperature-in-rome-on-march-25-2026",
                "city": "Rome",
                "local_date": "2026-03-25",
                "trade_type": "buy",
                "outcome": "no",
                "price": 0.95,
                "size": 10.0,
            },
            {
                "timestamp_utc": datetime(2026, 3, 25, 22, 5, 0, tzinfo=UTC),
                "condition_id": "cond-1",
                "event_slug": "highest-temperature-in-rome-on-march-25-2026",
                "city": "Rome",
                "local_date": "2026-03-25",
                "trade_type": "buy",
                "outcome": "yes",
                "price": 0.05,
                "size": 10.0,
            },
            {
                "timestamp_utc": datetime(2026, 3, 25, 22, 0, 30, tzinfo=UTC),
                "condition_id": "cond-2",
                "event_slug": "highest-temperature-in-milan-on-march-25-2026",
                "city": "Milan",
                "local_date": "2026-03-25",
                "trade_type": "buy",
                "outcome": "yes",
                "price": 0.03,
                "size": 8.0,
            },
        ]

        grouped = _group_public_trade_sequences(
            rows,
            gap_seconds=120,
            catalog_by_event={},
            quote_series={},
            quote_window_seconds=180,
        )

        self.assertEqual(len(grouped), 3)
        self.assertEqual(grouped[0]["trade_count"], 2)
        self.assertEqual(grouped[1]["condition_id"], "cond-2")
        self.assertEqual(grouped[2]["trade_count"], 1)

    def test_infer_public_sequence_label_detects_paired_under_par(self):
        rows = [
            {"trade_type": "buy", "outcome": "yes", "price": 0.49, "size": 10.0},
            {"trade_type": "buy", "outcome": "no", "price": 0.50, "size": 10.0},
        ]

        label = _infer_public_sequence_label(rows, None)

        self.assertEqual(label, "paired_under_par")

    def test_infer_public_sequence_label_detects_asymmetric_paired_accumulation(self):
        rows = [
            {"trade_type": "buy", "outcome": "yes", "price": 0.05, "size": 600.0},
            {"trade_type": "buy", "outcome": "no", "price": 0.95, "size": 400.0},
        ]

        label = _infer_public_sequence_label(rows, None)

        self.assertEqual(label, "asymmetric_paired_accumulation")

    def test_apply_size_model_caps_by_ask_fraction_and_reentry_scale(self):
        plan = {
            "playbook_key": "cheap_bucket_accumulation",
            "condition_id": "cond-1",
            "side": "yes",
            "price": 0.02,
            "target_shares": 500,
            "sequence_budget_usd": 5.0,
        }
        candidate = {
            "available_size": 300.0,
        }
        size_model = {
            "repeat_entry_cooldown_seconds": 60,
            "per_playbook": {
                "cheap_bucket_accumulation": {
                    "max_ask_size_fraction": 0.5,
                    "reentry_scale": 0.5,
                    "sequence_budget_usd": 3.0,
                }
            },
        }

        adjusted = _apply_size_model(
            plan,
            candidate=candidate,
            size_model=size_model,
            entry_counts={("cond-1", "yes", "cheap_bucket_accumulation"): 1},
        )

        self.assertIsNotNone(adjusted)
        self.assertEqual(adjusted["target_shares"], 150)
        self.assertEqual(adjusted["sequence_budget_usd"], 3.0)

    def test_apply_size_model_falls_back_to_budget_when_quote_size_is_missing(self):
        plan = {
            "playbook_key": "paired_under_par",
            "condition_id": "cond-1",
            "yes_price": 0.972,
            "no_price": 0.027,
            "combined_cost": 0.999,
            "target_shares": 50,
            "sequence_budget_usd": 50.0,
        }
        candidate = {
            "yes_ask": 0.972,
            "no_ask": 0.027,
            "yes_ask_size": None,
            "no_ask_size": None,
        }
        size_model = {
            "repeat_entry_cooldown_seconds": 60,
            "per_playbook": {
                "paired_under_par": {
                    "max_ask_size_fraction": 1.0,
                    "reentry_scale": 1.0,
                    "sequence_budget_usd": 50.0,
                }
            },
        }

        adjusted = _apply_size_model(
            plan,
            candidate=candidate,
            size_model=size_model,
            entry_counts={},
        )

        self.assertIsNotNone(adjusted)
        self.assertEqual(adjusted["target_shares"], 50)

    def test_apply_size_model_supports_asymmetric_pair_targets(self):
        plan = {
            "playbook_key": "asymmetric_paired_accumulation",
            "condition_id": "cond-1",
            "yes_price": 0.05,
            "no_price": 0.95,
            "combined_cost": 1.0,
            "target_shares": 20,
            "yes_target_shares": 100,
            "no_target_shares": 100,
            "sequence_budget_usd": 100.0,
        }
        candidate = {
            "yes_ask_size": None,
            "no_ask_size": None,
        }
        size_model = {
            "repeat_entry_cooldown_seconds": 60,
            "per_playbook": {
                "asymmetric_paired_accumulation": {
                    "max_ask_size_fraction": 1.0,
                    "reentry_scale": 1.0,
                    "sequence_budget_usd": 100.0,
                    "dominant_leg_budget_fraction": 0.95,
                }
            },
        }

        adjusted = _apply_size_model(
            plan,
            candidate=candidate,
            size_model=size_model,
            entry_counts={},
        )

        self.assertIsNotNone(adjusted)
        self.assertEqual(adjusted["yes_target_shares"], 100)
        self.assertEqual(adjusted["no_target_shares"], 100)
        self.assertEqual(adjusted["target_shares"], 100)

    def test_compare_replay_to_public_reports_match_and_size_error(self):
        public_rows = [
            {
                "timestamp_utc": datetime(2026, 3, 25, 22, 0, 0, tzinfo=UTC),
                "condition_id": "cond-1",
                "event_slug": "event-1",
                "city": "Rome",
                "bucket_label": "16C",
                "trade_type": "buy",
                "outcome": "yes",
                "public_playbook": "cheap_bucket_accumulation",
                "size": 100.0,
            }
        ]
        replay_rows = [
            {
                "timestamp_utc": datetime(2026, 3, 25, 22, 0, 20, tzinfo=UTC),
                "condition_id": "cond-1",
                "event_slug": "event-1",
                "city": "Rome",
                "bucket_label": "16C",
                "trade_type": "buy",
                "outcome": "yes",
                "playbook_key": "cheap_bucket_accumulation",
                "size": 120.0,
            }
        ]

        matched_rows, metrics = _compare_replay_to_public(
            public_rows=public_rows,
            replay_rows=replay_rows,
            match_window_seconds=60.0,
        )

        self.assertEqual(len(matched_rows), 1)
        self.assertTrue(matched_rows[0]["matched"])
        self.assertAlmostEqual(matched_rows[0]["size_error_ratio"], 0.2)
        self.assertEqual(metrics["covered_trade_match_rate_condition_side"], 1.0)

    def test_classify_miss_bucket_prefers_size_mismatch_for_near_match(self):
        bucket = _classify_miss_bucket(
            public_row={"public_playbook": "cheap_bucket_accumulation"},
            trade_time_row={"match_reason": "matched"},
            nearest_match={
                "within_match_window": True,
                "playbook_key": "cheap_bucket_accumulation",
                "size_error_ratio": 0.4,
            },
        )

        self.assertEqual(bucket, "order_size_model_mismatch")

    def test_deployment_gate_fails_on_threshold_breach(self):
        result = _deployment_gate_result(
            holdout_metrics={
                "covered_trade_match_rate_condition_side": 0.69,
                "covered_trade_match_rate_playbook": 0.60,
                "median_entry_time_delta_seconds": 40.0,
                "median_size_error_ratio": 0.30,
            },
            miss_rows=[
                {"condition_id": "cond-1", "miss_bucket": "unsupported_public_behavior"},
                {"condition_id": "cond-1", "miss_bucket": "unsupported_public_behavior"},
                {"condition_id": "cond-1", "miss_bucket": "matched"},
                {"condition_id": "cond-1", "miss_bucket": "matched"},
            ],
        )

        self.assertFalse(result["passed"])

    def test_requested_window_accepts_explicit_iso_range(self):
        window = _requested_window(
            48.0,
            window_start="2026-03-26T21:00:00+00:00",
            window_end="2026-03-26T23:00:00+00:00",
        )

        self.assertEqual(window["requested_start_utc"], datetime(2026, 3, 26, 21, 0, tzinfo=UTC))
        self.assertEqual(window["requested_end_utc"], datetime(2026, 3, 26, 23, 0, tzinfo=UTC))


if __name__ == "__main__":
    unittest.main()
