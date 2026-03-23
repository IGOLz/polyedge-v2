from __future__ import annotations

import logging
import unittest

from colorama import Fore, Style

from trading.utils import _color_for_record, setup_logging


def _record(level: int, message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="polyedge.trading",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


class TradingLoggingTests(unittest.TestCase):
    def test_trade_entries_are_green(self):
        color = _color_for_record(_record(logging.INFO, "[WEATHER-MERGE] Entered Rome 16C | 8 pairs @ 0.9910"))
        self.assertEqual(color, Fore.GREEN + Style.BRIGHT)

    def test_failures_are_red(self):
        color = _color_for_record(_record(logging.ERROR, "[WEATHER-MERGE] Cycle failed: RuntimeError"))
        self.assertEqual(color, Fore.RED + Style.BRIGHT)

    def test_heartbeat_is_cyan_and_logger_does_not_propagate(self):
        logger = setup_logging()
        color = _color_for_record(
            _record(logging.INFO, "[WEATHER-MERGE] Cycle OK | candidates=0 entries=0 | stand_down=no_qualifying_candidate")
        )
        self.assertEqual(color, Fore.YELLOW)
        self.assertFalse(logger.propagate)


if __name__ == "__main__":
    unittest.main()
