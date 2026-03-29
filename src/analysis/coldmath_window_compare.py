"""Compare a live weather-bot window against ColdMath's public weather activity."""

from __future__ import annotations

import argparse
import csv
import logging
import re
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from analysis.db_sync import get_connection
from analysis.wallet_forensics.db import load_rows
from analysis.wallet_forensics.decoder import decode_receipt_for_wallet
from analysis.wallet_forensics.fetchers import WalletForensicsClient, normalize_event_context
from analysis.wallet_forensics.ledger import build_wallet_ledger
from analysis.wallet_forensics.report import export_artifacts
from analysis.wallet_forensics.utils import ensure_dir, parse_iso_datetime, safe_float, utc_now
from analysis.wallet_forensics.weather_enrichment import enrich_ledger_with_weather

logger = logging.getLogger(__name__)

DEFAULT_PROFILE = "ColdMath"
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
DEFAULT_LOG_PATH = REPO_ROOT / "logs" / "trading-weather" / "trading.log"
DEFAULT_OUTPUT_DIR = SRC_ROOT / "results" / "wallet_forensics" / "coldmath_window_compare"

START_LINE_FRAGMENT = "[WEATHER-MERGE] Bot started | mode=LIVE"
HEARTBEAT_FRAGMENTS = ("[WEATHER-MERGE] Cycle OK", "[WEATHER-MERGE] Summary")
WEATHER_FRAGMENT = "[WEATHER-MERGE]"
RECEIPT_RPC_BATCH_SIZE = 100

BRACKET_LOG_RE = re.compile(
    r"^\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+\w+\s+(?P<message>.*)$"
)
ISO_PREFIX_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}T\S+)\s+(?P<message>.*)$")
CANDIDATE_COUNT_RE = re.compile(r"candidates=(?P<count>\d+)")
WEATHER_EVENT_RE = re.compile(
    r"^highest-temperature-in-(?P<city>[a-z0-9-]+)-on-(?P<month>[a-z]+)-(?P<day>\d{1,2})-(?P<year>\d{4})$"
)
WEATHER_TITLE_RE = re.compile(
    r"Will the highest temperature in (?P<city>.+?) be (?P<bucket>.+?) on (?P<month>[A-Za-z]+) (?P<day>\d{1,2})(?:,)?(?: (?P<year>\d{4}))?\?",
    re.IGNORECASE,
)
MONTH_NUMBER = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


@dataclass(slots=True)
class ParsedLogLine:
    timestamp_utc: datetime
    message: str
    raw_line: str
    source_path: str
    line_number: int
    raw_timestamp: str
    timestamp_source: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare a 24-hour weather bot window with ColdMath trades")
    identity_group = parser.add_mutually_exclusive_group()
    identity_group.add_argument("--profile", type=str, default=DEFAULT_PROFILE, help="Polymarket profile to compare")
    identity_group.add_argument("--wallet", type=str, help="Explicit proxy wallet to compare instead of a profile")
    parser.add_argument("--log-path", type=str, default=str(DEFAULT_LOG_PATH), help="Path to trading-weather trading.log")
    parser.add_argument(
        "--fallback-log-path",
        type=str,
        default=None,
        help="Optional fallback log path, such as docker compose logs output, used if the start line is missing",
    )
    parser.add_argument(
        "--lxc-date-is",
        type=str,
        default=None,
        help="Exact output from `date -Is` on the LXC, used to interpret naive log timestamps",
    )
    parser.add_argument(
        "--log-timezone",
        type=str,
        default=None,
        help="Fallback timezone for naive log timestamps, for example UTC, Europe/Rome, or +01:00",
    )
    parser.add_argument(
        "--window-start-utc",
        type=str,
        default=None,
        help="Explicit UTC window start ISO timestamp. Use with --window-end-utc to bypass log-based window detection.",
    )
    parser.add_argument(
        "--window-end-utc",
        type=str,
        default=None,
        help="Explicit UTC window end ISO timestamp. Use with --window-start-utc to bypass log-based window detection.",
    )
    parser.add_argument("--window-hours", type=float, default=24.0, help="Comparison window size in hours")
    parser.add_argument(
        "--heartbeat-gap-seconds",
        type=float,
        default=180.0,
        help="Gap threshold used to flag downtime in the bot log",
    )
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR), help="Artifact output directory")
    parser.add_argument("--verbose", action="store_true", help="Enable info logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for logger_name in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    result = run_window_comparison(args)
    logger.info(
        "ColdMath window comparison complete for %s with %d weather trades",
        result["wallet_target"]["proxy_wallet"],
        result["coldmath"]["trade_count"],
    )
    return 0


def run_window_comparison(args: argparse.Namespace | list[str] | None = None) -> dict[str, Any]:
    if not isinstance(args, argparse.Namespace):
        args = build_parser().parse_args(args)

    log_tz, tz_label, tz_source = _resolve_log_timezone(args)
    log_entries = _load_log_entries(
        log_paths=[
            Path(args.log_path).resolve(),
            Path(args.fallback_log_path).resolve() if args.fallback_log_path else None,
        ],
        default_tz=log_tz,
    )
    window = _determine_window(
        log_entries=log_entries,
        window_hours=float(args.window_hours),
        explicit_window_start_utc=args.window_start_utc,
        explicit_window_end_utc=args.window_end_utc,
    )
    if window["window_end_utc"] > utc_now():
        raise RuntimeError(
            "The requested comparison window ends in the future relative to the current machine clock"
        )
    uptime = _analyze_uptime(
        log_entries=log_entries,
        window_start_utc=window["window_start_utc"],
        window_end_utc=window["window_end_utc"],
        gap_threshold_seconds=float(args.heartbeat_gap_seconds),
    )

    conn = get_connection()
    try:
        bot_activity = _load_bot_activity(
            conn=conn,
            window_start_utc=window["window_start_utc"],
            window_end_utc=window["window_end_utc"],
        )
    finally:
        conn.close()

    output_dir = ensure_dir(Path(args.output_dir).resolve())
    wallet_result = _run_exact_window_wallet_slice(
        args=args,
        window_start_utc=window["window_start_utc"],
        window_end_utc=window["window_end_utc"],
        output_dir=output_dir,
    )

    coldmath = _load_coldmath_trade_summary(
        ledger_rows=wallet_result["ledger_rows"],
        heartbeat_rows=uptime["heartbeat_rows"],
        heartbeat_gap_seconds=float(args.heartbeat_gap_seconds),
    )

    report_path = output_dir / "coldmath_window_compare_report.md"
    trades_csv_path = output_dir / "coldmath_window_compare_trades.csv"
    _write_trade_csv(trades_csv_path, coldmath["trade_rows"])
    report_path.write_text(
        _build_markdown_report(
            wallet_result=wallet_result,
            window=window,
            tz_label=tz_label,
            tz_source=tz_source,
            uptime=uptime,
            bot_activity=bot_activity,
            coldmath=coldmath,
        ),
        encoding="utf-8",
    )

    return {
        "window": window,
        "timezone_label": tz_label,
        "timezone_source": tz_source,
        "uptime": uptime,
        "bot_activity": bot_activity,
        "wallet_target": wallet_result["target"],
        "wallet_result": wallet_result,
        "coldmath": coldmath,
        "report_path": str(report_path),
        "trades_csv_path": str(trades_csv_path),
    }


def _resolve_log_timezone(args: argparse.Namespace) -> tuple[tzinfo, str, str]:
    if args.lxc_date_is:
        lxc_now = _parse_iso_timestamp(args.lxc_date_is)
        if lxc_now.tzinfo is None:
            raise RuntimeError("--lxc-date-is must include a timezone offset")
        offset = lxc_now.utcoffset()
        if offset is None:
            raise RuntimeError("--lxc-date-is did not expose a usable timezone offset")
        resolved = timezone(offset)
        return resolved, _format_offset(offset), "lxc-date-is"

    if args.log_timezone:
        resolved = _parse_timezone_spec(str(args.log_timezone))
        if isinstance(resolved, timezone):
            offset = datetime.now(resolved).utcoffset() or timedelta(0)
            return resolved, _format_offset(offset), "log-timezone"
        try:
            offset = datetime.now(resolved).utcoffset() or timedelta(0)
        except Exception:
            offset = timedelta(0)
        return resolved, getattr(resolved, "key", str(args.log_timezone)), "log-timezone"

    return UTC, "UTC", "default_assumption"


def _parse_timezone_spec(value: str) -> tzinfo:
    text = str(value or "").strip()
    if not text:
        return UTC
    upper = text.upper()
    if upper in {"UTC", "Z"}:
        return UTC
    if re.fullmatch(r"[+-]\d{2}:\d{2}", text):
        sign = 1 if text[0] == "+" else -1
        hours = int(text[1:3])
        minutes = int(text[4:6])
        return timezone(sign * timedelta(hours=hours, minutes=minutes))
    try:
        return ZoneInfo(text)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Unsupported timezone value: {value!r}") from exc


def _parse_iso_timestamp(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise RuntimeError("Timestamp value is empty")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    match = re.match(r"^(?P<head>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?P<fraction>\.\d+)?(?P<tail>([+-]\d{2}:\d{2})?)$", text)
    if match and match.group("fraction") and len(match.group("fraction")) > 7:
        text = f"{match.group('head')}{match.group('fraction')[:7]}{match.group('tail')}"
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise RuntimeError(f"Could not parse ISO timestamp {value!r}") from exc


def _format_offset(offset: timedelta) -> str:
    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"{sign}{hours:02d}:{minutes:02d}"


def _load_log_entries(*, log_paths: list[Path | None], default_tz: tzinfo) -> list[ParsedLogLine]:
    parsed: list[ParsedLogLine] = []
    for path in log_paths:
        if path is None or not path.exists():
            continue
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            event = _parse_log_line(
                raw_line=raw_line,
                source_path=str(path),
                line_number=line_number,
                default_tz=default_tz,
            )
            if event is not None:
                parsed.append(event)
    parsed.sort(key=lambda item: (item.timestamp_utc, item.source_path, item.line_number))
    return parsed


def _parse_log_line(
    *,
    raw_line: str,
    source_path: str,
    line_number: int,
    default_tz: tzinfo,
) -> ParsedLogLine | None:
    normalized_line = _normalize_log_line(raw_line)

    bracket_match = BRACKET_LOG_RE.match(normalized_line)
    if bracket_match:
        naive = datetime.strptime(bracket_match.group("ts"), "%Y-%m-%d %H:%M:%S")
        local_dt = naive.replace(tzinfo=default_tz)
        return ParsedLogLine(
            timestamp_utc=local_dt.astimezone(UTC),
            message=bracket_match.group("message").strip(),
            raw_line=normalized_line,
            source_path=source_path,
            line_number=line_number,
            raw_timestamp=bracket_match.group("ts"),
            timestamp_source="naive_log",
        )

    iso_match = ISO_PREFIX_RE.match(normalized_line)
    if iso_match:
        parsed_ts = _parse_iso_timestamp(iso_match.group("ts"))
        if parsed_ts.tzinfo is None:
            parsed_ts = parsed_ts.replace(tzinfo=default_tz)
        return ParsedLogLine(
            timestamp_utc=parsed_ts.astimezone(UTC),
            message=iso_match.group("message").strip(),
            raw_line=normalized_line,
            source_path=source_path,
            line_number=line_number,
            raw_timestamp=iso_match.group("ts"),
            timestamp_source="explicit_log",
        )

    return None


def _normalize_log_line(raw_line: str) -> str:
    text = str(raw_line or "").strip()
    if not text:
        return text
    if BRACKET_LOG_RE.match(text) or ISO_PREFIX_RE.match(text):
        return text
    bracket_start = text.find("[20")
    if bracket_start > 0:
        candidate = text[bracket_start:]
        if BRACKET_LOG_RE.match(candidate):
            return candidate
    return text


def _determine_window(
    *,
    log_entries: list[ParsedLogLine],
    window_hours: float,
    explicit_window_start_utc: str | None = None,
    explicit_window_end_utc: str | None = None,
) -> dict[str, Any]:
    if bool(explicit_window_start_utc) != bool(explicit_window_end_utc):
        raise RuntimeError("Both --window-start-utc and --window-end-utc must be provided together")
    if explicit_window_start_utc and explicit_window_end_utc:
        window_start = _parse_iso_timestamp(str(explicit_window_start_utc).strip()).astimezone(UTC)
        window_end = _parse_iso_timestamp(str(explicit_window_end_utc).strip()).astimezone(UTC)
        if window_end <= window_start:
            raise RuntimeError("Explicit window end must be after the explicit window start")
        return {
            "window_start_utc": window_start,
            "window_end_utc": window_end,
            "start_source_path": "explicit_args",
            "start_source_line": None,
            "start_source_timestamp": explicit_window_start_utc,
            "start_source_message": "explicit window override",
        }

    live_start = next((item for item in log_entries if START_LINE_FRAGMENT in item.message), None)
    if live_start is None:
        raise RuntimeError("Could not find a live bot start line in the provided log files")
    window_start = live_start.timestamp_utc
    window_end = window_start + timedelta(hours=float(window_hours))
    return {
        "window_start_utc": window_start,
        "window_end_utc": window_end,
        "start_source_path": live_start.source_path,
        "start_source_line": live_start.line_number,
        "start_source_timestamp": live_start.raw_timestamp,
        "start_source_message": live_start.message,
    }


def _analyze_uptime(
    *,
    log_entries: list[ParsedLogLine],
    window_start_utc: datetime,
    window_end_utc: datetime,
    gap_threshold_seconds: float,
) -> dict[str, Any]:
    weather_rows = [
        item
        for item in log_entries
        if window_start_utc <= item.timestamp_utc <= window_end_utc and WEATHER_FRAGMENT in item.message
    ]
    heartbeat_rows = []
    for item in weather_rows:
        if any(fragment in item.message for fragment in HEARTBEAT_FRAGMENTS):
            heartbeat_rows.append(
                {
                    "timestamp_utc": item.timestamp_utc,
                    "message": item.message,
                    "candidate_count": _extract_candidate_count(item.message),
                    "source_path": item.source_path,
                    "line_number": item.line_number,
                }
            )
    start_rows = [item for item in weather_rows if START_LINE_FRAGMENT in item.message]
    restart_rows = [item for item in start_rows if item.timestamp_utc > window_start_utc]

    checkpoints = [window_start_utc, *[row["timestamp_utc"] for row in heartbeat_rows], window_end_utc]
    gaps: list[dict[str, Any]] = []
    for left, right in zip(checkpoints, checkpoints[1:]):
        gap_seconds = (right - left).total_seconds()
        if gap_seconds > float(gap_threshold_seconds):
            gaps.append(
                {
                    "gap_start_utc": left,
                    "gap_end_utc": right,
                    "gap_seconds": round(gap_seconds, 3),
                    "gap_minutes": round(gap_seconds / 60.0, 3),
                }
            )

    last_log_at = weather_rows[-1].timestamp_utc if weather_rows else None
    max_gap_seconds = max((item["gap_seconds"] for item in gaps), default=0.0)
    return {
        "weather_log_count": len(weather_rows),
        "heartbeat_count": len(heartbeat_rows),
        "restart_count": len(restart_rows),
        "restart_rows": restart_rows,
        "gaps": gaps,
        "gap_count": len(gaps),
        "max_gap_seconds": round(max_gap_seconds, 3),
        "last_weather_log_at": last_log_at,
        "heartbeat_rows": heartbeat_rows,
    }


def _extract_candidate_count(message: str) -> int | None:
    match = CANDIDATE_COUNT_RE.search(message or "")
    if not match:
        return None
    return int(match.group("count"))


def _load_bot_activity(
    *,
    conn,
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> dict[str, Any]:
    bot_logs = load_rows(
        conn,
        """
        SELECT logged_at, log_type, message, data
        FROM bot_logs
        WHERE logged_at BETWEEN %s AND %s
          AND log_type LIKE 'weather_merge%%'
        ORDER BY logged_at ASC
        """,
        (window_start_utc, window_end_utc),
    )
    position_rows = load_rows(
        conn,
        """
        SELECT
            id,
            status,
            opened_at,
            closed_at,
            last_checked_at,
            last_merged_at,
            city,
            local_date,
            bucket_label,
            total_entry_cost,
            merged_collateral_usdc,
            redeemed_collateral_usdc,
            unwind_collateral_usdc
        FROM weather_merge_positions
        WHERE opened_at BETWEEN %s AND %s
        ORDER BY opened_at ASC
        """,
        (window_start_utc, window_end_utc),
    )
    live_positions = [row for row in position_rows if str(row.get("status") or "").strip().lower() != "dry_run"]
    log_type_counts: dict[str, int] = {}
    for row in bot_logs:
        key = str(row.get("log_type") or "")
        log_type_counts[key] = log_type_counts.get(key, 0) + 1

    return {
        "bot_log_count": len(bot_logs),
        "bot_log_type_counts": log_type_counts,
        "position_rows": live_positions,
        "live_trade_count": len(live_positions),
        "entry_log_count": log_type_counts.get("weather_merge_entry", 0),
        "merge_position_count": sum(1 for row in live_positions if (safe_float(row.get("merged_collateral_usdc")) or 0.0) > 0),
        "redeem_position_count": sum(1 for row in live_positions if (safe_float(row.get("redeemed_collateral_usdc")) or 0.0) > 0),
        "unwind_position_count": sum(1 for row in live_positions if (safe_float(row.get("unwind_collateral_usdc")) or 0.0) > 0),
    }


def _run_exact_window_wallet_slice(
    *,
    args: argparse.Namespace,
    window_start_utc: datetime,
    window_end_utc: datetime,
    output_dir: Path,
) -> dict[str, Any]:
    client = WalletForensicsClient()
    conn = get_connection()
    try:
        target = _resolve_wallet_target(client, args)
        proxy_wallet = target["proxy_wallet"]
        start_ts = int(window_start_utc.timestamp())
        end_ts = int(window_end_utc.timestamp())

        logger.info(
            "Fetching exact-window ColdMath slice for %s between %s and %s",
            proxy_wallet,
            window_start_utc.isoformat(),
            window_end_utc.isoformat(),
        )
        activity_rows = client.fetch_activity(proxy_wallet, start_ts=start_ts, end_ts=end_ts)
        trade_rows = [
            row
            for row in activity_rows
            if str(row.get("type") or row.get("event_type") or "").strip().upper() == "TRADE"
        ]
        market_context_rows = _load_market_context_rows(client, activity_rows=activity_rows, trade_rows=trade_rows)
        receipt_rows = _load_receipt_rows(client, proxy_wallet=proxy_wallet, activity_rows=activity_rows, trade_rows=trade_rows)
        market_context = _market_context_by_condition(market_context_rows)
        receipt_map = _receipt_map(receipt_rows)
        ledger_rows, _position_snapshots = build_wallet_ledger(
            proxy_wallet=proxy_wallet,
            activity_rows=activity_rows,
            receipt_rows=receipt_map,
            market_context=market_context,
            closed_positions_rows=[],
            snapshot_mode="final",
        )
        weather_inputs = _load_weather_inputs(
            conn,
            condition_ids={str(row.get("condition_id") or "") for row in ledger_rows if row.get("condition_id")},
        )
        enriched_rows = enrich_ledger_with_weather(
            ledger_rows=ledger_rows,
            market_context=market_context,
            weather_market_rows=weather_inputs["weather_market_rows"],
            forecast_rows_by_market=weather_inputs["forecast_rows_by_market"],
            observations_by_station=weather_inputs["observations_by_station"],
        )
        weather_ledger = [row for row in enriched_rows if row.get("is_weather")]
        export_artifacts(
            output_dir=output_dir,
            ledger_rows=weather_ledger,
            inferred_rules=[],
            shadow_rows=[],
            playbook_sequences=[],
            strategy_blueprints=[],
            rule_summary=None,
            export_parquet=False,
        )
        return {
            "target": target,
            "completeness": {
                "trade_count": len(trade_rows),
                "activity_count": len(activity_rows),
                "receipt_count": len(receipt_rows),
                "market_context_count": len(market_context_rows),
                "ledger_event_count": len(weather_ledger),
                "backfill_complete": True,
            },
            "ledger_rows": weather_ledger,
            "raw_trade_rows": trade_rows,
            "raw_activity_rows": activity_rows,
            "output_dir": str(output_dir),
            "report_path": None,
        }
    finally:
        client.close()
        conn.close()


def _resolve_wallet_target(client: WalletForensicsClient, args: argparse.Namespace) -> dict[str, Any]:
    search_result: dict[str, Any] | None = None
    if args.wallet:
        wallet = str(args.wallet).strip().lower()
        if not wallet:
            raise RuntimeError("Wallet address is required")
    else:
        search_result = client.resolve_wallet(str(args.profile))
        wallet = _extract_wallet(search_result)
        if not wallet:
            raise RuntimeError(f"Could not resolve a proxy wallet for profile {args.profile!r}")

    profile_payload: dict[str, Any] = {}
    try:
        profile_payload = client.fetch_public_profile(wallet)
    except Exception:
        logger.warning("Public profile lookup failed for %s; continuing with limited metadata", wallet)

    return {
        "proxy_wallet": wallet,
        "profile_name": profile_payload.get("name") or (search_result or {}).get("name") or args.profile,
        "pseudonym": profile_payload.get("pseudonym"),
        "bio": profile_payload.get("bio"),
        "display_username_public": profile_payload.get("displayUsernamePublic"),
        "source_profile_json": {
            "search_result": search_result,
            "public_profile": profile_payload,
        },
    }


def _extract_wallet(payload: dict[str, Any]) -> str | None:
    for key in ("proxyWallet", "proxy_wallet", "walletAddress", "wallet", "address"):
        value = payload.get(key)
        if value:
            return str(value).strip().lower()
    return None


def _load_market_context_rows(
    client: WalletForensicsClient,
    *,
    activity_rows: list[dict[str, Any]],
    trade_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    event_slugs = sorted(
        {
            str(row.get("eventSlug") or row.get("event_slug") or "").strip()
            for row in [*activity_rows, *trade_rows]
            if str(row.get("eventSlug") or row.get("event_slug") or "").strip()
        }
    )
    for event_slug in event_slugs:
        event_payload = client.fetch_event_by_slug(event_slug)
        if not event_payload:
            continue
        for row in normalize_event_context(event_payload):
            market_id = str(row.get("market_id") or "").strip()
            if market_id:
                rows[market_id] = row
    return list(rows.values())


def _load_receipt_rows(
    client: WalletForensicsClient,
    *,
    proxy_wallet: str,
    activity_rows: list[dict[str, Any]],
    trade_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    activity_types_by_tx: dict[str, set[str]] = defaultdict(set)
    tx_hashes: set[str] = set()
    for row in activity_rows:
        tx_hash = str(row.get("transactionHash") or row.get("transaction_hash") or "").strip()
        if not tx_hash:
            continue
        tx_hashes.add(tx_hash)
        event_type = str(row.get("type") or row.get("event_type") or "").strip()
        if event_type:
            activity_types_by_tx[tx_hash].add(event_type)
    for row in trade_rows:
        tx_hash = str(row.get("transactionHash") or row.get("transaction_hash") or "").strip()
        if tx_hash:
            tx_hashes.add(tx_hash)

    ordered_hashes = sorted(tx_hashes)
    receipt_rows: list[dict[str, Any]] = []
    for batch_start in range(0, len(ordered_hashes), RECEIPT_RPC_BATCH_SIZE):
        batch = ordered_hashes[batch_start: batch_start + RECEIPT_RPC_BATCH_SIZE]
        payloads = client.fetch_transaction_receipts(batch)
        for tx_hash in batch:
            summary = decode_receipt_for_wallet(
                payloads.get(tx_hash),
                proxy_wallet,
                activity_types=sorted(activity_types_by_tx.get(tx_hash, ())),
            )
            if not summary.get("transaction_hash"):
                summary["transaction_hash"] = tx_hash
            receipt_rows.append(
                {
                    "transaction_hash": summary.get("transaction_hash"),
                    "block_number": summary.get("block_number"),
                    "block_timestamp": summary.get("block_timestamp"),
                    "classifications_json": summary.get("classifications") or [],
                    "touched_contracts_json": summary.get("touched_contracts") or [],
                    "usdc_in": summary.get("usdc_in"),
                    "usdc_out": summary.get("usdc_out"),
                    "payload_json": summary.get("payload_json") or {},
                }
            )
    return receipt_rows


def _receipt_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        tx_hash = str(row.get("transaction_hash") or "").strip()
        if not tx_hash:
            continue
        result[tx_hash] = {
            "transaction_hash": tx_hash,
            "block_number": row.get("block_number"),
            "block_timestamp": row.get("block_timestamp"),
            "classifications": row.get("classifications_json") or [],
            "touched_contracts": row.get("touched_contracts_json") or [],
            "usdc_in": row.get("usdc_in"),
            "usdc_out": row.get("usdc_out"),
        }
    return result


def _market_context_by_condition(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        market_id = str(row.get("market_id") or "").strip()
        if not market_id:
            continue
        result[market_id] = {
            "market_id": market_id,
            "event_id": row.get("event_id"),
            "event_slug": row.get("event_slug"),
            "gamma_market_id": row.get("gamma_market_id"),
            "market_slug": row.get("market_slug"),
            "question": row.get("question"),
            "title": row.get("title"),
            "category": row.get("category"),
            "end_date": row.get("end_date"),
            "active": row.get("active"),
            "closed": row.get("closed"),
            "neg_risk": row.get("neg_risk"),
            "resolution_source_url": row.get("resolution_source_url"),
            "yes_token_id": row.get("yes_token_id"),
            "no_token_id": row.get("no_token_id"),
            "yes_price": row.get("yes_price"),
            "no_price": row.get("no_price"),
            "outcomes": row.get("outcomes") or [],
            "outcome_prices": row.get("outcome_prices") or [],
            "sibling_market_ids": row.get("sibling_market_ids") or [],
            "payload_json": row.get("payload_json") or {},
        }
    return result


def _load_weather_inputs(conn, *, condition_ids: set[str]) -> dict[str, Any]:
    if not condition_ids:
        return {
            "weather_market_rows": {},
            "forecast_rows_by_market": {},
            "observations_by_station": {},
        }

    market_rows = load_rows(
        conn,
        """
        SELECT
            market_id,
            city,
            station_code,
            timezone,
            local_date,
            bucket_label,
            bucket_low,
            bucket_high,
            resolution_precision_scale
        FROM weather_market_catalog
        WHERE market_id = ANY(%s)
        """,
        (list(condition_ids),),
    )
    weather_market_rows = {str(row["market_id"]): row for row in market_rows}
    if not weather_market_rows:
        return {
            "weather_market_rows": {},
            "forecast_rows_by_market": {},
            "observations_by_station": {},
        }

    market_ids = list(weather_market_rows)
    forecast_rows = load_rows(
        conn,
        """
        SELECT
            market_id,
            captured_at,
            provider,
            model,
            run_at,
            forecast_for,
            temp_max,
            temp_hourly,
            cloud,
            wind,
            dewpoint,
            precip_prob,
            payload_json
        FROM weather_forecast_snapshots
        WHERE market_id = ANY(%s)
        ORDER BY market_id ASC, run_at ASC, captured_at ASC
        """,
        (market_ids,),
    )
    forecast_rows_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in forecast_rows:
        forecast_rows_by_market[str(row["market_id"])].append(row)

    station_codes = sorted(
        {
            str(row.get("station_code") or "").strip()
            for row in market_rows
            if str(row.get("station_code") or "").strip()
        }
    )
    observation_rows: list[dict[str, Any]] = []
    if station_codes:
        observation_rows = load_rows(
            conn,
            """
            SELECT
                station_code,
                observed_at,
                temperature,
                dewpoint,
                wind_speed,
                wind_direction,
                wind_gust,
                cloud,
                visibility,
                payload_json
            FROM weather_observations
            WHERE station_code = ANY(%s)
            ORDER BY station_code ASC, observed_at ASC
            """,
            (station_codes,),
        )
    observations_by_station: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in observation_rows:
        observations_by_station[str(row["station_code"])].append(row)

    return {
        "weather_market_rows": weather_market_rows,
        "forecast_rows_by_market": dict(forecast_rows_by_market),
        "observations_by_station": dict(observations_by_station),
    }


def _load_coldmath_trade_summary(
    *,
    ledger_rows: list[dict[str, Any]],
    heartbeat_rows: list[dict[str, Any]],
    heartbeat_gap_seconds: float,
) -> dict[str, Any]:
    trade_rows: list[dict[str, Any]] = []
    for row in ledger_rows:
        if str(row.get("event_type") or "").strip().lower() != "trade":
            continue
        occurred_at = row.get("occurred_at")
        if isinstance(occurred_at, str):
            occurred_at = parse_iso_datetime(occurred_at)
        if occurred_at is None:
            continue
        derived_meta = _derive_weather_trade_metadata(row)
        trade_rows.append(
            {
                "timestamp_utc": occurred_at,
                "timestamp_local": str(row.get("weather_local_time") or ""),
                "event_slug": str(row.get("event_slug") or ""),
                "city": derived_meta["city"],
                "local_date": derived_meta["local_date"],
                "bucket_label": derived_meta["bucket_label"],
                "side": str(row.get("side") or ""),
                "outcome": _clean_text(row.get("outcome")),
                "size": safe_float(row.get("size")) or 0.0,
                "price": safe_float(row.get("price")),
                "transaction_hash": str(row.get("transaction_hash") or ""),
                "condition_id": str(row.get("condition_id") or ""),
                "bot_candidates_last_seen": None,
                "bot_heartbeat_age_seconds": None,
            }
        )

    heartbeat_times = [row["timestamp_utc"] for row in heartbeat_rows]
    candidate_zero_count = 0
    candidate_nonzero_count = 0
    candidate_unknown_count = 0
    for row in trade_rows:
        index = bisect_right(heartbeat_times, row["timestamp_utc"]) - 1
        if index < 0:
            candidate_unknown_count += 1
            continue
        heartbeat = heartbeat_rows[index]
        age_seconds = (row["timestamp_utc"] - heartbeat["timestamp_utc"]).total_seconds()
        if age_seconds > float(heartbeat_gap_seconds):
            candidate_unknown_count += 1
            continue
        candidate_count = heartbeat.get("candidate_count")
        row["bot_candidates_last_seen"] = candidate_count
        row["bot_heartbeat_age_seconds"] = round(age_seconds, 3)
        if candidate_count == 0:
            candidate_zero_count += 1
        elif candidate_count is None:
            candidate_unknown_count += 1
        else:
            candidate_nonzero_count += 1

    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in trade_rows:
        key = (
            row["event_slug"],
            row["condition_id"],
            row["city"],
            row["local_date"],
            row["bucket_label"],
        )
        group = grouped.setdefault(
            key,
            {
                "event_slug": row["event_slug"],
                "condition_id": row["condition_id"],
                "city": row["city"],
                "local_date": row["local_date"],
                "bucket_label": row["bucket_label"],
                "trade_count": 0,
                "buy_count": 0,
                "sell_count": 0,
                "total_size": 0.0,
                "first_trade_utc": row["timestamp_utc"],
                "last_trade_utc": row["timestamp_utc"],
            },
        )
        group["trade_count"] += 1
        if row["side"].lower() == "buy":
            group["buy_count"] += 1
        elif row["side"].lower() == "sell":
            group["sell_count"] += 1
        group["total_size"] = round(group["total_size"] + row["size"], 6)
        if row["timestamp_utc"] < group["first_trade_utc"]:
            group["first_trade_utc"] = row["timestamp_utc"]
        if row["timestamp_utc"] > group["last_trade_utc"]:
            group["last_trade_utc"] = row["timestamp_utc"]

    grouped_rows = sorted(
        grouped.values(),
        key=lambda item: (item["first_trade_utc"], item["event_slug"], item["bucket_label"]),
    )

    return {
        "ledger_rows": ledger_rows,
        "trade_rows": sorted(trade_rows, key=lambda item: item["timestamp_utc"]),
        "trade_count": len(trade_rows),
        "distinct_condition_count": len({row["condition_id"] for row in trade_rows if row["condition_id"]}),
        "distinct_event_count": len({row["event_slug"] for row in trade_rows if row["event_slug"]}),
        "earliest_trade_utc": trade_rows[0]["timestamp_utc"] if trade_rows else None,
        "latest_trade_utc": trade_rows[-1]["timestamp_utc"] if trade_rows else None,
        "grouped_rows": grouped_rows,
        "candidate_zero_trade_count": candidate_zero_count,
        "candidate_nonzero_trade_count": candidate_nonzero_count,
        "candidate_unknown_trade_count": candidate_unknown_count,
    }


def _derive_weather_trade_metadata(row: dict[str, Any]) -> dict[str, str]:
    payload = row.get("payload_json") or {}
    raw_activity = payload.get("raw_activity") or {}
    title = _clean_text(raw_activity.get("title") or row.get("title") or "")
    event_slug = str(row.get("event_slug") or raw_activity.get("eventSlug") or "").strip()

    city = _clean_text(row.get("weather_city") or row.get("city") or "")
    local_date = _clean_text(row.get("weather_local_date") or "")
    bucket_label = _clean_text(row.get("weather_bucket_label") or "")

    if title:
        title_match = WEATHER_TITLE_RE.search(title)
        if title_match:
            if not city:
                city = _clean_text(title_match.group("city"))
            if not bucket_label:
                bucket_label = _clean_text(title_match.group("bucket"))
            if not local_date:
                parsed_local_date = _build_local_date(
                    month_text=title_match.group("month"),
                    day_text=title_match.group("day"),
                    year_text=title_match.group("year"),
                )
                if parsed_local_date:
                    local_date = parsed_local_date

    if event_slug:
        event_match = WEATHER_EVENT_RE.match(event_slug)
        if event_match:
            if not city:
                city = _clean_text(event_match.group("city").replace("-", " "))
            if not local_date:
                parsed_local_date = _build_local_date(
                    month_text=event_match.group("month"),
                    day_text=event_match.group("day"),
                    year_text=event_match.group("year"),
                )
                if parsed_local_date:
                    local_date = parsed_local_date

    return {
        "city": city,
        "local_date": local_date,
        "bucket_label": bucket_label,
    }


def _build_local_date(*, month_text: str | None, day_text: str | None, year_text: str | None) -> str:
    if not month_text or not day_text:
        return ""
    month_number = MONTH_NUMBER.get(str(month_text).strip().lower())
    if month_number is None:
        return ""
    try:
        year_value = int(year_text) if year_text else 2026
        day_value = int(day_text)
        return datetime(year_value, month_number, day_value, tzinfo=UTC).date().isoformat()
    except ValueError:
        return ""


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("Â°", "°").replace("Â", "")


def _write_trade_csv(path: Path, trade_rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "timestamp_utc",
        "event_slug",
        "city",
        "local_date",
        "bucket_label",
        "side",
        "size",
        "price",
        "transaction_hash",
        "condition_id",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in trade_rows:
            writer.writerow(
                {
                    "timestamp_utc": row["timestamp_utc"].isoformat(),
                    "event_slug": row["event_slug"],
                    "city": row["city"],
                    "local_date": row["local_date"],
                    "bucket_label": row["bucket_label"],
                    "side": row["side"],
                    "size": row["size"],
                    "price": row["price"],
                    "transaction_hash": row["transaction_hash"],
                    "condition_id": row["condition_id"],
                }
            )


def _build_markdown_report(
    *,
    wallet_result: dict[str, Any],
    window: dict[str, Any],
    tz_label: str,
    tz_source: str,
    uptime: dict[str, Any],
    bot_activity: dict[str, Any],
    coldmath: dict[str, Any],
) -> str:
    target = wallet_result["target"]
    completeness = wallet_result["completeness"]
    start_utc = window["window_start_utc"].isoformat()
    end_utc = window["window_end_utc"].isoformat()
    lines = [
        f"# ColdMath 24-Hour Window Comparison: {target.get('profile_name') or target['proxy_wallet']}",
        "",
        "## Window Provenance",
        f"- Window start UTC: `{start_utc}`",
        f"- Window end UTC: `{end_utc}`",
        f"- Start source: `{window['start_source_path']}:{window['start_source_line']}`",
        f"- Start log timestamp: `{window['start_source_timestamp']}`",
        f"- Start log message: `{window['start_source_message']}`",
        f"- Log timezone label: `{tz_label}`",
        f"- Log timezone source: `{tz_source}`",
        "",
        "## Bot Uptime Check",
        f"- Weather log rows in window: `{uptime['weather_log_count']}`",
        f"- Heartbeat rows in window: `{uptime['heartbeat_count']}`",
        f"- Restart lines after initial start: `{uptime['restart_count']}`",
        f"- Downtime gaps over threshold: `{uptime['gap_count']}`",
        f"- Max observed gap seconds: `{uptime['max_gap_seconds']}`",
        f"- Last weather log at UTC: `{uptime['last_weather_log_at'].isoformat() if uptime['last_weather_log_at'] else ''}`",
        "",
        "## Bot Activity",
        f"- Live positions opened in window: `{bot_activity['live_trade_count']}`",
        f"- Entry log rows: `{bot_activity['entry_log_count']}`",
        f"- Positions with merged collateral: `{bot_activity['merge_position_count']}`",
        f"- Positions with redeemed collateral: `{bot_activity['redeem_position_count']}`",
        f"- Positions with unwind collateral: `{bot_activity['unwind_position_count']}`",
        f"- Zero live trades verdict: `{'yes' if bot_activity['live_trade_count'] == 0 and bot_activity['entry_log_count'] == 0 else 'no'}`",
        "",
        "## ColdMath Weather Activity",
        f"- Proxy wallet: `{target['proxy_wallet']}`",
        f"- Raw trades fetched: `{completeness.get('trade_count', 0)}`",
        f"- Raw activity rows fetched: `{completeness.get('activity_count', 0)}`",
        f"- Ledger events rebuilt: `{completeness.get('ledger_event_count', 0)}`",
        f"- Weather trade events in window: `{coldmath['trade_count']}`",
        f"- Distinct conditions traded: `{coldmath['distinct_condition_count']}`",
        f"- Distinct events traded: `{coldmath['distinct_event_count']}`",
        f"- Earliest trade UTC: `{coldmath['earliest_trade_utc'].isoformat() if coldmath['earliest_trade_utc'] else ''}`",
        f"- Latest trade UTC: `{coldmath['latest_trade_utc'].isoformat() if coldmath['latest_trade_utc'] else ''}`",
        f"- Trades with latest bot heartbeat showing `candidates=0`: `{coldmath['candidate_zero_trade_count']}`",
        f"- Trades with latest bot heartbeat showing `candidates>0`: `{coldmath['candidate_nonzero_trade_count']}`",
        f"- Trades with unknown bot candidate state at trade time: `{coldmath['candidate_unknown_trade_count']}`",
        "",
        "## ColdMath Trade Timeline",
    ]

    if not coldmath["trade_rows"]:
        lines.append("- No ColdMath weather trades were observed in this exact window.")
    else:
        for row in coldmath["trade_rows"]:
            candidate_state = row["bot_candidates_last_seen"]
            if candidate_state is None:
                candidate_note = "bot_candidates=unknown"
            else:
                candidate_note = f"bot_candidates={candidate_state}"
            price_text = f"{row['price']:.4f}" if row["price"] is not None else "n/a"
            lines.append(
                "- "
                f"`{row['timestamp_utc'].isoformat()}` | "
                f"`{row['city']}` `{row['local_date']}` `{row['bucket_label']}` | "
                f"`{row['side']}` size `{row['size']:.4f}` @ `{price_text}` | "
                f"`{candidate_note}` | "
                f"`{row['condition_id']}`"
            )

    lines.extend(["", "## Grouped Summary"])
    if not coldmath["grouped_rows"]:
        lines.append("- None")
    else:
        for row in coldmath["grouped_rows"]:
            lines.append(
                "- "
                f"`{row['city']}` `{row['local_date']}` `{row['bucket_label']}` | "
                f"condition `{row['condition_id']}` | "
                f"trades `{row['trade_count']}` | buys `{row['buy_count']}` | sells `{row['sell_count']}` | "
                f"size `{row['total_size']:.4f}` | "
                f"first `{row['first_trade_utc'].isoformat()}` | last `{row['last_trade_utc'].isoformat()}`"
            )

    lines.extend(["", "## Downtime Gaps"])
    if not uptime["gaps"]:
        lines.append("- None")
    else:
        for gap in uptime["gaps"]:
            lines.append(
                "- "
                f"`{gap['gap_start_utc'].isoformat()}` -> `{gap['gap_end_utc'].isoformat()}` | "
                f"`{gap['gap_seconds']:.0f}s`"
            )

    traded_events = sorted({row["event_slug"] for row in coldmath["trade_rows"] if row["event_slug"]})
    lines.extend(
        [
            "",
            "## Conclusion",
            f"- ColdMath made weather trades during the exact 24-hour bot window: `{'yes' if coldmath['trade_count'] > 0 else 'no'}`",
            f"- Total ColdMath weather trades in window: `{coldmath['trade_count']}`",
            f"- Markets touched: `{', '.join(traded_events) if traded_events else 'none'}`",
            f"- ColdMath trades while the latest bot heartbeat still showed `candidates=0`: `{coldmath['candidate_zero_trade_count']}`",
            "- Public comparison covers executed observable activity only. Canceled orders and resting quotes remain out of scope.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
