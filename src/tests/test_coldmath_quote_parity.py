from __future__ import annotations

import unittest
from datetime import UTC, datetime

from analysis.coldmath_quote_parity import (
    _event_slug,
    _match_clone_trade_row,
    _nearest_quote_row,
    _normalize_weather_trades,
)


class ColdMathQuoteParityTests(unittest.TestCase):
    def test_normalize_weather_trades_derives_event_slug_from_title(self):
        rows = [
            {
                "timestamp_utc": datetime(2026, 3, 25, 22, 7, 9, tzinfo=UTC),
                "title": "Will the highest temperature in San Francisco be between 68-69°F on March 25?",
                "event_slug": "",
                "city": "",
                "local_date": "",
                "bucket_label": "",
            }
        ]

        normalized = _normalize_weather_trades(rows)

        self.assertEqual(
            normalized[0]["event_slug"],
            "highest-temperature-in-san-francisco-on-march-25-2026",
        )
        self.assertEqual(normalized[0]["bucket_label"], "68-69°F")

    def test_nearest_quote_row_uses_closest_snapshot_inside_window(self):
        target = datetime(2026, 3, 25, 22, 7, 9, tzinfo=UTC)
        series = {
            "times": [
                datetime(2026, 3, 25, 22, 7, 5, tzinfo=UTC),
                datetime(2026, 3, 25, 22, 7, 11, tzinfo=UTC),
            ],
            "rows": [
                {"time": datetime(2026, 3, 25, 22, 7, 5, tzinfo=UTC), "best_ask": 0.05},
                {"time": datetime(2026, 3, 25, 22, 7, 11, tzinfo=UTC), "best_ask": 0.06},
            ],
        }

        row = _nearest_quote_row(series, captured_at=target, quote_window_seconds=10)

        self.assertEqual(row["best_ask"], 0.06)

    def test_match_clone_trade_row_prefers_paired_over_directional_side_matching(self):
        rows = [
            {"playbook_key": "tail_bucket_accumulation", "side": "yes", "qualifies": True},
            {"playbook_key": "paired_under_par", "side": None, "qualifies": True},
        ]

        matched = _match_clone_trade_row(rows, trade_outcome="yes")

        self.assertEqual(matched["playbook_key"], "paired_under_par")

    def test_event_slug_helper_formats_city_and_date(self):
        self.assertEqual(
            _event_slug("San Francisco", "2026-03-25"),
            "highest-temperature-in-san-francisco-on-march-25-2026",
        )


if __name__ == "__main__":
    unittest.main()
