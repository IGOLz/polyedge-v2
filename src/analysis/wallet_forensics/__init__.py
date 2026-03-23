"""Wallet-forensics analysis pipeline for public Polymarket histories."""

from __future__ import annotations

from typing import Any


def run_wallet_forensics(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Import the heavy CLI pipeline lazily so lightweight helpers stay usable."""

    from analysis.wallet_forensics.main import run_wallet_forensics as _run_wallet_forensics

    return _run_wallet_forensics(*args, **kwargs)


__all__ = ["run_wallet_forensics"]
