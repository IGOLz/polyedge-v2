"""Dataclasses used by wallet-forensics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class WalletTarget:
    profile_name: str | None
    proxy_wallet: str
    pseudonym: str | None = None
    bio: str | None = None
    created_at: datetime | None = None
    display_username_public: bool | None = None
    total_traded_markets: int | None = None
    public_profile: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReceiptSummary:
    transaction_hash: str
    classifications: list[str]
    touched_contracts: list[str]
    usdc_in: float
    usdc_out: float
    wallet_token_ids_in: list[str] = field(default_factory=list)
    wallet_token_ids_out: list[str] = field(default_factory=list)
    raw_receipt: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PositionState:
    asset: str
    condition_id: str
    outcome: str | None
    size: float = 0.0
    cost_basis: float = 0.0
    realized_pnl: float = 0.0

    @property
    def average_cost(self) -> float:
        if self.size <= 0:
            return 0.0
        return self.cost_basis / self.size
