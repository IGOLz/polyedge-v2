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

    def test_normalize_weather_trades_uses_unix_timestamp_when_timestamp_utc_missing(self):
        rows = [
            {
                "timestamp": int(datetime(2026, 3, 25, 22, 7, 9, tzinfo=UTC).timestamp()),
                "conditionId": "cond-1",
                "eventSlug": "highest-temperature-in-rome-on-march-25-2026",
                "slug": "highest-temperature-in-rome-on-march-25-2026-16c",
                "title": "Will the highest temperature in Rome be 16C on March 25?",
                "side": "BUY",
                "outcome": "Yes",
                "price": "0.05",
                "size": "100",
            }
        ]

        normalized = _normalize_weather_trades(rows)

        self.assertEqual(normalized[0]["timestamp_utc"], datetime(2026, 3, 25, 22, 7, 9, tzinfo=UTC))
        self.assertEqual(normalized[0]["condition_id"], "cond-1")
        self.assertEqual(normalized[0]["trade_type"], "buy")
        self.assertEqual(normalized[0]["outcome"], "yes")
        self.assertEqual(normalized[0]["size"], 100.0)

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

    def test_nearest_quote_row_prefers_richer_snapshot_when_timestamps_are_nearby(self):
        target = datetime(2026, 3, 25, 22, 7, 9, tzinfo=UTC)
        series = {
            "times": [
                datetime(2026, 3, 25, 22, 7, 9, tzinfo=UTC),
                datetime(2026, 3, 25, 22, 7, 8, 900000, tzinfo=UTC),
            ],
            "rows": [
                {"time": datetime(2026, 3, 25, 22, 7, 9, tzinfo=UTC), "best_ask": None, "best_bid": None, "mid": 0.05},
                {
                    "time": datetime(2026, 3, 25, 22, 7, 8, 900000, tzinfo=UTC),
                    "best_ask": 0.06,
                    "best_bid": 0.05,
                    "best_ask_size": 100.0,
                    "best_bid_size": 90.0,
                    "mid": 0.055,
                },
            ],
        }

        row = _nearest_quote_row(series, captured_at=target, quote_window_seconds=10)

        self.assertEqual(row["best_ask"], 0.06)
        self.assertEqual(row["best_ask_size"], 100.0)

    def test_nearest_quote_row_prefers_narrow_spread_book_over_pathological_full_depth(self):
        target = datetime(2026, 3, 26, 21, 25, 33, tzinfo=UTC)
        series = {
            "times": [
                datetime(2026, 3, 26, 21, 25, 30, 28221, tzinfo=UTC),
                datetime(2026, 3, 26, 21, 25, 30, 32462, tzinfo=UTC),
            ],
            "rows": [
                {
                    "time": datetime(2026, 3, 26, 21, 25, 30, 28221, tzinfo=UTC),
                    "best_bid": 0.972,
                    "best_ask": 0.973,
                    "mid": 0.9725,
                    "best_bid_size": None,
                    "best_ask_size": None,
                },
                {
                    "time": datetime(2026, 3, 26, 21, 25, 30, 32462, tzinfo=UTC),
                    "best_bid": 0.001,
                    "best_ask": 0.999,
                    "mid": 0.5,
                    "best_bid_size": 4265.59,
                    "best_ask_size": 2098.25,
                },
            ],
        }

        row = _nearest_quote_row(series, captured_at=target, quote_window_seconds=10)

        self.assertEqual(row["best_bid"], 0.972)
        self.assertEqual(row["best_ask"], 0.973)

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
