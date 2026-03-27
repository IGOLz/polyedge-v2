"""Replay ColdMath weather trades against historical market quote snapshots."""

from __future__ import annotations

import argparse
from bisect import bisect_left
import json
import logging
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from analysis.coldmath_window_compare import DEFAULT_LOG_PATH, _derive_weather_trade_metadata, run_window_comparison
from analysis.db_sync import get_connection
from analysis.wallet_forensics.db import load_rows
from analysis.wallet_forensics.utils import ensure_dir, parse_iso_datetime, safe_float, safe_int
from trading_weather.clone_config import normalize_clone_bot_config
from trading_weather.clone_engine import build_clone_runtime, evaluate_clone_cycle
from trading_weather.strategy import build_runtime_config, scan_live_market_report
from weather.models import WeatherBucketMarket, WeatherMarketContext

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay ColdMath weather trades against historical quote snapshots")
    parser.add_argument("--profile", type=str, default="ColdMath")
    parser.add_argument("--wallet", type=str)
    parser.add_argument("--log-path", type=str, default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--fallback-log-path", type=str, default=None)
    parser.add_argument("--lxc-date-is", type=str, default=None)
    parser.add_argument("--log-timezone", type=str, default=None)
    parser.add_argument("--window-hours", type=float, default=8.0)
    parser.add_argument("--heartbeat-gap-seconds", type=float, default=180.0)
    parser.add_argument("--quote-window-seconds", type=int, default=180)
    parser.add_argument(
        "--merge-config-path",
        type=str,
        default="src/results/wallet_forensics/coldmath_resume_smoke_v3/wallet_inventory_rebalancing_merge_backtest_bot_config.json",
    )
    parser.add_argument(
        "--clone-config-path",
        type=str,
        default="src/results/wallet_forensics/coldmath_resume_smoke_v3/wallet_coldmath_clone_bot_config.json",
    )
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = run_quote_parity(args)
    logger.info(
        "Quote parity complete: merge %.4f clone %.4f",
        result["summary"]["merge_match_ratio"],
        result["summary"]["clone_match_ratio"],
    )
    return 0


def run_quote_parity(args: argparse.Namespace | list[str] | None = None) -> dict[str, Any]:
    if not isinstance(args, argparse.Namespace):
        args = build_parser().parse_args(args)

    comparison_result = run_window_comparison(
        argparse.Namespace(
            profile=args.profile,
            wallet=args.wallet,
            log_path=args.log_path,
            fallback_log_path=args.fallback_log_path,
            lxc_date_is=args.lxc_date_is,
            log_timezone=args.log_timezone,
            window_hours=args.window_hours,
            heartbeat_gap_seconds=args.heartbeat_gap_seconds,
            output_dir=str(
                ensure_dir(
                    Path(args.output_dir).resolve()
                    if args.output_dir
                    else Path(__file__).resolve().parents[2] / "src" / "results" / "wallet_forensics" / "coldmath_quote_parity"
                )
            ),
            verbose=args.verbose,
        )
    )
    trade_rows = _normalize_weather_trades(comparison_result["coldmath"]["trade_rows"])
    merge_config = json.loads(Path(args.merge_config_path).read_text(encoding="utf-8"))
    clone_config = normalize_clone_bot_config(json.loads(Path(args.clone_config_path).read_text(encoding="utf-8")))
    parity = _evaluate_historical_quote_parity(
        trade_rows=trade_rows,
        merge_config=merge_config,
        clone_config=clone_config,
        quote_window_seconds=int(args.quote_window_seconds),
    )
    output_dir = Path(comparison_result["report_path"]).resolve().parent
    report_path = output_dir / "coldmath_quote_parity_report.md"
    summary_path = output_dir / "coldmath_quote_parity_summary.json"
    report_path.write_text(
        _build_markdown_report(comparison_result=comparison_result, parity=parity),
        encoding="utf-8",
    )
    summary_path.write_text(json.dumps(parity, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return {
        "comparison_result": comparison_result,
        "summary": parity["summary"],
        "report_path": str(report_path),
        "summary_path": str(summary_path),
    }


def _normalize_weather_trades(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        merged = dict(row)
        timestamp_utc = _trade_timestamp_utc(merged)
        if timestamp_utc is None:
            continue
        merged["timestamp_utc"] = timestamp_utc
        derived = _derive_weather_trade_metadata(row)
        merged["condition_id"] = str(
            merged.get("condition_id")
            or merged.get("conditionId")
            or merged.get("market_id")
            or merged.get("market")
            or ""
        ).strip()
        if not merged.get("event_slug"):
            merged["event_slug"] = merged.get("eventSlug") or merged.get("event_slug")
        if not merged.get("market_slug"):
            merged["market_slug"] = merged.get("slug") or merged.get("market_slug")
        if not merged.get("city"):
            merged["city"] = derived.get("city")
        if not merged.get("local_date"):
            merged["local_date"] = derived.get("local_date")
        if not merged.get("bucket_label"):
            merged["bucket_label"] = _normalize_bucket_label(derived.get("bucket_label"))
        else:
            merged["bucket_label"] = _normalize_bucket_label(merged.get("bucket_label"))
        if not merged.get("event_slug") and merged.get("city") and merged.get("local_date"):
            merged["event_slug"] = _event_slug(str(merged["city"]), str(merged["local_date"]))
        side = str(merged.get("side") or "").strip().lower()
        merged["side"] = side
        outcome = str(merged.get("outcome") or "").strip().lower()
        if outcome in {"up", "yes"}:
            outcome = "yes"
        elif outcome in {"down", "no"}:
            outcome = "no"
        merged["outcome"] = outcome
        merged["trade_type"] = "sell" if side == "sell" else "buy"
        merged["price"] = safe_float(merged.get("price"))
        merged["size"] = safe_float(merged.get("size") or merged.get("usdcSize"))
        normalized.append(merged)
    normalized.sort(key=lambda item: item["timestamp_utc"])
    return normalized


def _trade_timestamp_utc(row: dict[str, Any]) -> datetime | None:
    existing = row.get("timestamp_utc")
    if isinstance(existing, datetime):
        return existing if existing.tzinfo is not None else existing.replace(tzinfo=UTC)
    if existing:
        try:
            parsed = parse_iso_datetime(existing)
        except Exception:
            parsed = None
        if parsed is not None:
            return parsed
    timestamp = safe_int(row.get("timestamp"))
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC)


def _event_slug(city: str, local_date: str) -> str:
    date_value = datetime.fromisoformat(local_date).date()
    month = date_value.strftime("%B").lower()
    city_slug = "-".join(city.strip().lower().split())
    return f"highest-temperature-in-{city_slug}-on-{month}-{date_value.day}-{date_value.year}"


def _normalize_bucket_label(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower().startswith("between "):
        return text[8:].strip()
    return text


def _evaluate_historical_quote_parity(
    *,
    trade_rows: list[dict[str, Any]],
    merge_config: dict[str, Any],
    clone_config: dict[str, Any],
    quote_window_seconds: int,
) -> dict[str, Any]:
    merge_runtime = build_runtime_config(
        merge_config,
        balance_usd=100.0,
        sequence_budget_cap_usd=5.0,
        max_total_exposure_cap_usd=10.0,
        daily_loss_limit_cap_usd=5.0,
        min_expected_edge_usd=0.0,
        max_concurrent_positions=10,
        partial_repair_window_seconds=30.0,
        min_target_shares=1,
        auto_merge=False,
    )
    clone_runtime = build_clone_runtime(clone_config, dry_run=False)
    clone_sequence_state: dict[str, dict[str, Any]] = {}
    context_cache: dict[tuple[str, datetime], Any] = {}
    merge_cache: dict[tuple[str, datetime], dict[str, Any]] = {}
    clone_cache: dict[tuple[str, datetime], dict[str, Any]] = {}
    event_slugs = sorted({str(row.get("event_slug") or "") for row in trade_rows if row.get("event_slug")})
    window_start = min(row["timestamp_utc"] for row in trade_rows) - timedelta(seconds=quote_window_seconds)
    window_end = max(row["timestamp_utc"] for row in trade_rows) + timedelta(seconds=quote_window_seconds)
    catalog_by_event, quote_series = _load_historical_weather_state(
        event_slugs=event_slugs,
        window_start=window_start,
        window_end=window_end,
    )

    unique_points = sorted(
        {
            (str(row.get("event_slug") or ""), row["timestamp_utc"])
            for row in trade_rows
            if row.get("event_slug")
        },
        key=lambda item: item[1],
    )

    for event_slug, captured_at in unique_points:
        context = _build_context_for_event(
            event_slug=event_slug,
            captured_at=captured_at,
            catalog_by_event=catalog_by_event,
            quote_series=quote_series,
            quote_window_seconds=quote_window_seconds,
        )
        if context is None:
            continue
        context_cache[(event_slug, captured_at)] = context
        merge_cache[(event_slug, captured_at)] = scan_live_market_report(
            [context],
            merge_runtime,
            captured_at=captured_at,
            near_miss_limit=max(10, len(context.markets)),
        )
        clone_cache[(event_slug, captured_at)] = evaluate_clone_cycle(
            contexts=[context],
            runtime=clone_runtime,
            captured_at=captured_at,
            health_state={
                "execution_allowed": True,
                "execution_auth": {"status": "healthy", "allowed": True},
                "market_data": {"status": "healthy", "reason": "historical_quote_replay"},
                "quote_coverage_ratio": 1.0,
            },
            sequence_state=clone_sequence_state,
            active_positions=[],
            active_market_ids=set(),
        )

    classified_rows: list[dict[str, Any]] = []
    merge_reasons = Counter()
    clone_reasons = Counter()
    clone_playbooks = Counter()
    merge_matches = 0
    clone_matches = 0

    for trade in trade_rows:
        key = (str(trade.get("event_slug") or ""), trade["timestamp_utc"])
        context = context_cache.get(key)
        trade_outcome = str(trade.get("outcome") or "").strip().lower()
        if context is None:
            classified_rows.append(
                {
                    **_trade_brief(trade),
                    "market_id": None,
                    "merge_match": False,
                    "merge_reason": "missing_historical_context",
                    "clone_match": False,
                    "clone_reason": "missing_historical_context",
                    "clone_playbook": None,
                }
            )
            merge_reasons["missing_historical_context"] += 1
            clone_reasons["missing_historical_context"] += 1
            continue

        market = next(
            (
                item
                for item in context.markets
                if str(item.bucket_label or "").strip() == str(trade.get("bucket_label") or "").strip()
            ),
            None,
        )
        if market is None:
            classified_rows.append(
                {
                    **_trade_brief(trade),
                    "market_id": None,
                    "merge_match": False,
                    "merge_reason": "market_not_found_in_context",
                    "clone_match": False,
                    "clone_reason": "market_not_found_in_context",
                    "clone_playbook": None,
                }
            )
            merge_reasons["market_not_found_in_context"] += 1
            clone_reasons["market_not_found_in_context"] += 1
            continue

        market_id = market.market_id
        merge_row = _row_by_market_id(merge_cache.get(key, {}).get("cycle_rows") or [], market_id)
        clone_rows = [row for row in (clone_cache.get(key, {}).get("cycle_rows") or []) if str(row.get("market_id") or "") == market_id]

        merge_match = bool(merge_row and merge_row.get("qualifies"))
        merge_reason = "matched" if merge_match else _first_reason(merge_row) or "not_qualified"
        if merge_match:
            merge_matches += 1
        else:
            merge_reasons[merge_reason] += 1

        clone_match_row = _match_clone_trade_row(clone_rows, trade_outcome=trade_outcome)
        clone_match = clone_match_row is not None
        clone_reason = "matched" if clone_match else _clone_reason(clone_rows, trade_outcome=trade_outcome)
        clone_playbook = str(clone_match_row.get("playbook_key") or "") if clone_match_row else None
        if clone_match:
            clone_matches += 1
            clone_playbooks[clone_playbook] += 1
        else:
            clone_reasons[clone_reason] += 1

        classified_rows.append(
            {
                **_trade_brief(trade),
                "market_id": market_id,
                "merge_match": merge_match,
                "merge_reason": merge_reason,
                "clone_match": clone_match,
                "clone_reason": clone_reason,
                "clone_playbook": clone_playbook,
                "merge_combined_cost": merge_row.get("combined_cost") if merge_row else None,
                "clone_rows": [
                    {
                        "playbook_key": row.get("playbook_key"),
                        "side": row.get("side"),
                        "qualifies": bool(row.get("qualifies")),
                        "rejection_reasons": row.get("rejection_reasons") or [],
                    }
                    for row in clone_rows
                ],
            }
        )

    trade_count = len(trade_rows)
    return {
        "classified_rows": classified_rows,
        "summary": {
            "trade_count": trade_count,
            "merge_match_count": merge_matches,
            "merge_match_ratio": round(merge_matches / trade_count, 6) if trade_count else 0.0,
            "clone_match_count": clone_matches,
            "clone_match_ratio": round(clone_matches / trade_count, 6) if trade_count else 0.0,
            "recommended_engine": "clone" if clone_matches > merge_matches else "merge",
            "top_merge_miss_reasons": _counter_rows(merge_reasons),
            "top_clone_miss_reasons": _counter_rows(clone_reasons),
            "matched_clone_playbooks": _counter_rows(clone_playbooks),
        },
    }


def _load_historical_weather_state(
    *,
    event_slugs: list[str],
    window_start: datetime,
    window_end: datetime,
) -> tuple[dict[str, list[dict[str, Any]]], dict[tuple[str, str], dict[str, Any]]]:
    conn = get_connection()
    try:
        catalog_rows = load_rows(
            conn,
            """
            SELECT
                market_id,
                event_id,
                event_slug,
                market_slug,
                question,
                city,
                city_key,
                station_code,
                station_name,
                lat,
                lon,
                timezone,
                local_date,
                unit,
                bucket_label,
                bucket_low,
                bucket_high,
                bucket_order,
                rule_family,
                resolution_source_url,
                resolution_precision_scale,
                neg_risk,
                active,
                eligible,
                eligibility_reason,
                yes_token_id,
                no_token_id,
                started_at,
                ended_at
            FROM weather_market_catalog
            WHERE event_slug = ANY(%s)
            ORDER BY event_id, bucket_order
            """,
            (event_slugs,),
        )
        quote_rows = load_rows(
            conn,
            """
            SELECT
                wmc.event_slug,
                mq.market_id,
                mq.outcome,
                mq.time,
                mq.best_bid,
                mq.best_ask,
                mq.mid,
                mq.best_bid_size,
                mq.best_ask_size
            FROM market_quotes mq
            JOIN weather_market_catalog wmc ON wmc.market_id = mq.market_id
            WHERE wmc.event_slug = ANY(%s)
              AND mq.time BETWEEN %s AND %s
            ORDER BY wmc.event_slug, mq.market_id, mq.outcome, mq.time ASC
            """,
            (event_slugs, window_start, window_end),
        )
    finally:
        conn.close()

    catalog_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in catalog_rows:
        catalog_by_event[str(row.get("event_slug") or "")].append(dict(row))

    quote_series: dict[tuple[str, str], dict[str, Any]] = {}
    for row in quote_rows:
        key = (str(row.get("market_id") or ""), str(row.get("outcome") or ""))
        bucket = quote_series.setdefault(key, {"times": [], "rows": []})
        bucket["times"].append(row["time"])
        bucket["rows"].append(dict(row))
    return dict(catalog_by_event), quote_series


def _build_context_for_event(
    *,
    event_slug: str,
    captured_at: datetime,
    catalog_by_event: dict[str, list[dict[str, Any]]],
    quote_series: dict[tuple[str, str], dict[str, Any]],
    quote_window_seconds: int,
) -> WeatherMarketContext | None:
    event_rows = catalog_by_event.get(event_slug) or []
    if not event_rows:
        return None
    first = event_rows[0]
    markets: list[WeatherBucketMarket] = []
    for row in event_rows:
        up = _nearest_quote_row(
            quote_series.get((str(row["market_id"]), "Up")),
            captured_at=captured_at,
            quote_window_seconds=quote_window_seconds,
        )
        down = _nearest_quote_row(
            quote_series.get((str(row["market_id"]), "Down")),
            captured_at=captured_at,
            quote_window_seconds=quote_window_seconds,
        )
        latest_quote_time = (up or {}).get("time") or (down or {}).get("time")
        markets.append(
            WeatherBucketMarket(
                market_id=str(row["market_id"]),
                event_id=str(row["event_id"]),
                event_slug=str(row["event_slug"]),
                market_slug=str(row.get("market_slug") or ""),
                question=str(row.get("question") or ""),
                city=str(row.get("city") or ""),
                city_key=str(row.get("city_key") or ""),
                station_code=row.get("station_code"),
                station_name=row.get("station_name"),
                lat=float(row["lat"]) if row.get("lat") is not None else None,
                lon=float(row["lon"]) if row.get("lon") is not None else None,
                timezone=row.get("timezone"),
                local_date=_date_value(row.get("local_date")),
                unit=row.get("unit"),
                bucket_label=str(row.get("bucket_label") or ""),
                bucket_low=float(row["bucket_low"]) if row.get("bucket_low") is not None else None,
                bucket_high=float(row["bucket_high"]) if row.get("bucket_high") is not None else None,
                bucket_order=int(row.get("bucket_order") or 0),
                rule_family=row.get("rule_family"),
                resolution_source_url=row.get("resolution_source_url"),
                resolution_precision_scale=int(row.get("resolution_precision_scale") or 0),
                neg_risk=bool(row.get("neg_risk")),
                active=bool(row.get("active")),
                eligible=bool(row.get("eligible")),
                eligibility_reason=row.get("eligibility_reason"),
                yes_token_id=row.get("yes_token_id"),
                no_token_id=row.get("no_token_id"),
                started_at=row.get("started_at"),
                ended_at=row.get("ended_at"),
                yes_bid=_float_value((up or {}).get("best_bid")),
                yes_ask=_float_value((up or {}).get("best_ask")),
                yes_mid=_float_value((up or {}).get("mid")),
                yes_bid_size=_float_value((up or {}).get("best_bid_size")),
                yes_ask_size=_float_value((up or {}).get("best_ask_size")),
                no_bid=_float_value((down or {}).get("best_bid")),
                no_ask=_float_value((down or {}).get("best_ask")),
                no_mid=_float_value((down or {}).get("mid")),
                no_bid_size=_float_value((down or {}).get("best_bid_size")),
                no_ask_size=_float_value((down or {}).get("best_ask_size")),
                latest_quote_time=latest_quote_time,
            )
        )

    local_date = _date_value(first.get("local_date"))
    return WeatherMarketContext(
        event_id=str(first["event_id"]),
        event_slug=str(first["event_slug"]),
        title=f"Highest temperature in {first['city']} on {local_date.isoformat()}" if local_date else str(first["event_slug"]),
        city=str(first["city"]),
        city_key=str(first["city_key"]),
        station_code=first.get("station_code"),
        station_name=first.get("station_name"),
        lat=float(first["lat"]) if first.get("lat") is not None else None,
        lon=float(first["lon"]) if first.get("lon") is not None else None,
        timezone=first.get("timezone"),
        local_date=local_date,
        unit=first.get("unit"),
        rule_family=first.get("rule_family"),
        resolution_source_url=first.get("resolution_source_url"),
        verified_station=False,
        observation_provider=None,
        forecast_provider=None,
        markets=markets,
    )


def _nearest_quote_row(
    series: dict[str, Any] | None,
    *,
    captured_at: datetime,
    quote_window_seconds: int,
) -> dict[str, Any] | None:
    if not series:
        return None
    times = series["times"]
    rows = series["rows"]
    index = bisect_left(times, captured_at)
    candidates: list[tuple[float, dict[str, Any]]] = []
    lower = max(0, index - 6)
    upper = min(len(times), index + 6)
    for candidate_index in range(lower, upper):
        if 0 <= candidate_index < len(times):
            row = rows[candidate_index]
            delta = abs((row["time"] - captured_at).total_seconds())
            if delta <= quote_window_seconds:
                candidates.append((delta, row))
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            _quote_row_quality_rank(item[1]),
            _quote_row_spread_penalty(item[1]),
            item[0],
            -_quote_row_richness(item[1]),
        )
    )
    return candidates[0][1]


def _quote_row_quality_rank(row: dict[str, Any]) -> int:
    best_bid = _float_value(row.get("best_bid"))
    best_ask = _float_value(row.get("best_ask"))
    if best_bid is not None and best_ask is not None:
        return 0
    if best_ask is not None:
        return 1
    if best_bid is not None:
        return 2
    if row.get("mid") is not None:
        return 3
    return 4


def _quote_row_spread_penalty(row: dict[str, Any]) -> float:
    best_bid = _float_value(row.get("best_bid"))
    best_ask = _float_value(row.get("best_ask"))
    if best_bid is None or best_ask is None:
        return 999.0
    return round(max(0.0, best_ask - best_bid), 6)


def _quote_row_richness(row: dict[str, Any]) -> int:
    score = 0
    if row.get("best_bid") is not None:
        score += 1
    if row.get("best_ask") is not None:
        score += 1
    if row.get("mid") is not None:
        score += 1
    if row.get("best_bid_size") is not None:
        score += 1
    if row.get("best_ask_size") is not None:
        score += 1
    return score


def _date_value(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _float_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_by_market_id(rows: list[dict[str, Any]], market_id: str) -> dict[str, Any] | None:
    for row in rows:
        if str(row.get("market_id") or "") == market_id:
            return row
    return None


def _match_clone_trade_row(rows: list[dict[str, Any]], *, trade_outcome: str) -> dict[str, Any] | None:
    for row in rows:
        if bool(row.get("qualifies")) and str(row.get("playbook_key") or "") == "paired_under_par":
            return row
    for row in rows:
        if not bool(row.get("qualifies")):
            continue
        if str(row.get("side") or "").strip().lower() == trade_outcome:
            return row
    return None


def _clone_reason(rows: list[dict[str, Any]], *, trade_outcome: str) -> str:
    if not rows:
        return "market_not_evaluated"
    paired = [row for row in rows if str(row.get("playbook_key") or "") == "paired_under_par"]
    if paired:
        return _first_reason(paired[0]) or "paired_under_par_not_qualified"
    sided = [row for row in rows if str(row.get("side") or "").strip().lower() == trade_outcome]
    if sided:
        return _first_reason(sided[0]) or "directional_not_qualified"
    return "side_not_evaluated"


def _first_reason(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    reasons = row.get("rejection_reasons") or []
    return str(reasons[0]) if reasons else None


def _trade_brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp_utc": row["timestamp_utc"],
        "event_slug": row.get("event_slug"),
        "city": row.get("city"),
        "local_date": row.get("local_date"),
        "bucket_label": row.get("bucket_label"),
        "side": row.get("side"),
        "outcome": row.get("outcome"),
        "price": row.get("price"),
        "size": row.get("size"),
    }


def _counter_rows(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"label": label, "count": count}
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]


def _build_markdown_report(*, comparison_result: dict[str, Any], parity: dict[str, Any]) -> str:
    summary = parity["summary"]
    window = comparison_result["window"]
    lines = [
        "# ColdMath Quote Parity",
        "",
        "## Window",
        f"- Start UTC: `{window['window_start_utc'].isoformat()}`",
        f"- End UTC: `{window['window_end_utc'].isoformat()}`",
        "",
        "## Summary",
        f"- ColdMath trade count: `{summary['trade_count']}`",
        f"- Merge match count: `{summary['merge_match_count']}`",
        f"- Merge match ratio: `{summary['merge_match_ratio']}`",
        f"- Clone match count: `{summary['clone_match_count']}`",
        f"- Clone match ratio: `{summary['clone_match_ratio']}`",
        f"- Recommended engine: `{summary['recommended_engine']}`",
        "",
        "## Top Merge Miss Reasons",
    ]
    merge_reasons = summary.get("top_merge_miss_reasons") or []
    if not merge_reasons:
        lines.append("- None")
    else:
        for item in merge_reasons:
            lines.append(f"- `{item['label']}`: `{item['count']}`")

    lines.extend(["", "## Top Clone Miss Reasons"])
    clone_reasons = summary.get("top_clone_miss_reasons") or []
    if not clone_reasons:
        lines.append("- None")
    else:
        for item in clone_reasons:
            lines.append(f"- `{item['label']}`: `{item['count']}`")

    lines.extend(["", "## Matched Clone Playbooks"])
    playbooks = summary.get("matched_clone_playbooks") or []
    if not playbooks:
        lines.append("- None")
    else:
        for item in playbooks:
            lines.append(f"- `{item['label']}`: `{item['count']}`")

    lines.extend(["", "## Trade Classification"])
    for row in parity["classified_rows"][:100]:
        lines.append(
            f"- `{row['timestamp_utc'].isoformat()}` | `{row.get('city')}` `{row.get('bucket_label')}` "
            f"| merge `{row['merge_reason']}` | clone `{row['clone_reason']}`"
            + (f" `{row['clone_playbook']}`" if row.get("clone_playbook") else "")
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
