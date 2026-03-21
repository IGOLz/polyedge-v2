from __future__ import annotations

from trading.redeemer import (
    CTF_ADDRESS,
    REDEEM_FUNCTION_SIGNATURE,
    REDEEM_SELECTOR,
    encode_redeem_calldata,
)


def test_redeem_selector_matches_signature_hash():
    assert REDEEM_FUNCTION_SIGNATURE == "redeemPositions(address,bytes32,bytes32,uint256[])"
    assert REDEEM_SELECTOR.hex() == "01b7037c"


def test_encode_redeem_calldata_uses_redeem_positions_selector():
    contract_address, calldata = encode_redeem_calldata(
        "0xbcb0ccec0b3eaad3f88926b8de345c998df35af5f6b2e0bdcac7dcfae4975bc9",
        False,
    )
    assert contract_address == CTF_ADDRESS
    assert calldata.hex().startswith("01b7037c")
