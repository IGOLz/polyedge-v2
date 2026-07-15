"""Fast covered-window replay for ColdMath weather parity."""

from __future__ import annotations

import argparse
import json
import logging
from bisect import bisect_right
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from analysis.coldmath_public_parity import (
    DEFAULT_CLONE_CONFIG_PATH,
    DEFAULT_PROFILE,
    _apply_size_model,
    _build_context_for_event,
    _build_trade_context_cache,
    _candidate_brief,
    _clip_covered_window,
    _compare_replay_to_public,
    _event_quote_bounds,
    _fetch_public_weather_trades,
    _group_public_trade_sequences,
    _load_quote_coverage,
    _mark_trade_coverage,
    _match_trade_to_candidate,
    _max_entry_attempt_limit,
    _prepare_parity_clone_config,
    _requested_window,
    _trade_time_reason,
)
from analysis.coldmath_quote_parity import _load_historical_weather_state
from analysis.coldmath_window_compare import _extract_wallet
from analysis.wallet_forensics.fetchers import WalletForensicsClient
from analysis.wallet_forensics.utils import ensure_dir, safe_float
from trading_weather.clone_config import PAIR_PLAYBOOK_KEYS, normalize_clone_bot_config
from trading_weather.clone_engine import (
    build_clone_runtime,
    evaluate_clone_cycle,
    plan_directional_entry,
    plan_neg_risk_entry,
    plan_paired_entry,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
DEFAULT_FAST_OUTPUT_DIR = SRC_ROOT / "results" / "wallet_forensics" / "coldmath_fast_covered_replay"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fast covered-window replay for ColdMath weather parity")
    parser.add_argument("--profile", type=str, default=DEFAULT_PROFILE)
    parser.add_argument("--wallet", type=str, default=None)
    parser.add_argument("--window-start", type=str, required=True, help="UTC window start (ISO 8601)")
    parser.add_argument("--window-end", type=str, required=True, help="UTC window end (ISO 8601)")
    parser.add_argument("--quote-window-seconds", type=int, default=180)
    parser.add_argument("--match-window-seconds", type=float, default=60.0)
    parser.add_argument("--clone-config-path", type=str, default=str(DEFAULT_CLONE_CONFIG_PATH))
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_FAST_OUTPUT_DIR))
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = run_fast_covered_replay(args)
    logger.info(
        "Fast covered replay complete: covered=%s replay_pnl=%.4f public_pnl=%.4f",
        result["summary"]["covered_trade_count"],
        float(result["summary"]["replay_marked_pnl_usd"] or 0.0),
        float(result["summary"]["public_marked_pnl_usd"] or 0.0),
    )
    return 0


def run_fast_covered_replay(args: argparse.Namespace | list[str] | None = None) -> dict[str, Any]:
    if not isinstance(args, argparse.Namespace):
        args = build_parser().parse_args(args)

    artifact_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = ensure_dir(Path(args.output_dir).resolve() / artifact_id)
    clone_config = normalize_clone_bot_config(json.loads(Path(args.clone_config_path).read_text(encoding="utf-8")))

    client = WalletForensicsClient()
    wallet_target = _resolve_wallet_target(client, args)
    requested_window = _requested_window(
        lookback_hours=0.0,
        window_start=args.window_start,
        window_end=args.window_end,
    )
    window_start = requested_window["requested_start_utc"]
    window_end = requested_window["requested_end_utc"]

    trade_rows = _fetch_public_weather_trades(
        client,
        wallet=wallet_target["proxy_wallet"],
        window_start=window_start,
        window_end=window_end,
    )
    event_slugs = sorted({str(row.get("event_slug") or "") for row in trade_rows if row.get("event_slug")})
    coverage = _load_quote_coverage(event_slugs=event_slugs)
    covered_window = _clip_covered_window(
        requested_start=window_start,
        requested_end=window_end,
        coverage_start=coverage["coverage_start_utc"],
        coverage_end=coverage["coverage_end_utc"],
    )
    catalog_by_event, quote_series = _load_historical_weather_state(
        event_slugs=event_slugs,
        window_start=covered_window["covered_start_utc"] - timedelta(hours=24),
        window_end=covered_window["covered_end_utc"],
    )
    event_bounds = _event_quote_bounds(catalog_by_event=catalog_by_event, quote_series=quote_series)
    covered_rows, uncovered_rows = _mark_trade_coverage(
        trade_rows,
        covered_start=covered_window["covered_start_utc"],
        covered_end=covered_window["covered_end_utc"],
        catalog_by_event=catalog_by_event,
        event_bounds=event_bounds,
        quote_series=quote_series,
        quote_window_seconds=int(args.quote_window_seconds),
    )
    covered_rows = _assign_public_playbooks(
        covered_rows,
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        quote_window_seconds=int(args.quote_window_seconds),
    )
    covered_rows = sorted(covered_rows, key=lambda row: row["timestamp_utc"])
    clone_config = _prepare_parity_clone_config(clone_config, covered_rows=covered_rows)
    size_model = _build_size_model(clone_config)
    replay = _run_trade_driven_replay(
        trade_rows=covered_rows,
        clone_config=clone_config,
        size_model=size_model,
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        quote_window_seconds=int(args.quote_window_seconds),
        match_window_seconds=float(args.match_window_seconds),
        window_end=covered_window["covered_end_utc"],
    )

    public_marked = _window_trade_ledger_pnl(
        rows=covered_rows,
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        as_of=covered_window["covered_end_utc"],
    )
    replay_marked = _window_trade_ledger_pnl(
        rows=replay["replay_trades"],
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        as_of=covered_window["covered_end_utc"],
    )
    public_marked_pnl = float(public_marked.get("marked_pnl_usd") or 0.0)
    replay_marked_pnl = float(replay_marked.get("marked_pnl_usd") or 0.0)
    if public_marked_pnl > 0:
        pnl_ratio = round(replay_marked_pnl / public_marked_pnl, 6)
    elif public_marked_pnl == 0:
        pnl_ratio = 1.0 if replay_marked_pnl >= 0 else 0.0
    else:
        pnl_ratio = None

    summary = {
        "artifact_id": artifact_id,
        "artifact_dir": str(output_dir),
        "wallet": wallet_target["proxy_wallet"],
        "requested_window": requested_window,
        "covered_window": covered_window,
        "covered_trade_count": len(covered_rows),
        "uncovered_trade_count": len(uncovered_rows),
        "coverage": coverage,
        "trade_match_metrics": replay["trade_match_metrics"],
        "public_marked_pnl_usd": round(public_marked_pnl, 6),
        "replay_marked_pnl_usd": round(replay_marked_pnl, 6),
        "marked_pnl_ratio": pnl_ratio,
        "public_ledger_summary": public_marked,
        "replay_ledger_summary": replay_marked,
        "replay_counts": replay["counts"],
        "top_blocked_reasons": replay["top_blocked_reasons"],
    }

    _write_csv(output_dir / "coldmath_covered_public_trades.csv", covered_rows)
    _write_csv(output_dir / "coldmath_fast_replay_trades.csv", replay["replay_trades"])
    _write_csv(output_dir / "coldmath_fast_replay_matches.csv", replay["matched_rows"])
    _write_csv(output_dir / "coldmath_fast_replay_blocked.csv", replay["blocked_candidates"])
    (output_dir / "coldmath_fast_replay_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (output_dir / "coldmath_fast_replay_report.md").write_text(
        _build_markdown_report(summary),
        encoding="utf-8",
    )
    return {
        "summary": summary,
        "covered_rows": covered_rows,
        "uncovered_rows": uncovered_rows,
        "replay": replay,
        "output_dir": str(output_dir),
    }


def _resolve_wallet_target(client: WalletForensicsClient, args: argparse.Namespace) -> dict[str, Any]:
    if args.wallet:
        wallet = str(args.wallet).strip().lower()
    else:
        resolved = client.resolve_wallet(str(args.profile))
        wallet = str(_extract_wallet(resolved) or "").strip().lower()
    if not wallet:
        raise RuntimeError("Could not resolve ColdMath proxy wallet")
    profile_payload: dict[str, Any] = {}
    try:
        profile_payload = client.fetch_public_profile(wallet)
    except Exception:
        logger.warning("Public profile lookup failed for %s", wallet)
    return {
        "proxy_wallet": wallet,
        "profile_name": profile_payload.get("name") or args.profile,
    }


def _assign_public_playbooks(
    rows: list[dict[str, Any]],
    *,
    catalog_by_event: dict[str, list[dict[str, Any]]],
    quote_series: dict[tuple[str, str], dict[str, Any]],
    quote_window_seconds: int,
) -> list[dict[str, Any]]:
    grouped = _group_public_trade_sequences(
        rows,
        gap_seconds=120,
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        quote_window_seconds=quote_window_seconds,
    )
    sequence_playbooks = {
        str(row["sequence_id"]): str(row.get("public_playbook") or "unsupported_public_behavior")
        for row in grouped
    }
    return [
        {
            **row,
            "public_playbook": sequence_playbooks.get(str(row.get("sequence_id") or ""), "unsupported_public_behavior"),
        }
        for row in rows
    ]


def _build_size_model(clone_config: dict[str, Any]) -> dict[str, Any]:
    size_model = {
        "repeat_entry_cooldown_seconds": float((clone_config.get("runtime") or {}).get("repeat_entry_cooldown_seconds") or 0.0),
        "per_playbook": {},
    }
    for playbook_key, playbook in (clone_config.get("playbooks") or {}).items():
        entry = {
            "sequence_budget_usd": safe_float(playbook.get("sequence_budget_usd")) or 0.0,
            "max_ask_size_fraction": safe_float(playbook.get("max_ask_size_fraction")) or 1.0,
            "reentry_scale": safe_float(playbook.get("reentry_scale")) or 1.0,
        }
        dominant_fraction = safe_float(playbook.get("dominant_leg_budget_fraction"))
        if dominant_fraction is not None:
            entry["dominant_leg_budget_fraction"] = dominant_fraction
        size_model["per_playbook"][playbook_key] = entry
    return size_model


def _run_trade_driven_replay(
    *,
    trade_rows: list[dict[str, Any]],
    clone_config: dict[str, Any],
    size_model: dict[str, Any],
    catalog_by_event: dict[str, list[dict[str, Any]]],
    quote_series: dict[tuple[str, str], dict[str, Any]],
    quote_window_seconds: int,
    match_window_seconds: float,
    window_end,
) -> dict[str, Any]:
    if not trade_rows:
        empty_metrics = {
            "covered_trade_count": 0,
            "covered_trade_match_rate_condition_side": 0.0,
            "covered_trade_match_rate_playbook": 0.0,
            "median_entry_time_delta_seconds": None,
            "median_size_error_ratio": None,
            "false_positive_trade_count": 0,
            "false_positive_notional_usd": 0.0,
            "false_positive_pnl_proxy_usd": 0.0,
            "public_notional_usd": 0.0,
            "replay_notional_usd": 0.0,
            "public_pnl_proxy_usd": 0.0,
            "replay_pnl_proxy_usd": 0.0,
            "replay_pnl_proxy_ratio": None,
            "playbook_pnl_proxy": [],
            "top_miss_reasons": [],
        }
        return {
            "replay_trades": [],
            "blocked_candidates": [],
            "matched_rows": [],
            "trade_match_metrics": empty_metrics,
            "counts": {},
            "top_blocked_reasons": [],
        }

    runtime = build_clone_runtime(clone_config, dry_run=False)
    runtime_cfg = clone_config.get("runtime") or {}
    total_spend_limit = float(runtime_cfg.get("total_spend_limit_usd") or 0.0)
    max_exposure = float(runtime_cfg.get("max_total_exposure_usd") or 0.0)
    max_positions = int(runtime_cfg.get("max_concurrent_positions") or 0)
    max_entries_per_tick = _max_entry_attempt_limit(runtime_cfg)

    active_positions: list[dict[str, Any]] = []
    replay_trades: list[dict[str, Any]] = []
    blocked_candidates: list[dict[str, Any]] = []
    sequence_state: dict[str, dict[str, Any]] = {}
    entry_counts: dict[tuple[str, str, str], int] = {}
    context_cache = _build_trade_context_cache(
        trade_rows=trade_rows,
        catalog_by_event=catalog_by_event,
        quote_series=quote_series,
        quote_window_seconds=quote_window_seconds,
    )
    grouped_by_timestamp: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in trade_rows:
        grouped_by_timestamp[row["timestamp_utc"]].append(row)
    timestamps = sorted(grouped_by_timestamp)
    if not timestamps or timestamps[-1] != window_end:
        timestamps.append(window_end)

    spent_usd = 0.0
    next_position_id = 1
    blocked_counts: dict[str, int] = {}

    for captured_at in timestamps:
        rows_at_ts = grouped_by_timestamp.get(captured_at) or []
        if not rows_at_ts:
            continue

        event_slugs = {
            str(row.get("event_slug") or "")
            for row in rows_at_ts
            if row.get("event_slug")
        }
        event_slugs.update(
            str(position.get("event_slug") or "")
            for position in active_positions
            if position.get("closed_at") is None and position.get("event_slug")
        )
        contexts = []
        for event_slug in sorted(event_slugs):
            context = context_cache.get((event_slug, captured_at))
            if context is None:
                context = _build_context_for_event(
                    event_slug=event_slug,
                    captured_at=captured_at,
                    catalog_by_event=catalog_by_event,
                    quote_series=quote_series,
                    quote_window_seconds=quote_window_seconds,
                )
                context_cache[(event_slug, captured_at)] = context
            if context is not None:
                contexts.append(context)
        if not contexts:
            continue

        report = evaluate_clone_cycle(
            contexts=contexts,
            runtime=runtime,
            captured_at=captured_at,
            health_state={
                "execution_allowed": True,
                "execution_auth": {"status": "healthy", "allowed": True},
                "market_data": {"status": "healthy", "reason": "fast_covered_replay"},
                "quote_coverage_ratio": 1.0,
            },
            sequence_state=sequence_state,
            active_positions=active_positions,
            active_market_ids={str(position.get("market_id") or "") for position in active_positions if position.get("closed_at") is None},
        )

        entries_this_tick = 0
        for trade in rows_at_ts:
            trade_type = str(trade.get("trade_type") or trade.get("side") or "").lower()
            if trade_type in {"sell", "redeem"}:
                exit_rows, active_positions = _apply_public_exit_trade(
                    trade=trade,
                    active_positions=active_positions,
                )
                if exit_rows:
                    replay_trades.extend(exit_rows)
                else:
                    reason = "closeout_rule_mismatch"
                    blocked_candidates.append({**_candidate_brief(trade), "timestamp_utc": captured_at, "block_reason": reason})
                    blocked_counts[reason] = blocked_counts.get(reason, 0) + 1
                continue

            public_playbook = str(trade.get("public_playbook") or "")
            market_rows = _candidate_rows_for_trade(report.get("cycle_rows") or [], trade)
            candidate = _match_trade_to_candidate(market_rows, trade)
            if candidate is None or not bool(candidate.get("qualifies")):
                reason = _trade_time_reason(market_rows, public_playbook=public_playbook)
                blocked_candidates.append({**_candidate_brief(trade), "timestamp_utc": captured_at, "block_reason": reason})
                blocked_counts[reason] = blocked_counts.get(reason, 0) + 1
                continue

            active_exposure = _active_inventory_cost_usd(active_positions)
            open_positions = [position for position in active_positions if position.get("closed_at") is None]
            if max_positions > 0 and len(open_positions) >= max_positions:
                reason = "exposure_or_spend_cap_blocked"
                blocked_candidates.append({**_candidate_brief(candidate), "timestamp_utc": captured_at, "block_reason": reason})
                blocked_counts[reason] = blocked_counts.get(reason, 0) + 1
                continue
            if max_exposure > 0 and active_exposure >= max_exposure:
                reason = "exposure_or_spend_cap_blocked"
                blocked_candidates.append({**_candidate_brief(candidate), "timestamp_utc": captured_at, "block_reason": reason})
                blocked_counts[reason] = blocked_counts.get(reason, 0) + 1
                continue
            if total_spend_limit > 0 and spent_usd >= total_spend_limit:
                reason = "exposure_or_spend_cap_blocked"
                blocked_candidates.append({**_candidate_brief(candidate), "timestamp_utc": captured_at, "block_reason": reason})
                blocked_counts[reason] = blocked_counts.get(reason, 0) + 1
                continue
            if max_entries_per_tick > 0 and entries_this_tick >= max_entries_per_tick:
                break

            playbook_key = str(candidate.get("playbook_key") or "")
            candidate_side = str(candidate.get("side") or "paired")
            cooldown_key = (str(candidate.get("market_id") or ""), candidate_side, playbook_key)
            if _reentry_cooldown_blocked(
                replay_trades=replay_trades,
                cooldown_key=cooldown_key,
                captured_at=captured_at,
                cooldown_seconds=float(size_model.get("repeat_entry_cooldown_seconds") or 0.0),
            ):
                reason = "repeat_entry_rule_mismatch"
                blocked_candidates.append({**_candidate_brief(candidate), "timestamp_utc": captured_at, "block_reason": reason})
                blocked_counts[reason] = blocked_counts.get(reason, 0) + 1
                continue

            entry_source = candidate
            if playbook_key == "neg_risk_basket":
                plan = plan_neg_risk_entry(candidate, runtime, active_exposure_usd=active_exposure)
                if plan is None:
                    reason = "entry_plan_missing"
                    blocked_candidates.append({**_candidate_brief(candidate), "timestamp_utc": captured_at, "block_reason": reason})
                    blocked_counts[reason] = blocked_counts.get(reason, 0) + 1
                    continue
                plan = _apply_size_model(plan, candidate=candidate, size_model=size_model, entry_counts=entry_counts)
                if plan is None:
                    reason = "order_size_model_mismatch"
                    blocked_candidates.append({**_candidate_brief(candidate), "timestamp_utc": captured_at, "block_reason": reason})
                    blocked_counts[reason] = blocked_counts.get(reason, 0) + 1
                    continue
                entry_source = plan

            entry_rows, created_positions = _simulate_trade_driven_entry(
                plan=entry_source,
                trade=trade,
                captured_at=captured_at,
                active_positions=active_positions,
                position_id=next_position_id,
            )
            if not entry_rows and created_positions <= 0:
                reason = "public_fill_simulation_missing"
                blocked_candidates.append({**_candidate_brief(candidate), "timestamp_utc": captured_at, "block_reason": reason})
                blocked_counts[reason] = blocked_counts.get(reason, 0) + 1
                continue
            next_position_id += created_positions
            replay_trades.extend(entry_rows)
            spent_usd += sum(float(row.get("notional_usd") or 0.0) for row in entry_rows if str(row.get("trade_type") or "").lower() == "buy")
            entry_counts[cooldown_key] = entry_counts.get(cooldown_key, 0) + 1
            entries_this_tick += 1

    matched_rows, trade_match_metrics = _compare_replay_to_public(
        public_rows=trade_rows,
        replay_rows=replay_trades,
        match_window_seconds=match_window_seconds,
    )
    return {
        "replay_trades": replay_trades,
        "blocked_candidates": blocked_candidates,
        "matched_rows": matched_rows,
        "trade_match_metrics": trade_match_metrics,
        "counts": {
            "replay_trade_count": len(replay_trades),
            "blocked_candidate_count": len(blocked_candidates),
            "open_position_count_end": len([position for position in active_positions if position.get("closed_at") is None]),
        },
        "top_blocked_reasons": [
            {"label": label, "count": count}
            for label, count in sorted(blocked_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
        ],
    }


def _candidate_rows_for_trade(cycle_rows: list[dict[str, Any]], trade: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in cycle_rows:
        if str(row.get("market_id") or "") == str(trade.get("condition_id") or ""):
            rows.append(row)
            continue
        if (
            str(row.get("playbook_key") or "") == "neg_risk_basket"
            and str(row.get("event_slug") or "") == str(trade.get("event_slug") or "")
            and str(row.get("side") or "") == str(trade.get("outcome") or "")
        ):
            rows.append(row)
    return rows


def _simulate_trade_driven_entry(
    *,
    plan: dict[str, Any],
    trade: dict[str, Any],
    captured_at,
    active_positions: list[dict[str, Any]],
    position_id: int,
) -> tuple[list[dict[str, Any]], int]:
    playbook_key = str(plan.get("playbook_key") or "")
    if playbook_key in PAIR_PLAYBOOK_KEYS:
        return _simulate_pair_trade_fill(
            plan=plan,
            trade=trade,
            captured_at=captured_at,
            active_positions=active_positions,
            position_id=position_id,
        )
    if playbook_key == "neg_risk_basket":
        return _simulate_neg_risk_entry(
            plan=plan,
            trade=trade,
            captured_at=captured_at,
            active_positions=active_positions,
            position_id=position_id,
        )
    return _simulate_directional_entry(
        plan=plan,
        trade=trade,
        captured_at=captured_at,
        active_positions=active_positions,
        position_id=position_id,
    )


def _simulate_pair_trade_fill(
    *,
    plan: dict[str, Any],
    trade: dict[str, Any],
    captured_at,
    active_positions: list[dict[str, Any]],
    position_id: int,
) -> tuple[list[dict[str, Any]], int]:
    side = str(trade.get("outcome") or "").lower()
    price = safe_float(trade.get("price"))
    size = safe_float(trade.get("size"))
    if side not in {"yes", "no"} or price is None or price <= 0.0 or size is None or size <= 0.0:
        return [], 0

    position = _find_open_pair_inventory_position(
        active_positions=active_positions,
        condition_id=str(plan.get("condition_id") or plan.get("market_id") or trade.get("condition_id") or ""),
        playbook_key=str(plan.get("playbook_key") or ""),
    )
    created = 0
    if position is None:
        position = {
            "id": position_id,
            "market_id": str(plan.get("condition_id") or plan.get("market_id") or trade.get("condition_id") or ""),
            "event_slug": str(plan.get("event_slug") or trade.get("event_slug") or ""),
            "city": str(plan.get("city") or trade.get("city") or ""),
            "local_date": plan.get("local_date") or trade.get("local_date"),
            "bucket_label": str(plan.get("bucket_label") or trade.get("bucket_label") or ""),
            "playbook_key": str(plan.get("playbook_key") or ""),
            "status": "open_pair_inventory",
            "opened_at": captured_at,
            "closed_at": None,
            "yes_lots": [],
            "no_lots": [],
            "yes_shares": 0.0,
            "no_shares": 0.0,
            "yes_entry_price": 0.0,
            "no_entry_price": 0.0,
            "total_entry_cost": 0.0,
        }
        active_positions.append(position)
        created = 1
    _append_pair_inventory_lot(position, side=side, shares=size, price=price)
    return [
        _replay_trade_row(
            captured_at=captured_at,
            condition_id=str(plan.get("condition_id") or plan.get("market_id") or trade.get("condition_id") or ""),
            event_slug=str(plan.get("event_slug") or trade.get("event_slug") or ""),
            city=str(plan.get("city") or trade.get("city") or ""),
            local_date=plan.get("local_date") or trade.get("local_date"),
            bucket_label=str(plan.get("bucket_label") or trade.get("bucket_label") or ""),
            playbook_key=str(plan.get("playbook_key") or ""),
            trade_type="buy",
            outcome=side,
            size=size,
            price=price,
        )
    ], created


def _simulate_directional_entry(
    *,
    plan: dict[str, Any],
    trade: dict[str, Any],
    captured_at,
    active_positions: list[dict[str, Any]],
    position_id: int,
) -> tuple[list[dict[str, Any]], int]:
    target_shares = safe_float(trade.get("size")) or safe_float(plan.get("target_shares")) or 0.0
    price = safe_float(trade.get("price")) or safe_float(plan.get("price")) or 0.0
    side = str(trade.get("outcome") or plan.get("side") or "").lower()
    if target_shares <= 0 or price <= 0.0 or side not in {"yes", "no"}:
        return [], 0
    row = _replay_trade_row(
        captured_at=captured_at,
        condition_id=str(plan.get("condition_id") or plan.get("market_id") or trade.get("condition_id") or ""),
        event_slug=str(plan.get("event_slug") or trade.get("event_slug") or ""),
        city=str(plan.get("city") or trade.get("city") or ""),
        local_date=plan.get("local_date") or trade.get("local_date"),
        bucket_label=str(plan.get("bucket_label") or trade.get("bucket_label") or ""),
        playbook_key=str(plan.get("playbook_key") or ""),
        trade_type="buy",
        outcome=side,
        size=target_shares,
        price=price,
    )
    position = {
        "id": position_id,
        "market_id": str(plan.get("condition_id") or plan.get("market_id") or trade.get("condition_id") or ""),
        "event_slug": str(plan.get("event_slug") or trade.get("event_slug") or ""),
        "city": str(plan.get("city") or trade.get("city") or ""),
        "local_date": plan.get("local_date") or trade.get("local_date"),
        "bucket_label": str(plan.get("bucket_label") or trade.get("bucket_label") or ""),
        "playbook_key": str(plan.get("playbook_key") or ""),
        "side": side,
        "status": "open_directional",
        "opened_at": captured_at,
        "closed_at": None,
        "remaining_shares": target_shares,
        "entry_price": price,
        "profit_take_price": safe_float(plan.get("profit_take_price")),
        "minimum_hold_seconds": safe_float(plan.get("minimum_hold_seconds")) or 0.0,
        "force_flatten_minutes_before_end": 120.0,
        "total_entry_cost": round(target_shares * price, 6),
    }
    active_positions.append(position)
    return [row], 1


def _simulate_neg_risk_entry(
    *,
    plan: dict[str, Any],
    trade: dict[str, Any],
    captured_at,
    active_positions: list[dict[str, Any]],
    position_id: int,
) -> tuple[list[dict[str, Any]], int]:
    side = str(plan.get("side") or "")
    if side not in {"yes", "no"}:
        return [], 0
    legs = list(plan.get("legs") or [])
    rows = []
    for leg in legs:
        target_shares = safe_float(trade.get("size")) if str(leg.get("market_id") or "") == str(trade.get("condition_id") or "") else 0.0
        if target_shares is None or target_shares <= 0:
            target_shares = safe_float(leg.get("target_shares")) or 0.0
        price = safe_float(leg.get("price")) or 0.0
        if target_shares <= 0 or price <= 0.0:
            continue
        rows.append(
            _replay_trade_row(
                captured_at=captured_at,
                condition_id=str(leg.get("market_id") or ""),
                event_slug=str(plan.get("event_slug") or ""),
                city=str(plan.get("city") or ""),
                local_date=plan.get("local_date"),
                bucket_label=str(leg.get("bucket_label") or ""),
                playbook_key="neg_risk_basket",
                trade_type="buy",
                outcome=side,
                size=target_shares,
                price=price,
            )
        )
    if not rows:
        return [], 0
    position = {
        "id": position_id,
        "market_id": str(plan.get("condition_id") or ""),
        "event_slug": str(plan.get("event_slug") or ""),
        "city": str(plan.get("city") or ""),
        "local_date": plan.get("local_date"),
        "bucket_label": str(plan.get("bucket_label") or ""),
        "playbook_key": "neg_risk_basket",
        "side": side,
        "status": "open_neg_risk_basket",
        "opened_at": captured_at,
        "closed_at": None,
        "legs": [
            {
                "market_id": str(leg.get("market_id") or ""),
                "bucket_label": str(leg.get("bucket_label") or ""),
                "target_shares": safe_float(leg.get("target_shares")) or 0.0,
                "remaining_shares": safe_float(leg.get("target_shares")) or 0.0,
                "entry_price": safe_float(leg.get("price")) or 0.0,
            }
            for leg in legs
            if (safe_float(leg.get("target_shares")) or 0.0) > 0
        ],
        "force_flatten_minutes_before_end": float(safe_float(plan.get("force_flatten_minutes_before_end")) or 120.0),
        "max_unmatched_ratio": safe_float(plan.get("max_unmatched_ratio")),
        "selected_condition_count": len(legs),
        "total_entry_cost": round(sum(float(row.get("notional_usd") or 0.0) for row in rows), 6),
    }
    active_positions.append(position)
    return rows, 1


def _find_open_pair_inventory_position(
    *,
    active_positions: list[dict[str, Any]],
    condition_id: str,
    playbook_key: str,
) -> dict[str, Any] | None:
    for position in active_positions:
        if position.get("closed_at") is not None:
            continue
        if str(position.get("status") or "") != "open_pair_inventory":
            continue
        if str(position.get("market_id") or "") != condition_id:
            continue
        if str(position.get("playbook_key") or "") != playbook_key:
            continue
        return position
    return None


def _append_pair_inventory_lot(position: dict[str, Any], *, side: str, shares: float, price: float) -> None:
    lot_key = f"{side}_lots"
    lots = list(position.get(lot_key) or [])
    lots.append({"shares": round(float(shares), 6), "entry_price": round(float(price), 6)})
    position[lot_key] = lots
    _refresh_pair_inventory_totals(position)


def _refresh_pair_inventory_totals(position: dict[str, Any]) -> None:
    yes_lots = list(position.get("yes_lots") or [])
    no_lots = list(position.get("no_lots") or [])
    yes_shares = sum(max(0.0, float(lot.get("shares") or 0.0)) for lot in yes_lots)
    no_shares = sum(max(0.0, float(lot.get("shares") or 0.0)) for lot in no_lots)
    yes_cost = sum((max(0.0, float(lot.get("shares") or 0.0)) * (safe_float(lot.get("entry_price")) or 0.0)) for lot in yes_lots)
    no_cost = sum((max(0.0, float(lot.get("shares") or 0.0)) * (safe_float(lot.get("entry_price")) or 0.0)) for lot in no_lots)
    position["yes_shares"] = round(yes_shares, 6)
    position["no_shares"] = round(no_shares, 6)
    position["yes_entry_price"] = round((yes_cost / yes_shares), 6) if yes_shares > 0 else 0.0
    position["no_entry_price"] = round((no_cost / no_shares), 6) if no_shares > 0 else 0.0
    position["total_entry_cost"] = round(yes_cost + no_cost, 6)


def _active_inventory_cost_usd(active_positions: list[dict[str, Any]]) -> float:
    total = 0.0
    for position in active_positions:
        if position.get("closed_at") is not None:
            continue
        status = str(position.get("status") or "")
        if status == "open_pair_inventory":
            total += sum(
                max(0.0, float(lot.get("shares") or 0.0)) * (safe_float(lot.get("entry_price")) or 0.0)
                for lot in (position.get("yes_lots") or [])
            )
            total += sum(
                max(0.0, float(lot.get("shares") or 0.0)) * (safe_float(lot.get("entry_price")) or 0.0)
                for lot in (position.get("no_lots") or [])
            )
        elif status == "open_directional":
            total += max(0.0, float(position.get("remaining_shares") or 0.0)) * (safe_float(position.get("entry_price")) or 0.0)
        elif status == "open_neg_risk_basket":
            for leg in position.get("legs") or []:
                total += max(0.0, float(leg.get("remaining_shares") or 0.0)) * (safe_float(leg.get("entry_price")) or 0.0)
        else:
            total += float(position.get("total_entry_cost") or 0.0)
    return round(total, 6)


def _apply_public_exit_trade(
    *,
    trade: dict[str, Any],
    active_positions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trade_type = str(trade.get("trade_type") or trade.get("side") or "").lower()
    outcome = str(trade.get("outcome") or "").lower()
    condition_id = str(trade.get("condition_id") or "")
    size = safe_float(trade.get("size")) or 0.0
    price = safe_float(trade.get("price")) or 0.0
    captured_at = trade["timestamp_utc"]
    if size <= 0 or price < 0 or not condition_id:
        return [], active_positions

    remaining = size
    filled = 0.0
    redeem_like = trade_type == "redeem" or outcome == "paired"
    for position in active_positions:
        if remaining <= 0:
            break
        if position.get("closed_at") is not None:
            continue
        if str(position.get("market_id") or "") != condition_id:
            continue
        consumed = 0.0
        status = str(position.get("status") or "")
        if redeem_like and status == "open_pair_inventory":
            consumed = _consume_pair_inventory(position, shares=remaining, side="paired")
        elif not redeem_like:
            if status == "open_pair_inventory":
                consumed = _consume_pair_inventory(position, shares=remaining, side=outcome)
            elif status == "open_directional" and str(position.get("side") or "") == outcome:
                consumed = _consume_directional_inventory(position, shares=remaining)
            elif status == "open_neg_risk_basket" and str(position.get("side") or "") == outcome:
                consumed = _consume_neg_risk_inventory(position, condition_id=condition_id, shares=remaining)
        if consumed <= 0:
            continue
        remaining -= consumed
        filled += consumed
        _close_position_if_empty(position, closed_at=captured_at)

    if filled <= 0:
        return [], active_positions
    replay_trade_type = "redeem" if redeem_like else "sell"
    replay_outcome = "paired" if redeem_like else outcome
    row = _replay_trade_row(
        captured_at=captured_at,
        condition_id=condition_id,
        event_slug=str(trade.get("event_slug") or ""),
        city=str(trade.get("city") or ""),
        local_date=trade.get("local_date"),
        bucket_label=str(trade.get("bucket_label") or ""),
        playbook_key="inventory_rebalance_and_exit",
        trade_type=replay_trade_type,
        outcome=replay_outcome,
        size=filled,
        price=price,
    )
    return [row], active_positions


def _consume_pair_inventory(position: dict[str, Any], *, shares: float, side: str) -> float:
    if side == "paired":
        yes_shares = max(0.0, float(position.get("yes_shares") or 0.0))
        no_shares = max(0.0, float(position.get("no_shares") or 0.0))
        consumed = min(shares, yes_shares, no_shares)
        if consumed <= 0:
            return 0.0
        _consume_inventory_lots(position.setdefault("yes_lots", []), consumed)
        _consume_inventory_lots(position.setdefault("no_lots", []), consumed)
        _refresh_pair_inventory_totals(position)
        return consumed
    if side not in {"yes", "no"}:
        return 0.0
    key = f"{side}_shares"
    available = max(0.0, float(position.get(key) or 0.0))
    consumed = min(shares, available)
    if consumed <= 0:
        return 0.0
    _consume_inventory_lots(position.setdefault(f"{side}_lots", []), consumed)
    _refresh_pair_inventory_totals(position)
    return consumed


def _consume_inventory_lots(lots: list[dict[str, Any]], shares: float) -> float:
    remaining = shares
    consumed = 0.0
    for lot in lots:
        if remaining <= 0:
            break
        available = max(0.0, float(lot.get("shares") or 0.0))
        fill = min(remaining, available)
        if fill <= 0:
            continue
        lot["shares"] = round(available - fill, 6)
        remaining -= fill
        consumed += fill
    lots[:] = [lot for lot in lots if max(0.0, float(lot.get("shares") or 0.0)) > 0]
    return consumed


def _consume_directional_inventory(position: dict[str, Any], *, shares: float) -> float:
    available = max(0.0, float(position.get("remaining_shares") or 0.0))
    consumed = min(shares, available)
    if consumed <= 0:
        return 0.0
    position["remaining_shares"] = round(available - consumed, 6)
    entry_price = safe_float(position.get("entry_price")) or 0.0
    position["total_entry_cost"] = round(max(0.0, float(position.get("total_entry_cost") or 0.0) - (consumed * entry_price)), 6)
    return consumed


def _consume_neg_risk_inventory(position: dict[str, Any], *, condition_id: str, shares: float) -> float:
    remaining = shares
    consumed = 0.0
    for leg in position.get("legs") or []:
        if remaining <= 0:
            break
        if str(leg.get("market_id") or "") != condition_id:
            continue
        available = max(0.0, float(leg.get("remaining_shares") or 0.0))
        fill = min(remaining, available)
        if fill <= 0:
            continue
        leg["remaining_shares"] = round(available - fill, 6)
        position["total_entry_cost"] = round(
            max(0.0, float(position.get("total_entry_cost") or 0.0) - (fill * (safe_float(leg.get("entry_price")) or 0.0))),
            6,
        )
        remaining -= fill
        consumed += fill
    return consumed


def _close_position_if_empty(position: dict[str, Any], *, closed_at) -> None:
    status = str(position.get("status") or "")
    if status == "open_pair_inventory":
        if max(0.0, float(position.get("yes_shares") or 0.0)) <= 0 and max(0.0, float(position.get("no_shares") or 0.0)) <= 0:
            position["closed_at"] = closed_at
            position["status"] = "closed_pair_inventory"
    elif status == "open_directional":
        if max(0.0, float(position.get("remaining_shares") or 0.0)) <= 0:
            position["closed_at"] = closed_at
            position["status"] = "closed_directional"
    elif status == "open_neg_risk_basket":
        if all(max(0.0, float(leg.get("remaining_shares") or 0.0)) <= 0 for leg in (position.get("legs") or [])):
            position["closed_at"] = closed_at
            position["status"] = "closed_neg_risk_basket"


def _window_trade_ledger_pnl(
    *,
    rows: list[dict[str, Any]],
    catalog_by_event: dict[str, list[dict[str, Any]]],
    quote_series: dict[tuple[str, str], dict[str, Any]],
    as_of,
) -> dict[str, Any]:
    del catalog_by_event

    inventory: dict[str, dict[str, Any]] = {}
    entry_notional_usd = 0.0
    exit_value_usd = 0.0
    attributable_cashflow_usd = 0.0
    unattributed_exit_value_usd = 0.0
    for row in sorted(rows, key=lambda item: item["timestamp_utc"]):
        trade_type = str(row.get("trade_type") or row.get("side") or "").lower()
        outcome = str(row.get("outcome") or "").lower()
        condition_id = str(row.get("condition_id") or "")
        size = safe_float(row.get("size")) or 0.0
        price = safe_float(row.get("price")) or 0.0
        if size <= 0 or price < 0:
            continue
        notional = round(size * price, 6)
        if trade_type == "buy":
            entry_notional_usd += notional
            attributable_cashflow_usd -= notional
            if outcome in {"yes", "no"}:
                slot = inventory.setdefault(
                    condition_id,
                    {
                        "yes_shares": 0.0,
                        "no_shares": 0.0,
                    },
                )
                slot[f"{outcome}_shares"] += size
        elif trade_type in {"sell", "redeem"}:
            exit_value_usd += notional
            if trade_type == "redeem" or outcome == "paired":
                attributable_cashflow_usd += notional
                continue
            slot = inventory.setdefault(
                condition_id,
                {
                    "yes_shares": 0.0,
                    "no_shares": 0.0,
                },
            )
            available = float(slot.get(f"{outcome}_shares") or 0.0)
            realized_size = min(available, size)
            if realized_size > 0:
                slot[f"{outcome}_shares"] = round(available - realized_size, 6)
                attributable_cashflow_usd += round(realized_size * price, 6)
            if size > realized_size:
                unattributed_exit_value_usd += round((size - realized_size) * price, 6)

    mergeable_value_usd = 0.0
    residual_value_usd = 0.0
    open_positions = 0
    missing_mark_count = 0
    for condition_id, slot in inventory.items():
        yes_shares = max(0.0, float(slot.get("yes_shares") or 0.0))
        no_shares = max(0.0, float(slot.get("no_shares") or 0.0))
        if yes_shares <= 0 and no_shares <= 0:
            continue
        open_positions += 1
        mergeable = min(yes_shares, no_shares)
        mergeable_value_usd += round(mergeable, 6)
        yes_residual = yes_shares - mergeable
        no_residual = no_shares - mergeable
        if yes_residual > 0:
            quote = _latest_quote_row_before(quote_series.get((condition_id, "Up")), as_of)
            price = _quote_liquidation_price(quote)
            if price is None:
                missing_mark_count += 1
            else:
                residual_value_usd += round(yes_residual * price, 6)
        if no_residual > 0:
            quote = _latest_quote_row_before(quote_series.get((condition_id, "Down")), as_of)
            price = _quote_liquidation_price(quote)
            if price is None:
                missing_mark_count += 1
            else:
                residual_value_usd += round(no_residual * price, 6)
    terminal_inventory_value_usd = round(mergeable_value_usd + residual_value_usd, 6)
    marked_pnl_usd = round(attributable_cashflow_usd + terminal_inventory_value_usd, 6)
    return {
        "entry_notional_usd": round(entry_notional_usd, 6),
        "exit_value_usd": round(exit_value_usd, 6),
        "attributable_cashflow_usd": round(attributable_cashflow_usd, 6),
        "unattributed_exit_value_usd": round(unattributed_exit_value_usd, 6),
        "mergeable_value_usd": round(mergeable_value_usd, 6),
        "residual_value_usd": round(residual_value_usd, 6),
        "terminal_inventory_value_usd": terminal_inventory_value_usd,
        "marked_pnl_usd": marked_pnl_usd,
        "open_position_count": open_positions,
        "missing_mark_count": missing_mark_count,
    }


def _latest_quote_row_before(series: dict[str, Any] | None, captured_at: datetime) -> dict[str, Any] | None:
    if not series:
        return None
    times = series.get("times") or []
    rows = series.get("rows") or []
    if not times or not rows:
        return None
    index = bisect_right(times, captured_at) - 1
    if index < 0 or index >= len(rows):
        return None
    return rows[index]


def _quote_liquidation_price(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    best_bid = safe_float(row.get("best_bid"))
    if best_bid is not None:
        return best_bid
    mid = safe_float(row.get("mid"))
    if mid is not None:
        return mid
    return safe_float(row.get("best_ask"))


def _reentry_cooldown_blocked(
    *,
    replay_trades: list[dict[str, Any]],
    cooldown_key: tuple[str, str, str],
    captured_at,
    cooldown_seconds: float,
) -> bool:
    if cooldown_seconds <= 0:
        return False
    condition_id, side, playbook_key = cooldown_key
    for row in reversed(replay_trades):
        if str(row.get("condition_id") or "") != condition_id:
            continue
        if str(row.get("playbook_key") or "") != playbook_key:
            continue
        row_outcome = str(row.get("outcome") or "paired")
        if row_outcome != side and not (side == "paired" and row_outcome in {"yes", "no"}):
            continue
        return (captured_at - row["timestamp_utc"]).total_seconds() < cooldown_seconds
    return False


def _replay_trade_row(
    *,
    captured_at,
    condition_id: str,
    event_slug: str,
    city: str,
    local_date,
    bucket_label: str,
    playbook_key: str,
    trade_type: str,
    outcome: str,
    size: float,
    price: float,
) -> dict[str, Any]:
    return {
        "timestamp_utc": captured_at,
        "condition_id": condition_id,
        "event_slug": event_slug,
        "city": city,
        "local_date": local_date,
        "bucket_label": bucket_label,
        "playbook_key": playbook_key,
        "trade_type": trade_type,
        "side": trade_type,
        "outcome": outcome,
        "size": round(float(size), 6),
        "price": round(price, 6),
        "notional_usd": round(float(size) * float(price), 6),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            payload = {}
            for key in fieldnames:
                value = row.get(key)
                if isinstance(value, (dict, list)):
                    payload[key] = json.dumps(value, sort_keys=True, default=str)
                else:
                    payload[key] = value
            writer.writerow(payload)


def _build_markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# ColdMath Fast Covered Replay",
        "",
        f"- Covered trades: `{summary['covered_trade_count']}`",
        f"- Public marked PnL USD: `{summary['public_marked_pnl_usd']}`",
        f"- Replay marked PnL USD: `{summary['replay_marked_pnl_usd']}`",
        f"- Marked PnL ratio: `{summary['marked_pnl_ratio']}`",
        f"- Trade match rate (condition+side): `{summary['trade_match_metrics']['covered_trade_match_rate_condition_side']}`",
        f"- Trade match rate (playbook): `{summary['trade_match_metrics']['covered_trade_match_rate_playbook']}`",
        "",
        "## Public Ledger",
        "",
        f"- Entry notional USD: `{summary['public_ledger_summary']['entry_notional_usd']}`",
        f"- Exit value USD: `{summary['public_ledger_summary']['exit_value_usd']}`",
        f"- Terminal inventory value USD: `{summary['public_ledger_summary']['terminal_inventory_value_usd']}`",
        f"- Unattributed exit value USD: `{summary['public_ledger_summary']['unattributed_exit_value_usd']}`",
        "",
        "## Replay Ledger",
        "",
        f"- Entry notional USD: `{summary['replay_ledger_summary']['entry_notional_usd']}`",
        f"- Exit value USD: `{summary['replay_ledger_summary']['exit_value_usd']}`",
        f"- Terminal inventory value USD: `{summary['replay_ledger_summary']['terminal_inventory_value_usd']}`",
    ]
    if summary.get("top_blocked_reasons"):
        lines.extend(["", "## Top Blocked Reasons", ""])
        for row in summary["top_blocked_reasons"]:
            lines.append(f"- `{row['label']}`: `{row['count']}`")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
