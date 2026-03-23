from __future__ import annotations

import unittest

from trading_weather.safe_ops import (
    CTF_ADDRESS,
    CTF_MERGE_SIGNATURE,
    MAIN_EXCHANGE_ADDRESS,
    NEG_RISK_ADAPTER_ADDRESS,
    NEG_RISK_MERGE_SIGNATURE,
    NEG_RISK_REDEEM_SIGNATURE,
    ApprovalState,
    build_allowance_calls,
    encode_merge_calldata,
    encode_redeem_calldata,
)


class TradingWeatherSafeOpsTests(unittest.TestCase):
    def test_encode_merge_calldata_uses_standard_ctf_signature_for_non_neg_risk(self):
        target, calldata = encode_merge_calldata(
            "0xbcb0ccec0b3eaad3f88926b8de345c998df35af5f6b2e0bdcac7dcfae4975bc9",
            neg_risk=False,
            shares=12,
        )

        self.assertEqual(CTF_MERGE_SIGNATURE, "mergePositions(address,bytes32,bytes32,uint256[],uint256)")
        self.assertEqual(target, CTF_ADDRESS)
        self.assertTrue(calldata.hex().startswith("9e7212ad"))

    def test_encode_merge_and_redeem_calldata_use_neg_risk_adapter_signatures(self):
        merge_target, merge_calldata = encode_merge_calldata(
            "0xbcb0ccec0b3eaad3f88926b8de345c998df35af5f6b2e0bdcac7dcfae4975bc9",
            neg_risk=True,
            shares=12,
        )
        redeem_target, redeem_calldata = encode_redeem_calldata(
            "0xbcb0ccec0b3eaad3f88926b8de345c998df35af5f6b2e0bdcac7dcfae4975bc9",
            neg_risk=True,
            yes_shares=7,
            no_shares=0,
        )

        self.assertEqual(NEG_RISK_MERGE_SIGNATURE, "mergePositions(bytes32,uint256)")
        self.assertEqual(NEG_RISK_REDEEM_SIGNATURE, "redeemPositions(bytes32,uint256[])")
        self.assertEqual(merge_target, NEG_RISK_ADAPTER_ADDRESS)
        self.assertEqual(redeem_target, NEG_RISK_ADAPTER_ADDRESS)
        self.assertTrue(merge_calldata.hex().startswith("b10c5c17"))
        self.assertTrue(redeem_calldata.hex().startswith("dbeccb23"))

    def test_build_allowance_calls_includes_usdc_and_ctf_transactions(self):
        calls = build_allowance_calls(
            ApprovalState(
                missing_usdc_spenders=[MAIN_EXCHANGE_ADDRESS],
                missing_ctf_operators=[NEG_RISK_ADAPTER_ADDRESS],
            )
        )

        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0]["to"], calls[1]["to"])
        self.assertTrue(calls[0]["data_hex"].startswith("0x095ea7b3"))
        self.assertTrue(calls[1]["data_hex"].startswith("0xa22cb465"))
