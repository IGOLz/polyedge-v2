import unittest
from datetime import UTC, date, datetime

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


if __name__ == "__main__":
    unittest.main()
