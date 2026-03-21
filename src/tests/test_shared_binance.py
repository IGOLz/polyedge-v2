import unittest
from datetime import datetime, timezone

from shared.binance import fill_missing_bars, parse_rest_kline_row, parse_ws_kline_message


class BinanceParsingTests(unittest.TestCase):
    def test_parse_closed_websocket_kline_message(self):
        message = {
            "stream": "btcusdt@kline_1s",
            "data": {
                "e": "kline",
                "E": 1711022401999,
                "s": "BTCUSDT",
                "k": {
                    "t": 1711022401000,
                    "T": 1711022401999,
                    "s": "BTCUSDT",
                    "i": "1s",
                    "o": "64000.0",
                    "c": "64001.5",
                    "h": "64002.0",
                    "l": "63999.5",
                    "v": "2.5",
                    "n": 15,
                    "x": True,
                    "q": "160003.75",
                    "V": "1.2",
                    "Q": "76801.8",
                },
            },
        }

        bar = parse_ws_kline_message(message, tracked_symbols={"BTCUSDT"})

        self.assertIsNotNone(bar)
        assert bar is not None
        self.assertEqual(bar.symbol, "BTCUSDT")
        self.assertEqual(bar.asset, "BTC")
        self.assertEqual(bar.quote_asset, "USDT")
        self.assertEqual(bar.time, datetime(2024, 3, 21, 12, 0, 1, tzinfo=timezone.utc))
        self.assertEqual(bar.close, 64001.5)
        self.assertEqual(bar.trade_count, 15)
        self.assertEqual(bar.source, "binance_live_ws")

    def test_parse_rest_kline_row(self):
        row = [
            1711022401000,
            "64000.0",
            "64002.0",
            "63999.5",
            "64001.5",
            "2.5",
            1711022401999,
            "160003.75",
            15,
            "1.2",
            "76801.8",
            "0",
        ]

        bar = parse_rest_kline_row("BTCUSDT", row)

        self.assertEqual(bar.symbol, "BTCUSDT")
        self.assertEqual(bar.time, datetime(2024, 3, 21, 12, 0, 1, tzinfo=timezone.utc))
        self.assertEqual(bar.open, 64000.0)
        self.assertEqual(bar.high, 64002.0)
        self.assertEqual(bar.low, 63999.5)
        self.assertEqual(bar.close, 64001.5)
        self.assertEqual(bar.quote_volume, 160003.75)
        self.assertEqual(bar.source, "binance_live_backfill")

    def test_fill_missing_bars_synthesizes_flat_gap_rows(self):
        start_time = datetime(2026, 3, 21, 12, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2026, 3, 21, 12, 0, 2, tzinfo=timezone.utc)
        first = parse_rest_kline_row(
            "BTCUSDT",
            [
                int(start_time.timestamp() * 1000),
                "100.0",
                "101.0",
                "99.5",
                "100.5",
                "1.0",
                int(start_time.timestamp() * 1000) + 999,
                "100.5",
                10,
                "0.6",
                "60.3",
                "0",
            ],
        )
        last = parse_rest_kline_row(
            "BTCUSDT",
            [
                int(end_time.timestamp() * 1000),
                "101.0",
                "102.0",
                "100.8",
                "101.5",
                "1.3",
                int(end_time.timestamp() * 1000) + 999,
                "132.0",
                12,
                "0.7",
                "71.0",
                "0",
            ],
        )

        filled = fill_missing_bars(
            "BTCUSDT",
            [first, last],
            start_time=start_time,
            end_time=end_time,
        )

        self.assertEqual(len(filled), 3)
        self.assertEqual([bar.time for bar in filled], [start_time, start_time.replace(second=1), end_time])
        self.assertEqual(filled[1].source, "binance_live_synth")
        self.assertEqual(filled[1].open, first.close)
        self.assertEqual(filled[1].close, first.close)
        self.assertEqual(filled[1].trade_count, 0)


if __name__ == "__main__":
    unittest.main()
