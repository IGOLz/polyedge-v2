"""Dedicated live weather merge bot based on the ColdMath public strategy."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from analysis.wallet_forensics.utils import safe_float
from shared.config import PROXY_URL
from shared.db import close_pool, create_weather_tables, init_pool
from trading import config as trading_config
from trading import db as trading_db
from trading.utils import log
from trading_weather.clone_config import is_clone_bot_config, normalize_clone_bot_config
from trading_weather.clone_db import (
    close_clone_position,
    create_weather_clone_tables,
    get_open_clone_positions,
    insert_clone_cycle,
    insert_clone_market_scans,
    insert_clone_position,
    update_clone_position_fill,
    upsert_clone_sequences,
)
from trading_weather.clone_engine import (
    append_clone_cycle_history,
    build_clone_cycle_summary,
    build_clone_runtime,
    clone_cycle_status_message,
    evaluate_clone_cycle,
    plan_paired_entry,
    preflight_clone_health,
    refresh_contexts_with_direct_quotes,
)
from trading_weather import config
from trading_weather import db as weather_db
from trading_weather.safe_ops import ensure_weather_allowances, merge_position, redeem_position
from trading_weather.strategy import (
    build_runtime_config,
    compute_mergeable_shares,
    open_position_exposure,
    plan_entry,
    scan_live_market_report,
)
from weather.storage import fetch_active_weather_contexts


@dataclass(slots=True)
class WeatherMergeTelemetryState:
    summary_interval_seconds: float
    history_path: Path
    iteration: int = 0
    last_summary_at: datetime | None = None
    last_candidate_signature: str | None = None
    last_candidate_brief: dict[str, Any] | None = None
    last_stand_down_reason: str | None = None


@dataclass(slots=True)
class WeatherCloneTelemetryState:
    summary_interval_seconds: float
    history_path: Path
    iteration: int = 0
    last_summary_at: datetime | None = None
    last_candidate_signature: str | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PolyEdge weather trading bot")
    parser.add_argument("--dry-run", action="store_true", help="Observe candidates without placing live orders")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    parser.add_argument(
        "--config-path",
        type=str,
        default=str(config.DEFAULT_BOT_CONFIG_PATH),
        help="Path to weather bot config json",
    )
    parser.add_argument(
        "--engine",
        choices=("auto", "merge", "clone"),
        default="auto",
        help="Runtime engine selection. auto uses clone for clone configs and merge for legacy configs.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable info logging")
    return parser


def _build_clob_client():
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds

    creds = ApiCreds(
        api_key=trading_config.API_KEY,
        api_secret=trading_config.API_SECRET,
        api_passphrase=trading_config.API_PASSPHRASE,
    )
    return ClobClient(
        trading_config.CLOB_BASE_URL,
        key=trading_config.PRIVATE_KEY,
        chain_id=137,
        creds=creds,
        signature_type=2,
        funder=trading_config.PROXY_WALLET,
    )


def _parse_fill_from_resp(resp: dict | None, fallback_shares: int, fallback_price: float) -> tuple[int, float]:
    fill_shares = fallback_shares
    fill_price = fallback_price
    if isinstance(resp, dict):
        raw_shares = resp.get("size_matched") or resp.get("matched_size") or resp.get("filled")
        raw_price = resp.get("average_price") or resp.get("price")
        if raw_shares is not None:
            try:
                parsed_shares = math.floor(float(raw_shares))
            except (TypeError, ValueError):
                parsed_shares = 0
            if parsed_shares > 0:
                fill_shares = parsed_shares
        if raw_price is not None:
            try:
                parsed_price = float(raw_price)
            except (TypeError, ValueError):
                parsed_price = 0.0
            if parsed_price > 0:
                fill_price = parsed_price
    return fill_shares, fill_price


def _best_book_price(clob, token_id: str, *, side: str) -> float | None:
    try:
        book = clob.get_order_book(token_id)
    except Exception:
        return None

    if side == "SELL":
        bids = book.bids if hasattr(book, "bids") else []
        if not bids:
            return None
        return float(max(bids, key=lambda item: float(item.price)).price)

    asks = book.asks if hasattr(book, "asks") else []
    if not asks:
        return None
    return float(min(asks, key=lambda item: float(item.price)).price)


def _get_token_balance(clob, token_id: str) -> float:
    from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

    balance = clob.get_balance_allowance(
        BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
    )
    return int(balance.get("balance", "0")) / 1_000_000


def _get_usdc_balance(clob) -> float:
    from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

    balance = clob.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
    return int(balance.get("balance", "0")) / 1_000_000


def _place_fok_order(clob, token_id: str, *, price: float, shares: int, side: str) -> dict[str, Any] | None:
    from py_clob_client.clob_types import OrderArgs, OrderType

    if shares <= 0:
        return None
    order_args = OrderArgs(token_id=token_id, price=round(price, 2), size=float(shares), side=side)
    signed = clob.create_order(order_args)
    resp = clob.post_order(signed, OrderType.FOK)
    status = (resp.get("status") or "").upper() if isinstance(resp, dict) else ""
    if status in {"MATCHED", "FILLED"}:
        fill_shares, fill_price = _parse_fill_from_resp(resp, shares, price)
        return {
            "order_id": resp.get("orderID") or resp.get("id"),
            "fill_shares": fill_shares,
            "fill_price": fill_price,
            "raw": resp,
        }
    return None


def _load_bot_config(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _resolve_engine(*, requested: str, raw_config: dict[str, Any]) -> str:
    if requested in {"merge", "clone"}:
        return requested
    return "clone" if is_clone_bot_config(raw_config) else "merge"


async def _log_event(log_type: str, message: str, data: dict[str, Any] | None = None) -> None:
    await trading_db.log_event(log_type, message, data, echo=False)
    log.info(message)


def _cycle_status_message(
    report: dict[str, Any],
) -> str:
    balance = safe_float(report.get("balance")) or 0.0
    active_positions = int(report.get("active_positions") or 0)
    active_exposure_usd = safe_float(report.get("active_exposure_usd")) or 0.0
    context_count = int(report.get("context_count") or 0)
    market_count = int(report.get("market_count") or 0)
    candidate_count = int(report.get("candidate_count") or 0)
    near_miss_count = int(report.get("near_miss_count") or 0)
    entry_attempts = int(report.get("entry_attempts") or 0)
    daily_realized_pnl = safe_float(report.get("daily_realized_pnl")) or 0.0
    stand_down_reason = str(report.get("stand_down_reason") or "").strip()
    top_candidate = report.get("top_candidate")
    top_near_miss = report.get("top_near_miss")
    top_rejection_reasons = report.get("top_rejection_reasons") or []
    message = (
        "[WEATHER-MERGE] Summary | "
        f"balance={balance:.2f} "
        f"daily_pnl={daily_realized_pnl:.2f} "
        f"active_positions={active_positions} "
        f"exposure={active_exposure_usd:.2f} "
        f"contexts={context_count} "
        f"markets={market_count} "
        f"candidates={candidate_count} "
        f"near_misses={near_miss_count} "
        f"entries={entry_attempts}"
    )
    if stand_down_reason:
        message += f" | stand_down={stand_down_reason}"
    if top_candidate:
        combined_cost = safe_float(top_candidate.get("combined_cost"))
        merge_edge = safe_float(top_candidate.get("merge_edge"))
        mergeable_size = safe_float(top_candidate.get("max_mergeable_size"))
        message += (
            " | top="
            f"{top_candidate.get('city')} {top_candidate.get('bucket_label')} "
            f"cost={(combined_cost if combined_cost is not None else float('nan')):.4f} "
            f"edge={(merge_edge if merge_edge is not None else float('nan')):.4f} "
            f"size={(mergeable_size if mergeable_size is not None else float('nan')):.2f} "
            f"quality={top_candidate.get('quote_quality_label') or 'n/a'}"
        )
    elif top_near_miss:
        combined_cost = safe_float(top_near_miss.get("combined_cost"))
        reasons = ", ".join((top_near_miss.get("rejection_reasons") or [])[:3]) or "n/a"
        message += (
            " | near="
            f"{top_near_miss.get('city')} {top_near_miss.get('bucket_label')} "
            f"cost={(combined_cost if combined_cost is not None else float('nan')):.4f} "
            f"reasons={reasons}"
        )
    if top_rejection_reasons:
        formatted_reasons = ",".join(
            f"{item.get('reason')}:{item.get('count')}"
            for item in top_rejection_reasons[:3]
        )
        if formatted_reasons:
            message += f" | rejections={formatted_reasons}"
    return message


def _round_value(value: Any, digits: int = 6) -> float | None:
    number = safe_float(value)
    if number is None:
        return None
    return round(number, digits)


def _candidate_brief(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not candidate:
        return None
    return {
        "market_id": candidate.get("market_id"),
        "city": candidate.get("city"),
        "local_date": candidate.get("local_date"),
        "bucket_label": candidate.get("bucket_label"),
        "combined_cost": _round_value(candidate.get("combined_cost"), 4),
        "merge_edge": _round_value(candidate.get("merge_edge"), 4),
        "max_mergeable_size": _round_value(candidate.get("max_mergeable_size"), 2),
        "inventory_imbalance_ratio": _round_value(candidate.get("inventory_imbalance_ratio"), 4),
        "quote_quality_label": candidate.get("quote_quality_label"),
        "rejection_reasons": list(candidate.get("rejection_reasons") or [])[:3],
    }


def _plan_brief(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not plan:
        return None
    return {
        "market_id": plan.get("market_id"),
        "city": plan.get("city"),
        "local_date": plan.get("local_date"),
        "bucket_label": plan.get("bucket_label"),
        "target_shares": int(plan.get("target_shares") or 0),
        "combined_cost": _round_value(plan.get("combined_cost"), 4),
        "expected_edge_usd": _round_value(plan.get("expected_edge_usd"), 4),
        "first_side": plan.get("first_side"),
        "second_side": plan.get("second_side"),
    }


def _report_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    generated_at = report.get("generated_at")
    if isinstance(generated_at, datetime):
        generated_at = generated_at.isoformat()
    return {
        "generated_at": generated_at,
        "dry_run": bool(report.get("dry_run")),
        "balance": _round_value(report.get("balance"), 2),
        "daily_realized_pnl": _round_value(report.get("daily_realized_pnl"), 2),
        "daily_loss": _round_value(report.get("daily_loss"), 2),
        "daily_loss_limit_usd": _round_value(report.get("daily_loss_limit_usd"), 2),
        "active_positions": int(report.get("active_positions") or 0),
        "active_exposure_usd": _round_value(report.get("active_exposure_usd"), 2),
        "context_count": int(report.get("context_count") or 0),
        "market_count": int(report.get("market_count") or 0),
        "candidate_count": int(report.get("candidate_count") or 0),
        "near_miss_count": int(report.get("near_miss_count") or 0),
        "entry_attempts": int(report.get("entry_attempts") or 0),
        "stand_down_reason": report.get("stand_down_reason"),
        "top_candidate": report.get("top_candidate"),
        "top_near_miss": report.get("top_near_miss"),
        "top_rejection_reasons": report.get("top_rejection_reasons") or [],
        "planned_entries": report.get("planned_entries") or [],
    }


def _candidate_signature(report: dict[str, Any]) -> str | None:
    candidate = report.get("top_candidate")
    if not candidate:
        return None
    payload = {
        "candidate_count": int(report.get("candidate_count") or 0),
        "market_id": candidate.get("market_id"),
        "combined_cost": _round_value(candidate.get("combined_cost"), 4),
        "max_mergeable_size": _round_value(candidate.get("max_mergeable_size"), 2),
        "quote_quality_label": candidate.get("quote_quality_label"),
    }
    return json.dumps(payload, sort_keys=True, default=str)


def _json_safe_payload(payload: Any) -> Any:
    return json.loads(json.dumps(payload, default=str))


def _stand_down_message(report: dict[str, Any]) -> str:
    reason = str(report.get("stand_down_reason") or "").strip()
    if reason == "daily_loss_limit_reached":
        return (
            "[WEATHER-MERGE] Stand down | "
            f"reason={reason} "
            f"daily_loss={(safe_float(report.get('daily_loss')) or 0.0):.2f} "
            f"limit={(safe_float(report.get('daily_loss_limit_usd')) or 0.0):.2f}"
        )
    if reason == "capacity_reached":
        return (
            "[WEATHER-MERGE] Stand down | "
            f"reason={reason} "
            f"active_positions={int(report.get('active_positions') or 0)} "
            f"exposure={(safe_float(report.get('active_exposure_usd')) or 0.0):.2f}"
        )
    return f"[WEATHER-MERGE] Stand down | reason={reason or 'n/a'}"


def _candidate_message(report: dict[str, Any]) -> str:
    candidate = report.get("top_candidate") or {}
    planned_entries = report.get("planned_entries") or []
    top_plan = planned_entries[0] if planned_entries else None
    message = (
        "[WEATHER-MERGE] Candidate | "
        f"{candidate.get('city')} {candidate.get('local_date')} {candidate.get('bucket_label')} "
        f"cost={(safe_float(candidate.get('combined_cost')) or float('nan')):.4f} "
        f"edge={(safe_float(candidate.get('merge_edge')) or float('nan')):.4f} "
        f"size={(safe_float(candidate.get('max_mergeable_size')) or float('nan')):.2f} "
        f"quality={candidate.get('quote_quality_label') or 'n/a'}"
    )
    if top_plan:
        message += (
            f" | plan_shares={int(top_plan.get('target_shares') or 0)} "
            f"plan_edge={(safe_float(top_plan.get('expected_edge_usd')) or 0.0):.4f}"
        )
    return message


def _candidate_cleared_message(previous: dict[str, Any] | None) -> str:
    if not previous:
        return "[WEATHER-MERGE] Candidate cleared"
    return (
        "[WEATHER-MERGE] Candidate cleared | "
        f"{previous.get('city')} {previous.get('local_date')} {previous.get('bucket_label')} "
        f"cost={(safe_float(previous.get('combined_cost')) or float('nan')):.4f}"
    )


def _append_cycle_history(*, history_path: Path, event_type: str, message: str, report: dict[str, Any]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "event_type": event_type,
        "message": message,
        **_report_snapshot(report),
    }
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


async def _emit_cycle_event(
    *,
    telemetry: WeatherMergeTelemetryState,
    log_type: str,
    event_type: str,
    message: str,
    report: dict[str, Any],
) -> None:
    _append_cycle_history(
        history_path=telemetry.history_path,
        event_type=event_type,
        message=message,
        report=report,
    )
    await _log_event(log_type, message, _report_snapshot(report))


async def _emit_cycle_telemetry(
    report: dict[str, Any],
    telemetry: WeatherMergeTelemetryState,
) -> None:
    now = datetime.now(UTC)
    telemetry.iteration += 1

    current_candidate_signature = _candidate_signature(report)
    current_stand_down_reason = str(report.get("stand_down_reason") or "").strip() or None

    if current_candidate_signature and current_candidate_signature != telemetry.last_candidate_signature:
        await _emit_cycle_event(
            telemetry=telemetry,
            log_type="weather_merge_signal",
            event_type="candidate",
            message=_candidate_message(report),
            report=report,
        )
    elif not current_candidate_signature and telemetry.last_candidate_signature:
        await _emit_cycle_event(
            telemetry=telemetry,
            log_type="weather_merge_signal_cleared",
            event_type="candidate_cleared",
            message=_candidate_cleared_message(telemetry.last_candidate_brief),
            report=report,
        )

    if current_stand_down_reason != telemetry.last_stand_down_reason:
        if current_stand_down_reason:
            await _emit_cycle_event(
                telemetry=telemetry,
                log_type="weather_merge_stand_down",
                event_type="stand_down",
                message=_stand_down_message(report),
                report=report,
            )
        elif telemetry.last_stand_down_reason:
            await _emit_cycle_event(
                telemetry=telemetry,
                log_type="weather_merge_resumed",
                event_type="stand_down_cleared",
                message="[WEATHER-MERGE] Stand down cleared | entries re-enabled",
                report=report,
            )

    if telemetry.last_summary_at is None or (
        now - telemetry.last_summary_at
    ).total_seconds() >= telemetry.summary_interval_seconds:
        await _emit_cycle_event(
            telemetry=telemetry,
            log_type="weather_merge_summary",
            event_type="summary",
            message=_cycle_status_message(report),
            report=report,
        )
        telemetry.last_summary_at = now

    telemetry.last_candidate_signature = current_candidate_signature
    telemetry.last_candidate_brief = report.get("top_candidate")
    telemetry.last_stand_down_reason = current_stand_down_reason


def _clone_candidate_signature(report: dict[str, Any]) -> str | None:
    candidates = report.get("candidates") or []
    if not candidates:
        return None
    top = candidates[0]
    payload = {
        "playbook_key": top.get("playbook_key"),
        "market_id": top.get("market_id"),
        "side": top.get("side"),
        "candidate_score": _round_value(top.get("candidate_score"), 6),
        "combined_cost": _round_value(top.get("combined_cost"), 4),
        "directional_price": _round_value(top.get("directional_price"), 4),
    }
    return json.dumps(payload, sort_keys=True, default=str)


async def _emit_clone_cycle_telemetry(
    summary: dict[str, Any],
    report: dict[str, Any],
    telemetry: WeatherCloneTelemetryState,
) -> None:
    now = datetime.now(UTC)
    telemetry.iteration += 1
    signature = _clone_candidate_signature(report)
    if signature and signature != telemetry.last_candidate_signature:
        top = (report.get("candidates") or [None])[0] or {}
        message = (
            "[WEATHER-CLONE] Candidate | "
            f"{top.get('playbook_key')} {top.get('city')} {top.get('local_date')} {top.get('bucket_label')} "
            f"side={top.get('side') or 'paired'} "
            f"score={(safe_float(top.get('candidate_score')) or float('nan')):.4f}"
        )
        await trading_db.log_event("weather_clone_signal", message, _json_safe_payload(top), echo=False)
        log.info(message)
    if telemetry.last_summary_at is None or (
        now - telemetry.last_summary_at
    ).total_seconds() >= telemetry.summary_interval_seconds:
        message = clone_cycle_status_message(summary)
        append_clone_cycle_history(history_path=telemetry.history_path, event_type="summary", payload=summary)
        await trading_db.log_event("weather_clone_summary", message, _json_safe_payload(summary), echo=False)
        log.info(message)
        telemetry.last_summary_at = now
    telemetry.last_candidate_signature = signature


def _clone_active_exposure_usd(positions: list[dict[str, Any]]) -> float:
    exposure = 0.0
    for position in positions:
        if position.get("closed_at") is not None:
            continue
        exposure += safe_float(position.get("total_entry_cost")) or 0.0
    return round(exposure, 6)


async def _attempt_clone_paired_entry(
    clob,
    plan: dict[str, Any],
    *,
    shadow_only: bool,
) -> None:
    position_id = await insert_clone_position(
        strategy_name=plan["strategy_name"],
        playbook_key=plan["playbook_key"],
        market_id=plan["market_id"],
        event_id=plan["event_id"],
        event_slug=plan["event_slug"],
        city=plan["city"],
        local_date=plan.get("local_date"),
        bucket_label=plan["bucket_label"],
        side=None,
        condition_id=plan["condition_id"],
        neg_risk=bool(plan.get("neg_risk")),
        yes_token_id=plan.get("yes_token_id"),
        no_token_id=plan.get("no_token_id"),
        status="pending_entry",
        shadow_only=shadow_only,
        target_shares=float(plan["target_shares"]),
        signal_score=float(plan.get("signal_score") or 0.0),
        expected_edge_usd=safe_float(plan.get("expected_edge_usd")),
        quote_snapshot=plan.get("quote_snapshot") or {},
        signal_data=plan.get("signal_data") or {},
        sequence_data=plan.get("sequence_data") or {},
    )
    if shadow_only:
        await close_clone_position(
            position_id,
            status="shadow_detected",
            close_reason="shadow_only",
            notes="Shadow-mode clone candidate recorded",
        )
        await trading_db.log_event(
            "weather_clone_shadow_entry",
            (
                "[WEATHER-CLONE] Shadow entry | "
                f"{plan['playbook_key']} {plan['city']} {plan['bucket_label']} "
                f"shares={plan['target_shares']} cost={plan['combined_cost']:.4f}"
            ),
            _json_safe_payload({"position_id": position_id, "plan": plan}),
            echo=False,
        )
        return

    first_side = plan["first_side"]
    second_side = plan["second_side"]
    first_token = plan["yes_token_id"] if first_side == "yes" else plan["no_token_id"]
    second_token = plan["yes_token_id"] if second_side == "yes" else plan["no_token_id"]
    first_price = plan["yes_price"] if first_side == "yes" else plan["no_price"]
    second_price = plan["yes_price"] if second_side == "yes" else plan["no_price"]
    target_shares = int(plan["target_shares"])
    first_fill = await asyncio.to_thread(
        _place_fok_order,
        clob,
        first_token,
        price=first_price,
        shares=target_shares,
        side="BUY",
    )
    if not first_fill:
        await close_clone_position(position_id, status="entry_failed", close_reason="first_leg_no_fill")
        return
    total_cost = first_fill["fill_shares"] * first_fill["fill_price"]
    second_fill = await asyncio.to_thread(
        _place_fok_order,
        clob,
        second_token,
        price=second_price,
        shares=first_fill["fill_shares"],
        side="BUY",
    )
    if not second_fill:
        unwind_token = first_token
        unwind_price = _best_book_price(clob, unwind_token, side="SELL")
        unwind_fill = None
        if unwind_price is not None:
            unwind_fill = await asyncio.to_thread(
                _place_fok_order,
                clob,
                unwind_token,
                price=unwind_price,
                shares=first_fill["fill_shares"],
                side="SELL",
            )
        await update_clone_position_fill(
            position_id,
            filled_shares=float(first_fill["fill_shares"]),
            avg_entry_price=float(first_fill["fill_price"]),
            total_entry_cost=total_cost,
            yes_shares=float(first_fill["fill_shares"] if first_side == "yes" else 0.0),
            no_shares=float(first_fill["fill_shares"] if first_side == "no" else 0.0),
            status="partial_entry",
            notes="First leg filled; second leg failed",
        )
        await close_clone_position(
            position_id,
            status="entry_failed",
            close_reason="second_leg_no_fill",
            realized_exit_value_usd=(
                float(unwind_fill["fill_shares"]) * float(unwind_fill["fill_price"]) if unwind_fill else None
            ),
            notes="Second leg failed; attempted immediate unwind",
        )
        return
    total_cost += second_fill["fill_shares"] * second_fill["fill_price"]
    filled_shares = float(min(first_fill["fill_shares"], second_fill["fill_shares"]))
    await update_clone_position_fill(
        position_id,
        filled_shares=filled_shares,
        avg_entry_price=float(total_cost / max(filled_shares * 2.0, 1.0)),
        total_entry_cost=total_cost,
        yes_shares=float(second_fill["fill_shares"] if second_side == "yes" else first_fill["fill_shares"]),
        no_shares=float(second_fill["fill_shares"] if second_side == "no" else first_fill["fill_shares"]),
        status="open_paired",
        notes="Both legs filled",
    )
    await trading_db.log_event(
        "weather_clone_entry",
        (
            "[WEATHER-CLONE] Entered | "
            f"{plan['city']} {plan['bucket_label']} "
            f"pairs={filled_shares:.0f} cost={total_cost / max(filled_shares, 1.0):.4f}"
        ),
        _json_safe_payload({"position_id": position_id, "plan": plan, "total_cost": round(total_cost, 6)}),
        echo=False,
    )


async def _handle_partial_unwind(clob, position: dict[str, Any]) -> None:
    yes_shares = safe_float(position.get("yes_shares")) or 0.0
    no_shares = safe_float(position.get("no_shares")) or 0.0
    side = "yes" if yes_shares > no_shares else "no"
    token_id = position["yes_token_id"] if side == "yes" else position["no_token_id"]
    shares = math.floor(abs(yes_shares - no_shares))
    if shares <= 0:
        return

    sell_price = _best_book_price(clob, token_id, side="SELL")
    if sell_price is None:
        await weather_db.update_weather_merge_status(
            position["id"],
            status="partial_orphaned",
            notes="Could not find sell liquidity for unmatched inventory",
        )
        return

    fill = await asyncio.to_thread(
        _place_fok_order,
        clob,
        token_id,
        price=sell_price,
        shares=shares,
        side="SELL",
    )
    if not fill:
        await weather_db.update_weather_merge_status(
            position["id"],
            status="partial_orphaned",
            notes="Unwind sell did not fill",
        )
        return

    remaining_yes = max(0.0, yes_shares - (fill["fill_shares"] if side == "yes" else 0.0))
    remaining_no = max(0.0, no_shares - (fill["fill_shares"] if side == "no" else 0.0))
    paired = compute_mergeable_shares(yes_shares=remaining_yes, no_shares=remaining_no)
    unwind_value = round(fill["fill_shares"] * fill["fill_price"], 6)
    await weather_db.record_weather_unwind(
        position["id"],
        unwind_collateral_usdc=unwind_value,
        status="partial_unwound" if remaining_yes == 0 and remaining_no == 0 else "open_partial",
        notes=f"Unwound unmatched {side} inventory at {fill['fill_price']:.4f}",
    )
    await weather_db.refresh_weather_position_balances(
        position["id"],
        yes_shares=remaining_yes,
        no_shares=remaining_no,
        paired_shares=paired,
        status="partial_unwound" if remaining_yes == 0 and remaining_no == 0 else "open_partial",
        notes=f"Unwound unmatched {side} inventory at {fill['fill_price']:.4f}",
    )
    if remaining_yes == 0 and remaining_no == 0:
        await weather_db.close_weather_merge_position(
            position["id"],
            status="partial_unwound",
            notes=f"Unwound unmatched {side} inventory at {fill['fill_price']:.4f}",
        )


async def _reconcile_position(clob, position: dict[str, Any], runtime) -> None:
    yes_balance = await asyncio.to_thread(_get_token_balance, clob, position["yes_token_id"])
    no_balance = await asyncio.to_thread(_get_token_balance, clob, position["no_token_id"])
    mergeable = compute_mergeable_shares(yes_shares=yes_balance, no_shares=no_balance)
    current_status = "open_paired" if mergeable > 0 else ("open_partial" if yes_balance > 0 or no_balance > 0 else "closed")
    await weather_db.refresh_weather_position_balances(
        position["id"],
        yes_shares=yes_balance,
        no_shares=no_balance,
        paired_shares=mergeable,
        status=current_status if current_status != "closed" else position["status"],
    )

    resolution = await weather_db.get_market_resolution(position["market_id"])
    resolved = bool((resolution or {}).get("resolved"))

    if mergeable > 0 and runtime.auto_merge and not resolved:
        merged_shares = mergeable
        result = await asyncio.to_thread(
            merge_position,
            position["condition_id"],
            neg_risk=bool(position.get("neg_risk")),
            shares=merged_shares,
        )
        await weather_db.record_weather_merge(
            position["id"],
            merged_shares=merged_shares,
            merged_collateral_usdc=float(merged_shares),
            mode=result.mode,
            transaction_hash=result.transaction_hash,
            state=result.state,
            status="merged",
        )
        yes_balance = await asyncio.to_thread(_get_token_balance, clob, position["yes_token_id"])
        no_balance = await asyncio.to_thread(_get_token_balance, clob, position["no_token_id"])
        mergeable = compute_mergeable_shares(yes_shares=yes_balance, no_shares=no_balance)
        await weather_db.refresh_weather_position_balances(
            position["id"],
            yes_shares=yes_balance,
            no_shares=no_balance,
            paired_shares=mergeable,
            status="open_partial" if (yes_balance > 0 or no_balance > 0) else "merged_closed",
        )
        if yes_balance == 0 and no_balance == 0:
            await weather_db.close_weather_merge_position(
                position["id"],
                status="merged_closed",
                notes=f"Merged {merged_shares} matched shares",
            )
            return

    if resolved and (yes_balance > 0 or no_balance > 0):
        result = await asyncio.to_thread(
            redeem_position,
            position["condition_id"],
            neg_risk=bool(position.get("neg_risk")),
            yes_shares=yes_balance,
            no_shares=no_balance,
        )
        winning_shares = max(yes_balance, no_balance)
        await weather_db.record_weather_redeem(
            position["id"],
            redeemed_collateral_usdc=winning_shares,
            mode=result.mode,
            transaction_hash=result.transaction_hash,
            state=result.state,
            status="redeemed",
        )
        await weather_db.close_weather_merge_position(
            position["id"],
            status="redeemed_closed",
            notes="Redeemed remaining resolved inventory",
        )
        return

    if mergeable == 0 and (yes_balance > 0 or no_balance > 0):
        opened_at = position.get("opened_at")
        if isinstance(opened_at, datetime):
            age_seconds = (datetime.now(UTC) - opened_at.astimezone(UTC)).total_seconds()
            if age_seconds >= runtime.partial_repair_window_seconds and not resolved:
                await _handle_partial_unwind(clob, position)


async def _attempt_entry(clob, candidate: dict[str, Any], plan: dict[str, Any], runtime, *, dry_run: bool) -> None:
    position_id = await weather_db.insert_weather_merge_position(
        plan=plan,
        max_complete_set_cost=runtime.live_rules["complete_set_cost_lte"],
        max_inventory_imbalance_ratio=runtime.live_rules.get("max_inventory_imbalance_ratio"),
    )

    if dry_run:
        await weather_db.close_weather_merge_position(
            position_id,
            status="dry_run",
            notes="Dry-run candidate only",
        )
        await _log_event(
            "weather_merge_dry_run",
            f"[WEATHER-MERGE] Dry run candidate {plan['city']} {plan['bucket_label']} | cost {plan['combined_cost']:.4f}",
            {"position_id": position_id, "plan": plan},
        )
        return

    first_side = plan["first_side"]
    second_side = plan["second_side"]
    first_token = plan["yes_token_id"] if first_side == "yes" else plan["no_token_id"]
    second_token = plan["yes_token_id"] if second_side == "yes" else plan["no_token_id"]
    first_price = plan["yes_price"] if first_side == "yes" else plan["no_price"]
    second_price = plan["yes_price"] if second_side == "yes" else plan["no_price"]
    target_shares = int(plan["target_shares"])

    first_fill = await asyncio.to_thread(
        _place_fok_order,
        clob,
        first_token,
        price=first_price,
        shares=target_shares,
        side="BUY",
    )
    if not first_fill:
        await weather_db.close_weather_merge_position(
            position_id,
            status="entry_failed",
            notes=f"First {first_side} leg did not fill",
        )
        return

    total_cost = first_fill["fill_shares"] * first_fill["fill_price"]
    await weather_db.record_weather_entry_fill(
        position_id,
        side=first_side,
        shares=first_fill["fill_shares"],
        fill_price=first_fill["fill_price"],
        order_id=first_fill.get("order_id"),
        total_entry_cost=total_cost,
        status="entry_first_leg_filled",
        notes=f"Filled {first_side} leg first",
    )

    max_second_leg_price = runtime.live_rules["complete_set_cost_lte"] - first_fill["fill_price"]
    if second_price > max_second_leg_price + 1e-9:
        await _handle_partial_unwind(
            clob,
            {
                "id": position_id,
                "yes_token_id": plan["yes_token_id"],
                "no_token_id": plan["no_token_id"],
                "yes_shares": first_fill["fill_shares"] if first_side == "yes" else 0.0,
                "no_shares": first_fill["fill_shares"] if first_side == "no" else 0.0,
            },
        )
        await weather_db.close_weather_merge_position(
            position_id,
            status="entry_failed",
            notes="Second leg moved above complete-set threshold",
        )
        return

    second_fill = await asyncio.to_thread(
        _place_fok_order,
        clob,
        second_token,
        price=second_price,
        shares=first_fill["fill_shares"],
        side="BUY",
    )
    if not second_fill:
        await _handle_partial_unwind(
            clob,
            {
                "id": position_id,
                "yes_token_id": plan["yes_token_id"],
                "no_token_id": plan["no_token_id"],
                "yes_shares": first_fill["fill_shares"] if first_side == "yes" else 0.0,
                "no_shares": first_fill["fill_shares"] if first_side == "no" else 0.0,
            },
        )
        await weather_db.close_weather_merge_position(
            position_id,
            status="entry_failed",
            notes=f"Second {second_side} leg did not fill",
        )
        return

    total_cost += second_fill["fill_shares"] * second_fill["fill_price"]
    await weather_db.record_weather_entry_fill(
        position_id,
        side=second_side,
        shares=second_fill["fill_shares"],
        fill_price=second_fill["fill_price"],
        order_id=second_fill.get("order_id"),
        total_entry_cost=total_cost,
        status="open_paired",
        notes="Both legs filled",
    )
    await weather_db.refresh_weather_position_balances(
        position_id,
        yes_shares=second_fill["fill_shares"] if second_side == "yes" else first_fill["fill_shares"],
        no_shares=second_fill["fill_shares"] if second_side == "no" else first_fill["fill_shares"],
        paired_shares=min(first_fill["fill_shares"], second_fill["fill_shares"]),
        status="open_paired",
    )
    await _log_event(
        "weather_merge_entry",
        f"[WEATHER-MERGE] Entered {plan['city']} {plan['bucket_label']} | {first_fill['fill_shares']} pairs @ {total_cost / max(first_fill['fill_shares'], 1):.4f}",
        {"position_id": position_id, "plan": plan, "total_cost": round(total_cost, 4)},
    )

    if runtime.auto_merge:
        await asyncio.sleep(config.SETTLEMENT_WAIT_SECONDS)
        position = {
            "id": position_id,
            "market_id": plan["market_id"],
            "condition_id": plan["condition_id"],
            "neg_risk": plan["neg_risk"],
            "yes_token_id": plan["yes_token_id"],
            "no_token_id": plan["no_token_id"],
            "opened_at": datetime.now(UTC),
            "status": "open_paired",
        }
        await _reconcile_position(clob, position, runtime)


async def _run_cycle(clob, bot_config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    generated_at = datetime.now(UTC)
    balance = await asyncio.to_thread(_get_usdc_balance, clob)
    runtime = build_runtime_config(
        bot_config,
        balance_usd=balance,
        sequence_budget_cap_usd=config.DEFAULT_SEQUENCE_BUDGET_USD,
        max_total_exposure_cap_usd=config.DEFAULT_MAX_TOTAL_EXPOSURE_USD,
        daily_loss_limit_cap_usd=config.DEFAULT_DAILY_LOSS_LIMIT_USD,
        min_expected_edge_usd=config.DEFAULT_MIN_EXPECTED_EDGE_USD,
        max_concurrent_positions=config.DEFAULT_MAX_CONCURRENT_POSITIONS,
        partial_repair_window_seconds=config.DEFAULT_PARTIAL_REPAIR_WINDOW_SECONDS,
        min_target_shares=config.DEFAULT_MIN_TARGET_SHARES,
        auto_merge=config.AUTO_MERGE and not dry_run,
    )

    daily_realized_pnl = await weather_db.get_daily_realized_pnl()
    daily_loss = max(0.0, -daily_realized_pnl)

    positions = await weather_db.get_active_weather_merge_positions()
    for position in positions:
        await _reconcile_position(clob, position, runtime)

    positions = await weather_db.get_active_weather_merge_positions()
    active_exposure_usd = round(sum(open_position_exposure(position) for position in positions), 6)
    active_market_ids = {str(position.get("market_id")) for position in positions}
    contexts = await fetch_active_weather_contexts(eligible_only=True)
    scan_report = scan_live_market_report(
        contexts,
        runtime,
        captured_at=generated_at,
        excluded_market_ids=active_market_ids,
        near_miss_limit=config.DEFAULT_NEAR_MISS_LIMIT,
    )

    stand_down_reason: str | None = None
    if daily_loss >= runtime.daily_loss_limit_usd:
        stand_down_reason = "daily_loss_limit_reached"
    elif len(positions) >= runtime.max_concurrent_positions or active_exposure_usd >= runtime.max_total_exposure_usd:
        stand_down_reason = "capacity_reached"

    candidates = list(scan_report.get("candidates") or [])
    entry_limit = config.DEFAULT_MAX_ENTRY_ATTEMPTS if config.DEFAULT_MAX_ENTRY_ATTEMPTS > 0 else None
    entry_attempts = 0
    planned_entries: list[dict[str, Any]] = []
    if stand_down_reason is None:
        for candidate in candidates:
            positions = await weather_db.get_active_weather_merge_positions()
            active_exposure_usd = round(sum(open_position_exposure(position) for position in positions), 6)
            active_market_ids = {str(position.get("market_id")) for position in positions}
            if len(positions) >= runtime.max_concurrent_positions or active_exposure_usd >= runtime.max_total_exposure_usd:
                stand_down_reason = "capacity_reached"
                break
            if entry_limit is not None and entry_attempts >= entry_limit:
                break
            if str(candidate.get("market_id")) in active_market_ids:
                continue
            plan = plan_entry(candidate, runtime, active_exposure_usd=active_exposure_usd)
            if plan is None:
                continue
            planned_entries.append(_plan_brief(plan))
            entry_attempts += 1
            if dry_run:
                continue
            await _attempt_entry(clob, candidate, plan, runtime, dry_run=False)

    final_positions = await weather_db.get_active_weather_merge_positions()
    final_exposure_usd = round(sum(open_position_exposure(position) for position in final_positions), 6)
    near_misses = scan_report.get("near_misses") or []
    return {
        "generated_at": generated_at,
        "dry_run": dry_run,
        "balance": round(balance, 6),
        "daily_realized_pnl": round(daily_realized_pnl, 6),
        "daily_loss": round(daily_loss, 6),
        "daily_loss_limit_usd": runtime.daily_loss_limit_usd,
        "active_positions": len(final_positions),
        "active_exposure_usd": final_exposure_usd,
        "context_count": int(scan_report.get("context_count") or 0),
        "market_count": int(scan_report.get("market_count") or 0),
        "candidate_count": int(scan_report.get("candidate_count") or 0),
        "near_miss_count": int(scan_report.get("near_miss_count") or 0),
        "entry_attempts": entry_attempts,
        "stand_down_reason": stand_down_reason,
        "top_candidate": _candidate_brief(candidates[0] if candidates else None),
        "top_near_miss": _candidate_brief(near_misses[0] if near_misses else None),
        "top_rejection_reasons": list(scan_report.get("rejection_reason_counts") or [])[:3],
        "planned_entries": planned_entries[:3],
    }


async def _run_clone_cycle(
    clob,
    bot_config: dict[str, Any],
    *,
    dry_run: bool,
    telemetry: WeatherCloneTelemetryState,
    sequence_state: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    captured_at = datetime.now(UTC)
    health_state = preflight_clone_health(clob, dry_run=dry_run)
    balance = None
    try:
        balance = await asyncio.to_thread(_get_usdc_balance, clob)
    except Exception as exc:
        health_state["execution_auth"] = {
            "status": "unhealthy" if not dry_run else "shadow_only",
            "reason": f"{type(exc).__name__}: {exc}",
            "allowed": dry_run,
        }
    runtime = build_clone_runtime(bot_config, dry_run=dry_run)
    contexts = await fetch_active_weather_contexts(eligible_only=True)
    direct_quote_result = refresh_contexts_with_direct_quotes(
        clob,
        contexts,
        captured_at=captured_at,
        health_config=bot_config.get("health") or {},
    )
    total_markets = int(direct_quote_result.get("total_markets") or 0)
    quote_pair_markets = int(direct_quote_result.get("quote_pair_markets") or 0)
    quote_coverage_ratio = (quote_pair_markets / total_markets) if total_markets > 0 else 0.0
    min_quote_coverage_ratio = float((bot_config.get("health") or {}).get("min_quote_coverage_ratio") or 0.0)
    health_state["quote_pair_markets"] = quote_pair_markets
    health_state["total_markets"] = total_markets
    health_state["quote_coverage_ratio"] = round(quote_coverage_ratio, 6)
    health_state["direct_quote_markets"] = int(direct_quote_result.get("direct_quote_markets") or 0)
    health_state["direct_quote_tokens"] = int(direct_quote_result.get("direct_quote_tokens") or 0)
    book_errors = list(direct_quote_result.get("book_errors") or [])
    health_state["market_data"] = {
        "status": "healthy" if quote_coverage_ratio >= min_quote_coverage_ratio and not book_errors else "degraded",
        "reason": "ok" if quote_coverage_ratio >= min_quote_coverage_ratio and not book_errors else (
            "; ".join(book_errors[:3]) or f"quote_coverage_below_threshold:{quote_coverage_ratio:.3f}"
        ),
    }

    if dry_run or bot_config.get("execution_mode") != "live_small":
        health_state["execution_allowed"] = False
    else:
        health_state["execution_allowed"] = bool((health_state.get("execution_auth") or {}).get("allowed"))
        if bool((bot_config.get("health") or {}).get("require_execution_auth_for_live", True)) and not health_state["execution_allowed"]:
            health_state["execution_allowed"] = False

    active_positions = await get_open_clone_positions()
    active_market_ids = {str(position.get("market_id") or "") for position in active_positions}
    report = evaluate_clone_cycle(
        contexts=contexts,
        runtime=runtime,
        captured_at=captured_at,
        health_state=health_state,
        sequence_state=sequence_state,
        active_positions=active_positions,
        active_market_ids=active_market_ids,
    )

    entry_attempts = 0
    if report["candidates"]:
        for candidate in report["candidates"]:
            if candidate.get("playbook_key") != "paired_under_par":
                continue
            if not (candidate.get("qualifies") and candidate.get("live_eligible")):
                continue
            active_positions = await get_open_clone_positions()
            active_exposure = _clone_active_exposure_usd(active_positions)
            plan = plan_paired_entry(candidate, runtime, active_exposure_usd=active_exposure)
            if plan is None:
                continue
            entry_attempts += 1
            await _attempt_clone_paired_entry(
                clob,
                plan,
                shadow_only=not bool(health_state.get("execution_allowed")),
            )
            break

    active_positions = await get_open_clone_positions()
    summary = build_clone_cycle_summary(
        report=report,
        health_state=health_state,
        active_positions=active_positions,
        entry_attempts=entry_attempts,
    )
    cycle_id = await insert_clone_cycle(
        captured_at=captured_at,
        strategy_name=runtime.strategy_name,
        dry_run=dry_run,
        execution_allowed=bool(health_state.get("execution_allowed")),
        execution_health=str((health_state.get("execution_auth") or {}).get("status") or ""),
        market_data_health=str((health_state.get("market_data") or {}).get("status") or ""),
        quote_coverage_ratio=float(health_state.get("quote_coverage_ratio") or 0.0),
        context_count=int(report.get("context_count") or 0),
        market_count=int(report.get("market_count") or 0),
        candidate_count=int(report.get("candidate_count") or 0),
        sequence_count=len(report.get("sequence_snapshots") or []),
        entry_attempt_count=entry_attempts,
        top_rejection_reasons=report.get("top_rejection_reasons") or [],
        health_data=health_state,
        summary_data=summary,
    )
    await insert_clone_market_scans(cycle_id, report.get("cycle_rows") or [], captured_at=captured_at)
    await upsert_clone_sequences(report.get("sequence_snapshots") or [])
    await _emit_clone_cycle_telemetry(summary, report, telemetry)
    return {
        "summary": summary,
        "report": report,
        "health_state": health_state,
        "balance": balance,
    }


async def run_clone(*, config_path: str, dry_run: bool, once: bool) -> None:
    trading_config.patch_clob_client_proxy(PROXY_URL)
    await init_pool()
    await trading_db.create_trading_tables()
    await create_weather_tables()
    await create_weather_clone_tables()

    raw_config = _load_bot_config(config_path)
    bot_config = normalize_clone_bot_config(raw_config)
    clob = _build_clob_client()
    telemetry = WeatherCloneTelemetryState(
        summary_interval_seconds=float((bot_config.get("runtime") or {}).get("summary_interval_seconds") or config.DEFAULT_SUMMARY_INTERVAL_SECONDS),
        history_path=config.DEFAULT_CLONE_HISTORY_PATH,
    )
    sequence_state: dict[str, dict[str, Any]] = {}

    await trading_db.log_event(
        "weather_clone_start",
        f"[WEATHER-CLONE] Bot started | mode={'DRY RUN' if dry_run else 'LIVE'} | config={config_path}",
        {
            "dry_run": dry_run,
            "config_path": config_path,
            "loop_interval_seconds": float((bot_config.get('runtime') or {}).get("loop_interval_seconds") or config.DEFAULT_LOOP_INTERVAL_SECONDS),
            "summary_interval_seconds": float((bot_config.get('runtime') or {}).get("summary_interval_seconds") or config.DEFAULT_SUMMARY_INTERVAL_SECONDS),
            "history_path": str(config.DEFAULT_CLONE_HISTORY_PATH),
            "execution_mode": bot_config.get("execution_mode"),
        },
        echo=False,
    )
    log.info(
        "[WEATHER-CLONE] Bot started | mode=%s | config=%s",
        "DRY RUN" if dry_run else "LIVE",
        config_path,
    )

    while True:
        try:
            await _run_clone_cycle(
                clob,
                bot_config,
                dry_run=dry_run,
                telemetry=telemetry,
                sequence_state=sequence_state,
            )
        except Exception as exc:
            await trading_db.log_event(
                "weather_clone_error",
                f"[WEATHER-CLONE] Cycle failed: {type(exc).__name__}: {exc}",
                {"error": str(exc), "error_type": type(exc).__name__},
                echo=False,
            )
            log.warning("[WEATHER-CLONE] Cycle failed: %s: %s", type(exc).__name__, exc)
        if once:
            return
        loop_interval = float((bot_config.get("runtime") or {}).get("loop_interval_seconds") or config.DEFAULT_LOOP_INTERVAL_SECONDS)
        await asyncio.sleep(loop_interval)


async def run(*, config_path: str, dry_run: bool, once: bool, engine: str) -> None:
    raw_config = _load_bot_config(config_path)
    resolved_engine = _resolve_engine(requested=engine, raw_config=raw_config)
    if resolved_engine == "clone":
        await run_clone(config_path=config_path, dry_run=dry_run, once=once)
        return

    trading_config.patch_clob_client_proxy(PROXY_URL)
    await init_pool()
    await trading_db.create_trading_tables()
    await create_weather_tables()
    await weather_db.create_weather_merge_tables()

    bot_config = raw_config
    clob = _build_clob_client()
    telemetry = WeatherMergeTelemetryState(
        summary_interval_seconds=config.DEFAULT_SUMMARY_INTERVAL_SECONDS,
        history_path=config.DEFAULT_HISTORY_PATH,
    )

    if not dry_run:
        approval_state = await asyncio.to_thread(ensure_weather_allowances, auto_approve=config.AUTO_APPROVE)
        if not approval_state.ready:
            raise RuntimeError("Weather bot approvals are not ready")

    await _log_event(
        "weather_merge_start",
        f"[WEATHER-MERGE] Bot started | mode={'DRY RUN' if dry_run else 'LIVE'} | config={config_path}",
        {
            "dry_run": dry_run,
            "config_path": config_path,
            "loop_interval_seconds": config.DEFAULT_LOOP_INTERVAL_SECONDS,
            "summary_interval_seconds": config.DEFAULT_SUMMARY_INTERVAL_SECONDS,
            "history_path": str(config.DEFAULT_HISTORY_PATH),
        },
    )

    while True:
        try:
            report = await _run_cycle(clob, bot_config, dry_run=dry_run)
            await _emit_cycle_telemetry(report, telemetry)
        except Exception as exc:
            await _log_event(
                "weather_merge_error",
                f"[WEATHER-MERGE] Cycle failed: {type(exc).__name__}: {exc}",
                {"error": str(exc), "error_type": type(exc).__name__},
            )
        if once:
            return
        await asyncio.sleep(config.DEFAULT_LOOP_INTERVAL_SECONDS)


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for logger_name in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    try:
        asyncio.run(run(config_path=args.config_path, dry_run=args.dry_run, once=args.once, engine=args.engine))
    except KeyboardInterrupt:
        log.info("[TRADING-WEATHER] Stopped by operator")
    finally:
        try:
            asyncio.run(close_pool())
        except Exception:
            pass


if __name__ == "__main__":
    main()
