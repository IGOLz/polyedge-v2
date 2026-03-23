from __future__ import annotations

import unittest
from datetime import UTC, date, datetime

from trading_weather.strategy import (
    build_runtime_config,
    compute_mergeable_shares,
    open_position_exposure,
    plan_entry,
    rank_live_candidates,
)
from weather.models import WeatherBucketMarket, WeatherMarketContext


def _market(
    market_id: str,
    *,
    yes_bid: float,
    yes_ask: float,
    no_bid: float,
    no_ask: float,
    yes_ask_size: float,
    no_ask_size: float,
) -> WeatherBucketMarket:
    now = datetime(2026, 3, 23, 14, 0, tzinfo=UTC)
    return WeatherBucketMarket(
        market_id=market_id,
        event_id="evt-1",
        event_slug="highest-temperature-in-rome-on-march-24-2026",
        market_slug=f"{market_id}-slug",
        question="Will the highest temperature in Rome be 16C?",
        city="Rome",
        city_key="rome",
        station_code="LIRU",
        station_name="Rome",
        lat=41.8,
        lon=12.2,
        timezone="Europe/Rome",
        local_date=date(2026, 3, 24),
        unit="C",
        bucket_label="16C",
        bucket_low=16.0,
        bucket_high=16.0,
        bucket_order=1,
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
        ended_at=datetime(2026, 3, 24, 22, 0, tzinfo=UTC),
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        yes_mid=round((yes_bid + yes_ask) / 2.0, 4),
        yes_bid_size=50.0,
        yes_ask_size=yes_ask_size,
        no_bid=no_bid,
        no_ask=no_ask,
        no_mid=round((no_bid + no_ask) / 2.0, 4),
        no_bid_size=50.0,
        no_ask_size=no_ask_size,
        latest_quote_time=now,
    )


def _context(markets: list[WeatherBucketMarket]) -> WeatherMarketContext:
    return WeatherMarketContext(
        event_id="evt-1",
        event_slug="highest-temperature-in-rome-on-march-24-2026",
        title="Highest temperature in Rome on 2026-03-24",
        city="Rome",
        city_key="rome",
        station_code="LIRU",
        station_name="Rome",
        lat=41.8,
        lon=12.2,
        timezone="Europe/Rome",
        local_date=date(2026, 3, 24),
        unit="C",
        rule_family="wunderground_daily",
        resolution_source_url="https://example.test",
        verified_station=True,
        observation_provider="aviationweather",
        forecast_provider="open_meteo",
        markets=markets,
    )


def _bot_config() -> dict:
    return {
        "strategy_name": "coldmath_inventory_rebalancing_merge_v2",
        "entry_rule": {
            "complete_set_cost_lte": 0.995,
            "require_full_buy_fill_context": True,
            "min_under_par_buy_fill_ratio": 0.5,
            "max_worse_buy_fill_ratio": 0.25,
            "worse_buy_override_complete_set_cost_lte": 0.98,
        },
        "inventory_balancing_rule": {"max_inventory_imbalance_ratio": 0.491617},
        "risk_rule": {"reject_missing_fill_context": True},
        "exit_rule": {"max_merge_delay_minutes": 240},
    }


class TradingWeatherStrategyTests(unittest.TestCase):
    captured_at = datetime(2026, 3, 23, 14, 0, tzinfo=UTC)

    def _runtime(self):
        return build_runtime_config(
            _bot_config(),
            balance_usd=80.0,
            sequence_budget_cap_usd=0.0,
            max_total_exposure_cap_usd=0.0,
            daily_loss_limit_cap_usd=0.0,
            min_expected_edge_usd=0.03,
            max_concurrent_positions=0,
            partial_repair_window_seconds=30.0,
            min_target_shares=5,
            auto_merge=True,
        )

    def test_runtime_config_uses_full_bankroll_when_caps_removed(self):
        runtime = self._runtime()

        self.assertEqual(runtime.sequence_budget_usd, 8.0)
        self.assertEqual(runtime.max_total_exposure_usd, 80.0)
        self.assertEqual(runtime.daily_loss_limit_usd, 80.0)
        self.assertEqual(runtime.max_concurrent_positions, 10)
        self.assertTrue(runtime.auto_merge)

    def test_runtime_config_still_honors_explicit_caps(self):
        runtime = build_runtime_config(
            _bot_config(),
            balance_usd=80.0,
            sequence_budget_cap_usd=12.0,
            max_total_exposure_cap_usd=24.0,
            daily_loss_limit_cap_usd=12.0,
            min_expected_edge_usd=0.03,
            max_concurrent_positions=2,
            partial_repair_window_seconds=30.0,
            min_target_shares=5,
            auto_merge=True,
        )

        self.assertEqual(runtime.sequence_budget_usd, 12.0)
        self.assertEqual(runtime.max_total_exposure_usd, 24.0)
        self.assertEqual(runtime.daily_loss_limit_usd, 12.0)
        self.assertEqual(runtime.max_concurrent_positions, 2)

    def test_rank_live_candidates_keeps_merge_metadata(self):
        candidates = rank_live_candidates(
            [_context([_market("m1", yes_bid=0.489, yes_ask=0.49, no_bid=0.5, no_ask=0.501, yes_ask_size=12, no_ask_size=18)])],
            self._runtime(),
            captured_at=self.captured_at,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["market_id"], "m1")
        self.assertEqual(candidates[0]["yes_token_id"], "m1-yes")
        self.assertEqual(candidates[0]["no_token_id"], "m1-no")
        self.assertTrue(candidates[0]["neg_risk"])

    def test_plan_entry_uses_budget_liquidity_and_expected_edge(self):
        candidate = rank_live_candidates(
            [_context([_market("m1", yes_bid=0.489, yes_ask=0.49, no_bid=0.5, no_ask=0.501, yes_ask_size=12, no_ask_size=18)])],
            self._runtime(),
            captured_at=self.captured_at,
        )[0]

        plan = plan_entry(candidate, self._runtime(), active_exposure_usd=0.0)

        self.assertIsNotNone(plan)
        self.assertEqual(plan["target_shares"], 8)
        self.assertEqual(plan["first_side"], "yes")
        self.assertEqual(plan["second_side"], "no")
        self.assertEqual(plan["sequence_budget_usd"], 8.0)
        self.assertEqual(plan["combined_cost"], 0.991)
        self.assertEqual(plan["expected_edge_usd"], 0.072)

    def test_mergeable_shares_and_exposure_helpers(self):
        self.assertEqual(compute_mergeable_shares(yes_shares=11.9, no_shares=10.2), 10)
        self.assertEqual(
            open_position_exposure(
                {
                    "total_entry_cost": 11.88,
                    "unwind_collateral_usdc": 1.0,
                    "merged_collateral_usdc": 10.0,
                    "redeemed_collateral_usdc": 0.0,
                }
            ),
            0.88,
        )
