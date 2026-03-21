"""Trading-specific configuration — extends shared config.

Trading auth, strategy constants, execution config all live here.
"""

import os

from shared.config import TRADING_AUTH, CHAIN_ID, PROXY_URL

import httpx

# ── Re-export auth keys with convenient names ────────────────────────────

PRIVATE_KEY = TRADING_AUTH.get("private_key", "")
API_KEY = TRADING_AUTH.get("polymarket_api_key", "")
API_SECRET = TRADING_AUTH.get("polymarket_api_secret", "")
API_PASSPHRASE = TRADING_AUTH.get("polymarket_api_passphrase", "")
PROXY_WALLET = TRADING_AUTH.get("proxy_wallet", "")
EOA_ADDRESS = TRADING_AUTH.get("eoa_address", "")
RELAYER_API_KEY = os.getenv("RELAYER_API_KEY", "").strip()
RELAYER_API_KEY_ADDRESS = os.getenv("RELAYER_API_KEY_ADDRESS", EOA_ADDRESS).strip() or EOA_ADDRESS
RELAYER_BASE_URL = os.getenv("RELAYER_BASE_URL", "https://relayer-v2.polymarket.com").strip().rstrip("/")
REDEEM_ONCHAIN_FALLBACK = os.getenv("REDEEM_ONCHAIN_FALLBACK", "true").strip().lower() == "true"

CLOB_BASE_URL = "https://clob.polymarket.com"

# ── Betting parameters ──────────────────────────────────────────────────

BET_SIZE_USD: float = float(os.getenv("BET_SIZE_USD", "1.5"))
DAILY_LOSS_LIMIT: float = float(os.getenv("DAILY_LOSS_LIMIT", "30.0"))
LOOP_INTERVAL: int = int(os.getenv("LOOP_INTERVAL", "1"))
DRY_RUN: bool = False


# ── Strategy toggles ────────────────────────────────────────────────────

STRATEGY_MOMENTUM_ENABLED: bool = os.getenv("STRATEGY_MOMENTUM_ENABLED", "true").lower() == "true"


# ── HTTP helpers ─────────────────────────────────────────────────────────

def get_http_client(**kwargs) -> httpx.AsyncClient:
    if PROXY_URL:
        kwargs.setdefault("proxy", PROXY_URL)
    kwargs.setdefault("timeout", 30.0)
    return httpx.AsyncClient(**kwargs)


def get_sync_http_client(**kwargs) -> httpx.Client:
    if PROXY_URL:
        kwargs.setdefault("proxy", PROXY_URL)
    kwargs.setdefault("timeout", 30.0)
    return httpx.Client(**kwargs)


def patch_clob_client_proxy(proxy_url: str = "") -> None:
    if not proxy_url:
        return
    import py_clob_client.http_helpers.helpers as clob_helpers
    clob_helpers._http_client = httpx.Client(proxy=proxy_url, timeout=30.0)
