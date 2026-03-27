import unittest
from datetime import UTC, date, datetime

from weather.models import complete_neg_risk_quotes
from weather.storage import _row_effectively_eligible, _row_effectively_live


class WeatherStorageTests(unittest.TestCase):
    def test_same_day_market_with_stale_noon_end_is_still_live(self):
        row = {
            "local_date": date(2026, 3, 25),
            "timezone": "America/Los_Angeles",
            "ended_at": datetime(2026, 3, 25, 12, 0, tzinfo=UTC),
        }

        self.assertTrue(
            _row_effectively_live(
                row,
                now=datetime(2026, 3, 25, 22, 7, tzinfo=UTC),
            )
        )

    def test_outside_lookahead_reason_is_overridden_when_effective_close_is_in_window(self):
        row = {
            "eligible": False,
            "eligibility_reason": "outside 72h lookahead",
            "local_date": date(2026, 3, 25),
            "timezone": "America/Los_Angeles",
            "ended_at": datetime(2026, 3, 25, 12, 0, tzinfo=UTC),
        }

        self.assertTrue(
            _row_effectively_eligible(
                row,
                now=datetime(2026, 3, 25, 22, 7, tzinfo=UTC),
            )
        )

    def test_non_window_eligibility_reasons_stay_ineligible(self):
        row = {
            "eligible": False,
            "eligibility_reason": "missing station mapping; outside 72h lookahead",
            "local_date": date(2026, 3, 25),
            "timezone": "America/Los_Angeles",
            "ended_at": datetime(2026, 3, 25, 12, 0, tzinfo=UTC),
        }

        self.assertFalse(
            _row_effectively_eligible(
                row,
                now=datetime(2026, 3, 25, 22, 7, tzinfo=UTC),
            )
        )

    def test_complete_neg_risk_quotes_fills_missing_complementary_quotes(self):
        completed = complete_neg_risk_quotes(
            neg_risk=True,
            yes_bid=0.04,
            yes_ask=0.05,
            yes_mid=None,
            yes_bid_size=120.0,
            yes_ask_size=80.0,
            no_bid=None,
            no_ask=None,
            no_mid=None,
            no_bid_size=None,
            no_ask_size=None,
        )

        self.assertEqual(completed["no_bid"], 0.95)
        self.assertEqual(completed["no_ask"], 0.96)
        self.assertEqual(completed["yes_mid"], 0.045)
        self.assertEqual(completed["no_mid"], 0.955)
        self.assertEqual(completed["no_bid_size"], 80.0)
        self.assertEqual(completed["no_ask_size"], 120.0)


if __name__ == "__main__":
    unittest.main()
