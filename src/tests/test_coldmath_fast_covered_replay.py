from __future__ import annotations

import unittest
from datetime import UTC, datetime

from analysis.coldmath_fast_covered_replay import (
    _apply_public_exit_trade,
    _simulate_pair_trade_fill,
    _window_trade_ledger_pnl,
)


class ColdMathFastCoveredReplayTests(unittest.TestCase):
    def test_simulate_pair_trade_fill_accumulates_single_side_inventory(self):
        active_positions: list[dict[str, object]] = []
        rows, created = _simulate_pair_trade_fill(
            plan={
                "playbook_key": "asymmetric_paired_accumulation",
                "condition_id": "cond-1",
                "event_slug": "event-1",
                "city": "Rome",
                "local_date": "2026-03-25",
                "bucket_label": "74-75F",
            },
            trade={
                "condition_id": "cond-1",
                "outcome": "yes",
                "size": 100,
                "price": 0.95,
            },
            captured_at=datetime(2026, 3, 25, 12, 0, tzinfo=UTC),
            active_positions=active_positions,
            position_id=1,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["trade_type"], "buy")
        self.assertEqual(rows[0]["outcome"], "yes")
        self.assertEqual(created, 1)
        self.assertEqual(len(active_positions), 1)
        self.assertEqual(active_positions[0]["status"], "open_pair_inventory")
        self.assertEqual(active_positions[0]["yes_shares"], 100.0)
        self.assertEqual(active_positions[0]["no_shares"], 0.0)
        self.assertEqual(active_positions[0]["yes_lots"], [{"shares": 100.0, "entry_price": 0.95}])

        rows, created = _simulate_pair_trade_fill(
            plan={
                "playbook_key": "asymmetric_paired_accumulation",
                "condition_id": "cond-1",
                "event_slug": "event-1",
                "city": "Rome",
                "local_date": "2026-03-25",
                "bucket_label": "74-75F",
            },
            trade={
                "condition_id": "cond-1",
                "outcome": "no",
                "size": 10,
                "price": 0.02,
            },
            captured_at=datetime(2026, 3, 25, 12, 1, tzinfo=UTC),
            active_positions=active_positions,
            position_id=2,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(created, 0)
        self.assertEqual(len(active_positions), 1)
        self.assertEqual(active_positions[0]["yes_shares"], 100.0)
        self.assertEqual(active_positions[0]["no_shares"], 10.0)
        self.assertEqual(active_positions[0]["no_lots"], [{"shares": 10.0, "entry_price": 0.02}])

    def test_apply_public_exit_trade_consumes_pair_inventory_before_directional_residual(self):
        captured_at = datetime(2026, 3, 25, 12, 15, tzinfo=UTC)
        exit_rows, positions = _apply_public_exit_trade(
            trade={
                "timestamp_utc": captured_at,
                "condition_id": "cond-1",
                "event_slug": "event-1",
                "city": "Rome",
                "local_date": "2026-03-25",
                "bucket_label": "74-75F",
                "trade_type": "redeem",
                "outcome": "paired",
                "size": 10,
                "price": 1.0,
            },
            active_positions=[
                {
                    "id": 1,
                    "market_id": "cond-1",
                    "event_slug": "event-1",
                    "status": "open_pair_inventory",
                    "closed_at": None,
                    "yes_lots": [{"shares": 100.0, "entry_price": 0.95}],
                    "no_lots": [{"shares": 10.0, "entry_price": 0.02}],
                    "yes_shares": 100.0,
                    "no_shares": 10.0,
                    "yes_entry_price": 0.95,
                    "no_entry_price": 0.02,
                    "total_entry_cost": 95.2,
                }
            ],
        )

        self.assertEqual(len(exit_rows), 1)
        self.assertEqual(exit_rows[0]["trade_type"], "redeem")
        self.assertEqual(exit_rows[0]["size"], 10)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["yes_shares"], 90.0)
        self.assertEqual(positions[0]["no_shares"], 0.0)
        self.assertEqual(positions[0]["yes_lots"], [{"shares": 90.0, "entry_price": 0.95}])
        self.assertEqual(positions[0]["no_lots"], [])
        self.assertEqual(positions[0]["closed_at"], None)

    def test_window_trade_ledger_pnl_marks_pairable_inventory_and_excludes_unattributed_sells(self):
        as_of = datetime(2026, 3, 27, 0, 0, tzinfo=UTC)
        quote_series = {
            ("cond-1", "Up"): {
                "times": [as_of],
                "rows": [{"time": as_of, "best_bid": 0.45}],
            },
            ("cond-1", "Down"): {
                "times": [as_of],
                "rows": [{"time": as_of, "best_bid": 0.55}],
            },
        }
        summary = _window_trade_ledger_pnl(
            rows=[
                {
                    "timestamp_utc": datetime(2026, 3, 25, 10, 0, tzinfo=UTC),
                    "condition_id": "cond-1",
                    "trade_type": "buy",
                    "outcome": "yes",
                    "size": 10,
                    "price": 0.4,
                },
                {
                    "timestamp_utc": datetime(2026, 3, 25, 10, 1, tzinfo=UTC),
                    "condition_id": "cond-1",
                    "trade_type": "buy",
                    "outcome": "no",
                    "size": 8,
                    "price": 0.5,
                },
                {
                    "timestamp_utc": datetime(2026, 3, 25, 10, 2, tzinfo=UTC),
                    "condition_id": "cond-2",
                    "trade_type": "sell",
                    "outcome": "yes",
                    "size": 5,
                    "price": 0.7,
                },
            ],
            catalog_by_event={},
            quote_series=quote_series,
            as_of=as_of,
        )

        self.assertEqual(summary["entry_notional_usd"], 8.0)
        self.assertEqual(summary["unattributed_exit_value_usd"], 3.5)
        self.assertEqual(summary["mergeable_value_usd"], 8.0)
        self.assertEqual(summary["residual_value_usd"], 0.9)
        self.assertEqual(summary["marked_pnl_usd"], 0.9)


if __name__ == "__main__":
    unittest.main()
