import unittest
from datetime import UTC, datetime

from weather.parser import parse_weather_event


class WeatherParserTests(unittest.TestCase):
    def setUp(self):
        self.station_rows = {
            "london": {
                "city_key": "london",
                "city": "London",
                "station_code": "EGLC",
                "station_name": "London City Airport",
                "lat": 51.5,
                "lon": 0.05,
                "timezone": "Europe/London",
                "verified": True,
            },
            "hong-kong": {
                "city_key": "hong-kong",
                "city": "Hong Kong",
                "station_code": "HKO",
                "timezone": "Asia/Hong_Kong",
                "verified": False,
            },
        }

    def test_parse_whole_degree_wunderground_event(self):
        event = {
            "id": "evt-1",
            "slug": "highest-temperature-in-london-on-march-22-2026",
            "title": "Highest temperature in London on March 22 2026?",
            "description": (
                "This market will resolve according to the highest temperature posted on "
                "Weather Underground for station EGLC. The reported high will be rounded "
                "to the nearest whole degree Celsius."
            ),
            "resolutionSource": "https://www.wunderground.com/history/daily/gb/london/EGLC",
            "negRisk": True,
            "liquidity": "25000",
            "markets": [
                {
                    "conditionId": "m-low",
                    "groupItemTitle": "12°C or below",
                    "question": "12°C or below?",
                    "active": True,
                    "endDate": "2026-03-22T23:59:00Z",
                },
                {
                    "conditionId": "m-mid",
                    "groupItemTitle": "13°C",
                    "question": "13°C?",
                    "active": True,
                    "endDate": "2026-03-22T23:59:00Z",
                },
                {
                    "conditionId": "m-high",
                    "groupItemTitle": "14°C or higher",
                    "question": "14°C or higher?",
                    "active": True,
                    "endDate": "2026-03-22T23:59:00Z",
                },
            ],
        }

        parsed = parse_weather_event(
            event,
            self.station_rows,
            now=datetime(2026, 3, 22, 8, 0, tzinfo=UTC),
        )

        self.assertIsNotNone(parsed)
        self.assertTrue(parsed.eligible)
        self.assertEqual(parsed.city, "London")
        self.assertEqual(parsed.station_code, "EGLC")
        self.assertEqual(parsed.unit, "C")
        self.assertEqual(parsed.rule_family, "wunderground_daily")
        self.assertEqual(parsed.local_date.isoformat(), "2026-03-22")
        self.assertEqual(parsed.markets[0].bucket_high, 12.0)
        self.assertEqual(parsed.markets[1].bucket_low, 13.0)
        self.assertEqual(parsed.markets[1].bucket_high, 13.0)
        self.assertIsNone(parsed.markets[2].bucket_high)

    def test_parse_one_decimal_event_is_ineligible_for_pilot(self):
        event = {
            "id": "evt-2",
            "slug": "highest-temperature-in-hong-kong-on-march-22-2026",
            "title": "Highest temperature in Hong Kong on March 22 2026?",
            "description": (
                "This market will resolve using the Hong Kong Observatory. "
                "The official high is measured to one decimal place."
            ),
            "resolutionSource": "https://www.hko.gov.hk/en/cis/dailyExtract.htm",
            "negRisk": True,
            "liquidity": "22000",
            "markets": [
                {
                    "conditionId": "m1",
                    "groupItemTitle": "24.0°C or below",
                    "question": "24.0°C or below?",
                    "active": True,
                    "endDate": "2026-03-22T23:59:00Z",
                }
            ],
        }

        parsed = parse_weather_event(
            event,
            self.station_rows,
            now=datetime(2026, 3, 22, 8, 0, tzinfo=UTC),
        )

        self.assertIsNotNone(parsed)
        self.assertFalse(parsed.eligible)
        self.assertIn("resolution is not whole-degree", parsed.eligibility_reason)


if __name__ == "__main__":
    unittest.main()
