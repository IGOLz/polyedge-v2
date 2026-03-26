from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import UTC, date, datetime

from analysis.coldmath_clone_parity import _match_signals_to_trades
from trading_weather.clone_config import normalize_clone_bot_config
from trading_weather.clone_engine import (
    _minimum_buy_target_shares,
    _minimum_pair_target_shares,
    _normalize_buy_target_shares,
    _normalize_pair_target_shares,
    build_clone_runtime,
    clone_cycle_status_message,
    evaluate_clone_cycle,
    plan_directional_entry,
    preflight_clone_health,
    refresh_contexts_with_direct_quotes,
)
from trading_weather.main import _minimum_buy_order_shares, _normalize_buy_order_shares, _normalize_order_price
from weather.models import WeatherBucketMarket, WeatherMarketContext


def _market(
    market_id: str,
    *,
    bucket_order: int = 1,
    yes_bid: float | None = 0.49,
    yes_ask: float | None = 0.49,
    no_bid: float | None = 0.50,
    no_ask: float | None = 0.50,
    yes_ask_size: float | None = 20.0,
    no_ask_size: float | None = 20.0,
    latest_quote_time: datetime | None = None,
) -> WeatherBucketMarket:
    now = latest_quote_time or datetime(2026, 3, 24, 12, 0, tzinfo=UTC)
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
        bucket_label=f"{15 + bucket_order}C",
        bucket_low=float(15 + bucket_order),
        bucket_high=float(15 + bucket_order),
        bucket_order=bucket_order,
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
        yes_mid=((yes_bid + yes_ask) / 2.0 if yes_bid is not None and yes_ask is not None else None),
        yes_bid_size=50.0 if yes_bid is not None else None,
        yes_ask_size=yes_ask_size,
        no_bid=no_bid,
        no_ask=no_ask,
        no_mid=((no_bid + no_ask) / 2.0 if no_bid is not None and no_ask is not None else None),
        no_bid_size=50.0 if no_bid is not None else None,
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


def _merge_config() -> dict:
    return {
        "strategy_name": "coldmath_inventory_rebalancing_merge_v2",
        "entry_rule": {
            "complete_set_cost_lte": 0.995,
            "max_inventory_imbalance_ratio": 0.491617,
            "min_matched_size": 0.0,
            "require_full_buy_fill_context": True,
        },
        "inventory_balancing_rule": {"max_inventory_imbalance_ratio": 0.491617},
        "risk_rule": {"reject_missing_fill_context": True},
        "exit_rule": {"max_merge_delay_minutes": 240.0},
        "sizing_rule": {"max_sequence_buy_usdc": 8.0},
    }


@dataclass
class _FakeLevel:
    price: str
    size: str


@dataclass
class _FakeBook:
    asset_id: str
    bids: list[_FakeLevel]
    asks: list[_FakeLevel]
    timestamp: str


class _HealthyClob:
    def get_api_keys(self):
        return {"api_key": "ok"}


class _UnhealthyClob:
    def get_api_keys(self):
        raise RuntimeError("Invalid api key")


class _BookClob:
    def __init__(self, summaries):
        self.summaries = summaries

    def get_order_books(self, params):
        return self.summaries


class TradingWeatherCloneTests(unittest.TestCase):
    def setUp(self):
        self.config = normalize_clone_bot_config(_merge_config())
        self.runtime = build_clone_runtime(self.config, dry_run=True)
        self.captured_at = datetime(2026, 3, 24, 12, 0, tzinfo=UTC)

    def test_normalize_clone_bot_config_converts_merge_bot(self):
        self.assertEqual(self.config["mode"], "coldmath_weather_clone")
        self.assertEqual(self.config["execution_mode"], "shadow_only")
        self.assertIn("paired_under_par", self.config["playbooks"])
        self.assertTrue(self.config["playbooks"]["tail_bucket_accumulation"]["enabled"])

    def test_preflight_clone_health_reports_auth_status(self):
        healthy = preflight_clone_health(_HealthyClob(), dry_run=False)
        unhealthy = preflight_clone_health(_UnhealthyClob(), dry_run=False)

        self.assertEqual(healthy["execution_auth"]["status"], "healthy")
        self.assertTrue(healthy["execution_auth"]["allowed"])
        self.assertEqual(unhealthy["execution_auth"]["status"], "unhealthy")
        self.assertFalse(unhealthy["execution_auth"]["allowed"])

    def test_direct_quote_refresh_populates_missing_quotes(self):
        market = _market("m1", yes_bid=None, yes_ask=None, no_bid=None, no_ask=None, latest_quote_time=None)
        context = _context([market])
        summaries = [
            _FakeBook("m1-yes", bids=[_FakeLevel("0.48", "12")], asks=[_FakeLevel("0.49", "10")], timestamp="2026-03-24T12:00:00+00:00"),
            _FakeBook("m1-no", bids=[_FakeLevel("0.50", "14")], asks=[_FakeLevel("0.51", "9")], timestamp="2026-03-24T12:00:00+00:00"),
        ]

        result = refresh_contexts_with_direct_quotes(
            _BookClob(summaries),
            [context],
            captured_at=self.captured_at,
            health_config=self.config["health"],
        )

        self.assertEqual(result["direct_quote_markets"], 1)
        self.assertEqual(result["direct_quote_tokens"], 2)
        self.assertEqual(context.markets[0].yes_ask, 0.49)
        self.assertEqual(context.markets[0].no_ask, 0.51)

    def test_evaluate_clone_cycle_detects_paired_tail_and_high_prob_playbooks(self):
        markets = [
            _market("paired", bucket_order=1, yes_ask=0.49, no_ask=0.50),
            _market("tail", bucket_order=0, yes_ask=0.03, no_ask=0.97),
            _market("high", bucket_order=2, yes_ask=0.97, no_ask=0.03),
        ]
        report = evaluate_clone_cycle(
            contexts=[_context(markets)],
            runtime=self.runtime,
            captured_at=self.captured_at,
            health_state={
                "execution_auth": {"status": "unknown", "reason": "dry_run"},
                "market_data": {"status": "healthy", "reason": "ok"},
                "quote_coverage_ratio": 1.0,
                "execution_allowed": False,
            },
            sequence_state={},
            active_market_ids=set(),
        )

        playbooks = {(row["playbook_key"], row.get("market_id"), row.get("side")) for row in report["candidates"]}
        self.assertIn(("paired_under_par", "paired", None), playbooks)
        self.assertIn(("tail_bucket_accumulation", "tail", "yes"), playbooks)
        self.assertIn(("high_prob_bucket_accumulation", "high", "yes"), playbooks)

    def test_sequence_state_moves_from_watching_to_paired(self):
        sequence_state: dict[str, dict] = {}
        context = _context([_market("m1", yes_ask=0.60, no_ask=0.50)])
        first = evaluate_clone_cycle(
            contexts=[context],
            runtime=self.runtime,
            captured_at=self.captured_at,
            health_state={
                "execution_auth": {"status": "unknown", "reason": "dry_run"},
                "market_data": {"status": "healthy", "reason": "ok"},
                "quote_coverage_ratio": 1.0,
                "execution_allowed": False,
            },
            sequence_state=sequence_state,
            active_market_ids=set(),
        )
        second_context = _context([_market("m1", yes_ask=0.49, no_ask=0.50)])
        second = evaluate_clone_cycle(
            contexts=[second_context],
            runtime=self.runtime,
            captured_at=self.captured_at.replace(second=30),
            health_state={
                "execution_auth": {"status": "unknown", "reason": "dry_run"},
                "market_data": {"status": "healthy", "reason": "ok"},
                "quote_coverage_ratio": 1.0,
                "execution_allowed": False,
            },
            sequence_state=sequence_state,
            active_market_ids=set(),
        )

        first_sequence = next(row["sequence_data"] for row in first["cycle_rows"] if row["playbook_key"] == "paired_under_par")
        second_sequence = next(row["sequence_data"] for row in second["cycle_rows"] if row["playbook_key"] == "paired_under_par")
        self.assertEqual(first_sequence["state"], "watching")
        self.assertEqual(second_sequence["state"], "paired")
        self.assertGreaterEqual(second_sequence["qualify_count"], 1)

    def test_rejection_reasons_include_missing_quote_pair_and_stale_quote(self):
        stale_market = _market("stale", yes_ask=0.49, no_ask=None, latest_quote_time=datetime(2026, 3, 24, 11, 55, tzinfo=UTC))
        report = evaluate_clone_cycle(
            contexts=[_context([stale_market])],
            runtime=self.runtime,
            captured_at=self.captured_at,
            health_state={
                "execution_auth": {"status": "unknown", "reason": "dry_run"},
                "market_data": {"status": "healthy", "reason": "ok"},
                "quote_coverage_ratio": 0.0,
                "execution_allowed": False,
            },
            sequence_state={},
            active_market_ids=set(),
        )

        paired_row = next(row for row in report["cycle_rows"] if row["playbook_key"] == "paired_under_par")
        self.assertIn("missing_pair_ask", paired_row["rejection_reasons"])
        self.assertIn("stale_quote", paired_row["rejection_reasons"])

    def test_inventory_exit_playbook_flags_timed_out_partial_entry(self):
        report = evaluate_clone_cycle(
            contexts=[],
            runtime=build_clone_runtime(self.config, dry_run=False),
            captured_at=self.captured_at,
            health_state={
                "execution_auth": {"status": "healthy", "reason": "ok"},
                "market_data": {"status": "healthy", "reason": "ok"},
                "quote_coverage_ratio": 1.0,
                "execution_allowed": True,
            },
            sequence_state={},
            active_positions=[
                {
                    "id": 7,
                    "market_id": "m1",
                    "event_id": "evt-1",
                    "event_slug": "highest-temperature-in-rome-on-march-24-2026",
                    "city": "Rome",
                    "local_date": date(2026, 3, 24),
                    "bucket_label": "16C",
                    "side": None,
                    "status": "partial_entry",
                    "opened_at": datetime(2026, 3, 24, 11, 58, tzinfo=UTC),
                }
            ],
            active_market_ids=set(),
        )

        exit_row = next(row for row in report["cycle_rows"] if row["playbook_key"] == "inventory_exit_and_closeout")
        self.assertTrue(exit_row["qualifies"])
        self.assertTrue(exit_row["live_eligible"])

    def test_match_signals_to_trades_reports_matches_and_top_miss_reasons(self):
        trade_rows = [
            {
                "timestamp_utc": datetime(2026, 3, 24, 12, 0, 10, tzinfo=UTC),
                "condition_id": "m1",
                "city": "Rome",
                "bucket_label": "16C",
            },
            {
                "timestamp_utc": datetime(2026, 3, 24, 12, 5, 10, tzinfo=UTC),
                "condition_id": "m2",
                "city": "Rome",
                "bucket_label": "17C",
            },
        ]
        signal_rows = [
            {
                "captured_at": datetime(2026, 3, 24, 12, 0, 0, tzinfo=UTC),
                "market_id": "m1",
                "bucket_label": "16C",
                "qualifies": True,
                "candidate_score": 1.2,
                "playbook_key": "paired_under_par",
            },
            {
                "captured_at": datetime(2026, 3, 24, 12, 5, 0, tzinfo=UTC),
                "market_id": "m2",
                "bucket_label": "17C",
                "qualifies": False,
                "candidate_score": 0.0,
                "rejection_reasons": ["missing_full_quote_pair"],
                "playbook_key": "paired_under_par",
            },
        ]

        result = _match_signals_to_trades(
            trade_rows=trade_rows,
            signal_rows=signal_rows,
            match_window_seconds=15.0,
        )

        self.assertEqual(result["summary"]["matched_trade_count"], 1)
        self.assertEqual(result["summary"]["missed_high_confidence_trade_count"], 1)
        self.assertEqual(result["summary"]["top_miss_reasons"][0]["reason"], "missing_full_quote_pair")

    def test_plan_directional_entry_uses_playbook_budget(self):
        markets = [_market("tail", bucket_order=0, yes_ask=0.02, no_ask=0.98, yes_ask_size=300.0, no_ask_size=10.0)]
        report = evaluate_clone_cycle(
            contexts=[_context(markets)],
            runtime=self.runtime,
            captured_at=self.captured_at,
            health_state={
                "execution_auth": {"status": "healthy", "reason": "ok"},
                "market_data": {"status": "healthy", "reason": "ok"},
                "quote_coverage_ratio": 1.0,
                "execution_allowed": True,
            },
            sequence_state={},
            active_positions=[],
            active_market_ids=set(),
        )
        candidate = next(
            row for row in report["candidates"]
            if row["playbook_key"] == "tail_bucket_accumulation" and row["side"] == "yes"
        )

        plan = plan_directional_entry(candidate, build_clone_runtime(self.config, dry_run=False), active_exposure_usd=0.0)

        self.assertIsNotNone(plan)
        self.assertEqual(plan["playbook_key"], "tail_bucket_accumulation")
        self.assertEqual(plan["side"], "yes")
        self.assertEqual(plan["sequence_budget_usd"], 5.0)
        self.assertEqual(plan["target_shares"], 250)

    def test_normalize_order_price_preserves_low_tick_prices(self):
        self.assertEqual(_normalize_order_price(0.001), 0.001)
        self.assertEqual(_normalize_order_price(0.002), 0.002)
        self.assertEqual(_normalize_order_price(0.0004), 0.001)
        self.assertEqual(_normalize_order_price(1.0), 0.999)

    def test_normalize_buy_shares_respects_cents_precision(self):
        self.assertEqual(_normalize_buy_target_shares(0.003, 666), 660)
        self.assertEqual(_normalize_buy_target_shares(0.002, 999), 995)
        self.assertEqual(_normalize_pair_target_shares(0.499, 0.501, 27), 20)
        self.assertEqual(_normalize_buy_order_shares(0.999, 9), 0)
        self.assertEqual(_minimum_buy_target_shares(0.495), 4)
        self.assertEqual(_minimum_pair_target_shares(0.499, 0.501), 10)
        self.assertEqual(_minimum_buy_order_shares(0.99), 2)

    def test_clone_cycle_status_message_includes_spend_and_stand_down(self):
        message = clone_cycle_status_message(
            {
                "execution_allowed": False,
                "execution_health": "healthy",
                "market_data_health": "healthy",
                "quote_coverage_ratio": 0.75,
                "total_spent_usd": 7.5,
                "total_spend_limit_usd": 30.0,
                "context_count": 4,
                "market_count": 44,
                "candidate_count": 2,
                "sequence_count": 5,
                "active_positions": 1,
                "active_exposure_usd": 3.25,
                "entry_attempts": 0,
                "stand_down_reason": "foreign_wallet_activity_detected",
                "top_rejection_reasons": [{"reason": "missing_directional_ask", "count": 8}],
            }
        )

        self.assertIn("spent=7.50/30.00", message)
        self.assertIn("exposure=3.25", message)
        self.assertIn("stand_down=foreign_wallet_activity_detected", message)


if __name__ == "__main__":
    unittest.main()
