"""Summarize wallet-tracker and weather-clone health from Postgres."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from typing import Any

from analysis.db_sync import get_connection


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Weather bot health report")
    parser.add_argument("--profile", type=str, default="ColdMath", help="Wallet tracker profile name")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser


def _maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _minutes_since(value: datetime | None) -> float | None:
    if value is None:
        return None
    current = datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return round((current - value).total_seconds() / 60.0, 3)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat()


def build_report(profile: str) -> dict[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    MAX(to_timestamp(timestamp)) AS latest_activity_at_utc,
                    MAX(fetched_at) AS latest_fetch_at_utc,
                    COUNT(*) AS activity_row_count
                FROM wallet_tracker_activity
                WHERE profile_name = %s
                """,
                (profile,),
            )
            latest_activity_at, latest_fetch_at, activity_row_count = cur.fetchone()

            cur.execute(
                """
                SELECT proxy_wallet, last_timestamp, updated_at
                FROM wallet_tracker_watermark
                WHERE profile_name = %s
                """,
                (profile,),
            )
            watermark_row = cur.fetchone()

            cur.execute(
                """
                SELECT
                    captured_at,
                    execution_allowed,
                    execution_health,
                    market_data_health,
                    quote_coverage_ratio,
                    health_data,
                    summary_data
                FROM weather_clone_cycles
                ORDER BY captured_at DESC
                LIMIT 1
                """
            )
            clone_row = cur.fetchone()

            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE closed_at IS NULL) AS open_positions,
                    COUNT(*) FILTER (WHERE closed_at IS NULL AND status = 'pending_entry') AS pending_entries,
                    COUNT(*) FILTER (WHERE closed_at IS NULL AND shadow_only = FALSE) AS live_open_positions
                FROM weather_clone_positions
                """
            )
            open_positions, pending_entries, live_open_positions = cur.fetchone()
    finally:
        conn.close()

    proxy_wallet = None
    watermark_ts = None
    watermark_updated_at = None
    if watermark_row:
        proxy_wallet, watermark_ts, watermark_updated_at = watermark_row
    watermark_activity_at = (
        datetime.fromtimestamp(int(watermark_ts), tz=UTC) if watermark_ts is not None else None
    )

    clone_summary = _maybe_json(clone_row[6]) if clone_row else {}
    clone_health = _maybe_json(clone_row[5]) if clone_row else {}
    wallet_guard = _maybe_json((clone_summary or {}).get("wallet_guard") or {})
    guard_stats = _maybe_json((wallet_guard or {}).get("stats") or {})

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "tracker": {
            "profile_name": profile,
            "proxy_wallet": proxy_wallet,
            "activity_row_count": int(activity_row_count or 0),
            "latest_activity_at_utc": _isoformat(latest_activity_at),
            "latest_fetch_at_utc": _isoformat(latest_fetch_at),
            "latest_watermark_activity_at_utc": _isoformat(watermark_activity_at),
            "watermark_updated_at_utc": _isoformat(watermark_updated_at),
            "activity_freshness_minutes": _minutes_since(latest_activity_at),
            "watermark_freshness_minutes": _minutes_since(watermark_updated_at),
        },
        "clone": {
            "latest_cycle_at_utc": _isoformat(clone_row[0]) if clone_row else None,
            "cycle_freshness_minutes": _minutes_since(clone_row[0]) if clone_row else None,
            "execution_allowed": bool(clone_row[1]) if clone_row else False,
            "execution_health": clone_row[2] if clone_row else None,
            "market_data_health": clone_row[3] if clone_row else None,
            "quote_coverage_ratio": float(clone_row[4] or 0.0) if clone_row else None,
            "stand_down_reason": (clone_summary or {}).get("stand_down_reason"),
            "guard_warning_reason": (clone_summary or {}).get("guard_warning_reason"),
            "wallet_guard_reason": (wallet_guard or {}).get("reason"),
            "orphaned_weather_positions_count": int(guard_stats.get("orphaned_weather_positions_count") or 0),
            "open_positions": int(open_positions or 0),
            "pending_entries": int(pending_entries or 0),
            "live_open_positions": int(live_open_positions or 0),
            "health_state": clone_health or {},
        },
    }
    return report


def _render_markdown(report: dict[str, Any]) -> str:
    tracker = report["tracker"]
    clone = report["clone"]
    lines = [
        "# Weather Bot Health",
        "",
        "## Wallet Tracker",
        f"- Profile: `{tracker['profile_name']}`",
        f"- Wallet: `{tracker['proxy_wallet'] or 'unknown'}`",
        f"- Activity rows: `{tracker['activity_row_count']}`",
        f"- Latest activity UTC: `{tracker['latest_activity_at_utc'] or 'n/a'}`",
        f"- Latest fetch UTC: `{tracker['latest_fetch_at_utc'] or 'n/a'}`",
        f"- Watermark activity UTC: `{tracker['latest_watermark_activity_at_utc'] or 'n/a'}`",
        f"- Watermark updated UTC: `{tracker['watermark_updated_at_utc'] or 'n/a'}`",
        f"- Activity freshness minutes: `{tracker['activity_freshness_minutes']}`",
        f"- Watermark freshness minutes: `{tracker['watermark_freshness_minutes']}`",
        "",
        "## Clone Runtime",
        f"- Latest cycle UTC: `{clone['latest_cycle_at_utc'] or 'n/a'}`",
        f"- Cycle freshness minutes: `{clone['cycle_freshness_minutes']}`",
        f"- Execution allowed: `{clone['execution_allowed']}`",
        f"- Execution health: `{clone['execution_health'] or 'n/a'}`",
        f"- Market data health: `{clone['market_data_health'] or 'n/a'}`",
        f"- Quote coverage ratio: `{clone['quote_coverage_ratio']}`",
        f"- Stand down reason: `{clone['stand_down_reason'] or 'n/a'}`",
        f"- Guard warning reason: `{clone['guard_warning_reason'] or 'n/a'}`",
        f"- Wallet guard reason: `{clone['wallet_guard_reason'] or 'n/a'}`",
        f"- Orphaned weather positions: `{clone['orphaned_weather_positions_count']}`",
        f"- Open positions: `{clone['open_positions']}`",
        f"- Pending entries: `{clone['pending_entries']}`",
        f"- Live open positions: `{clone['live_open_positions']}`",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(args.profile)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(_render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
