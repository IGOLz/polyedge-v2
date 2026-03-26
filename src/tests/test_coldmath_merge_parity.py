from __future__ import annotations

import unittest
from datetime import UTC, datetime

from analysis.coldmath_merge_parity import (
    _classify_merge_parity,
    _classify_trade_group_pattern,
)


class ColdMathMergeParityTests(unittest.TestCase):
    def test_classify_trade_group_pattern_detects_under_par_pair(self):
        rows = [
            {"price": 0.02},
            {"price": 0.94},
            {"price": 0.05},
        ]

        self.assertEqual(_classify_trade_group_pattern(rows), "paired_complementary_under_par")

    def test_classify_merge_parity_uses_guard_when_no_scan_row_exists(self):
        trade_rows = [
            {
                "timestamp_utc": datetime(2026, 3, 25, 22, 7, 9, tzinfo=UTC),
                "condition_id": "cond-1",
                "event_slug": "highest-temperature-in-san-francisco-on-march-25-2026",
                "city": "san francisco",
                "local_date": "2026-03-25",
                "bucket_label": "68-69°F",
                "price": 0.02,
                "size": 10.76,
            }
        ]
        summary_rows = [
            {
                "logged_at": datetime(2026, 3, 25, 22, 7, 8, tzinfo=UTC),
                "data": {"stand_down_reason": "foreign_wallet_activity_detected"},
            }
        ]

        result = _classify_merge_parity(
            trade_rows=trade_rows,
            market_scan_rows=[],
            summary_rows=summary_rows,
            catalog_rows=[],
            match_window_seconds=120.0,
        )

        self.assertEqual(result["classified_rows"][0]["root_cause"], "guard_blocked:foreign_wallet_activity_detected")


if __name__ == "__main__":
    unittest.main()
