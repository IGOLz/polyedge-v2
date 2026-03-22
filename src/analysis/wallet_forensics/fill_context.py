"""Fill-context analysis for wallet-forensics trade events."""

from __future__ import annotations

import argparse
import bisect
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from analysis.db_sync import get_connection
from analysis.wallet_forensics.db import load_rows
from analysis.wallet_forensics.fetchers import WalletForensicsClient
from analysis.wallet_forensics.main import _resolve_output_dir, _resolve_target
from analysis.wallet_forensics.report import (
    build_fill_context_markdown,
    build_fill_context_summary,
    export_fill_context_artifacts,
)
from analysis.wallet_forensics.utils import ensure_dir, row_hash, safe_float, safe_int

logger = logging.getLogger(__name__)

DEFAULT_LOOKAROUND_MINUTES = 30
DEFAULT_FIDELITY_MINUTES = 1
LOCAL_QUOTE_WINDOW_SECONDS = 300
QUOTE_TOLERANCE = 0.005
HISTORY_ALIGNMENT_BPS = 50.0
MAX_PRICE_HISTORY_CHUNK_SECONDS = 3 * 24 * 60 * 60


@dataclass(slots=True)
class PriceSeries:
    asset_id: str
    points: list[dict[str, Any]]
    timestamps: list[int]

    def nearest(self, target_ts: int) -> dict[str, Any] | None:
        if not self.points:
            return None
        position = bisect.bisect_left(self.timestamps, target_ts)
        candidates: list[dict[str, Any]] = []
        if position < len(self.points):
            candidates.append(self.points[position])
        if position > 0:
            candidates.append(self.points[position - 1])
        if not candidates:
            return None
        nearest = min(candidates, key=lambda item: abs(int(item["timestamp"]) - target_ts))
        return {
            **nearest,
            "distance_seconds": abs(int(nearest["timestamp"]) - target_ts),
            "time": datetime.fromtimestamp(int(nearest["timestamp"]), tz=UTC),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze fill context around public Polymarket wallet fills")
    identity_group = parser.add_mutually_exclusive_group(required=True)
    identity_group.add_argument("--profile", type=str, help="Polymarket profile name, for example ColdMath")
    identity_group.add_argument("--wallet", type=str, help="Proxy wallet address to analyze")
    scope_group = parser.add_mutually_exclusive_group()
    scope_group.add_argument("--weather-only", action="store_true", help="Restrict to weather fills")
    scope_group.add_argument("--all-markets", action="store_true", help="Analyze all fill markets")
    parser.add_argument("--output-dir", type=str, default=None, help="Artifact output directory")
    parser.add_argument(
        "--lookaround-minutes",
        type=int,
        default=DEFAULT_LOOKAROUND_MINUTES,
        help="Historical context window to request around each fill",
    )
    parser.add_argument(
        "--fidelity-minutes",
        type=int,
        default=DEFAULT_FIDELITY_MINUTES,
        help="Polymarket prices-history fidelity in minutes",
    )
    parser.add_argument("--max-fills", type=int, default=None, help="Optional max fills to analyze")
    parser.add_argument("--refresh-history-cache", action="store_true", help="Ignore cached prices-history payloads")
    parser.add_argument("--skip-parquet", action="store_true", help="Skip parquet export")
    parser.add_argument("--verbose", action="store_true", help="Enable info logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = run_fill_context_analysis(args)
    logger.info(
        "Fill-context analysis complete for %s with %d fills",
        result["target"]["proxy_wallet"],
        result["fill_count"],
    )
    return 0


def run_fill_context_analysis(args: argparse.Namespace | list[str] | None = None) -> dict[str, Any]:
    if not isinstance(args, argparse.Namespace):
        args = build_parser().parse_args(args)

    client = WalletForensicsClient()
    conn = get_connection()
    try:
        target = _resolve_target(client, args)
        output_dir = _resolve_output_dir(args, target)
        fill_rows = _load_trade_fill_rows(
            conn,
            proxy_wallet=target["proxy_wallet"],
            weather_only=bool(args.weather_only and not args.all_markets),
            max_fills=args.max_fills,
        )
        if not fill_rows:
            raise RuntimeError(f"No trade fills available for wallet {target['proxy_wallet']}")

        quote_bounds = _load_market_quote_bounds(conn)
        price_cache_dir = ensure_dir(output_dir / "fill_context_price_cache")
        histories = _load_price_histories(
            client=client,
            fill_rows=fill_rows,
            cache_dir=price_cache_dir,
            lookaround_minutes=max(1, int(args.lookaround_minutes)),
            fidelity_minutes=max(1, int(args.fidelity_minutes)),
            refresh_cache=bool(args.refresh_history_cache),
        )

        fill_context_rows: list[dict[str, Any]] = []
        for index, fill in enumerate(fill_rows, start=1):
            occurred_at = fill["occurred_at"]
            target_ts = int(occurred_at.timestamp())
            local_quote = _load_local_quote_near(
                conn,
                market_id=str(fill.get("condition_id") or ""),
                asset_id=str(fill.get("asset") or ""),
                target=occurred_at,
                quote_bounds=quote_bounds,
            )
            opposite_local_quote = _load_local_quote_near(
                conn,
                market_id=str(fill.get("condition_id") or ""),
                asset_id=str(fill.get("opposite_asset") or ""),
                target=occurred_at,
                quote_bounds=quote_bounds,
            )
            history_point = histories.get(str(fill.get("asset") or ""))
            opposite_history_point = histories.get(str(fill.get("opposite_asset") or ""))
            fill_context_rows.append(
                build_fill_context_row(
                    fill=fill,
                    local_quote=local_quote,
                    opposite_local_quote=opposite_local_quote,
                    history_point=history_point.nearest(target_ts) if history_point else None,
                    opposite_history_point=opposite_history_point.nearest(target_ts) if opposite_history_point else None,
                )
            )
            if args.verbose and index % 1000 == 0:
                logger.info("Analyzed fill context for %d/%d fills", index, len(fill_rows))

        summary = build_fill_context_summary(
            target=target,
            fill_context_rows=fill_context_rows,
        )
        export_fill_context_artifacts(
            output_dir=output_dir,
            fill_context_rows=fill_context_rows,
            fill_context_summary=summary,
            export_parquet=not bool(args.skip_parquet),
        )
        report_path = output_dir / "wallet_fill_context_report.md"
        report_path.write_text(
            build_fill_context_markdown(
                target=target,
                fill_context_summary=summary,
                fill_context_rows=fill_context_rows,
            ),
            encoding="utf-8",
        )
        return {
            "target": target,
            "fill_count": len(fill_context_rows),
            "output_dir": str(output_dir),
            "report_path": str(report_path),
            "summary_path": str(output_dir / "wallet_fill_context_summary.json"),
            "data_path": str(output_dir / "wallet_fill_context.csv"),
        }
    finally:
        client.close()
        conn.close()


def build_fill_context_row(
    *,
    fill: dict[str, Any],
    local_quote: dict[str, Any] | None,
    opposite_local_quote: dict[str, Any] | None,
    history_point: dict[str, Any] | None,
    opposite_history_point: dict[str, Any] | None,
) -> dict[str, Any]:
    side = str(fill.get("side") or "").lower()
    executed_price = safe_float(fill.get("price"))
    local_analysis = _analyze_local_execution(side=side, executed_price=executed_price, quote=local_quote)
    history_analysis = _analyze_history_execution(side=side, executed_price=executed_price, point=history_point)

    opposite_local_best_ask = safe_float((opposite_local_quote or {}).get("best_ask"))
    local_best_ask = safe_float((local_quote or {}).get("best_ask"))
    history_price = safe_float((history_point or {}).get("price"))
    opposite_history_price = safe_float((opposite_history_point or {}).get("price"))

    executed_plus_opposite_local_best_ask = _pair_cost(
        side=side,
        executed_price=executed_price,
        opposite_reference=opposite_local_best_ask,
    )
    executed_plus_opposite_history_price = _pair_cost(
        side=side,
        executed_price=executed_price,
        opposite_reference=opposite_history_price,
    )
    local_pair_reference_cost = _combine_values(local_best_ask, opposite_local_best_ask)
    history_pair_reference_cost = _combine_values(history_price, opposite_history_price)

    local_quote_coverage = _coverage_label(local_quote, opposite_local_quote)
    price_history_coverage = _coverage_label(history_point, opposite_history_point)
    context_source = _context_source(local_quote_coverage, price_history_coverage)

    payload = {
        "local_quote": local_quote,
        "opposite_local_quote": opposite_local_quote,
        "history_point": _jsonable_point(history_point),
        "opposite_history_point": _jsonable_point(opposite_history_point),
    }
    fill_context_id = row_hash(
        {
            "ledger_event_id": fill.get("ledger_event_id"),
            "asset": fill.get("asset"),
            "opposite_asset": fill.get("opposite_asset"),
            "context_source": context_source,
        }
    )
    return {
        "fill_context_id": fill_context_id,
        "ledger_event_id": fill.get("ledger_event_id"),
        "proxy_wallet": fill.get("proxy_wallet"),
        "occurred_at": fill.get("occurred_at"),
        "transaction_hash": fill.get("transaction_hash"),
        "condition_id": fill.get("condition_id"),
        "event_slug": fill.get("event_slug"),
        "question": fill.get("question"),
        "asset": fill.get("asset"),
        "opposite_asset": fill.get("opposite_asset"),
        "yes_token_id": fill.get("yes_token_id"),
        "no_token_id": fill.get("no_token_id"),
        "executed_token_role": fill.get("executed_token_role"),
        "outcome": fill.get("outcome"),
        "side": side,
        "executed_price": executed_price,
        "executed_size": safe_float(fill.get("size")),
        "token_mapping_found": bool(fill.get("token_mapping_found")),
        "is_weather": bool(fill.get("is_weather")),
        "local_quote_coverage": local_quote_coverage,
        "price_history_coverage": price_history_coverage,
        "context_source": context_source,
        "local_quote_time": (local_quote or {}).get("time"),
        "local_quote_distance_seconds": safe_float((local_quote or {}).get("distance_seconds")),
        "local_best_bid": safe_float((local_quote or {}).get("best_bid")),
        "local_best_ask": local_best_ask,
        "local_mid": safe_float((local_quote or {}).get("mid")),
        "local_best_bid_size": safe_float((local_quote or {}).get("best_bid_size")),
        "local_best_ask_size": safe_float((local_quote or {}).get("best_ask_size")),
        "opposite_local_quote_time": (opposite_local_quote or {}).get("time"),
        "opposite_local_quote_distance_seconds": safe_float((opposite_local_quote or {}).get("distance_seconds")),
        "opposite_local_best_bid": safe_float((opposite_local_quote or {}).get("best_bid")),
        "opposite_local_best_ask": opposite_local_best_ask,
        "opposite_local_mid": safe_float((opposite_local_quote or {}).get("mid")),
        "price_history_time": (history_point or {}).get("time"),
        "price_history_distance_seconds": safe_float((history_point or {}).get("distance_seconds")),
        "price_history_price": history_price,
        "opposite_price_history_time": (opposite_history_point or {}).get("time"),
        "opposite_price_history_distance_seconds": safe_float((opposite_history_point or {}).get("distance_seconds")),
        "opposite_price_history_price": opposite_history_price,
        "local_reference_price": local_analysis["reference_price"],
        "local_reference_kind": local_analysis["reference_kind"],
        "local_execution_edge_bps": local_analysis["edge_bps"],
        "local_execution_label": local_analysis["label"],
        "price_history_reference_price": history_analysis["reference_price"],
        "price_history_execution_edge_bps": history_analysis["edge_bps"],
        "price_history_execution_label": history_analysis["label"],
        "executed_plus_opposite_local_best_ask": executed_plus_opposite_local_best_ask,
        "executed_plus_opposite_price_history": executed_plus_opposite_history_price,
        "local_pair_reference_cost": local_pair_reference_cost,
        "price_history_pair_reference_cost": history_pair_reference_cost,
        "local_pair_under_par": _under_par(executed_plus_opposite_local_best_ask),
        "price_history_pair_under_par": _under_par(executed_plus_opposite_history_price),
        "payload_json": payload,
    }


def _load_trade_fill_rows(
    conn,
    *,
    proxy_wallet: str,
    weather_only: bool,
    max_fills: int | None,
) -> list[dict[str, Any]]:
    where_sql = """
        WHERE l.proxy_wallet = %s
          AND l.event_type = 'trade'
    """
    params: list[Any] = [proxy_wallet]
    if weather_only:
        where_sql += " AND COALESCE(l.event_slug, '') LIKE 'highest-temperature-in-%%'"
    rows = load_rows(
        conn,
        f"""
        SELECT
            l.ledger_event_id,
            l.proxy_wallet,
            l.occurred_at,
            l.transaction_hash,
            l.condition_id,
            l.event_slug,
            l.asset,
            l.outcome,
            l.side,
            l.size,
            l.price,
            l.payload_json,
            mc.question,
            mc.yes_token_id,
            mc.no_token_id
        FROM wallet_ledger_events l
        LEFT JOIN wallet_market_context mc
          ON mc.market_id = l.condition_id
        {where_sql}
        ORDER BY l.occurred_at ASC, l.transaction_hash ASC, l.ledger_event_id ASC
        """,
        tuple(params),
    )
    result: list[dict[str, Any]] = []
    for row in rows[: max_fills or len(rows)]:
        enriched = dict(row)
        asset = str(row.get("asset") or "")
        yes_token_id = str(row.get("yes_token_id") or "")
        no_token_id = str(row.get("no_token_id") or "")
        outcome = str(row.get("outcome") or "").strip().lower()
        opposite_asset = None
        executed_token_role = None
        if asset and yes_token_id and asset == yes_token_id:
            opposite_asset = no_token_id or None
            executed_token_role = "yes"
        elif asset and no_token_id and asset == no_token_id:
            opposite_asset = yes_token_id or None
            executed_token_role = "no"
        elif outcome == "yes" and no_token_id:
            opposite_asset = no_token_id
            executed_token_role = "yes"
        elif outcome == "no" and yes_token_id:
            opposite_asset = yes_token_id
            executed_token_role = "no"
        enriched["opposite_asset"] = opposite_asset
        enriched["executed_token_role"] = executed_token_role
        enriched["token_mapping_found"] = bool(asset and opposite_asset)
        enriched["is_weather"] = str(row.get("event_slug") or "").startswith("highest-temperature-in-")
        result.append(enriched)
    return result


def _load_market_quote_bounds(conn) -> tuple[datetime | None, datetime | None]:
    rows = load_rows(
        conn,
        """
        SELECT MIN(time) AS min_time, MAX(time) AS max_time
        FROM market_quotes
        """,
        (),
    )
    row = rows[0] if rows else {}
    return row.get("min_time"), row.get("max_time")


def _load_local_quote_near(
    conn,
    *,
    market_id: str,
    asset_id: str,
    target: datetime,
    quote_bounds: tuple[datetime | None, datetime | None],
    window_seconds: int = LOCAL_QUOTE_WINDOW_SECONDS,
) -> dict[str, Any] | None:
    if not market_id or not asset_id:
        return None
    min_time, max_time = quote_bounds
    if min_time is None or max_time is None:
        return None
    if target < min_time - timedelta(seconds=window_seconds) or target > max_time + timedelta(seconds=window_seconds):
        return None
    rows = load_rows(
        conn,
        """
        SELECT
            time,
            market_id,
            outcome,
            asset_id,
            best_bid,
            best_ask,
            mid,
            best_bid_size,
            best_ask_size,
            ABS(EXTRACT(EPOCH FROM (time - %s))) AS distance_seconds
        FROM market_quotes
        WHERE market_id = %s
          AND asset_id = %s
          AND time BETWEEN %s AND %s
        ORDER BY distance_seconds ASC
        LIMIT 1
        """,
        (
            target,
            market_id,
            asset_id,
            target - timedelta(seconds=window_seconds),
            target + timedelta(seconds=window_seconds),
        ),
    )
    return rows[0] if rows else None


def _load_price_histories(
    *,
    client: WalletForensicsClient,
    fill_rows: list[dict[str, Any]],
    cache_dir: Path,
    lookaround_minutes: int,
    fidelity_minutes: int,
    refresh_cache: bool,
) -> dict[str, PriceSeries]:
    asset_windows = _build_asset_windows(fill_rows, lookaround_minutes=lookaround_minutes)
    histories: dict[str, PriceSeries] = {}
    logger.info("Loading prices-history context for %d unique assets", len(asset_windows))
    for index, (asset_id, window) in enumerate(asset_windows.items(), start=1):
        cache_path = _history_cache_path(
            cache_dir=cache_dir,
            asset_id=asset_id,
            start_ts=window["start_ts"],
            end_ts=window["end_ts"],
            fidelity_minutes=fidelity_minutes,
        )
        points: list[dict[str, Any]]
        if cache_path.exists() and not refresh_cache:
            points = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            raw_points = _fetch_price_history_range(
                client=client,
                asset_id=asset_id,
                start_ts=window["start_ts"],
                end_ts=window["end_ts"],
                fidelity_minutes=fidelity_minutes,
            )
            points = _normalize_price_history_points(raw_points)
            cache_path.write_text(json.dumps(points, indent=2), encoding="utf-8")
        histories[asset_id] = PriceSeries(
            asset_id=asset_id,
            points=points,
            timestamps=[int(point["timestamp"]) for point in points],
        )
        if index % 200 == 0:
            logger.info("Loaded prices-history for %d/%d assets", index, len(asset_windows))
    return histories


def _build_asset_windows(
    fill_rows: list[dict[str, Any]],
    *,
    lookaround_minutes: int,
) -> dict[str, dict[str, int]]:
    lookaround_seconds = lookaround_minutes * 60
    windows: dict[str, dict[str, int]] = {}
    for fill in fill_rows:
        occurred_at = fill.get("occurred_at")
        if not isinstance(occurred_at, datetime):
            continue
        center_ts = int(occurred_at.timestamp())
        for asset_id in {str(fill.get("asset") or ""), str(fill.get("opposite_asset") or "")}:
            if not asset_id:
                continue
            window = windows.setdefault(
                asset_id,
                {
                    "start_ts": center_ts - lookaround_seconds,
                    "end_ts": center_ts + lookaround_seconds,
                },
            )
            window["start_ts"] = min(window["start_ts"], center_ts - lookaround_seconds)
            window["end_ts"] = max(window["end_ts"], center_ts + lookaround_seconds)
    return windows


def _fetch_price_history_range(
    *,
    client: WalletForensicsClient,
    asset_id: str,
    start_ts: int,
    end_ts: int,
    fidelity_minutes: int,
    max_chunk_seconds: int = MAX_PRICE_HISTORY_CHUNK_SECONDS,
) -> list[dict[str, Any]]:
    if start_ts >= end_ts:
        return client.fetch_prices_history(
            asset_id,
            start_ts=start_ts,
            end_ts=end_ts,
            fidelity=fidelity_minutes,
        )
    points: list[dict[str, Any]] = []
    chunk_start = start_ts
    while chunk_start <= end_ts:
        chunk_end = min(end_ts, chunk_start + max_chunk_seconds)
        try:
            points.extend(
                client.fetch_prices_history(
                    asset_id,
                    start_ts=chunk_start,
                    end_ts=chunk_end,
                    fidelity=fidelity_minutes,
                )
            )
        except httpx.HTTPStatusError as exc:
            if exc.response is None or exc.response.status_code != 400 or max_chunk_seconds <= 12 * 60 * 60:
                raise
            logger.warning(
                "Reducing prices-history chunk size for %s after HTTP 400 on %s-%s",
                asset_id,
                chunk_start,
                chunk_end,
            )
            points.extend(
                _fetch_price_history_range(
                    client=client,
                    asset_id=asset_id,
                    start_ts=chunk_start,
                    end_ts=chunk_end,
                    fidelity_minutes=fidelity_minutes,
                    max_chunk_seconds=max_chunk_seconds // 2,
                )
            )
        chunk_start = chunk_end + 1
    return points


def _history_cache_path(
    *,
    cache_dir: Path,
    asset_id: str,
    start_ts: int,
    end_ts: int,
    fidelity_minutes: int,
) -> Path:
    digest = row_hash(
        {
            "asset_id": asset_id,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "fidelity_minutes": fidelity_minutes,
        }
    )
    return cache_dir / f"{digest}.json"


def _normalize_price_history_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[int, dict[str, Any]] = {}
    for item in points:
        timestamp = safe_int(item.get("t") or item.get("timestamp") or item.get("time"))
        price = safe_float(item.get("p") or item.get("price") or item.get("mid"))
        if timestamp is None or price is None:
            continue
        deduped[timestamp] = {
            "timestamp": timestamp,
            "price": price,
        }
    return [deduped[key] for key in sorted(deduped)]


def _analyze_local_execution(
    *,
    side: str,
    executed_price: float | None,
    quote: dict[str, Any] | None,
) -> dict[str, Any]:
    if not quote or executed_price is None:
        return {"reference_price": None, "reference_kind": None, "edge_bps": None, "label": "unknown"}
    bid = safe_float(quote.get("best_bid"))
    ask = safe_float(quote.get("best_ask"))
    mid = safe_float(quote.get("mid"))
    if side == "buy":
        if ask is not None and executed_price >= ask - QUOTE_TOLERANCE:
            return _reference_result(
                executed_price=executed_price,
                reference_price=ask,
                reference_kind="local_best_ask",
                side=side,
                label="aggressive_taker_like",
            )
        if bid is not None and executed_price <= bid + QUOTE_TOLERANCE:
            return _reference_result(
                executed_price=executed_price,
                reference_price=bid,
                reference_kind="local_best_bid",
                side=side,
                label="passive_maker_like",
            )
        if bid is not None and ask is not None and bid < executed_price < ask:
            return _reference_result(
                executed_price=executed_price,
                reference_price=mid if mid is not None else (bid + ask) / 2.0,
                reference_kind="local_mid",
                side=side,
                label="inside_spread",
            )
    if side == "sell":
        if bid is not None and executed_price <= bid + QUOTE_TOLERANCE:
            return _reference_result(
                executed_price=executed_price,
                reference_price=bid,
                reference_kind="local_best_bid",
                side=side,
                label="aggressive_taker_like",
            )
        if ask is not None and executed_price >= ask - QUOTE_TOLERANCE:
            return _reference_result(
                executed_price=executed_price,
                reference_price=ask,
                reference_kind="local_best_ask",
                side=side,
                label="passive_maker_like",
            )
        if bid is not None and ask is not None and bid < executed_price < ask:
            return _reference_result(
                executed_price=executed_price,
                reference_price=mid if mid is not None else (bid + ask) / 2.0,
                reference_kind="local_mid",
                side=side,
                label="inside_spread",
            )
    fallback = ask if side == "buy" else bid
    if fallback is None:
        fallback = mid
    if fallback is None:
        return {"reference_price": None, "reference_kind": None, "edge_bps": None, "label": "unknown"}
    return _reference_result(
        executed_price=executed_price,
        reference_price=fallback,
        reference_kind="local_fallback",
        side=side,
        label="unknown",
    )


def _analyze_history_execution(
    *,
    side: str,
    executed_price: float | None,
    point: dict[str, Any] | None,
) -> dict[str, Any]:
    reference_price = safe_float((point or {}).get("price"))
    if executed_price is None or reference_price is None:
        return {"reference_price": None, "edge_bps": None, "label": "unknown"}
    edge_bps = _execution_edge_bps(side=side, executed_price=executed_price, reference_price=reference_price)
    if edge_bps is None:
        return {"reference_price": reference_price, "edge_bps": None, "label": "unknown"}
    if edge_bps > HISTORY_ALIGNMENT_BPS:
        label = "better_than_nearby_trade"
    elif edge_bps < -HISTORY_ALIGNMENT_BPS:
        label = "worse_than_nearby_trade"
    else:
        label = "nearby_trade_aligned"
    return {
        "reference_price": reference_price,
        "edge_bps": edge_bps,
        "label": label,
    }


def _reference_result(
    *,
    executed_price: float,
    reference_price: float,
    reference_kind: str,
    side: str,
    label: str,
) -> dict[str, Any]:
    return {
        "reference_price": reference_price,
        "reference_kind": reference_kind,
        "edge_bps": _execution_edge_bps(side=side, executed_price=executed_price, reference_price=reference_price),
        "label": label,
    }


def _execution_edge_bps(
    *,
    side: str,
    executed_price: float,
    reference_price: float,
) -> float | None:
    if side == "buy":
        return round((reference_price - executed_price) * 10_000.0, 4)
    if side == "sell":
        return round((executed_price - reference_price) * 10_000.0, 4)
    return None


def _coverage_label(primary: dict[str, Any] | None, opposite: dict[str, Any] | None) -> str:
    if primary and opposite:
        return "full_pair"
    if primary:
        return "executed_only"
    if opposite:
        return "opposite_only"
    return "none"


def _context_source(local_quote_coverage: str, price_history_coverage: str) -> str:
    has_local = local_quote_coverage != "none"
    has_history = price_history_coverage != "none"
    if has_local and has_history:
        return "mixed"
    if has_local:
        return "local_quotes"
    if has_history:
        return "prices_history"
    return "none"


def _pair_cost(
    *,
    side: str,
    executed_price: float | None,
    opposite_reference: float | None,
) -> float | None:
    if side != "buy":
        return None
    return _combine_values(executed_price, opposite_reference)


def _combine_values(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return round(left + right, 6)


def _under_par(value: float | None) -> bool | None:
    if value is None:
        return None
    return value < 1.0


def _jsonable_point(point: dict[str, Any] | None) -> dict[str, Any] | None:
    if point is None:
        return None
    return {
        key: (value.isoformat() if isinstance(value, datetime) else value)
        for key, value in point.items()
    }


if __name__ == "__main__":
    raise SystemExit(main())
