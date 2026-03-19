import unittest
from unittest.mock import AsyncMock, patch

from core import main as core_main


class CoreDebugModeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_debug_mode = core_main.CORE_DEBUG_MODE

    async def asyncTearDown(self):
        core_main.CORE_DEBUG_MODE = self.original_debug_mode

    async def test_upsert_market_outcome_skips_database_in_debug_mode(self):
        core_main.CORE_DEBUG_MODE = True

        with patch.object(core_main.db, "upsert_market_outcome", AsyncMock()) as upsert_mock:
            await core_main._upsert_market_outcome(
                market_id="market-123456789",
                market_type="BTC-5M",
                started_at=None,
                ended_at=None,
            )

        upsert_mock.assert_not_awaited()

    async def test_insert_tick_skips_database_in_debug_mode(self):
        core_main.CORE_DEBUG_MODE = True

        with patch.object(core_main.db, "insert_tick", AsyncMock()) as insert_mock:
            await core_main._insert_tick(
                second=0,
                tick_time=None,
                market_id="market-123456789",
                up_price=0.51,
                volume=None,
            )

        insert_mock.assert_not_awaited()

    async def test_recover_unresolved_markets_skips_database_in_debug_mode(self):
        core_main.CORE_DEBUG_MODE = True
        app_state = core_main.AppState()

        with patch.object(core_main.db, "fetch_unresolved_markets", AsyncMock()) as fetch_mock:
            await core_main.recover_unresolved_markets(app_state, AsyncMock())

        fetch_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
