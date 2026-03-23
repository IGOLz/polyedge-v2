from __future__ import annotations

import importlib
import sys
import unittest


class TradingWeatherImportTests(unittest.TestCase):
    def test_strategy_import_does_not_require_pandas(self):
        saved_pandas = sys.modules.get("pandas")
        had_pandas = "pandas" in sys.modules
        for module_name in (
            "trading_weather.strategy",
            "analysis.wallet_forensics.paper_scan",
        ):
            sys.modules.pop(module_name, None)
        sys.modules["pandas"] = None

        try:
            strategy = importlib.import_module("trading_weather.strategy")
        finally:
            sys.modules.pop("trading_weather.strategy", None)
            sys.modules.pop("analysis.wallet_forensics.paper_scan", None)
            if had_pandas:
                sys.modules["pandas"] = saved_pandas
            else:
                sys.modules.pop("pandas", None)

        self.assertTrue(callable(strategy.build_runtime_config))


if __name__ == "__main__":
    unittest.main()
