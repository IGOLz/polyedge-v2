from __future__ import annotations

from decimal import Decimal
from unittest import TestCase

from trading_weather.cleanup_wallet import (
    ConditionSnapshot,
    aggregate_condition_snapshots,
    assess_snapshot,
)


class TradingWeatherCleanupTests(TestCase):
    def test_aggregate_condition_snapshots_groups_yes_no(self) -> None:
        rows = [
            {
                "conditionId": "cond-1",
                "title": "Will the highest temperature in Rome be 20°C?",
                "slug": "highest-temperature-in-rome",
                "redeemable": False,
                "outcome": "Yes",
                "size": "12.5",
                "asset": "yes-token",
            },
            {
                "conditionId": "cond-1",
                "title": "Will the highest temperature in Rome be 20°C?",
                "slug": "highest-temperature-in-rome",
                "redeemable": False,
                "outcome": "No",
                "size": "3.25",
                "asset": "no-token",
            },
        ]

        [snapshot] = aggregate_condition_snapshots(rows)

        self.assertEqual(snapshot.condition_id, "cond-1")
        self.assertEqual(snapshot.yes_shares, Decimal("12.5"))
        self.assertEqual(snapshot.no_shares, Decimal("3.25"))

    def test_assess_snapshot_redeems_first(self) -> None:
        snapshot = ConditionSnapshot(
            bucket="crypto_updown",
            condition_id="cond-2",
            title="BTC up/down",
            slug="btc-updown-1",
            redeemable=True,
            yes_shares=Decimal("10"),
            no_shares=Decimal("0"),
            token_id="token",
        )
        self.assertEqual(assess_snapshot(snapshot), ("redeem_now", "public_api_redeemable"))

    def test_assess_snapshot_requires_full_bid_depth(self) -> None:
        snapshot = ConditionSnapshot(
            bucket="weather",
            condition_id="cond-3",
            title="Shanghai",
            slug="highest-temperature-in-shanghai",
            redeemable=False,
            yes_shares=Decimal("25"),
            no_shares=Decimal("0"),
            token_id="token",
            top_bid_price=0.001,
            top_bid_size=10.0,
            current_side="yes",
            current_shares=Decimal("25"),
        )
        self.assertEqual(assess_snapshot(snapshot), ("manual_blocked", "insufficient_bid_depth"))

    def test_assess_snapshot_allows_full_size_weather_sell(self) -> None:
        snapshot = ConditionSnapshot(
            bucket="weather",
            condition_id="cond-4",
            title="Atlanta",
            slug="highest-temperature-in-atlanta",
            redeemable=False,
            yes_shares=Decimal("0"),
            no_shares=Decimal("20"),
            token_id="token",
            top_bid_price=0.001,
            top_bid_size=25.0,
            current_side="no",
            current_shares=Decimal("20"),
        )
        self.assertEqual(assess_snapshot(snapshot), ("sell_now", "full_size_bid_available"))
