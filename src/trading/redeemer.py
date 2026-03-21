"""Auto-redeem resolved Polymarket positions via the relayer or on-chain fallback."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

from eth_abi import encode as abi_encode
from web3 import Web3

from trading import config
from trading import db
from trading.balance import get_usdc_balance
from trading.relayer import PolymarketRelayerClient, build_safe_call, relayer_auth_configured
from trading.utils import log

REDEEM_INTERVAL = 5 * 60  # 5 minutes

USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
NEG_RISK_ADDRESS = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
REDEEM_FUNCTION_SIGNATURE = "redeemPositions(address,bytes32,bytes32,uint256[])"
REDEEM_SELECTOR = Web3.keccak(text=REDEEM_FUNCTION_SIGNATURE)[:4]
HASH_ZERO = b"\x00" * 32

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

_w3: Web3 | None = None


@dataclass(slots=True)
class RedemptionResult:
    mode: str
    transaction_hash: str
    transaction_id: str | None = None
    state: str | None = None


def describe_redemption_mode() -> str:
    if relayer_auth_configured():
        return "relayer"
    if config.REDEEM_ONCHAIN_FALLBACK:
        return "onchain_fallback"
    return "disabled"


def get_w3() -> Web3:
    global _w3
    if _w3 is None:
        rpc_url = os.environ["POLYGON_RPC_URL"]
        _w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        if not _w3.is_connected():
            raise ConnectionError(f"Cannot connect to RPC: {rpc_url}")
        log.info("[REDEEM] Web3 connected for fallback: %s", rpc_url)
    return _w3


def encode_redeem_calldata(condition_id: str, neg_risk: bool) -> tuple[str, bytes]:
    """Return (contract_address, calldata_bytes) for redeemPositions."""
    contract_address = NEG_RISK_ADDRESS if neg_risk else CTF_ADDRESS
    condition_id_bytes = bytes.fromhex(condition_id.removeprefix("0x"))
    encoded_args = abi_encode(
        ["address", "bytes32", "bytes32", "uint256[]"],
        [USDC_ADDRESS, HASH_ZERO, condition_id_bytes, [1, 2]],
    )
    return contract_address, REDEEM_SELECTOR + encoded_args


def build_redeem_safe_call(condition_id: str, neg_risk: bool):
    contract_address, calldata = encode_redeem_calldata(condition_id, neg_risk)
    return build_safe_call(contract_address, "0x" + calldata.hex())


def build_caller_approved_signature(eoa_address: str) -> bytes:
    """Build a Safe caller-approved signature for direct on-chain fallback."""
    addr_bytes = bytes.fromhex(eoa_address.lower().removeprefix("0x"))
    r = b"\x00" * 12 + addr_bytes
    s = b"\x00" * 32
    v = b"\x01"
    return r + s + v


async def is_neg_risk_market(condition_id: str) -> bool:
    """Query the Gamma API to check if a market uses the NegRisk adapter."""
    url = f"https://gamma-api.polymarket.com/markets?conditionId={condition_id}"
    async with config.get_http_client() as client:
        try:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data:
                return bool(data[0].get("negRisk", False))
        except Exception as exc:
            log.warning(
                "[REDEEM] Gamma API lookup failed for %s: %s",
                condition_id[:10],
                exc,
            )
    return False


def _startup_redemption_preflight_sync() -> dict[str, Any]:
    mode = describe_redemption_mode()
    if mode == "relayer":
        client = PolymarketRelayerClient()
        api_keys = client.get_api_keys()
        return {
            "mode": "relayer",
            "signer_address": client.signer_address,
            "proxy_wallet": client.proxy_wallet,
            "visible_keys": len(api_keys),
        }

    if mode == "onchain_fallback":
        w3 = get_w3()
        return {
            "mode": "onchain_fallback",
            "rpc_connected": w3.is_connected(),
            "signer_address": config.EOA_ADDRESS,
            "proxy_wallet": config.PROXY_WALLET,
        }

    raise RuntimeError(
        "Redemption is disabled: RELAYER_API_KEY is not configured and REDEEM_ONCHAIN_FALLBACK is false"
    )


async def startup_redemption_preflight() -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    details = await loop.run_in_executor(None, _startup_redemption_preflight_sync)
    if details["mode"] == "relayer":
        log.info(
            "[REDEEM] Startup preflight ok - mode=relayer signer=%s proxy=%s visible_keys=%s",
            details["signer_address"],
            details["proxy_wallet"],
            details["visible_keys"],
        )
    elif details["mode"] == "onchain_fallback":
        log.warning(
            "[REDEEM] Startup preflight ok - mode=onchain_fallback signer=%s proxy=%s",
            details["signer_address"],
            details["proxy_wallet"],
        )
    return details


def _redeem_condition_via_relayer(
    condition_id: str,
    neg_risk: bool,
    metadata: str | None = None,
) -> RedemptionResult:
    client = PolymarketRelayerClient()
    log.info(
        "[REDEEM] Using relayer key auth for %s via signer=%s proxy=%s",
        condition_id[:10],
        client.signer_address,
        client.proxy_wallet,
    )
    submission = client.submit_safe_transactions(
        [build_redeem_safe_call(condition_id, neg_risk)],
        metadata=metadata or f"Redeem {condition_id}",
    )
    txn = client.wait_for_terminal_state(submission.transaction_id)
    tx_hash = str(txn.get("transactionHash") or submission.transaction_hash or "")
    state = str(txn.get("state") or submission.state or "")
    log.info(
        "[REDEEM] Relayer confirmed %s id=%s state=%s hash=%s",
        condition_id[:10],
        submission.transaction_id,
        state or "?",
        tx_hash or "",
    )
    return RedemptionResult(
        mode="relayer",
        transaction_hash=tx_hash,
        transaction_id=submission.transaction_id,
        state=state,
    )


def _redeem_condition_onchain(
    condition_id: str,
    neg_risk: bool,
) -> RedemptionResult:
    private_key = config.PRIVATE_KEY
    proxy_wallet = config.PROXY_WALLET
    eoa_address = config.EOA_ADDRESS
    contract_address, calldata = encode_redeem_calldata(condition_id, neg_risk)

    w3 = get_w3()
    safe = w3.eth.contract(
        address=Web3.to_checksum_address(proxy_wallet),
        abi=SAFE_ABI,
    )

    safe_nonce = safe.functions.nonce().call()
    log.info("[REDEEM] Fallback on-chain redeem %s safe_nonce=%d", condition_id[:10], safe_nonce)

    signature = build_caller_approved_signature(eoa_address)
    tx = safe.functions.execTransaction(
        Web3.to_checksum_address(contract_address),
        0,
        calldata,
        0,
        0,
        0,
        0,
        Web3.to_checksum_address(ZERO_ADDRESS),
        Web3.to_checksum_address(ZERO_ADDRESS),
        signature,
    ).build_transaction(
        {
            "from": Web3.to_checksum_address(eoa_address),
            "nonce": w3.eth.get_transaction_count(Web3.to_checksum_address(eoa_address)),
            "gas": 300_000,
            "maxFeePerGas": w3.to_wei("100", "gwei"),
            "maxPriorityFeePerGas": w3.to_wei("30", "gwei"),
        }
    )

    signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hash_hex = tx_hash.hex()
    log.info("[REDEEM] Fallback tx submitted: %s", tx_hash_hex)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt["status"] == 0:
        raise RuntimeError(f"Fallback redemption reverted on-chain: {tx_hash_hex}")

    log.info(
        "[REDEEM] Fallback confirmed block=%d tx=%s",
        receipt["blockNumber"],
        tx_hash_hex,
    )
    return RedemptionResult(
        mode="onchain_fallback",
        transaction_hash=tx_hash_hex,
        state="STATE_CONFIRMED",
    )


async def redeem_condition(
    condition_id: str,
    neg_risk: bool,
    metadata: str | None = None,
) -> RedemptionResult:
    loop = asyncio.get_event_loop()
    if relayer_auth_configured():
        return await loop.run_in_executor(
            None,
            lambda: _redeem_condition_via_relayer(condition_id, neg_risk, metadata),
        )

    if config.REDEEM_ONCHAIN_FALLBACK:
        log.warning(
            "[REDEEM] RELAYER_API_KEY not configured, using direct on-chain fallback for %s",
            condition_id[:10],
        )
        return await loop.run_in_executor(
            None,
            lambda: _redeem_condition_onchain(condition_id, neg_risk),
        )

    raise RuntimeError(
        "RELAYER_API_KEY is not configured and REDEEM_ONCHAIN_FALLBACK is disabled"
    )


async def _redeem_cycle() -> None:
    """One pass: fetch unredeemed winning trades, redeem them, then mark in DB."""
    fills = await db.get_unredeemed_fills()
    if not fills:
        return

    seen: dict[str, dict[str, Any]] = {}
    for fill in fills:
        condition_id = fill["condition_id"]
        if condition_id and condition_id not in seen:
            seen[condition_id] = fill

    if not seen:
        return

    log.info("[REDEEM] %d condition(s) queued", len(seen))

    for condition_id, fill in seen.items():
        short = condition_id[:10]
        try:
            neg_risk = await is_neg_risk_market(condition_id)
            balance_before = await get_usdc_balance()
            result = await redeem_condition(
                condition_id,
                neg_risk,
                metadata=f"PolyEdge redeem {condition_id}",
            )
            balance_after = await get_usdc_balance()
            amount = (
                max(0.0, balance_after - balance_before)
                if balance_before >= 0 and balance_after >= 0
                else 0.0
            )

            log.info(
                "[REDEEM] Completed %s mode=%s state=%s tx=%s",
                short,
                result.mode,
                result.state or "?",
                result.transaction_hash or "",
            )

            await db.record_redemption_success(
                condition_id,
                mode=result.mode,
                transaction_id=result.transaction_id,
                transaction_hash=result.transaction_hash,
                state=result.state,
                amount_redeemed=amount,
            )
            log.info("[REDEEM] Marked redeemed %s ($%.2f returned)", short, amount)

            if amount > 0:
                await db.log_event(
                    "trade_redeemed",
                    f"Redeemed winning position - ${amount:.2f} returned",
                    {
                        "market_id": fill.get("market_id"),
                        "amount_redeemed": round(amount, 2),
                        "condition_id": condition_id,
                        "redemption_mode": result.mode,
                        "relayer_transaction_id": result.transaction_id,
                        "relayer_state": result.state,
                        "tx_hash": result.transaction_hash,
                    },
                )
        except Exception as exc:
            await db.record_redemption_failure(condition_id, str(exc))
            log.error("[REDEEM] Failed %s: %s", short, exc, exc_info=True)
            continue

        await asyncio.sleep(10)


async def redemption_loop() -> None:
    """Run redemption checks every 5 minutes, starting immediately."""
    log.info("Redemption loop started (every %d min)", REDEEM_INTERVAL // 60)
    while True:
        try:
            await _redeem_cycle()
        except Exception:
            log.exception("Unexpected error in redemption loop")
        await asyncio.sleep(REDEEM_INTERVAL)
