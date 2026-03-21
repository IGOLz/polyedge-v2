"""Helpers for Polymarket relayer submissions using relayer API keys."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from py_builder_relayer_client.builder.derive import derive
from py_builder_relayer_client.builder.safe import build_safe_transaction_request
from py_builder_relayer_client.config import get_contract_config
from py_builder_relayer_client.models import (
    OperationType,
    SafeTransaction,
    SafeTransactionArgs,
)
from py_builder_relayer_client.signer import Signer

from trading import config
from trading.utils import log


TERMINAL_SUCCESS_STATES = {"STATE_MINED", "STATE_CONFIRMED"}
TERMINAL_FAILURE_STATES = {"STATE_FAILED", "STATE_INVALID"}


class RelayerError(RuntimeError):
    """Raised when relayer configuration or submission fails."""


@dataclass(slots=True)
class RelayerSubmission:
    transaction_id: str
    transaction_hash: str
    state: str
    raw: dict[str, Any]


def relayer_auth_configured(
    api_key: str | None = None,
    api_key_address: str | None = None,
) -> bool:
    key = (api_key if api_key is not None else config.RELAYER_API_KEY).strip()
    address = (
        api_key_address
        if api_key_address is not None
        else config.RELAYER_API_KEY_ADDRESS or config.EOA_ADDRESS
    ).strip()
    return bool(key and address)


def build_relayer_auth_headers(
    api_key: str | None = None,
    api_key_address: str | None = None,
) -> dict[str, str]:
    key = (api_key if api_key is not None else config.RELAYER_API_KEY).strip()
    address = (
        api_key_address
        if api_key_address is not None
        else config.RELAYER_API_KEY_ADDRESS or config.EOA_ADDRESS
    ).strip()
    if not key:
        raise RelayerError("RELAYER_API_KEY is required for relayer submissions")
    if not address:
        raise RelayerError(
            "RELAYER_API_KEY_ADDRESS (or EOA_ADDRESS) is required for relayer submissions"
        )
    return {
        "RELAYER_API_KEY": key,
        "RELAYER_API_KEY_ADDRESS": address,
        "Content-Type": "application/json",
    }


def build_safe_call(to_address: str, data_hex: str, value: str = "0") -> SafeTransaction:
    return SafeTransaction(
        to=to_address,
        operation=OperationType.Call,
        data=data_hex,
        value=value,
    )


class PolymarketRelayerClient:
    """Minimal relayer client for SAFE transactions using relayer API keys."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        private_key: str | None = None,
        signer_address: str | None = None,
        proxy_wallet: str | None = None,
        api_key: str | None = None,
        api_key_address: str | None = None,
        chain_id: int | None = None,
    ) -> None:
        self.base_url = (base_url or config.RELAYER_BASE_URL).rstrip("/")
        self.private_key = (private_key or config.PRIVATE_KEY).strip()
        if not self.private_key:
            raise RelayerError("PRIVATE_KEY is required for relayer submissions")
        self.chain_id = chain_id or config.CHAIN_ID
        self.signer = Signer(self.private_key, self.chain_id)
        self.signer_address = (signer_address or config.EOA_ADDRESS or self.signer.address()).strip()
        self.api_key = (api_key or config.RELAYER_API_KEY).strip()
        self.api_key_address = (
            api_key_address or config.RELAYER_API_KEY_ADDRESS or self.signer_address
        ).strip()
        self.contract_config = get_contract_config(self.chain_id)
        self.derived_proxy_wallet = derive(
            self.signer.address(), self.contract_config.safe_factory
        )
        self.proxy_wallet = (proxy_wallet or config.PROXY_WALLET or self.derived_proxy_wallet).strip()
        self._validate_configuration()

    def _validate_configuration(self) -> None:
        if not self.base_url:
            raise RelayerError("RELAYER_BASE_URL is required")
        if self.signer_address.lower() != self.signer.address().lower():
            raise RelayerError(
                "EOA_ADDRESS does not match the configured PRIVATE_KEY signer address"
            )
        if not relayer_auth_configured(self.api_key, self.api_key_address):
            raise RelayerError(
                "Relayer auth is not configured. Set RELAYER_API_KEY and RELAYER_API_KEY_ADDRESS."
            )
        if self.api_key_address.lower() != self.signer_address.lower():
            raise RelayerError(
                "RELAYER_API_KEY_ADDRESS must match the signer/EOA address for this wallet"
            )
        if self.proxy_wallet.lower() != self.derived_proxy_wallet.lower():
            raise RelayerError(
                "PROXY_WALLET does not match the Safe derived from PRIVATE_KEY/EOA_ADDRESS"
            )

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> Any:
        url = f"{self.base_url}{path}"
        request_headers = headers or {}
        with config.get_sync_http_client(timeout=timeout) as client:
            response = client.request(
                method=method,
                url=url,
                headers=request_headers,
                params=params,
                json=json,
            )
            response.raise_for_status()
            return response.json()

    def get_api_keys(self) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "/relayer/api/keys",
            headers=build_relayer_auth_headers(self.api_key, self.api_key_address),
            timeout=15.0,
        )
        return payload if isinstance(payload, list) else []

    def get_nonce(self) -> str:
        payload = self._request(
            "GET",
            "/nonce",
            params={"address": self.signer_address, "type": "SAFE"},
            timeout=15.0,
        )
        nonce = ""
        if isinstance(payload, dict):
            nonce = str(payload.get("nonce") or "").strip()
        if not nonce:
            raise RelayerError(f"Invalid nonce payload received: {payload!r}")
        return nonce

    def is_safe_deployed(self) -> bool:
        payload = self._request(
            "GET",
            "/deployed",
            params={"address": self.proxy_wallet},
            timeout=15.0,
        )
        return bool(payload.get("deployed")) if isinstance(payload, dict) else False

    def get_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        payload = self._request(
            "GET",
            "/transaction",
            params={"id": transaction_id},
            timeout=15.0,
        )
        if isinstance(payload, list):
            return payload[0] if payload else None
        if isinstance(payload, dict):
            return payload
        return None

    def submit_safe_transactions(
        self,
        transactions: list[SafeTransaction],
        *,
        metadata: str = "",
    ) -> RelayerSubmission:
        if not transactions:
            raise RelayerError("At least one transaction is required")
        if not self.is_safe_deployed():
            raise RelayerError(
                f"Safe {self.proxy_wallet} is not deployed on the Polymarket relayer"
            )

        request_body = build_safe_transaction_request(
            signer=self.signer,
            args=SafeTransactionArgs(
                from_address=self.signer_address,
                nonce=self.get_nonce(),
                chain_id=self.chain_id,
                transactions=transactions,
            ),
            config=self.contract_config,
            metadata=metadata,
        ).to_dict()

        request_proxy = str(request_body.get("proxyWallet") or "").strip()
        if request_proxy.lower() != self.proxy_wallet.lower():
            raise RelayerError(
                "Relayer request proxy wallet does not match configured PROXY_WALLET"
            )

        response = self._request(
            "POST",
            "/submit",
            headers=build_relayer_auth_headers(self.api_key, self.api_key_address),
            json=request_body,
            timeout=30.0,
        )
        if not isinstance(response, dict):
            raise RelayerError(f"Unexpected relayer submit response: {response!r}")

        submission = RelayerSubmission(
            transaction_id=str(response.get("transactionID") or ""),
            transaction_hash=str(response.get("transactionHash") or ""),
            state=str(response.get("state") or ""),
            raw=response,
        )
        if not submission.transaction_id:
            raise RelayerError(f"Relayer submission missing transactionID: {response!r}")
        log.info(
            "[RELAYER] Submitted SAFE tx id=%s state=%s hash=%s",
            submission.transaction_id,
            submission.state or "?",
            submission.transaction_hash or "",
        )
        return submission

    def wait_for_terminal_state(
        self,
        transaction_id: str,
        *,
        poll_interval_seconds: float = 2.0,
        max_polls: int = 60,
    ) -> dict[str, Any]:
        import time

        for attempt in range(1, max_polls + 1):
            txn = self.get_transaction(transaction_id)
            if txn:
                state = str(txn.get("state") or "")
                tx_hash = str(txn.get("transactionHash") or "")
                log.info(
                    "[RELAYER] Poll %d/%d tx=%s state=%s hash=%s",
                    attempt,
                    max_polls,
                    transaction_id,
                    state or "?",
                    tx_hash or "",
                )
                if state in TERMINAL_SUCCESS_STATES:
                    return txn
                if state in TERMINAL_FAILURE_STATES:
                    raise RelayerError(
                        f"Relayer transaction {transaction_id} ended in failure state {state}"
                    )
            time.sleep(poll_interval_seconds)

        raise RelayerError(
            f"Timed out waiting for relayer transaction {transaction_id} to finish"
        )
