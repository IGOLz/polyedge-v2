"""Safe/relayer operations for weather merge and redeem flows."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from eth_abi import encode as abi_encode
from web3 import Web3

from trading import config as trading_config

USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
MAIN_EXCHANGE_ADDRESS = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_EXCHANGE_ADDRESS = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
NEG_RISK_ADAPTER_ADDRESS = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
MAX_UINT256 = (1 << 256) - 1
HASH_ZERO = b"\x00" * 32
TOKEN_DECIMALS = 1_000_000

ERC20_APPROVE_SIGNATURE = "approve(address,uint256)"
ERC20_APPROVE_SELECTOR = Web3.keccak(text=ERC20_APPROVE_SIGNATURE)[:4]
ERC1155_SET_APPROVAL_SIGNATURE = "setApprovalForAll(address,bool)"
ERC1155_SET_APPROVAL_SELECTOR = Web3.keccak(text=ERC1155_SET_APPROVAL_SIGNATURE)[:4]
CTF_MERGE_SIGNATURE = "mergePositions(address,bytes32,bytes32,uint256[],uint256)"
CTF_MERGE_SELECTOR = Web3.keccak(text=CTF_MERGE_SIGNATURE)[:4]
NEG_RISK_MERGE_SIGNATURE = "mergePositions(bytes32,uint256)"
NEG_RISK_MERGE_SELECTOR = Web3.keccak(text=NEG_RISK_MERGE_SIGNATURE)[:4]
CTF_REDEEM_SIGNATURE = "redeemPositions(address,bytes32,bytes32,uint256[])"
CTF_REDEEM_SELECTOR = Web3.keccak(text=CTF_REDEEM_SIGNATURE)[:4]
NEG_RISK_REDEEM_SIGNATURE = "redeemPositions(bytes32,uint256[])"
NEG_RISK_REDEEM_SELECTOR = Web3.keccak(text=NEG_RISK_REDEEM_SIGNATURE)[:4]

SAFE_ABI = [
    {
        "name": "execTransaction",
        "type": "function",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "data", "type": "bytes"},
            {"name": "operation", "type": "uint8"},
            {"name": "safeTxGas", "type": "uint256"},
            {"name": "baseGas", "type": "uint256"},
            {"name": "gasPrice", "type": "uint256"},
            {"name": "gasToken", "type": "address"},
            {"name": "refundReceiver", "type": "address"},
            {"name": "signatures", "type": "bytes"},
        ],
        "outputs": [{"name": "success", "type": "bool"}],
        "stateMutability": "payable",
    },
    {
        "name": "nonce",
        "type": "function",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
]

ERC20_ABI = [
    {
        "name": "allowance",
        "type": "function",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    }
]

ERC1155_ABI = [
    {
        "name": "isApprovedForAll",
        "type": "function",
        "inputs": [
            {"name": "account", "type": "address"},
            {"name": "operator", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
    }
]


@dataclass(slots=True)
class SafeExecutionResult:
    mode: str
    transaction_hash: str
    state: str | None = None
    transaction_id: str | None = None


@dataclass(slots=True)
class ApprovalState:
    missing_usdc_spenders: list[str]
    missing_ctf_operators: list[str]

    @property
    def ready(self) -> bool:
        return not self.missing_usdc_spenders and not self.missing_ctf_operators


def _condition_bytes(condition_id: str) -> bytes:
    return bytes.fromhex(condition_id.removeprefix("0x"))


def _share_units(shares: float) -> int:
    return max(0, int(round(float(shares) * TOKEN_DECIMALS)))


def encode_erc20_approve_calldata(spender: str, amount: int = MAX_UINT256) -> bytes:
    return ERC20_APPROVE_SELECTOR + abi_encode(
        ["address", "uint256"],
        [spender, amount],
    )


def encode_set_approval_for_all_calldata(operator: str, approved: bool = True) -> bytes:
    return ERC1155_SET_APPROVAL_SELECTOR + abi_encode(
        ["address", "bool"],
        [operator, approved],
    )


def encode_merge_calldata(condition_id: str, *, neg_risk: bool, shares: float) -> tuple[str, bytes]:
    amount_units = _share_units(shares)
    condition_bytes = _condition_bytes(condition_id)
    if neg_risk:
        calldata = NEG_RISK_MERGE_SELECTOR + abi_encode(
            ["bytes32", "uint256"],
            [condition_bytes, amount_units],
        )
        return NEG_RISK_ADAPTER_ADDRESS, calldata

    calldata = CTF_MERGE_SELECTOR + abi_encode(
        ["address", "bytes32", "bytes32", "uint256[]", "uint256"],
        [USDC_ADDRESS, HASH_ZERO, condition_bytes, [1, 2], amount_units],
    )
    return CTF_ADDRESS, calldata


def encode_redeem_calldata(
    condition_id: str,
    *,
    neg_risk: bool,
    yes_shares: float,
    no_shares: float,
) -> tuple[str, bytes]:
    condition_bytes = _condition_bytes(condition_id)
    if neg_risk:
        calldata = NEG_RISK_REDEEM_SELECTOR + abi_encode(
            ["bytes32", "uint256[]"],
            [condition_bytes, [_share_units(yes_shares), _share_units(no_shares)]],
        )
        return NEG_RISK_ADAPTER_ADDRESS, calldata

    calldata = CTF_REDEEM_SELECTOR + abi_encode(
        ["address", "bytes32", "bytes32", "uint256[]"],
        [USDC_ADDRESS, HASH_ZERO, condition_bytes, [1, 2]],
    )
    return CTF_ADDRESS, calldata


def build_allowance_calls(state: ApprovalState) -> list[dict[str, str]]:
    calls: list[dict[str, str]] = []
    for spender in state.missing_usdc_spenders:
        calls.append(
            {
                "to": USDC_ADDRESS,
                "data_hex": "0x" + encode_erc20_approve_calldata(spender).hex(),
            }
        )
    for operator in state.missing_ctf_operators:
        calls.append(
            {
                "to": CTF_ADDRESS,
                "data_hex": "0x" + encode_set_approval_for_all_calldata(operator).hex(),
            }
        )
    return calls


@lru_cache(maxsize=1)
def _get_w3() -> Web3:
    rpc_url = os.environ["POLYGON_RPC_URL"]
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to RPC: {rpc_url}")
    return w3


def fetch_weather_approval_state(owner_address: str | None = None) -> ApprovalState:
    owner = Web3.to_checksum_address(owner_address or trading_config.PROXY_WALLET)
    w3 = _get_w3()
    usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=ERC20_ABI)
    ctf = w3.eth.contract(address=Web3.to_checksum_address(CTF_ADDRESS), abi=ERC1155_ABI)
    operators = [
        MAIN_EXCHANGE_ADDRESS,
        NEG_RISK_EXCHANGE_ADDRESS,
        NEG_RISK_ADAPTER_ADDRESS,
    ]
    missing_usdc_spenders = [
        spender
        for spender in operators
        if int(usdc.functions.allowance(owner, Web3.to_checksum_address(spender)).call()) == 0
    ]
    missing_ctf_operators = [
        operator
        for operator in operators
        if not bool(ctf.functions.isApprovedForAll(owner, Web3.to_checksum_address(operator)).call())
    ]
    return ApprovalState(
        missing_usdc_spenders=missing_usdc_spenders,
        missing_ctf_operators=missing_ctf_operators,
    )


def _build_caller_approved_signature(eoa_address: str) -> bytes:
    addr_bytes = bytes.fromhex(eoa_address.lower().removeprefix("0x"))
    r = b"\x00" * 12 + addr_bytes
    s = b"\x00" * 32
    v = b"\x01"
    return r + s + v


def _execute_safe_calls_via_relayer(
    calls: list[dict[str, str]],
    *,
    metadata: str,
) -> SafeExecutionResult:
    from trading.relayer import PolymarketRelayerClient, build_safe_call

    client = PolymarketRelayerClient()
    submission = client.submit_safe_transactions(
        [build_safe_call(call["to"], call["data_hex"]) for call in calls],
        metadata=metadata,
    )
    txn = client.wait_for_terminal_state(submission.transaction_id)
    tx_hash = str(txn.get("transactionHash") or submission.transaction_hash or "")
    state = str(txn.get("state") or submission.state or "")
    return SafeExecutionResult(
        mode="relayer",
        transaction_hash=tx_hash,
        state=state,
        transaction_id=submission.transaction_id,
    )


def _execute_safe_calls_onchain(
    calls: list[dict[str, str]],
    *,
    metadata: str,
) -> SafeExecutionResult:
    del metadata  # metadata is only meaningful for relayer submissions
    w3 = _get_w3()
    safe = w3.eth.contract(
        address=Web3.to_checksum_address(trading_config.PROXY_WALLET),
        abi=SAFE_ABI,
    )
    private_key = trading_config.PRIVATE_KEY
    eoa_address = Web3.to_checksum_address(trading_config.EOA_ADDRESS)
    signature = _build_caller_approved_signature(trading_config.EOA_ADDRESS)
    last_tx_hash = ""
    next_nonce = w3.eth.get_transaction_count(eoa_address, "pending")
    for call in calls:
        tx = safe.functions.execTransaction(
            Web3.to_checksum_address(call["to"]),
            0,
            bytes.fromhex(call["data_hex"].removeprefix("0x")),
            0,
            0,
            0,
            0,
            Web3.to_checksum_address(ZERO_ADDRESS),
            Web3.to_checksum_address(ZERO_ADDRESS),
            signature,
        ).build_transaction(
            {
                "from": eoa_address,
                "nonce": next_nonce,
                "gas": 300_000,
                "maxFeePerGas": w3.to_wei("100", "gwei"),
                "maxPriorityFeePerGas": w3.to_wei("30", "gwei"),
            }
        )
        signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        last_tx_hash = tx_hash.hex()
        next_nonce += 1
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        if receipt["status"] == 0:
            raise RuntimeError(f"Safe call reverted on-chain: {last_tx_hash}")
    return SafeExecutionResult(
        mode="onchain_fallback",
        transaction_hash=last_tx_hash,
        state="STATE_CONFIRMED",
    )


def execute_safe_calls(calls: list[dict[str, str]], *, metadata: str) -> SafeExecutionResult:
    if not calls:
        raise ValueError("At least one safe call is required")

    if trading_config.RELAYER_API_KEY and trading_config.RELAYER_API_KEY_ADDRESS:
        return _execute_safe_calls_via_relayer(calls, metadata=metadata)

    if trading_config.REDEEM_ONCHAIN_FALLBACK:
        return _execute_safe_calls_onchain(calls, metadata=metadata)

    raise RuntimeError(
        "Neither relayer auth nor on-chain fallback is configured for weather merge operations"
    )


def ensure_weather_allowances(*, auto_approve: bool) -> ApprovalState:
    state = fetch_weather_approval_state()
    if state.ready:
        return state
    if not auto_approve:
        raise RuntimeError(
            "Weather bot approvals are missing and WEATHER_MERGE_AUTO_APPROVE is disabled"
        )
    calls = build_allowance_calls(state)
    execute_safe_calls(calls, metadata="PolyEdge weather approvals")
    return fetch_weather_approval_state()


def merge_position(condition_id: str, *, neg_risk: bool, shares: float) -> SafeExecutionResult:
    to_address, calldata = encode_merge_calldata(condition_id, neg_risk=neg_risk, shares=shares)
    return execute_safe_calls(
        [{"to": to_address, "data_hex": "0x" + calldata.hex()}],
        metadata=f"PolyEdge weather merge {condition_id}",
    )


def redeem_position(
    condition_id: str,
    *,
    neg_risk: bool,
    yes_shares: float,
    no_shares: float,
) -> SafeExecutionResult:
    to_address, calldata = encode_redeem_calldata(
        condition_id,
        neg_risk=neg_risk,
        yes_shares=yes_shares,
        no_shares=no_shares,
    )
    return execute_safe_calls(
        [{"to": to_address, "data_hex": "0x" + calldata.hex()}],
        metadata=f"PolyEdge weather redeem {condition_id}",
    )
