import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from shared.strategies.S10.strategy import S10Strategy
from shared.strategies.S13.strategy import S13Strategy
from shared.strategies.S14.strategy import S14Strategy
from trading import strategy_adapter
from trading.db import MarketInfo, Tick
from trading.live_profile import (
    build_live_s10_config,
    build_live_s13_config,
    build_live_s14_config,
)


class FrozenDateTime(datetime):
    frozen_now = datetime(2026, 3, 21, 13, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.frozen_now.replace(tzinfo=None)
        return cls.frozen_now.astimezone(tz)


def _make_market(
    *,
    market_id: str,
    market_type: str,
    started_at: datetime,
    duration_minutes: int,
) -> MarketInfo:
    return MarketInfo(
        market_id=market_id,
        market_type=market_type,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=duration_minutes),
        up_token_id="up-token",
        down_token_id="down-token",
    )


def _make_ticks(
    market_id: str,
    started_at: datetime,
    second_to_price: dict[int, float],
) -> list[Tick]:
    return [
        Tick(
            market_id=market_id,
            time=started_at + timedelta(seconds=second),
            up_price=price,
            down_price=round(1.0 - price, 6),
        )
        for second, price in sorted(second_to_price.items())
    ]


def _make_crypto_rows(
    symbol: str,
    started_at: datetime,
    closes: list[float],
) -> list[dict]:
    asset = symbol.replace("USDT", "")
    rows = []
    for second, close in enumerate(closes):
        rows.append(
            {
                "symbol": symbol,
                "asset": asset,
                "quote_asset": "USDT",
                "time": started_at + timedelta(seconds=second),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1.0,
                "quote_volume": close,
                "trade_count": 1,
                "taker_buy_base_volume": 0.5,
                "taker_buy_quote_volume": close * 0.5,
                "source": "binance_live_ws",
            }
        )
    return rows


class StrategyAdapterLiveFeatureTests(unittest.IsolatedAsyncioTestCase):
    async def test_evaluate_strategies_builds_live_features_for_s13(self):
        FrozenDateTime.frozen_now = datetime(2026, 3, 21, 13, 0, 30, tzinfo=timezone.utc)
        started_at = FrozenDateTime.frozen_now - timedelta(seconds=30)
        market = _make_market(
            market_id="btc-s13-market",
            market_type="btc_5m",
            started_at=started_at,
            duration_minutes=5,
        )
        ticks = _make_ticks(
            market.market_id,
            started_at,
            {second: 0.53 + (0.02 * second / 30.0) for second in range(31)},
        )
        crypto_rows = _make_crypto_rows(
            "BTCUSDT",
            started_at,
            [100.0 + (0.025 * second) for second in range(31)],
        )
        strategies = (S13Strategy(build_live_s13_config()),)

        with patch.object(strategy_adapter, "datetime", FrozenDateTime), patch.object(
            strategy_adapter, "get_live_strategies", return_value=strategies
        ), patch.object(
            strategy_adapter, "get_usdc_balance", AsyncMock(return_value=1000.0)
        ), patch.object(
            strategy_adapter, "already_traded_this_market", AsyncMock(return_value=False)
        ), patch.object(
            strategy_adapter.shared_db,
            "get_latest_crypto_bar_time",
            AsyncMock(return_value=FrozenDateTime.frozen_now),
        ), patch.object(
            strategy_adapter, "latest_bar_is_fresh", return_value=True
        ) as freshness_mock, patch.object(
            strategy_adapter.shared_db,
            "fetch_crypto_price_bars",
            AsyncMock(return_value=crypto_rows),
        ) as fetch_mock:
            signals = await strategy_adapter.evaluate_strategies(market, ticks)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].strategy_name, "S13_underlying_lag_follow")
        self.assertEqual(signals[0].direction, "Up")
        freshness_mock.assert_called_once()
        fetch_mock.assert_awaited_once()

    async def test_evaluate_strategies_builds_live_features_for_s14(self):
        FrozenDateTime.frozen_now = datetime(2026, 3, 21, 13, 5, 30, tzinfo=timezone.utc)
        started_at = FrozenDateTime.frozen_now - timedelta(seconds=30)
        market = _make_market(
            market_id="btc-s14-market",
            market_type="btc_5m",
            started_at=started_at,
            duration_minutes=5,
        )
        ticks = _make_ticks(
            market.market_id,
            started_at,
            {second: 0.42 - (0.08 * second / 30.0) for second in range(31)},
        )
        crypto_rows = _make_crypto_rows(
            "BTCUSDT",
            started_at,
            [100.0 + (0.05 * second / 30.0) for second in range(31)],
        )
        strategies = (S14Strategy(build_live_s14_config()),)

        with patch.object(strategy_adapter, "datetime", FrozenDateTime), patch.object(
            strategy_adapter, "get_live_strategies", return_value=strategies
        ), patch.object(
            strategy_adapter, "get_usdc_balance", AsyncMock(return_value=1000.0)
        ), patch.object(
            strategy_adapter, "already_traded_this_market", AsyncMock(return_value=False)
        ), patch.object(
            strategy_adapter.shared_db,
            "get_latest_crypto_bar_time",
            AsyncMock(return_value=FrozenDateTime.frozen_now),
        ), patch.object(
            strategy_adapter, "latest_bar_is_fresh", return_value=True
        ), patch.object(
            strategy_adapter.shared_db,
            "fetch_crypto_price_bars",
            AsyncMock(return_value=crypto_rows),
        ):
            signals = await strategy_adapter.evaluate_strategies(market, ticks)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].strategy_name, "S14_divergence_fade")
        self.assertEqual(signals[0].direction, "Up")

    async def test_stale_crypto_data_skips_feature_strategies_only(self):
        FrozenDateTime.frozen_now = datetime(2026, 3, 21, 13, 10, 50, tzinfo=timezone.utc)
        started_at = FrozenDateTime.frozen_now - timedelta(seconds=50)
        market = _make_market(
            market_id="btc-stale-market",
            market_type="btc_5m",
            started_at=started_at,
            duration_minutes=5,
        )
        ticks = _make_ticks(
            market.market_id,
            started_at,
            {
                **{
                    second: 0.30 + ((0.45 - 0.30) * (second - 20) / 25.0)
                    for second in range(20, 46)
                },
                46: 0.42,
                47: 0.40,
                48: 0.41,
                49: 0.42,
                50: 0.43,
            },
        )
        strategies = (
            S10Strategy(build_live_s10_config()),
            S14Strategy(build_live_s14_config()),
        )

        with patch.object(strategy_adapter, "datetime", FrozenDateTime), patch.object(
            strategy_adapter, "get_live_strategies", return_value=strategies
        ), patch.object(
            strategy_adapter, "get_usdc_balance", AsyncMock(return_value=1000.0)
        ), patch.object(
            strategy_adapter, "already_traded_this_market", AsyncMock(return_value=False)
        ), patch.object(
            strategy_adapter.shared_db,
            "get_latest_crypto_bar_time",
            AsyncMock(return_value=FrozenDateTime.frozen_now - timedelta(seconds=10)),
        ), patch.object(
            strategy_adapter, "latest_bar_is_fresh", return_value=False
        ), patch.object(
            strategy_adapter.shared_db,
            "fetch_crypto_price_bars",
            AsyncMock(),
        ) as fetch_mock:
            signals = await strategy_adapter.evaluate_strategies(market, ticks)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].strategy_name, "S10_pullback_continuation")
        self.assertEqual(signals[0].direction, "Up")
        fetch_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
