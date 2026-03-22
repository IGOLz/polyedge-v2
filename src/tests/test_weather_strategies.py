import unittest
from datetime import UTC, date, datetime

from weather.models import WeatherBucketMarket, WeatherMarketContext, WeatherSnapshot
from weather.strategies import evaluate_weather_decision


def _market(
    market_id: str,
    label: str,
    low,
    high,
    order: int,
    *,
    yes_bid: float,
    yes_ask: float,
    no_bid: float,
    no_ask: float,
) -> WeatherBucketMarket:
    now = datetime(2026, 3, 22, 15, 0, tzinfo=UTC)
    return WeatherBucketMarket(
        market_id=market_id,
        event_id="evt-1",
        event_slug="highest-temperature-in-london-on-march-22-2026",
        market_slug=market_id,
        question=label,
        city="London",
        city_key="london",
        station_code="EGLC",
        station_name="London City Airport",
        lat=51.5,
        lon=0.05,
        timezone="UTC",
        local_date=date(2026, 3, 22),
        unit="C",
        bucket_label=label,
        bucket_low=low,
        bucket_high=high,
        bucket_order=order,
        rule_family="wunderground_daily",
        resolution_source_url="https://example.test",
        resolution_precision_scale=0,
        neg_risk=True,
        active=True,
        eligible=True,
        eligibility_reason=None,
        yes_token_id=f"{market_id}-yes",
        no_token_id=f"{market_id}-no",
        started_at=now,
        ended_at=now,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        yes_mid=round((yes_bid + yes_ask) / 2, 4),
        yes_bid_size=100.0,
        yes_ask_size=100.0,
        no_bid=no_bid,
        no_ask=no_ask,
        no_mid=round((no_bid + no_ask) / 2, 4),
        no_bid_size=100.0,
        no_ask_size=100.0,
        latest_quote_time=datetime(2026, 3, 22, 14, 59, tzinfo=UTC),
    )


class WeatherStrategyTests(unittest.TestCase):
    def _context(self, markets):
        return WeatherMarketContext(
            event_id="evt-1",
            event_slug="highest-temperature-in-london-on-march-22-2026",
            title="Highest temperature in London on 2026-03-22",
            city="London",
            city_key="london",
            station_code="EGLC",
            station_name="London City Airport",
            lat=51.5,
            lon=0.05,
            timezone="UTC",
            local_date=date(2026, 3, 22),
            unit="C",
            rule_family="wunderground_daily",
            resolution_source_url="https://example.test",
            verified_station=True,
            observation_provider="aviationweather",
            forecast_provider="open_meteo",
            markets=markets,
        )

    def test_w1_ensemble_probabilities_sum_and_signal(self):
        markets = [
            _market("m1", "12°C or below", None, 12.0, 0, yes_bid=0.08, yes_ask=0.10, no_bid=0.89, no_ask=0.91),
            _market("m2", "13°C", 13.0, 13.0, 1, yes_bid=0.63, yes_ask=0.65, no_bid=0.33, no_ask=0.35),
            _market("m3", "14°C or higher", 14.0, None, 2, yes_bid=0.08, yes_ask=0.10, no_bid=0.89, no_ask=0.91),
        ]
        payload = {
            "hourly": {
                "temperature_2m_member01": [13],
                "temperature_2m_member02": [13],
                "temperature_2m_member03": [13],
                "temperature_2m_member04": [13],
                "temperature_2m_member05": [13],
                "temperature_2m_member06": [13],
                "temperature_2m_member07": [13],
                "temperature_2m_member08": [13],
                "temperature_2m_member09": [12],
                "temperature_2m_member10": [14],
            }
        }
        snapshot = WeatherSnapshot(
            context=self._context(markets),
            captured_at=datetime(2026, 3, 22, 15, 0, tzinfo=UTC),
            forecasts=[
                {
                    "provider": "open_meteo",
                    "model": "ensemble",
                    "run_at": datetime(2026, 3, 22, 14, 45, tzinfo=UTC),
                    "payload_json": payload,
                }
            ],
            recent_forecasts=[
                {
                    "provider": "open_meteo",
                    "model": "ensemble",
                    "run_at": datetime(2026, 3, 22, 14, 45, tzinfo=UTC),
                    "payload_json": payload,
                }
            ],
        )

        decision = evaluate_weather_decision(snapshot)

        self.assertEqual(decision.signals[0].strategy_name, "W1_ensemble_fair_value")
        self.assertEqual(decision.signals[0].signal_data["market_id"], "m2")
        self.assertAlmostEqual(sum(decision.fair_probabilities.values()), 1.0, places=6)

    def test_w3_nowcast_marks_high_bucket_impossible(self):
        markets = [
            _market("m1", "16°C or below", None, 16.0, 0, yes_bid=0.10, yes_ask=0.12, no_bid=0.86, no_ask=0.88),
            _market("m2", "17°C", 17.0, 17.0, 1, yes_bid=0.92, yes_ask=0.94, no_bid=0.04, no_ask=0.06),
            _market("m3", "18°C or higher", 18.0, None, 2, yes_bid=0.16, yes_ask=0.18, no_bid=0.80, no_ask=0.82),
        ]
        ensemble_payload = {
            "hourly": {
                "temperature_2m_member01": [17],
                "temperature_2m_member02": [17],
                "temperature_2m_member03": [17],
                "temperature_2m_member04": [17],
            }
        }
        snapshot = WeatherSnapshot(
            context=self._context(markets),
            captured_at=datetime(2026, 3, 22, 15, 0, tzinfo=UTC),
            forecasts=[
                {
                    "provider": "open_meteo",
                    "model": "ensemble",
                    "run_at": datetime(2026, 3, 22, 14, 40, tzinfo=UTC),
                    "payload_json": ensemble_payload,
                },
                {
                    "provider": "open_meteo",
                    "model": "deterministic",
                    "run_at": datetime(2026, 3, 22, 14, 45, tzinfo=UTC),
                    "temp_hourly": {
                        "time": ["2026-03-22T15:00:00+00:00", "2026-03-22T16:00:00+00:00"],
                        "values": [17.0, 17.1],
                    },
                },
            ],
            recent_forecasts=[
                {
                    "provider": "open_meteo",
                    "model": "ensemble",
                    "run_at": datetime(2026, 3, 22, 14, 40, tzinfo=UTC),
                    "payload_json": ensemble_payload,
                }
            ],
            observations=[
                {"observed_at": datetime(2026, 3, 22, 14, 55, tzinfo=UTC), "temperature": 17.0},
                {"observed_at": datetime(2026, 3, 22, 13, 30, tzinfo=UTC), "temperature": 16.4},
            ],
        )

        decision = evaluate_weather_decision(snapshot)

        self.assertEqual(decision.signals[0].strategy_name, "W3_intraday_observation_nowcast")
        self.assertEqual(decision.signals[0].direction, "Down")
        self.assertEqual(decision.signals[0].signal_data["market_id"], "m3")


if __name__ == "__main__":
    unittest.main()
