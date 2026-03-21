import unittest

from shared.api import (
    _detect_asset,
    _detect_duration,
    _extract_resolution_details,
    _is_up_down_market,
    _normalize_resolution_outcome,
)
from shared.ws import extract_up_prices


class DiscoveryHelperTests(unittest.TestCase):
    def test_detect_asset(self):
        self.assertEqual(_detect_asset("btc-up-or-down-5m"), "BTC")
        self.assertEqual(_detect_asset("Ethereum up or down 15 minutes"), "ETH")
        self.assertEqual(_detect_asset("xrp updown market"), "XRP")
        self.assertEqual(_detect_asset("solana up or down"), "SOL")

    def test_detect_duration(self):
        self.assertEqual(_detect_duration("btc-updown-5m"), 5)
        self.assertEqual(_detect_duration("Will ETH be up or down in 15 minutes?"), 15)
        self.assertIsNone(_detect_duration("daily bitcoin market"))

    def test_up_down_detection(self):
        self.assertTrue(_is_up_down_market("btc-up-or-down-5m"))
        self.assertTrue(_is_up_down_market("Will SOL be up or down in 15 minutes?"))
        self.assertFalse(_is_up_down_market("Will BTC be above 120k tomorrow?"))

    def test_normalize_resolution_outcome(self):
        self.assertEqual(_normalize_resolution_outcome("UP"), "Up")
        self.assertEqual(_normalize_resolution_outcome("down"), "Down")
        self.assertEqual(_normalize_resolution_outcome("YES"), "Up")
        self.assertEqual(_normalize_resolution_outcome("NO"), "Down")
        self.assertIsNone(_normalize_resolution_outcome("MAYBE"))

    def test_extract_resolution_details_from_top_level_resolution(self):
        result = _extract_resolution_details(
            {
                "resolved": True,
                "winner": "UP",
                "volume": "12.34",
                "tokens": [
                    {"outcome": "Up", "price": "1", "token_id": "up-token"},
                    {"outcome": "Down", "price": "0", "token_id": "down-token"},
                ],
            }
        )
        self.assertEqual(
            result,
            {
                "resolved": True,
                "winner": "Up",
                "final_up_price": 1.0,
                "total_volume": 12.34,
                "resolution_source": "top_level",
            },
        )

    def test_extract_resolution_details_from_token_winner_flag(self):
        result = _extract_resolution_details(
            {
                "closed": True,
                "accepting_orders": False,
                "resolved": None,
                "winner": None,
                "tokens": [
                    {"outcome": "Up", "price": "0", "winner": False, "token_id": "up-token"},
                    {"outcome": "Down", "price": "1", "winner": True, "token_id": "down-token"},
                ],
                "volumeNum": "55.5",
            }
        )
        self.assertEqual(
            result,
            {
                "resolved": True,
                "winner": "Down",
                "final_up_price": 0.0,
                "total_volume": 55.5,
                "resolution_source": "token_flag",
            },
        )


class WebsocketParsingTests(unittest.TestCase):
    def test_extract_price_change_midpoint(self):
        msg = {
            "event_type": "price_change",
            "price_changes": [
                {
                    "asset_id": "up-token",
                    "best_bid": "0.44",
                    "best_ask": "0.46",
                }
            ],
        }
        self.assertEqual(extract_up_prices(msg, {"up-token"}), {"up-token": 0.45})

    def test_extract_best_bid_ask_midpoint(self):
        msg = {
            "event_type": "best_bid_ask",
            "asset_id": "up-token",
            "best_bid": "0.51",
            "best_ask": "0.53",
        }
        self.assertEqual(extract_up_prices(msg, {"up-token"}), {"up-token": 0.52})

    def test_extract_book_midpoint(self):
        msg = {
            "event_type": "book",
            "asset_id": "up-token",
            "bids": [{"price": "0.40"}],
            "asks": [{"price": "0.42"}],
        }
        self.assertEqual(extract_up_prices(msg, {"up-token"}), {"up-token": 0.41})


if __name__ == "__main__":
    unittest.main()
