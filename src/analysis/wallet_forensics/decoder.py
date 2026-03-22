"""Decode Polygon receipts into wallet-relevant Polymarket classifications."""

from __future__ import annotations

from typing import Any

from analysis.wallet_forensics.constants import (
    CTF_ADDRESS,
    CTF_EXCHANGE_ADDRESS,
    CTF_MERGE_TOPIC,
    CTF_REDEEM_TOPIC,
    CTF_SPLIT_TOPIC,
    ERC20_TRANSFER_TOPIC,
    ERC1155_TRANSFER_BATCH_TOPIC,
    ERC1155_TRANSFER_SINGLE_TOPIC,
    EXCHANGE_TRADE_TOPICS,
    NEG_RISK_ADAPTER_ADDRESS,
    NEG_RISK_MERGE_TOPIC,
    NEG_RISK_REDEEM_TOPIC,
    NEG_RISK_SPLIT_TOPIC,
    USDC_ADDRESS,
)


def decode_receipt_for_wallet(
    receipt: dict[str, Any] | None,
    wallet: str,
    *,
    activity_types: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    if not receipt:
        return {
            "transaction_hash": "",
            "block_number": None,
            "block_timestamp": None,
            "classifications": list(dict.fromkeys(str(item).lower() for item in activity_types)),
            "touched_contracts": [],
            "usdc_in": 0.0,
            "usdc_out": 0.0,
            "wallet_token_ids_in": [],
            "wallet_token_ids_out": [],
            "payload_json": {},
        }

    wallet_lower = wallet.lower()
    touched_contracts: set[str] = set()
    classifications: list[str] = [str(item).lower() for item in activity_types]
    token_ids_in: list[str] = []
    token_ids_out: list[str] = []
    usdc_in = 0.0
    usdc_out = 0.0
    trade_like = False

    for log in receipt.get("logs") or []:
        address = str(log.get("address") or "").lower()
        touched_contracts.add(address)
        topics = [str(topic).lower() for topic in log.get("topics") or []]
        if not topics:
            continue
        topic0 = topics[0]

        if topic0 == ERC20_TRANSFER_TOPIC and address == USDC_ADDRESS:
            amount = _parse_uint(log.get("data"))
            from_addr = _topic_address(topics, 1)
            to_addr = _topic_address(topics, 2)
            if to_addr == wallet_lower:
                usdc_in += amount
            if from_addr == wallet_lower:
                usdc_out += amount
            continue

        if topic0 == ERC1155_TRANSFER_SINGLE_TOPIC:
            from_addr = _topic_address(topics, 2)
            to_addr = _topic_address(topics, 3)
            token_id = _parse_erc1155_single_id(log.get("data"))
            if to_addr == wallet_lower and token_id:
                token_ids_in.append(token_id)
            if from_addr == wallet_lower and token_id:
                token_ids_out.append(token_id)
            continue

        if topic0 == ERC1155_TRANSFER_BATCH_TOPIC:
            from_addr = _topic_address(topics, 2)
            to_addr = _topic_address(topics, 3)
            ids = _parse_erc1155_batch_ids(log.get("data"))
            if to_addr == wallet_lower:
                token_ids_in.extend(ids)
            if from_addr == wallet_lower:
                token_ids_out.extend(ids)
            continue

        if address == NEG_RISK_ADAPTER_ADDRESS and topic0 == NEG_RISK_SPLIT_TOPIC:
            classifications.append("split")
        elif address == NEG_RISK_ADAPTER_ADDRESS and topic0 == NEG_RISK_MERGE_TOPIC:
            classifications.append("merge")
        elif address == NEG_RISK_ADAPTER_ADDRESS and topic0 == NEG_RISK_REDEEM_TOPIC:
            classifications.append("redeem")
        elif address == CTF_ADDRESS and topic0 == CTF_SPLIT_TOPIC:
            classifications.append("split")
        elif address == CTF_ADDRESS and topic0 == CTF_MERGE_TOPIC:
            classifications.append("merge")
        elif address == CTF_ADDRESS and topic0 == CTF_REDEEM_TOPIC:
            classifications.append("redeem")
        elif address == CTF_EXCHANGE_ADDRESS and topic0 in EXCHANGE_TRADE_TOPICS:
            trade_like = True

    if trade_like or (
        CTF_EXCHANGE_ADDRESS in touched_contracts and (usdc_in > 0 or usdc_out > 0) and (token_ids_in or token_ids_out)
    ):
        classifications.append("trade")

    if "conversion" in {item.lower() for item in activity_types}:
        classifications.append("conversion")

    deduped = list(dict.fromkeys(item for item in classifications if item))
    return {
        "transaction_hash": receipt.get("transactionHash") or "",
        "block_number": _parse_int(receipt.get("blockNumber")),
        "block_timestamp": _parse_int_from_logs(receipt.get("logs") or []),
        "classifications": deduped,
        "touched_contracts": sorted(touched_contracts),
        "usdc_in": usdc_in,
        "usdc_out": usdc_out,
        "wallet_token_ids_in": token_ids_in,
        "wallet_token_ids_out": token_ids_out,
        "payload_json": receipt,
    }


def _topic_address(topics: list[str], index: int) -> str | None:
    if len(topics) <= index:
        return None
    topic = topics[index]
    if len(topic) < 42:
        return None
    return "0x" + topic[-40:]


def _parse_uint(value: Any) -> float:
    text = str(value or "0x0")
    try:
        return float(int(text, 16))
    except (TypeError, ValueError):
        return 0.0


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value)
    try:
        if text.startswith("0x"):
            return int(text, 16)
        return int(text)
    except (TypeError, ValueError):
        return None


def _parse_int_from_logs(logs: list[dict[str, Any]]) -> int | None:
    for log in logs:
        raw = log.get("blockTimestamp")
        parsed = _parse_int(raw)
        if parsed is not None:
            return parsed
    return None


def _parse_erc1155_single_id(data: Any) -> str | None:
    text = str(data or "")
    if not text.startswith("0x"):
        return None
    payload = text[2:]
    if len(payload) < 64:
        return None
    return "0x" + payload[:64].lower()


def _parse_erc1155_batch_ids(data: Any) -> list[str]:
    text = str(data or "")
    if not text.startswith("0x"):
        return []
    payload = text[2:]
    if len(payload) < 64 * 4:
        return []
    ids_offset = int(payload[0:64], 16) * 2
    if ids_offset + 64 > len(payload):
        return []
    count = int(payload[ids_offset: ids_offset + 64], 16)
    ids: list[str] = []
    cursor = ids_offset + 64
    for _ in range(count):
        if cursor + 64 > len(payload):
            break
        ids.append("0x" + payload[cursor: cursor + 64].lower())
        cursor += 64
    return ids
