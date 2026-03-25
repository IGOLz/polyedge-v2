"""Public Polymarket and Polygon fetchers for wallet-forensics."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from datetime import UTC
from typing import Any, Callable
from urllib.parse import quote_plus

import httpx

from analysis.wallet_forensics.constants import (
    CLOB_API_BASE,
    DATA_API_BASE,
    DEFAULT_PAGE_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    FORENSICS_USER_AGENT,
    GAMMA_API_BASE,
    MAX_OFFSET,
    MIN_SPLIT_WINDOW_SECONDS,
    POLYGON_RPC_URL,
)
from analysis.wallet_forensics.utils import parse_iso_datetime, row_hash, safe_int, utc_now
from shared.http import get_sync_http_client

logger = logging.getLogger(__name__)


class WalletForensicsClient:
    """Thin client for public Polymarket and Polygon endpoints."""

    def __init__(self) -> None:
        self._http = get_sync_http_client(
            timeout=DEFAULT_TIMEOUT_SECONDS,
            headers={"User-Agent": FORENSICS_USER_AGENT},
        )

    def close(self) -> None:
        self._http.close()

    def _get_json(self, url: str, **kwargs) -> Any:
        return self._request_json("GET", url, **kwargs)

    def _post_json(self, url: str, payload: Any) -> Any:
        return self._request_json("POST", url, json=payload)

    def _request_json(self, method: str, url: str, **kwargs) -> Any:
        response = None
        for attempt in range(6):
            response = self._http.request(method, url, **kwargs)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 5:
                delay = _retry_delay_seconds(response, attempt)
                logger.warning(
                    "Retrying %s %s after HTTP %s (sleep %.1fs, attempt %s)",
                    method,
                    url,
                    response.status_code,
                    delay,
                    attempt + 1,
                )
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response.json()
        assert response is not None
        response.raise_for_status()
        return response.json()

    def resolve_wallet(self, profile_name: str) -> dict[str, Any]:
        encoded = quote_plus(profile_name)
        payload = self._get_json(
            f"{GAMMA_API_BASE}/public-search?q={encoded}&search_profiles=true&limit_per_type=10"
        )
        candidates = payload.get("profiles") or []
        if not candidates:
            raise RuntimeError(f"No profile match found for {profile_name!r}")

        lowered = profile_name.strip().lower()
        exact = next(
            (item for item in candidates if str(item.get("name", "")).strip().lower() == lowered),
            None,
        )
        return exact or candidates[0]

    def fetch_public_profile(self, proxy_wallet: str) -> dict[str, Any]:
        return self._get_json(f"{GAMMA_API_BASE}/public-profile?address={proxy_wallet}")

    def fetch_traded_count(self, proxy_wallet: str) -> int | None:
        payload = self._get_json(f"{DATA_API_BASE}/traded?user={proxy_wallet}")
        return safe_int(payload.get("traded"))

    def fetch_value_snapshot(self, proxy_wallet: str) -> Any:
        return self._get_json(f"{DATA_API_BASE}/value?user={proxy_wallet}")

    def fetch_positions(self, proxy_wallet: str, *, closed: bool) -> list[dict[str, Any]]:
        endpoint = "closed-positions" if closed else "positions"

        def _fetch_page(offset: int, limit: int) -> list[dict[str, Any]]:
            params = {
                "user": proxy_wallet,
                "limit": limit,
                "offset": offset,
            }
            if closed:
                params.update({"sortBy": "TIMESTAMP", "sortDirection": "DESC"})
            else:
                params.update({"sortBy": "TOKENS", "sortDirection": "DESC"})
            return self._get_json(
                f"{DATA_API_BASE}/{endpoint}",
                params=params,
            )

        return collect_offset_pages(_fetch_page)

    def fetch_activity(
        self,
        proxy_wallet: str,
        *,
        markets: list[str] | None = None,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> list[dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        market_filters = markets or [None]
        for market_id in market_filters:
            def _fetch_page(offset: int, limit: int, market: str | None = market_id) -> list[dict[str, Any]]:
                params = {
                    "user": proxy_wallet,
                    "limit": limit,
                    "offset": offset,
                    "sortBy": "TIMESTAMP",
                    "sortDirection": "DESC",
                }
                if market:
                    params["market"] = market
                return self._get_json(
                    f"{DATA_API_BASE}/activity",
                    params=params,
                )

            def _fetch_window(
                offset: int,
                limit: int,
                window_start: int,
                window_end: int,
                market: str | None = market_id,
            ) -> list[dict[str, Any]]:
                params = {
                    "user": proxy_wallet,
                    "limit": limit,
                    "offset": offset,
                    "sortBy": "TIMESTAMP",
                    "sortDirection": "DESC",
                    "start": window_start,
                    "end": window_end,
                }
                if market:
                    params["market"] = market
                return self._get_json(
                    f"{DATA_API_BASE}/activity",
                    params=params,
                )

            for row in _collect_market_rows(
                fetch_offset_page=_fetch_page,
                fetch_window_page=_fetch_window,
                start_ts=start_ts,
                end_ts=end_ts,
                description=f"activity {market_id or proxy_wallet}",
            ):
                records[row_hash(row)] = row

        rows = list(records.values())
        rows.sort(key=lambda item: (safe_int(item.get("timestamp")) or 0, item.get("transactionHash") or "", row_hash(item)))
        return rows

    def fetch_trades(
        self,
        proxy_wallet: str,
        *,
        markets: list[str] | None = None,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> list[dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        market_filters = markets or [None]
        for market_id in market_filters:
            def _fetch_page(offset: int, limit: int, market: str | None = market_id) -> list[dict[str, Any]]:
                params = {
                    "user": proxy_wallet,
                    "limit": limit,
                    "offset": offset,
                    "sortDirection": "DESC",
                    "takerOnly": "false",
                }
                if market:
                    params["market"] = market
                return self._get_json(
                    f"{DATA_API_BASE}/trades",
                    params=params,
                )

            try:
                market_rows = collect_offset_pages(_fetch_page)
            except (RuntimeError, httpx.HTTPStatusError) as exc:
                if not _should_fallback_to_activity(exc, start_ts=start_ts, end_ts=end_ts):
                    raise
                logger.warning(
                    "Falling back to activity-derived trade reconstruction for %s after offset cap: %s",
                    market_id or proxy_wallet,
                    exc,
                )
                market_rows = [
                    _activity_trade_row(row)
                    for row in self.fetch_activity(
                        proxy_wallet,
                        markets=[market_id] if market_id else None,
                        start_ts=start_ts,
                        end_ts=end_ts,
                    )
                    if str(row.get("type") or "").upper() == "TRADE"
                ]

            for row in market_rows:
                records[row_hash(row)] = row

        values = list(records.values())
        values.sort(key=lambda item: (safe_int(item.get("timestamp")) or 0, item.get("transactionHash") or "", row_hash(item)))
        return values

    def fetch_event_by_slug(self, event_slug: str) -> dict[str, Any] | None:
        payload = self._get_json(
            f"{GAMMA_API_BASE}/events",
            params={"slug": event_slug},
        )
        if isinstance(payload, list):
            return payload[0] if payload else None
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            return data[0] if data else None
        return payload if isinstance(payload, dict) else None

    def fetch_prices_history(
        self,
        asset_id: str,
        *,
        start_ts: int | None = None,
        end_ts: int | None = None,
        fidelity: int = 1,
        interval: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "market": asset_id,
            "fidelity": fidelity,
        }
        if interval:
            params["interval"] = interval
        if start_ts is not None:
            params["startTs"] = start_ts
        if end_ts is not None:
            params["endTs"] = end_ts
        payload = self._get_json(
            f"{CLOB_API_BASE}/prices-history",
            params=params,
        )
        if isinstance(payload, dict):
            history = payload.get("history")
            if isinstance(history, list):
                return history
        if isinstance(payload, list):
            return payload
        return []

    def fetch_transaction_receipt(self, tx_hash: str) -> dict[str, Any] | None:
        payload = self._post_json(
            POLYGON_RPC_URL,
            {
                "jsonrpc": "2.0",
                "method": "eth_getTransactionReceipt",
                "params": [tx_hash],
                "id": 1,
            },
        )
        return payload.get("result")

    def fetch_transaction_receipts(self, tx_hashes: Sequence[str]) -> dict[str, dict[str, Any] | None]:
        normalized = [str(tx_hash).strip() for tx_hash in tx_hashes if str(tx_hash).strip()]
        if not normalized:
            return {}
        if len(normalized) == 1:
            tx_hash = normalized[0]
            return {tx_hash: self.fetch_transaction_receipt(tx_hash)}

        payload = [
            {
                "jsonrpc": "2.0",
                "method": "eth_getTransactionReceipt",
                "params": [tx_hash],
                "id": tx_hash,
            }
            for tx_hash in normalized
        ]
        response = self._post_json(POLYGON_RPC_URL, payload)
        if not isinstance(response, list):
            logger.warning("Polygon batch receipt RPC returned non-list payload; falling back to single requests")
            return {tx_hash: self.fetch_transaction_receipt(tx_hash) for tx_hash in normalized}

        receipts: dict[str, dict[str, Any] | None] = {tx_hash: None for tx_hash in normalized}
        for item in response:
            if not isinstance(item, dict):
                continue
            tx_hash = str(item.get("id") or "").strip()
            if not tx_hash or tx_hash not in receipts:
                continue
            if item.get("error"):
                logger.warning("Polygon batch receipt RPC returned an error for %s: %s", tx_hash, item["error"])
                receipts[tx_hash] = self.fetch_transaction_receipt(tx_hash)
                continue
            receipts[tx_hash] = item.get("result")
        missing = [tx_hash for tx_hash, receipt in receipts.items() if tx_hash and receipt is None]
        if missing:
            logger.warning("Polygon batch receipt RPC returned %s missing receipts; falling back to single requests", len(missing))
            for tx_hash in missing:
                receipts[tx_hash] = self.fetch_transaction_receipt(tx_hash)
        return receipts


def infer_wallet_time_bounds(target: dict[str, Any], start: str | None, end: str | None) -> tuple[int, int]:
    created_at = parse_iso_datetime(target.get("createdAt")) or utc_now()
    start_dt = parse_iso_datetime(start) if start else created_at
    end_dt = parse_iso_datetime(end) if end else utc_now()
    start_dt = start_dt.astimezone(UTC)
    end_dt = end_dt.astimezone(UTC)
    return int(start_dt.timestamp()), int(end_dt.timestamp())


def collect_offset_pages(
    fetch_page: Callable[[int, int], list[dict[str, Any]]],
    *,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    seen: set[str] = set()
    while True:
        page = fetch_page(offset, limit)
        if not page:
            break
        for row in page:
            digest = row_hash(row)
            if digest in seen:
                continue
            seen.add(digest)
            items.append(row)
        if len(page) < limit:
            break
        offset += limit
        if offset > MAX_OFFSET:
            raise RuntimeError("Offset pagination exceeded public API limit")
    return items


def collect_time_sliced_pages(
    *,
    fetch_page: Callable[[int, int, int, int], list[dict[str, Any]]],
    start_ts: int,
    end_ts: int,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}

    def _fetch_window(window_start: int, window_end: int) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        offset = 0
        while True:
            try:
                page = fetch_page(offset, limit, window_start, window_end)
            except httpx.HTTPStatusError as exc:
                if _is_offset_limit_error(exc):
                    if window_end - window_start <= MIN_SPLIT_WINDOW_SECONDS:
                        logger.warning(
                            "Window %s-%s hit an API offset cap at offset %s; returning deduplicated partial slice",
                            window_start,
                            window_end,
                            offset,
                        )
                        return records
                    midpoint = window_start + (window_end - window_start) // 2
                    left = _fetch_window(window_start, midpoint)
                    right = _fetch_window(midpoint + 1, window_end)
                    return left + right
                raise
            if not page:
                break
            records.extend(page)
            if len(page) < limit:
                return records
            offset += limit
            if offset > MAX_OFFSET:
                if window_end - window_start <= MIN_SPLIT_WINDOW_SECONDS:
                    logger.warning(
                        "Window %s-%s exceeded offset limit; returning deduplicated partial slice",
                        window_start,
                        window_end,
                    )
                    return records
                midpoint = window_start + (window_end - window_start) // 2
                left = _fetch_window(window_start, midpoint)
                right = _fetch_window(midpoint + 1, window_end)
                return left + right
        return records

    for row in _fetch_window(start_ts, end_ts):
        seen[row_hash(row)] = row
    values = list(seen.values())
    values.sort(key=lambda item: (safe_int(item.get("timestamp")) or 0, item.get("transactionHash") or "", row_hash(item)))
    return values


def _collect_market_rows(
    *,
    fetch_offset_page: Callable[[int, int], list[dict[str, Any]]],
    fetch_window_page: Callable[[int, int, int, int], list[dict[str, Any]]],
    start_ts: int | None,
    end_ts: int | None,
    description: str,
) -> list[dict[str, Any]]:
    try:
        return collect_offset_pages(fetch_offset_page)
    except (RuntimeError, httpx.HTTPStatusError) as exc:
        if not _should_fallback_to_time_slicing(exc, start_ts=start_ts, end_ts=end_ts):
            raise
        logger.warning(
            "Falling back to time-sliced pagination for %s after offset cap: %s",
            description,
            exc,
        )
    assert start_ts is not None and end_ts is not None
    return collect_time_sliced_pages(
        fetch_page=fetch_window_page,
        start_ts=start_ts,
        end_ts=end_ts,
    )


def _should_fallback_to_time_slicing(
    exc: Exception,
    *,
    start_ts: int | None,
    end_ts: int | None,
) -> bool:
    if start_ts is None or end_ts is None:
        return False
    if isinstance(exc, RuntimeError):
        return "Offset pagination exceeded public API limit" in str(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        return _is_offset_limit_error(exc)
    return False


def _should_fallback_to_activity(
    exc: Exception,
    *,
    start_ts: int | None,
    end_ts: int | None,
) -> bool:
    return _should_fallback_to_time_slicing(exc, start_ts=start_ts, end_ts=end_ts)


def _activity_trade_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload.pop("type", None)
    payload.pop("usdcSize", None)
    return payload


def _is_offset_limit_error(exc: httpx.HTTPStatusError) -> bool:
    if exc.response is None or exc.response.status_code != 400:
        return False
    try:
        payload = exc.response.json()
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        message = str(payload.get("error") or "")
    else:
        message = exc.response.text
    lowered = message.lower()
    return "offset" in lowered and "exceeded" in lowered


def _retry_delay_seconds(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass
    return min(30.0, float(2 ** attempt))


def normalize_event_context(event_payload: dict[str, Any]) -> list[dict[str, Any]]:
    event_id = str(event_payload.get("id") or "")
    event_slug = event_payload.get("slug")
    title = event_payload.get("title")
    category = event_payload.get("category")
    resolution_source_url = event_payload.get("resolutionSource")
    sibling_market_ids: list[str] = []
    markets = event_payload.get("markets") or []
    for market in markets:
        market_id = market.get("conditionId")
        if market_id:
            sibling_market_ids.append(str(market_id))

    rows: list[dict[str, Any]] = []
    for market in markets:
        market_id = str(market.get("conditionId") or "").strip()
        if not market_id:
            continue
        outcomes = parse_jsonish_list(market.get("outcomes"))
        outcome_prices = parse_jsonish_list(market.get("outcomePrices"))
        clob_token_ids = parse_jsonish_list(market.get("clobTokenIds"))
        yes_token_id, no_token_id = extract_binary_token_ids(outcomes, clob_token_ids)
        yes_price, no_price = extract_binary_prices(outcomes, outcome_prices)
        rows.append(
            {
                "market_id": market_id,
                "event_id": event_id,
                "event_slug": event_slug,
                "gamma_market_id": str(market.get("id") or ""),
                "market_slug": market.get("slug"),
                "question": market.get("question"),
                "title": title,
                "category": category,
                "end_date": parse_iso_datetime(market.get("endDateIso") or market.get("endDate")),
                "active": market.get("active"),
                "closed": market.get("closed"),
                "neg_risk": bool(market.get("negRisk") or event_payload.get("negRisk")),
                "resolution_source_url": market.get("resolutionSource") or resolution_source_url,
                "yes_token_id": yes_token_id,
                "no_token_id": no_token_id,
                "yes_price": yes_price,
                "no_price": no_price,
                "outcomes": outcomes,
                "outcome_prices": outcome_prices,
                "sibling_market_ids": sibling_market_ids,
                "payload_json": {"event": event_payload, "market": market},
            }
        )
    return rows


def parse_jsonish_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    if text[0] != "[":
        return [text]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [text]
    return parsed if isinstance(parsed, list) else []


def extract_binary_token_ids(outcomes: list[Any], token_ids: list[Any]) -> tuple[str | None, str | None]:
    yes_token_id = None
    no_token_id = None
    for idx, outcome in enumerate(outcomes):
        name = str(outcome).strip().lower()
        token_id = str(token_ids[idx]) if idx < len(token_ids) else None
        if name == "yes":
            yes_token_id = token_id
        elif name == "no":
            no_token_id = token_id
    if yes_token_id or no_token_id:
        return yes_token_id, no_token_id
    if len(token_ids) >= 2:
        return str(token_ids[0]), str(token_ids[1])
    return None, None


def extract_binary_prices(outcomes: list[Any], prices: list[Any]) -> tuple[float | None, float | None]:
    yes_price = None
    no_price = None
    for idx, outcome in enumerate(outcomes):
        price = prices[idx] if idx < len(prices) else None
        try:
            parsed = float(price)
        except (TypeError, ValueError):
            parsed = None
        name = str(outcome).strip().lower()
        if name == "yes":
            yes_price = parsed
        elif name == "no":
            no_price = parsed
    if yes_price is not None or no_price is not None:
        return yes_price, no_price
    if len(prices) >= 2:
        try:
            return float(prices[0]), float(prices[1])
        except (TypeError, ValueError):
            return None, None
    return None, None
