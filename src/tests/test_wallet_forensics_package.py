from __future__ import annotations

import importlib
import sys
import unittest


class WalletForensicsPackageTests(unittest.TestCase):
    def test_package_import_is_lightweight(self):
        sys.modules.pop("analysis.wallet_forensics", None)
        sys.modules.pop("analysis.wallet_forensics.main", None)

        package = importlib.import_module("analysis.wallet_forensics")

        self.assertTrue(callable(package.run_wallet_forensics))
        self.assertNotIn("analysis.wallet_forensics.main", sys.modules)


if __name__ == "__main__":
    unittest.main()
