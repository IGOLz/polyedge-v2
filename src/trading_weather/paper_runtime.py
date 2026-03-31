"""Paper-trading runtime for the ColdMath weather clone bot."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from analysis.wallet_forensics.utils import safe_float
from shared.config import PROXY_URL
from shared.db import create_weather_tables, init_pool
from trading import config as trading_config
from trading import db as trading_db
from trading.utils import log
from trading_weather import config
from trading_weather import db as weather_db
from trading_weather.clone_config import PLAYBOOK_ORDER, PAIR_PLAYBOOK_KEYS, normalize_clone_bot_config, playbook_enabled
from trading_weather.clone_engine import (
    build_clone_cycle_summary,
    build_clone_runtime,
    clone_cycle_status_message,
    evaluate_clone_cycle,
    plan_directional_entry,
    plan_neg_risk_entry,
    plan_paired_entry,
    preflight_clone_health,
    refresh_contexts_with_direct_quotes,
)
from trading_weather.paper_db import (
    close_paper_position,
    create_weather_paper_tables,
    get_open_paper_positions,
    get_paper_daily_realized_pnl,
    get_paper_daily_spend_usd,
    get_paper_entry_activity,
    get_paper_run_totals,
    insert_paper_cycle,
    insert_paper_equity_snapshot,
    insert_paper_market_scans,
    insert_paper_position,
    insert_paper_position_event,
    update_paper_position_fill,
    update_paper_position_inventory,
    upsert_paper_sequences,
)
from weather.storage import fetch_active_weather_contexts


@dataclass(slots=True)
class WeatherPaperTelemetryState:
    summary_interval_seconds: float
    history_path: Path
    paper_run_id: str
    iteration: int = 0
    last_summary_at: datetime | None = None
    last_candidate_signature: str | None = None
    last_snapshot_at: datetime | None = None


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


def _json_safe_payload(payload: Any) -> Any:
    return json.loads(json.dumps(payload, default=str))


def _load_bot_config(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fingerprint_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:12]


def _code_fingerprint() -> str:
    digest = hashlib.sha1()
    for path in (
        Path(__file__),
        Path(__file__).with_name("config.py"),
        Path(__file__).with_name("clone_config.py"),
        Path(__file__).with_name("clone_engine.py"),
    ):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return None
    value = result.stdout.strip()
    return value or None


def _paper_run_id(config_fingerprint: str) -> str:
    return f"paper-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{config_fingerprint}-{uuid4().hex[:6]}"


def _paper_history_path(paper_run_id: str) -> Path:
    return config.DEFAULT_PAPER_HISTORY_PATH.parent / f"{paper_run_id}.jsonl"


def _clone_quote_snapshot_counts(contexts) -> dict[str, int]:
    total_markets = 0
    quote_pair_markets = 0
    for context in contexts:
        for market in context.markets:
            total_markets += 1
            if market.yes_ask is not None and market.no_ask is not None:
                quote_pair_markets += 1
    return {
        "quote_pair_markets": quote_pair_markets,
        "total_markets": total_markets,
    }


async def _refresh_clone_quotes_with_timeout(
    clob,
    contexts,
    *,
    captured_at: datetime,
    health_config: dict[str, Any],
) -> dict[str, Any]:
    baseline = {
        **_clone_quote_snapshot_counts(contexts),
        "direct_quote_markets": 0,
        "direct_quote_tokens": 0,
        "book_errors": [],
    }
    timeout_seconds = float(health_config.get("direct_quote_timeout_seconds") or 8.0)
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                refresh_contexts_with_direct_quotes,
                clob,
                contexts,
                captured_at=captured_at,
                health_config=health_config,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        return {
            **baseline,
            "book_errors": [f"TimeoutError: direct quote refresh exceeded {timeout_seconds:.1f}s"],
        }
    except Exception as exc:
        return {
            **baseline,
            "book_errors": [f"{type(exc).__name__}: {exc}"],
        }


def _runtime_float_setting(bot_config: dict[str, Any], key: str, default: float) -> float:
    runtime = bot_config.get("runtime") or {}
    value = runtime.get(key)
    if value is None or value == "":
        return float(default)
    return float(value)


def build_startup_telemetry(
    *,
    config_path: str,
    bot_config: dict[str, Any],
    paper_run_id: str,
    config_fingerprint: str,
    git_sha: str | None,
) -> dict[str, Any]:
    paper_config = bot_config.get("paper") or {}
    cap_settings = {
        "sequence_budget_usd": _runtime_float_setting(bot_config, "sequence_budget_usd", config.DEFAULT_SEQUENCE_BUDGET_USD),
        "max_total_exposure_usd": _runtime_float_setting(bot_config, "max_total_exposure_usd", config.DEFAULT_MAX_TOTAL_EXPOSURE_USD),
        "daily_loss_limit_usd": _runtime_float_setting(bot_config, "daily_loss_limit_usd", config.DEFAULT_DAILY_LOSS_LIMIT_USD),
        "daily_spend_limit_usd": _runtime_float_setting(bot_config, "daily_spend_limit_usd", config.DEFAULT_TOTAL_SPEND_LIMIT_USD),
        "loop_interval_seconds": _runtime_float_setting(bot_config, "loop_interval_seconds", config.DEFAULT_LOOP_INTERVAL_SECONDS),
        "summary_interval_seconds": _runtime_float_setting(bot_config, "summary_interval_seconds", config.DEFAULT_SUMMARY_INTERVAL_SECONDS),
        "fill_model": str(paper_config.get("fill_model") or "touch_realistic"),
        "snapshot_interval_seconds": float(paper_config.get("snapshot_interval_seconds") or config.DEFAULT_SUMMARY_INTERVAL_SECONDS),
    }
    return {
        "config_path": config_path,
        "paper_run_id": paper_run_id,
        "history_path": str(_paper_history_path(paper_run_id)),
        "strategy_name": str(bot_config.get("strategy_name") or "coldmath_weather_clone_v1"),
        "execution_mode": str(bot_config.get("execution_mode") or "paper_live"),
        "code_fingerprint": _code_fingerprint(),
        "config_fingerprint": config_fingerprint,
        "git_sha": git_sha,
        **cap_settings,
    }


def _paper_trade_event_payload(
    *,
    paper_run_id: str,
    position_id: int,
    plan: dict[str, Any] | None = None,
    position: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = plan or position or {}
    payload = {
        "engine": "weather_paper",
        "paper_run_id": paper_run_id,
        "weather_paper_position_id": position_id,
        "strategy_name": source.get("strategy_name"),
        "playbook_key": source.get("playbook_key"),
        "event_id": source.get("event_id"),
        "event_slug": source.get("event_slug"),
        "market_id": source.get("market_id"),
        "city": source.get("city"),
        "local_date": source.get("local_date"),
        "bucket_label": source.get("bucket_label"),
        "side": source.get("side"),
        "condition_id": source.get("condition_id"),
    }
    if plan is not None:
        payload["plan"] = _json_safe_payload(plan)
    if position is not None:
        payload["position"] = _json_safe_payload(position)
    if extra:
        payload.update(_json_safe_payload(extra))
    return payload


async def _record_paper_position_event(
    position_id: int,
    *,
    paper_run_id: str,
    strategy_name: str,
    playbook_key: str,
    config_fingerprint: str,
    git_sha: str | None,
    event_type: str,
    status: str | None = None,
    side: str | None = None,
    target_shares: float | None = None,
    filled_shares: float | None = None,
    price: float | None = None,
    value_usd: float | None = None,
    order_id: str | None = None,
    tx_hash: str | None = None,
    reason: str | None = None,
    notes: str | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> None:
    try:
        await insert_paper_position_event(
            position_id,
            paper_run_id=paper_run_id,
            strategy_name=strategy_name,
            playbook_key=playbook_key,
            config_fingerprint=config_fingerprint,
            git_sha=git_sha,
            event_type=event_type,
            status=status,
            side=side,
            target_shares=target_shares,
            filled_shares=filled_shares,
            price=price,
            value_usd=value_usd,
            order_id=order_id,
            tx_hash=tx_hash,
            reason=reason,
            notes=notes,
            raw_payload=raw_payload,
        )
    except Exception as exc:
        log.warning("Failed to write weather_paper_position_event: %s", exc)


def _paper_candidate_signature(report: dict[str, Any]) -> str | None:
    candidates = report.get("candidates") or []
    if not candidates:
        return None
    top = candidates[0]
    payload = {
        "playbook_key": top.get("playbook_key"),
        "market_id": top.get("market_id"),
        "side": top.get("side"),
        "candidate_score": round(float(top.get("candidate_score") or 0.0), 6),
        "combined_cost": round(float(top.get("combined_cost") or 0.0), 4),
        "directional_price": round(float(top.get("directional_price") or 0.0), 4),
    }
    return json.dumps(payload, sort_keys=True, default=str)


def _paper_persist_sort_key(row: dict[str, Any]) -> tuple[int, int, float]:
    playbook_key = str(row.get("playbook_key") or "")
    playbook_rank = PLAYBOOK_ORDER.index(playbook_key) if playbook_key in PLAYBOOK_ORDER else 999
    return (
        1 if bool(row.get("qualifies")) else 0,
        -playbook_rank,
        float(row.get("candidate_score") or 0.0),
    )


def _select_paper_persistence_rows(
    report: dict[str, Any],
    *,
    health_config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = list(report.get("cycle_rows") or [])
    max_market_rows = max(0, int(health_config.get("max_persisted_market_rows_per_cycle") or 0))
    max_sequences = max(0, int(health_config.get("max_persisted_sequences_per_cycle") or 0))
    persist_all_market_rows = bool(health_config.get("persist_all_market_rows", True))
    persist_all_scans = bool(health_config.get("persist_all_scans", True))

    ordered_rows = sorted(rows, key=_paper_persist_sort_key, reverse=True)
    if not persist_all_market_rows:
        ordered_rows = [row for row in ordered_rows if bool(row.get("qualifies"))][: max_market_rows or None]
    elif max_market_rows > 0:
        ordered_rows = ordered_rows[:max_market_rows]

    sequence_rows = [row.get("sequence_data") or {} for row in ordered_rows]
    if not persist_all_scans:
        sequence_rows = [row.get("sequence_data") or {} for row in ordered_rows if bool(row.get("qualifies"))]

    unique_sequences: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for row in sequence_rows:
        sequence_key = str(row.get("sequence_key") or "").strip()
        if not sequence_key or sequence_key in seen_keys:
            continue
        unique_sequences.append(row)
        seen_keys.add(sequence_key)
        if max_sequences > 0 and len(unique_sequences) >= max_sequences:
            break
    return ordered_rows, unique_sequences


def _paper_market_lookup(contexts) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for context in contexts:
        for market in context.markets:
            result[str(market.market_id)] = market
    return result


def _paper_quote_snapshot(market: Any) -> dict[str, Any]:
    return {
        "yes_bid": safe_float(getattr(market, "yes_bid", None)),
        "yes_ask": safe_float(getattr(market, "yes_ask", None)),
        "yes_mid": safe_float(getattr(market, "yes_mid", None)),
        "yes_bid_size": safe_float(getattr(market, "yes_bid_size", None)),
        "yes_ask_size": safe_float(getattr(market, "yes_ask_size", None)),
        "no_bid": safe_float(getattr(market, "no_bid", None)),
        "no_ask": safe_float(getattr(market, "no_ask", None)),
        "no_mid": safe_float(getattr(market, "no_mid", None)),
        "no_bid_size": safe_float(getattr(market, "no_bid_size", None)),
        "no_ask_size": safe_float(getattr(market, "no_ask_size", None)),
        "latest_quote_time": getattr(market, "latest_quote_time", None),
    }


def _paper_mark_price(market: Any, *, side: str) -> float:
    if side == "yes":
        bid = safe_float(getattr(market, "yes_bid", None))
        if bid is not None and bid >= 0:
            return bid
        mid = safe_float(getattr(market, "yes_mid", None))
        return mid or 0.0
    bid = safe_float(getattr(market, "no_bid", None))
    if bid is not None and bid >= 0:
        return bid
    mid = safe_float(getattr(market, "no_mid", None))
    return mid or 0.0


def _paper_fill_quote(plan: dict[str, Any], *, side: str) -> tuple[float | None, float | None]:
    normalized_side = str(side or "").strip().lower()
    if normalized_side in {"yes", "no"}:
        leg_price = safe_float(plan.get(f"{normalized_side}_price"))
        leg_size = safe_float(plan.get(f"{normalized_side}_ask_size"))
        if leg_price is not None or leg_size is not None:
            return leg_price, leg_size
        quote_snapshot = plan.get("quote_snapshot") or {}
        quote_price = safe_float(quote_snapshot.get(f"{normalized_side}_ask"))
        quote_size = safe_float(quote_snapshot.get(f"{normalized_side}_ask_size"))
        if quote_price is not None or quote_size is not None:
            return quote_price, quote_size
        plan_side = str(plan.get("side") or "").strip().lower()
        if not plan_side or plan_side == normalized_side:
            return safe_float(plan.get("price")), safe_float(plan.get("available_size"))
        return None, None
    return safe_float(plan.get("price")), safe_float(plan.get("available_size"))


def _paper_fill_shares(*, target_shares: int, available_size: float | None) -> int:
    if target_shares <= 0:
        return 0
    if available_size is None:
        return target_shares
    return max(0, min(target_shares, math.floor(available_size)))


def _paper_candidate_enabled(bot_config: dict[str, Any], playbook_key: str) -> bool:
    paper_config = bot_config.get("paper") or {}
    if bool(paper_config.get("execute_shadow_playbooks", False)):
        return playbook_enabled(bot_config, playbook_key, live=False) or playbook_enabled(bot_config, playbook_key, live=True)
    return playbook_enabled(bot_config, playbook_key, live=True)


def _paper_position_effective_cost_usd(position: dict[str, Any]) -> float:
    total_entry_cost = safe_float(position.get("total_entry_cost")) or 0.0
    return round(total_entry_cost, 6)


def _paper_active_exposure_usd(positions: list[dict[str, Any]]) -> float:
    exposure = 0.0
    for position in positions:
        if position.get("closed_at") is not None:
            continue
        exposure += _paper_position_effective_cost_usd(position)
    return round(exposure, 6)


def _clone_entry_condition_id(candidate: dict[str, Any], plan: dict[str, Any] | None = None) -> str:
    if plan is not None and str(plan.get("condition_id") or "").strip():
        return str(plan.get("condition_id") or "").strip()
    return str(candidate.get("condition_id") or candidate.get("market_id") or "").strip()


def _clone_runtime_cooldown_blocked(*, latest_opened_at: datetime | None, captured_at: datetime, cooldown_seconds: float) -> bool:
    if latest_opened_at is None or cooldown_seconds <= 0:
        return False
    latest = latest_opened_at.astimezone(UTC) if latest_opened_at.tzinfo else latest_opened_at.replace(tzinfo=UTC)
    return (captured_at - latest).total_seconds() < cooldown_seconds


def _clone_apply_runtime_size_controls(
    plan: dict[str, Any],
    *,
    runtime,
    repeat_count: int,
) -> dict[str, Any] | None:
    playbook_key = str(plan.get("playbook_key") or "")
    playbook = ((runtime.config.get("playbooks") or {}).get(playbook_key) or {})
    sequence_budget = safe_float(playbook.get("sequence_budget_usd")) or safe_float(plan.get("sequence_budget_usd")) or 0.0
    max_ask_fraction = safe_float(playbook.get("max_ask_size_fraction")) or 1.0
    reentry_scale = safe_float(playbook.get("reentry_scale")) or 1.0
    effective_budget = max(0.0, sequence_budget * (reentry_scale ** max(0, repeat_count)))
    adjusted = dict(plan)
    adjusted["sequence_budget_usd"] = round(sequence_budget, 6)
    if playbook_key in PAIR_PLAYBOOK_KEYS:
        yes_price = safe_float(plan.get("yes_price")) or 0.0
        no_price = safe_float(plan.get("no_price")) or 0.0
        yes_target = max(0, math.floor((safe_float(plan.get("yes_target_shares")) or 0.0) * (reentry_scale ** max(0, repeat_count))))
        no_target = max(0, math.floor((safe_float(plan.get("no_target_shares")) or 0.0) * (reentry_scale ** max(0, repeat_count))))
        yes_ask_size = safe_float(plan.get("yes_ask_size"))
        no_ask_size = safe_float(plan.get("no_ask_size"))
        if yes_ask_size is not None and yes_ask_size > 0:
            yes_target = min(yes_target, math.floor(yes_ask_size * max_ask_fraction))
        if no_ask_size is not None and no_ask_size > 0:
            no_target = min(no_target, math.floor(no_ask_size * max_ask_fraction))
        total_target_cost = (yes_target * yes_price) + (no_target * no_price)
        if effective_budget > 0 and total_target_cost > effective_budget:
            scale = effective_budget / max(total_target_cost, 1e-9)
            yes_target = math.floor(yes_target * scale)
            no_target = math.floor(no_target * scale)
            total_target_cost = (yes_target * yes_price) + (no_target * no_price)
        paired_target = min(yes_target, no_target)
        if paired_target <= 0 or total_target_cost <= 0:
            return None
        adjusted["yes_target_shares"] = yes_target
        adjusted["no_target_shares"] = no_target
        adjusted["target_shares"] = paired_target
        adjusted["total_target_cost"] = round(total_target_cost, 6)
        adjusted["expected_edge_usd"] = round(max(0.0, 1.0 - (safe_float(adjusted.get("combined_cost")) or 1.0)) * paired_target, 6)
        return adjusted
    if playbook_key == "neg_risk_basket":
        legs = list(plan.get("legs") or [])
        if not legs:
            return None
        per_leg_budget = effective_budget / max(len(legs), 1)
        adjusted_legs: list[dict[str, Any]] = []
        for leg in legs:
            price = safe_float(leg.get("price")) or 0.0
            available_size = safe_float(leg.get("available_size"))
            if price <= 0:
                continue
            target_shares = math.floor(per_leg_budget / price)
            if available_size is not None and available_size > 0:
                target_shares = min(target_shares, math.floor(available_size * max_ask_fraction))
            if target_shares <= 0:
                continue
            adjusted_legs.append({**leg, "target_shares": int(target_shares)})
        required = int(safe_float(plan.get("selected_condition_count")) or len(legs) or 0)
        if len(adjusted_legs) < max(1, required):
            return None
        adjusted["legs"] = adjusted_legs
        adjusted["selected_condition_count"] = len(adjusted_legs)
        adjusted["target_shares"] = int(sum(int(leg.get("target_shares") or 0) for leg in adjusted_legs))
        adjusted["combined_cost"] = round(sum((safe_float(leg.get("price")) or 0.0) for leg in adjusted_legs), 6)
        adjusted["total_target_cost"] = round(
            sum((safe_float(leg.get("price")) or 0.0) * int(leg.get("target_shares") or 0) for leg in adjusted_legs),
            6,
        )
        return adjusted if adjusted["target_shares"] > 0 else None
    target_shares = max(0, math.floor((safe_float(plan.get("target_shares")) or 0.0) * (reentry_scale ** max(0, repeat_count))))
    available_size = safe_float(plan.get("available_size"))
    price = safe_float(plan.get("price")) or 0.0
    if available_size is not None and available_size > 0:
        target_shares = min(target_shares, math.floor(available_size * max_ask_fraction))
    if effective_budget > 0 and price > 0:
        target_shares = min(target_shares, math.floor(effective_budget / price))
    if target_shares <= 0:
        return None
    adjusted["target_shares"] = int(target_shares)
    adjusted["expected_edge_usd"] = round(max(0.0, (safe_float(plan.get("profit_take_price")) or price) - price) * target_shares, 6)
    return adjusted


def _paper_fill_status(*, yes_shares: float, no_shares: float, target_shares: float) -> str:
    filled = yes_shares + no_shares
    if yes_shares > 0 and no_shares > 0:
        if yes_shares == no_shares:
            return "open_paired"
        return "open_partial_pair"
    if filled > 0:
        return "open_directional"
    return "entry_rejected"


def _paper_resolution_side(resolution: dict[str, Any] | None) -> str | None:
    outcome = str((resolution or {}).get("final_outcome") or "").strip().lower()
    if outcome in {"yes", "up", "true", "resolved_yes"}:
        return "yes"
    if outcome in {"no", "down", "false", "resolved_no"}:
        return "no"
    return None


def _paper_position_mark_value(position: dict[str, Any], market_lookup: dict[str, Any]) -> float:
    market = market_lookup.get(str(position.get("market_id") or ""))
    if market is None:
        return 0.0
    yes_shares = max(0.0, safe_float(position.get("yes_shares")) or 0.0)
    no_shares = max(0.0, safe_float(position.get("no_shares")) or 0.0)
    matched = min(yes_shares, no_shares)
    residual_yes = max(0.0, yes_shares - matched)
    residual_no = max(0.0, no_shares - matched)
    value = matched
    value += residual_yes * _paper_mark_price(market, side="yes")
    value += residual_no * _paper_mark_price(market, side="no")
    return round(value, 6)


def _paper_open_position_pnl(position: dict[str, Any], market_lookup: dict[str, Any]) -> float:
    realized_exit_value = safe_float(position.get("realized_exit_value_usd")) or 0.0
    entry_cost = safe_float(position.get("total_entry_cost")) or 0.0
    return round(realized_exit_value + _paper_position_mark_value(position, market_lookup) - entry_cost, 6)


def _paper_build_equity_snapshot(
    positions: list[dict[str, Any]],
    market_lookup: dict[str, Any],
    *,
    realized_pnl_usd: float,
    entry_notional_usd: float,
    exit_notional_usd: float,
) -> dict[str, Any]:
    unrealized = 0.0
    for position in positions:
        unrealized += _paper_open_position_pnl(position, market_lookup)
    unrealized = round(unrealized, 6)
    return {
        "realized_pnl_usd": round(realized_pnl_usd, 6),
        "unrealized_pnl_usd": unrealized,
        "equity_pnl_usd": round(realized_pnl_usd + unrealized, 6),
        "entry_notional_usd": round(entry_notional_usd, 6),
        "exit_notional_usd": round(exit_notional_usd, 6),
        "open_position_count": len(positions),
        "mark_method": "mergeable_par_at_1.0_and_residual_best_bid_else_mid",
    }


def _append_paper_cycle_history(*, history_path: Path, event_type: str, payload: dict[str, Any]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"event_type": event_type, **payload}
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


async def _emit_paper_cycle_telemetry(
    summary: dict[str, Any],
    report: dict[str, Any],
    telemetry: WeatherPaperTelemetryState,
) -> None:
    now = datetime.now(UTC)
    telemetry.iteration += 1
    signature = _paper_candidate_signature(report)
    if signature and signature != telemetry.last_candidate_signature:
        top = (report.get("candidates") or [None])[0] or {}
        message = (
            "[WEATHER-PAPER] Candidate | "
            f"{top.get('playbook_key')} {top.get('city')} {top.get('local_date')} {top.get('bucket_label')} "
            f"side={top.get('side') or 'paired'} "
            f"score={(safe_float(top.get('candidate_score')) or float('nan')):.4f}"
        )
        await trading_db.log_event("weather_paper_signal", message, _json_safe_payload(top), echo=False)
        log.info(message)
    if telemetry.last_summary_at is None or (now - telemetry.last_summary_at).total_seconds() >= telemetry.summary_interval_seconds:
        message = clone_cycle_status_message(summary).replace("[WEATHER-CLONE]", "[WEATHER-PAPER]")
        _append_paper_cycle_history(history_path=telemetry.history_path, event_type="summary", payload=summary)
        await trading_db.log_event("weather_paper_summary", message, _json_safe_payload(summary), echo=False)
        log.info(message)
        telemetry.last_summary_at = now
    telemetry.last_candidate_signature = signature


async def _paper_execute_directional_entry(
    plan: dict[str, Any],
    *,
    paper_run_id: str,
    config_fingerprint: str,
    git_sha: str | None,
) -> dict[str, float]:
    playbook_key = str(plan.get("playbook_key") or "")
    strategy_name = str(plan.get("strategy_name") or "")
    side = str(plan.get("side") or "")
    position_id = await insert_paper_position(
        paper_run_id=paper_run_id,
        strategy_name=strategy_name,
        playbook_key=playbook_key,
        market_id=str(plan.get("market_id") or ""),
        event_id=str(plan.get("event_id") or ""),
        event_slug=str(plan.get("event_slug") or ""),
        city=str(plan.get("city") or ""),
        local_date=plan.get("local_date"),
        bucket_label=str(plan.get("bucket_label") or ""),
        side=side,
        condition_id=str(plan.get("condition_id") or ""),
        neg_risk=bool(plan.get("neg_risk")),
        yes_token_id=plan.get("yes_token_id"),
        no_token_id=plan.get("no_token_id"),
        status="pending_entry",
        target_shares=float(plan.get("target_shares") or 0.0),
        signal_score=float(plan.get("signal_score") or 0.0),
        expected_edge_usd=safe_float(plan.get("expected_edge_usd")),
        config_fingerprint=config_fingerprint,
        git_sha=git_sha,
        quote_snapshot=plan.get("quote_snapshot") or {},
        signal_data=plan.get("signal_data") or {},
        sequence_data=plan.get("sequence_data") or {},
    )
    base_payload = _paper_trade_event_payload(paper_run_id=paper_run_id, position_id=position_id, plan=plan)
    target_shares = int(plan.get("target_shares") or 0)
    await _record_paper_position_event(
        position_id,
        paper_run_id=paper_run_id,
        strategy_name=strategy_name,
        playbook_key=playbook_key,
        config_fingerprint=config_fingerprint,
        git_sha=git_sha,
        event_type="entry_planned",
        status="pending_entry",
        side=side,
        target_shares=target_shares,
        raw_payload=base_payload,
    )
    price, available_size = _paper_fill_quote(plan, side=side)
    await _record_paper_position_event(
        position_id,
        paper_run_id=paper_run_id,
        strategy_name=strategy_name,
        playbook_key=playbook_key,
        config_fingerprint=config_fingerprint,
        git_sha=git_sha,
        event_type="order_intent",
        status="pending_entry",
        side=side,
        target_shares=target_shares,
        price=price,
        raw_payload=_paper_trade_event_payload(
            paper_run_id=paper_run_id,
            position_id=position_id,
            plan=plan,
            extra={"trade_type": "buy", "available_size": available_size},
        ),
    )
    if price is None or price <= 0 or available_size is None or available_size <= 0:
        await close_paper_position(position_id, status="entry_rejected", close_reason="missing_quote_liquidity", notes="Paper fill rejected due to missing top-of-book ask liquidity")
        await _record_paper_position_event(
            position_id,
            paper_run_id=paper_run_id,
            strategy_name=strategy_name,
            playbook_key=playbook_key,
            config_fingerprint=config_fingerprint,
            git_sha=git_sha,
            event_type="entry_rejected",
            status="entry_rejected",
            side=side,
            target_shares=target_shares,
            reason="missing_quote_liquidity",
            raw_payload=base_payload,
        )
        return {"fill_count": 0.0, "partial_fill_count": 0.0, "fill_notional_usd": 0.0}

    fill_shares = _paper_fill_shares(target_shares=target_shares, available_size=available_size)
    if fill_shares <= 0:
        await close_paper_position(position_id, status="entry_rejected", close_reason="top_of_book_exhausted", notes="Paper fill rejected because top-of-book size was zero")
        await _record_paper_position_event(
            position_id,
            paper_run_id=paper_run_id,
            strategy_name=strategy_name,
            playbook_key=playbook_key,
            config_fingerprint=config_fingerprint,
            git_sha=git_sha,
            event_type="entry_rejected",
            status="entry_rejected",
            side=side,
            target_shares=target_shares,
            reason="top_of_book_exhausted",
            raw_payload=base_payload,
        )
        return {"fill_count": 0.0, "partial_fill_count": 0.0, "fill_notional_usd": 0.0}

    total_cost = round(fill_shares * price, 6)
    yes_shares = float(fill_shares if side == "yes" else 0.0)
    no_shares = float(fill_shares if side == "no" else 0.0)
    status = "open_directional"
    await update_paper_position_fill(
        position_id,
        filled_shares=float(fill_shares),
        avg_entry_price=float(price),
        total_entry_cost=total_cost,
        yes_shares=yes_shares,
        no_shares=no_shares,
        status=status,
        notes="Paper directional position opened",
    )
    fill_event_type = "partial_fill" if fill_shares < target_shares else "order_fill"
    await _record_paper_position_event(
        position_id,
        paper_run_id=paper_run_id,
        strategy_name=strategy_name,
        playbook_key=playbook_key,
        config_fingerprint=config_fingerprint,
        git_sha=git_sha,
        event_type=fill_event_type,
        status=status,
        side=side,
        target_shares=target_shares,
        filled_shares=float(fill_shares),
        price=float(price),
        value_usd=total_cost,
        raw_payload=_paper_trade_event_payload(
            paper_run_id=paper_run_id,
            position_id=position_id,
            plan=plan,
            extra={"trade_type": "buy", "available_size": available_size},
        ),
    )
    await _record_paper_position_event(
        position_id,
        paper_run_id=paper_run_id,
        strategy_name=strategy_name,
        playbook_key=playbook_key,
        config_fingerprint=config_fingerprint,
        git_sha=git_sha,
        event_type="position_opened",
        status=status,
        side=side,
        filled_shares=float(fill_shares),
        price=float(price),
        value_usd=total_cost,
        raw_payload=base_payload,
    )
    return {
        "fill_count": 1.0,
        "partial_fill_count": 1.0 if fill_shares < target_shares else 0.0,
        "fill_notional_usd": total_cost,
    }


async def _paper_execute_pair_entry(
    plan: dict[str, Any],
    *,
    paper_run_id: str,
    config_fingerprint: str,
    git_sha: str | None,
) -> dict[str, float]:
    playbook_key = str(plan.get("playbook_key") or "")
    strategy_name = str(plan.get("strategy_name") or "")
    position_id = await insert_paper_position(
        paper_run_id=paper_run_id,
        strategy_name=strategy_name,
        playbook_key=playbook_key,
        market_id=str(plan.get("market_id") or ""),
        event_id=str(plan.get("event_id") or ""),
        event_slug=str(plan.get("event_slug") or ""),
        city=str(plan.get("city") or ""),
        local_date=plan.get("local_date"),
        bucket_label=str(plan.get("bucket_label") or ""),
        side=None,
        condition_id=str(plan.get("condition_id") or ""),
        neg_risk=bool(plan.get("neg_risk")),
        yes_token_id=plan.get("yes_token_id"),
        no_token_id=plan.get("no_token_id"),
        status="pending_entry",
        target_shares=float(plan.get("target_shares") or 0.0),
        signal_score=float(plan.get("signal_score") or 0.0),
        expected_edge_usd=safe_float(plan.get("expected_edge_usd")),
        config_fingerprint=config_fingerprint,
        git_sha=git_sha,
        quote_snapshot=plan.get("quote_snapshot") or {},
        signal_data=plan.get("signal_data") or {},
        sequence_data=plan.get("sequence_data") or {},
    )
    base_payload = _paper_trade_event_payload(paper_run_id=paper_run_id, position_id=position_id, plan=plan)
    yes_target = int(plan.get("yes_target_shares") or plan.get("target_shares") or 0)
    no_target = int(plan.get("no_target_shares") or plan.get("target_shares") or 0)
    await _record_paper_position_event(
        position_id,
        paper_run_id=paper_run_id,
        strategy_name=strategy_name,
        playbook_key=playbook_key,
        config_fingerprint=config_fingerprint,
        git_sha=git_sha,
        event_type="entry_planned",
        status="pending_entry",
        target_shares=float(plan.get("target_shares") or 0.0),
        raw_payload=base_payload,
    )
    fill_count = 0.0
    partial_fill_count = 0.0
    fill_notional_usd = 0.0
    fills: dict[str, tuple[int, float]] = {}
    for side, target in (("yes", yes_target), ("no", no_target)):
        price, available_size = _paper_fill_quote(plan, side=side)
        await _record_paper_position_event(
            position_id,
            paper_run_id=paper_run_id,
            strategy_name=strategy_name,
            playbook_key=playbook_key,
            config_fingerprint=config_fingerprint,
            git_sha=git_sha,
            event_type="order_intent",
            status="pending_entry",
            side=side,
            target_shares=target,
            price=price,
            raw_payload=_paper_trade_event_payload(
                paper_run_id=paper_run_id,
                position_id=position_id,
                plan=plan,
                extra={"trade_type": "buy", "available_size": available_size, "leg_side": side},
            ),
        )
        if price is None or price <= 0 or available_size is None or available_size <= 0:
            fills[side] = (0, 0.0)
            continue
        fill_shares = _paper_fill_shares(target_shares=target, available_size=available_size)
        fills[side] = (fill_shares, float(price))
        if fill_shares <= 0:
            continue
        notional = round(fill_shares * float(price), 6)
        fill_notional_usd += notional
        fill_count += 1.0
        if fill_shares < target:
            partial_fill_count += 1.0
        await _record_paper_position_event(
            position_id,
            paper_run_id=paper_run_id,
            strategy_name=strategy_name,
            playbook_key=playbook_key,
            config_fingerprint=config_fingerprint,
            git_sha=git_sha,
            event_type="partial_fill" if fill_shares < target else "order_fill",
            status="pending_entry",
            side=side,
            target_shares=target,
            filled_shares=float(fill_shares),
            price=float(price),
            value_usd=notional,
            raw_payload=_paper_trade_event_payload(
                paper_run_id=paper_run_id,
                position_id=position_id,
                plan=plan,
                extra={"trade_type": "buy", "available_size": available_size, "leg_side": side},
            ),
        )

    yes_fill, yes_price = fills.get("yes", (0, 0.0))
    no_fill, no_price = fills.get("no", (0, 0.0))
    if yes_fill <= 0 and no_fill <= 0:
        await close_paper_position(position_id, status="entry_rejected", close_reason="missing_quote_liquidity", notes="Paper pair fill rejected due to missing top-of-book ask liquidity")
        await _record_paper_position_event(
            position_id,
            paper_run_id=paper_run_id,
            strategy_name=strategy_name,
            playbook_key=playbook_key,
            config_fingerprint=config_fingerprint,
            git_sha=git_sha,
            event_type="entry_rejected",
            status="entry_rejected",
            reason="missing_quote_liquidity",
            raw_payload=base_payload,
        )
        return {"fill_count": 0.0, "partial_fill_count": 0.0, "fill_notional_usd": 0.0}

    total_cost = round((yes_fill * yes_price) + (no_fill * no_price), 6)
    paired_shares = min(yes_fill, no_fill)
    status = _paper_fill_status(yes_shares=float(yes_fill), no_shares=float(no_fill), target_shares=float(plan.get("target_shares") or 0.0))
    average_price = total_cost / max(yes_fill + no_fill, 1)
    await update_paper_position_fill(
        position_id,
        filled_shares=float(yes_fill + no_fill),
        avg_entry_price=average_price,
        total_entry_cost=total_cost,
        yes_shares=float(yes_fill),
        no_shares=float(no_fill),
        status=status,
        notes="Paper pair position opened",
    )
    await _record_paper_position_event(
        position_id,
        paper_run_id=paper_run_id,
        strategy_name=strategy_name,
        playbook_key=playbook_key,
        config_fingerprint=config_fingerprint,
        git_sha=git_sha,
        event_type="position_opened",
        status=status,
        target_shares=float(plan.get("target_shares") or 0.0),
        filled_shares=float(yes_fill + no_fill),
        value_usd=total_cost,
        raw_payload=_paper_trade_event_payload(
            paper_run_id=paper_run_id,
            position_id=position_id,
            plan=plan,
            extra={"paired_shares": paired_shares, "trade_type": "pair_entry"},
        ),
    )
    return {
        "fill_count": fill_count,
        "partial_fill_count": partial_fill_count,
        "fill_notional_usd": round(fill_notional_usd, 6),
    }


async def _paper_execute_neg_risk_entry(
    plan: dict[str, Any],
    *,
    paper_run_id: str,
    config_fingerprint: str,
    git_sha: str | None,
) -> dict[str, float]:
    total_fill_count = 0.0
    total_partial_count = 0.0
    total_notional = 0.0
    strategy_name = str(plan.get("strategy_name") or "")
    playbook_key = "neg_risk_basket"
    side = str(plan.get("side") or "")
    for leg in plan.get("legs") or []:
        leg_plan = {
            "playbook_key": playbook_key,
            "strategy_name": strategy_name,
            "market_id": str(leg.get("market_id") or ""),
            "event_id": str(plan.get("event_id") or ""),
            "event_slug": str(plan.get("event_slug") or ""),
            "city": str(plan.get("city") or ""),
            "local_date": plan.get("local_date"),
            "bucket_label": str(leg.get("bucket_label") or plan.get("bucket_label") or ""),
            "condition_id": str(leg.get("market_id") or ""),
            "neg_risk": True,
            "yes_token_id": str(leg.get("token_id") or "") if side == "yes" else None,
            "no_token_id": str(leg.get("token_id") or "") if side == "no" else None,
            "side": side,
            "price": safe_float(leg.get("price")) or 0.0,
            "available_size": safe_float(leg.get("available_size")),
            "target_shares": int(leg.get("target_shares") or 0),
            "expected_edge_usd": safe_float(plan.get("expected_edge_usd")),
            "signal_score": safe_float(plan.get("signal_score")) or 0.0,
            "quote_snapshot": plan.get("quote_snapshot") or {},
            "signal_data": {**(plan.get("signal_data") or {}), "selected_leg": leg},
            "sequence_data": plan.get("sequence_data") or {},
        }
        result = await _paper_execute_directional_entry(
            leg_plan,
            paper_run_id=paper_run_id,
            config_fingerprint=config_fingerprint,
            git_sha=git_sha,
        )
        total_fill_count += result["fill_count"]
        total_partial_count += result["partial_fill_count"]
        total_notional += result["fill_notional_usd"]
    return {
        "fill_count": round(total_fill_count, 6),
        "partial_fill_count": round(total_partial_count, 6),
        "fill_notional_usd": round(total_notional, 6),
    }


async def _reconcile_paper_positions(
    positions: list[dict[str, Any]],
    *,
    contexts,
    bot_config: dict[str, Any],
    paper_run_id: str,
    config_fingerprint: str,
    git_sha: str | None,
) -> None:
    market_lookup = _paper_market_lookup(contexts)
    for position in positions:
        position_id = int(position["id"])
        playbook_key = str(position.get("playbook_key") or "")
        strategy_name = str(position.get("strategy_name") or "")
        yes_shares = max(0.0, safe_float(position.get("yes_shares")) or 0.0)
        no_shares = max(0.0, safe_float(position.get("no_shares")) or 0.0)
        realized_exit = safe_float(position.get("realized_exit_value_usd")) or 0.0
        matched = min(yes_shares, no_shares)

        if matched > 0 and playbook_key in PAIR_PLAYBOOK_KEYS:
            remaining_yes = max(0.0, yes_shares - matched)
            remaining_no = max(0.0, no_shares - matched)
            new_realized = round(realized_exit + matched, 6)
            close_position = remaining_yes <= 0 and remaining_no <= 0
            status = "merged_closed" if close_position else "open_directional"
            await update_paper_position_inventory(
                position_id,
                yes_shares=remaining_yes,
                no_shares=remaining_no,
                filled_shares=remaining_yes + remaining_no,
                realized_exit_value_usd=new_realized,
                status=status,
                close_reason="merged" if close_position else None,
                notes="Paper auto-merged matched inventory",
                close_position=close_position,
            )
            await _record_paper_position_event(
                position_id,
                paper_run_id=paper_run_id,
                strategy_name=strategy_name,
                playbook_key=playbook_key,
                config_fingerprint=config_fingerprint,
                git_sha=git_sha,
                event_type="merge_fill",
                status=status,
                filled_shares=matched,
                value_usd=matched,
                reason="paper_auto_merge",
                notes="Paper auto-merged matched inventory",
                raw_payload=_paper_trade_event_payload(
                    paper_run_id=paper_run_id,
                    position_id=position_id,
                    position=position,
                    extra={"trade_type": "merge", "shares": matched},
                ),
            )
            if close_position:
                await _record_paper_position_event(
                    position_id,
                    paper_run_id=paper_run_id,
                    strategy_name=strategy_name,
                    playbook_key=playbook_key,
                    config_fingerprint=config_fingerprint,
                    git_sha=git_sha,
                    event_type="position_closed",
                    status="merged_closed",
                    reason="paper_auto_merge",
                    value_usd=new_realized,
                    raw_payload=_paper_trade_event_payload(
                        paper_run_id=paper_run_id,
                        position_id=position_id,
                        position={**position, "yes_shares": remaining_yes, "no_shares": remaining_no},
                        extra={"trade_type": "merge"},
                    ),
                )
                continue
            await _record_paper_position_event(
                position_id,
                paper_run_id=paper_run_id,
                strategy_name=strategy_name,
                playbook_key=playbook_key,
                config_fingerprint=config_fingerprint,
                git_sha=git_sha,
                event_type="position_reduced",
                status=status,
                filled_shares=remaining_yes + remaining_no,
                value_usd=new_realized,
                reason="paper_auto_merge",
                raw_payload=_paper_trade_event_payload(
                    paper_run_id=paper_run_id,
                    position_id=position_id,
                    position={**position, "yes_shares": remaining_yes, "no_shares": remaining_no},
                    extra={"trade_type": "merge"},
                ),
            )
            position = {**position, "yes_shares": remaining_yes, "no_shares": remaining_no, "realized_exit_value_usd": new_realized}
            yes_shares = remaining_yes
            no_shares = remaining_no

        resolution = await weather_db.get_market_resolution(str(position.get("market_id") or ""))
        winner = _paper_resolution_side(resolution)
        if winner:
            payout = yes_shares if winner == "yes" else no_shares
            new_realized = round((safe_float(position.get("realized_exit_value_usd")) or 0.0) + payout, 6)
            await close_paper_position(
                position_id,
                status="redeemed_closed",
                close_reason="redeemed",
                realized_exit_value_usd=new_realized,
                notes="Paper resolution redemption",
            )
            await _record_paper_position_event(
                position_id,
                paper_run_id=paper_run_id,
                strategy_name=strategy_name,
                playbook_key=playbook_key,
                config_fingerprint=config_fingerprint,
                git_sha=git_sha,
                event_type="redeem_fill",
                status="redeemed_closed",
                side=winner,
                filled_shares=payout,
                value_usd=payout,
                reason="resolved_market",
                raw_payload=_paper_trade_event_payload(
                    paper_run_id=paper_run_id,
                    position_id=position_id,
                    position=position,
                    extra={"trade_type": "redeem", "winner": winner},
                ),
            )
            await _record_paper_position_event(
                position_id,
                paper_run_id=paper_run_id,
                strategy_name=strategy_name,
                playbook_key=playbook_key,
                config_fingerprint=config_fingerprint,
                git_sha=git_sha,
                event_type="position_closed",
                status="redeemed_closed",
                side=winner,
                value_usd=new_realized,
                reason="resolved_market",
                raw_payload=_paper_trade_event_payload(
                    paper_run_id=paper_run_id,
                    position_id=position_id,
                    position=position,
                    extra={"trade_type": "redeem", "winner": winner},
                ),
            )
            continue

        playbook = ((bot_config.get("playbooks") or {}).get(playbook_key) or {})
        profit_take_price = safe_float(playbook.get("profit_take_price"))
        if profit_take_price is None or profit_take_price <= 0:
            continue
        market = market_lookup.get(str(position.get("market_id") or ""))
        if market is None:
            continue
        side = "yes" if yes_shares > no_shares else "no"
        remaining_shares = yes_shares if side == "yes" else no_shares
        if remaining_shares <= 0:
            continue
        bid_price = _paper_mark_price(market, side=side)
        if bid_price < profit_take_price:
            continue
        proceeds = round(remaining_shares * bid_price, 6)
        new_realized = round((safe_float(position.get("realized_exit_value_usd")) or 0.0) + proceeds, 6)
        await close_paper_position(
            position_id,
            status="closed_profit_take",
            close_reason="profit_take",
            realized_exit_value_usd=new_realized,
            notes=f"Paper directional exit at {bid_price:.4f}",
        )
        await _record_paper_position_event(
            position_id,
            paper_run_id=paper_run_id,
            strategy_name=strategy_name,
            playbook_key=playbook_key,
            config_fingerprint=config_fingerprint,
            git_sha=git_sha,
            event_type="exit_fill",
            status="closed_profit_take",
            side=side,
            filled_shares=remaining_shares,
            price=bid_price,
            value_usd=proceeds,
            reason="profit_take",
            raw_payload=_paper_trade_event_payload(
                paper_run_id=paper_run_id,
                position_id=position_id,
                position=position,
                extra={"trade_type": "sell", "profit_take_price": profit_take_price},
            ),
        )
        await _record_paper_position_event(
            position_id,
            paper_run_id=paper_run_id,
            strategy_name=strategy_name,
            playbook_key=playbook_key,
            config_fingerprint=config_fingerprint,
            git_sha=git_sha,
            event_type="position_closed",
            status="closed_profit_take",
            side=side,
            value_usd=new_realized,
            reason="profit_take",
            raw_payload=_paper_trade_event_payload(
                paper_run_id=paper_run_id,
                position_id=position_id,
                position=position,
                extra={"trade_type": "sell"},
            ),
        )


async def _persist_paper_cycle_state(
    *,
    captured_at: datetime,
    strategy_name: str,
    paper_run_id: str,
    config_fingerprint: str,
    git_sha: str | None,
    bot_config: dict[str, Any],
    health_state: dict[str, Any],
    summary: dict[str, Any],
    report: dict[str, Any],
    equity_snapshot: dict[str, Any],
) -> None:
    persist_timeout = float((bot_config.get("health") or {}).get("persist_timeout_seconds") or 5.0)
    persisted_rows, persisted_sequences = _select_paper_persistence_rows(report, health_config=bot_config.get("health") or {})
    cycle_id: int | None = None
    try:
        cycle_id = await asyncio.wait_for(
            insert_paper_cycle(
                paper_run_id=paper_run_id,
                strategy_name=strategy_name,
                config_fingerprint=config_fingerprint,
                git_sha=git_sha,
                fill_model=str((bot_config.get("paper") or {}).get("fill_model") or "touch_realistic"),
                execution_mode=str(bot_config.get("execution_mode") or "paper_live"),
                captured_at=captured_at,
                execution_allowed=bool(health_state.get("execution_allowed")),
                execution_health=str((health_state.get("execution_auth") or {}).get("status") or ""),
                market_data_health=str((health_state.get("market_data") or {}).get("status") or ""),
                quote_coverage_ratio=float(health_state.get("quote_coverage_ratio") or 0.0),
                context_count=int(report.get("context_count") or 0),
                market_count=int(report.get("market_count") or 0),
                candidate_count=int(report.get("candidate_count") or 0),
                sequence_count=len(persisted_sequences),
                entry_attempt_count=int(summary.get("entry_attempts") or 0),
                fill_count=int(summary.get("fill_count") or 0),
                partial_fill_count=int(summary.get("partial_fill_count") or 0),
                fill_notional_usd=float(summary.get("fill_notional_usd") or 0.0),
                realized_pnl_usd=float(equity_snapshot.get("realized_pnl_usd") or 0.0),
                unrealized_pnl_usd=float(equity_snapshot.get("unrealized_pnl_usd") or 0.0),
                equity_pnl_usd=float(equity_snapshot.get("equity_pnl_usd") or 0.0),
                top_rejection_reasons=report.get("top_rejection_reasons") or [],
                health_data=health_state,
                summary_data=summary,
            ),
            timeout=persist_timeout,
        )
    except Exception as exc:
        log.warning("[WEATHER-PAPER] Failed to persist cycle summary: %s: %s", type(exc).__name__, exc)

    if cycle_id is not None and persisted_rows:
        try:
            await asyncio.wait_for(
                insert_paper_market_scans(
                    cycle_id,
                    persisted_rows,
                    paper_run_id=paper_run_id,
                    strategy_name=strategy_name,
                    config_fingerprint=config_fingerprint,
                    git_sha=git_sha,
                    captured_at=captured_at,
                ),
                timeout=persist_timeout,
            )
        except Exception as exc:
            log.warning("[WEATHER-PAPER] Failed to persist market scans: %s: %s", type(exc).__name__, exc)

    if persisted_sequences:
        try:
            await asyncio.wait_for(
                upsert_paper_sequences(
                    persisted_sequences,
                    paper_run_id=paper_run_id,
                    strategy_name=strategy_name,
                    config_fingerprint=config_fingerprint,
                    git_sha=git_sha,
                ),
                timeout=persist_timeout,
            )
        except Exception as exc:
            log.warning("[WEATHER-PAPER] Failed to persist sequence state: %s: %s", type(exc).__name__, exc)

    try:
        await asyncio.wait_for(
            insert_paper_equity_snapshot(
                paper_run_id=paper_run_id,
                strategy_name=strategy_name,
                config_fingerprint=config_fingerprint,
                git_sha=git_sha,
                captured_at=captured_at,
                realized_pnl_usd=float(equity_snapshot.get("realized_pnl_usd") or 0.0),
                unrealized_pnl_usd=float(equity_snapshot.get("unrealized_pnl_usd") or 0.0),
                equity_pnl_usd=float(equity_snapshot.get("equity_pnl_usd") or 0.0),
                entry_notional_usd=float(equity_snapshot.get("entry_notional_usd") or 0.0),
                exit_notional_usd=float(equity_snapshot.get("exit_notional_usd") or 0.0),
                open_position_count=int(equity_snapshot.get("open_position_count") or 0),
                mark_method=str(equity_snapshot.get("mark_method") or "touch_realistic"),
            ),
            timeout=persist_timeout,
        )
    except Exception as exc:
        log.warning("[WEATHER-PAPER] Failed to persist equity snapshot: %s: %s", type(exc).__name__, exc)


async def _run_clone_paper_cycle(
    clob,
    bot_config: dict[str, Any],
    *,
    paper_run_id: str,
    config_fingerprint: str,
    git_sha: str | None,
    telemetry: WeatherPaperTelemetryState,
    sequence_state: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    captured_at = datetime.now(UTC)
    runtime = build_clone_runtime(bot_config, dry_run=False)
    health_state = preflight_clone_health(clob, dry_run=True)
    health_state["execution_auth"] = {
        "status": "paper_live",
        "reason": "paper_trading_mode",
        "allowed": False,
    }
    health_state["execution_allowed"] = False

    contexts = await fetch_active_weather_contexts(eligible_only=True)
    direct_quote_result = await _refresh_clone_quotes_with_timeout(
        clob,
        contexts,
        captured_at=captured_at,
        health_config=bot_config.get("health") or {},
    )
    total_markets = int(direct_quote_result.get("total_markets") or 0)
    quote_pair_markets = int(direct_quote_result.get("quote_pair_markets") or 0)
    quote_coverage_ratio = (quote_pair_markets / total_markets) if total_markets > 0 else 0.0
    min_quote_coverage_ratio = float((bot_config.get("health") or {}).get("min_quote_coverage_ratio") or 0.0)
    book_errors = list(direct_quote_result.get("book_errors") or [])
    health_state["quote_pair_markets"] = quote_pair_markets
    health_state["total_markets"] = total_markets
    health_state["quote_coverage_ratio"] = round(quote_coverage_ratio, 6)
    health_state["direct_quote_markets"] = int(direct_quote_result.get("direct_quote_markets") or 0)
    health_state["direct_quote_tokens"] = int(direct_quote_result.get("direct_quote_tokens") or 0)
    health_state["market_data"] = {
        "status": "healthy" if quote_coverage_ratio >= min_quote_coverage_ratio and not book_errors else "degraded",
        "reason": "ok" if quote_coverage_ratio >= min_quote_coverage_ratio and not book_errors else (
            "; ".join(book_errors[:3]) or f"quote_coverage_below_threshold:{quote_coverage_ratio:.3f}"
        ),
    }

    await _reconcile_paper_positions(
        await get_open_paper_positions(paper_run_id=paper_run_id),
        contexts=contexts,
        bot_config=bot_config,
        paper_run_id=paper_run_id,
        config_fingerprint=config_fingerprint,
        git_sha=git_sha,
    )
    active_positions = await get_open_paper_positions(paper_run_id=paper_run_id)
    active_exposure = _paper_active_exposure_usd(active_positions)
    total_spent_usd = await get_paper_daily_spend_usd(paper_run_id=paper_run_id)
    daily_realized_pnl = await get_paper_daily_realized_pnl(paper_run_id=paper_run_id)
    daily_loss = max(0.0, -daily_realized_pnl)
    runtime_limits = runtime.runtime or {}
    daily_loss_limit_usd = float(runtime_limits.get("daily_loss_limit_usd") or config.DEFAULT_DAILY_LOSS_LIMIT_USD)
    daily_spend_limit_usd = float(runtime_limits.get("daily_spend_limit_usd") or config.DEFAULT_TOTAL_SPEND_LIMIT_USD)
    max_total_exposure_usd = float(runtime_limits.get("max_total_exposure_usd") or config.DEFAULT_MAX_TOTAL_EXPOSURE_USD)
    stand_down_reason: str | None = None
    if daily_loss_limit_usd > 0 and daily_loss >= daily_loss_limit_usd:
        stand_down_reason = "daily_loss_limit_reached"
    elif daily_spend_limit_usd > 0 and total_spent_usd >= daily_spend_limit_usd:
        stand_down_reason = "total_spend_limit_reached"
    elif active_exposure >= max_total_exposure_usd > 0:
        stand_down_reason = "capacity_reached"

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
    fill_count = 0.0
    partial_fill_count = 0.0
    fill_notional_usd = 0.0
    max_entry_attempts = int(runtime.runtime.get("max_entry_attempts") or config.DEFAULT_MAX_ENTRY_ATTEMPTS or 1)
    if stand_down_reason is None and report.get("candidates"):
        for candidate in report["candidates"]:
            playbook_key = str(candidate.get("playbook_key") or "")
            if not bool(candidate.get("qualifies")) or not _paper_candidate_enabled(bot_config, playbook_key):
                continue
            if max_entry_attempts > 0 and entry_attempts >= max_entry_attempts:
                break
            active_positions = await get_open_paper_positions(paper_run_id=paper_run_id)
            active_exposure = _paper_active_exposure_usd(active_positions)
            total_spent_usd = await get_paper_daily_spend_usd(paper_run_id=paper_run_id)
            if daily_spend_limit_usd > 0 and total_spent_usd >= daily_spend_limit_usd:
                stand_down_reason = "total_spend_limit_reached"
                break
            candidate_side = str(candidate.get("side") or "paired")
            entry_activity = await get_paper_entry_activity(
                paper_run_id=paper_run_id,
                condition_id=_clone_entry_condition_id(candidate),
                playbook_key=playbook_key,
                side=candidate_side,
            )
            if _clone_runtime_cooldown_blocked(
                latest_opened_at=entry_activity.get("latest_opened_at"),
                captured_at=captured_at,
                cooldown_seconds=float(runtime.runtime.get("repeat_entry_cooldown_seconds") or 0.0),
            ):
                continue
            if playbook_key in PAIR_PLAYBOOK_KEYS:
                plan = plan_paired_entry(candidate, runtime, active_exposure_usd=active_exposure)
            elif playbook_key == "neg_risk_basket":
                plan = plan_neg_risk_entry(candidate, runtime, active_exposure_usd=active_exposure)
            else:
                plan = plan_directional_entry(candidate, runtime, active_exposure_usd=active_exposure)
            if plan is None:
                continue
            plan = _clone_apply_runtime_size_controls(plan, runtime=runtime, repeat_count=int(entry_activity.get("entry_count") or 0))
            if plan is None:
                continue
            entry_attempts += 1
            if playbook_key in PAIR_PLAYBOOK_KEYS:
                result = await _paper_execute_pair_entry(plan, paper_run_id=paper_run_id, config_fingerprint=config_fingerprint, git_sha=git_sha)
            elif playbook_key == "neg_risk_basket":
                result = await _paper_execute_neg_risk_entry(plan, paper_run_id=paper_run_id, config_fingerprint=config_fingerprint, git_sha=git_sha)
            else:
                result = await _paper_execute_directional_entry(plan, paper_run_id=paper_run_id, config_fingerprint=config_fingerprint, git_sha=git_sha)
            fill_count += result["fill_count"]
            partial_fill_count += result["partial_fill_count"]
            fill_notional_usd += result["fill_notional_usd"]

    active_positions = await get_open_paper_positions(paper_run_id=paper_run_id)
    market_lookup = _paper_market_lookup(contexts)
    total_spent_usd = await get_paper_daily_spend_usd(paper_run_id=paper_run_id)
    daily_realized_pnl = await get_paper_daily_realized_pnl(paper_run_id=paper_run_id)
    daily_loss = max(0.0, -daily_realized_pnl)
    active_exposure = _paper_active_exposure_usd(active_positions)
    run_totals = await get_paper_run_totals(paper_run_id=paper_run_id)
    equity_snapshot = _paper_build_equity_snapshot(
        active_positions,
        market_lookup,
        realized_pnl_usd=daily_realized_pnl,
        entry_notional_usd=float(run_totals.get("entry_notional_usd") or 0.0),
        exit_notional_usd=float(run_totals.get("exit_notional_usd") or 0.0),
    )
    for position in active_positions:
        mark_value = _paper_position_mark_value(position, market_lookup)
        await _record_paper_position_event(
            int(position["id"]),
            paper_run_id=paper_run_id,
            strategy_name=str(position.get("strategy_name") or runtime.strategy_name),
            playbook_key=str(position.get("playbook_key") or ""),
            config_fingerprint=config_fingerprint,
            git_sha=git_sha,
            event_type="mark_snapshot",
            status=str(position.get("status") or ""),
            side=str(position.get("side") or None) if position.get("side") is not None else None,
            filled_shares=float(position.get("filled_shares") or 0.0),
            value_usd=mark_value,
            raw_payload=_paper_trade_event_payload(
                paper_run_id=paper_run_id,
                position_id=int(position["id"]),
                position=position,
                extra={"trade_type": "mark", "mark_value_usd": mark_value},
            ),
        )
    summary = build_clone_cycle_summary(
        report=report,
        health_state=health_state,
        active_positions=active_positions,
        entry_attempts=entry_attempts,
    )
    summary.update(
        {
            "stand_down_reason": stand_down_reason,
            "daily_realized_pnl": round(daily_realized_pnl, 6),
            "daily_loss": round(daily_loss, 6),
            "daily_loss_limit_usd": round(daily_loss_limit_usd, 6),
            "total_spent_usd": round(total_spent_usd, 6),
            "total_spend_limit_usd": round(daily_spend_limit_usd, 6),
            "active_exposure_usd": round(active_exposure, 6),
            "fill_count": round(fill_count, 6),
            "partial_fill_count": round(partial_fill_count, 6),
            "fill_notional_usd": round(fill_notional_usd, 6),
            "paper_run_id": paper_run_id,
            "execution_mode": str(bot_config.get("execution_mode") or "paper_live"),
            "fill_model": str((bot_config.get("paper") or {}).get("fill_model") or "touch_realistic"),
            "equity_snapshot": equity_snapshot,
        }
    )
    await _persist_paper_cycle_state(
        captured_at=captured_at,
        strategy_name=runtime.strategy_name,
        paper_run_id=paper_run_id,
        config_fingerprint=config_fingerprint,
        git_sha=git_sha,
        bot_config=bot_config,
        health_state=health_state,
        summary=summary,
        report=report,
        equity_snapshot=equity_snapshot,
    )
    await _emit_paper_cycle_telemetry(summary, report, telemetry)
    return {"summary": summary, "report": report, "equity_snapshot": equity_snapshot}


async def run_clone_paper(*, config_path: str, dry_run: bool, once: bool) -> None:
    trading_config.patch_clob_client_proxy(PROXY_URL)
    await init_pool()
    await trading_db.create_trading_tables()
    await create_weather_tables()
    await create_weather_paper_tables()

    raw_config = _load_bot_config(config_path)
    bot_config = normalize_clone_bot_config(raw_config)
    config_fingerprint = _fingerprint_payload(bot_config)
    git_sha = _git_sha()
    paper_run_id = _paper_run_id(config_fingerprint)
    startup = build_startup_telemetry(
        config_path=config_path,
        bot_config=bot_config,
        paper_run_id=paper_run_id,
        config_fingerprint=config_fingerprint,
        git_sha=git_sha,
    )
    telemetry = WeatherPaperTelemetryState(
        summary_interval_seconds=float((bot_config.get("runtime") or {}).get("summary_interval_seconds") or config.DEFAULT_SUMMARY_INTERVAL_SECONDS),
        history_path=_paper_history_path(paper_run_id),
        paper_run_id=paper_run_id,
    )
    clob = _build_clob_client()
    sequence_state: dict[str, dict[str, Any]] = {}

    await trading_db.log_event(
        "weather_paper_start",
        (
            "[WEATHER-PAPER] Bot started | "
            f"mode=PAPER "
            f"config={config_path} "
            f"run={paper_run_id} "
            f"cfg={config_fingerprint} "
            f"fill_model={startup['fill_model']} "
            f"loop={startup['loop_interval_seconds']:.0f}s "
            f"caps={startup['sequence_budget_usd']:.2f}/{startup['max_total_exposure_usd']:.2f}/{startup['daily_loss_limit_usd']:.2f} "
            f"spend_cap={startup['daily_spend_limit_usd']:.2f} "
            "real_orders_sent=false"
        ),
        {
            **startup,
            "dry_run_flag": dry_run,
            "real_orders_sent": False,
            "paper_mode": True,
        },
        echo=False,
    )
    log.info("[WEATHER-PAPER] Bot started | run=%s | config=%s", paper_run_id, config_path)

    while True:
        try:
            await _run_clone_paper_cycle(
                clob,
                bot_config,
                paper_run_id=paper_run_id,
                config_fingerprint=config_fingerprint,
                git_sha=git_sha,
                telemetry=telemetry,
                sequence_state=sequence_state,
            )
        except Exception as exc:
            await trading_db.log_event(
                "weather_paper_error",
                f"[WEATHER-PAPER] Cycle failed: {type(exc).__name__}: {exc}",
                {"error": str(exc), "error_type": type(exc).__name__},
                echo=False,
            )
            log.warning("[WEATHER-PAPER] Cycle failed: %s: %s", type(exc).__name__, exc)
        if once:
            return
        loop_interval = float((bot_config.get("runtime") or {}).get("loop_interval_seconds") or config.DEFAULT_LOOP_INTERVAL_SECONDS)
        await asyncio.sleep(loop_interval)
