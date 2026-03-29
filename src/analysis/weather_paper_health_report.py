"""Summarize weather paper-trading health and paper PnL from Postgres."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from typing import Any

from analysis.db_sync import get_connection


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Weather paper bot health report")
    parser.add_argument("--paper-run-id", type=str, default=None, help="Specific paper run id")
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


def build_report(paper_run_id: str | None = None) -> dict[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if paper_run_id:
                cur.execute(
                    """
                    SELECT paper_run_id
                    FROM weather_paper_cycles
                    WHERE paper_run_id = %s
                    ORDER BY captured_at DESC
                    LIMIT 1
                    """,
                    (paper_run_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT paper_run_id
                    FROM weather_paper_cycles
                    ORDER BY captured_at DESC
                    LIMIT 1
                    """
                )
            run_row = cur.fetchone()
            resolved_run_id = str(run_row[0]) if run_row else None

            if not resolved_run_id:
                return {
                    "generated_at_utc": datetime.now(UTC).isoformat(),
                    "paper": None,
                }

            cur.execute(
                """
                SELECT
                    captured_at,
                    strategy_name,
                    execution_mode,
                    fill_model,
                    execution_allowed,
                    execution_health,
                    market_data_health,
                    quote_coverage_ratio,
                    summary_data
                FROM weather_paper_cycles
                WHERE paper_run_id = %s
                ORDER BY captured_at DESC
                LIMIT 1
                """,
                (resolved_run_id,),
            )
            cycle_row = cur.fetchone()

            cur.execute(
                """
                SELECT
                    captured_at,
                    realized_pnl_usd,
                    unrealized_pnl_usd,
                    equity_pnl_usd,
                    entry_notional_usd,
                    exit_notional_usd,
                    open_position_count,
                    mark_method
                FROM weather_paper_equity_snapshots
                WHERE paper_run_id = %s
                ORDER BY captured_at DESC
                LIMIT 1
                """,
                (resolved_run_id,),
            )
            equity_row = cur.fetchone()

            cur.execute(
                """
                SELECT COUNT(*)
                FROM weather_paper_positions
                WHERE paper_run_id = %s
                  AND closed_at IS NULL
                """,
                (resolved_run_id,),
            )
            open_positions = int(cur.fetchone()[0] or 0)

            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE event_type IN ('order_fill','partial_fill')) AS fill_events,
                    COUNT(*) FILTER (WHERE event_type = 'entry_rejected') AS rejected_events
                FROM weather_paper_position_events
                WHERE paper_run_id = %s
                """,
                (resolved_run_id,),
            )
            fill_events, rejected_events = cur.fetchone()

            cur.execute(
                """
                SELECT COALESCE(reason, 'unknown') AS reason, COUNT(*) AS count
                FROM weather_paper_position_events
                WHERE paper_run_id = %s
                  AND event_type = 'entry_rejected'
                GROUP BY 1
                ORDER BY count DESC, reason ASC
                LIMIT 5
                """,
                (resolved_run_id,),
            )
            top_rejections = [{"reason": row[0], "count": int(row[1] or 0)} for row in cur.fetchall()]
    finally:
        conn.close()

    summary_data = _maybe_json(cycle_row[8]) if cycle_row else {}
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "paper": {
            "paper_run_id": resolved_run_id,
            "latest_cycle_at_utc": _isoformat(cycle_row[0]) if cycle_row else None,
            "cycle_freshness_minutes": _minutes_since(cycle_row[0]) if cycle_row else None,
            "strategy_name": cycle_row[1] if cycle_row else None,
            "execution_mode": cycle_row[2] if cycle_row else None,
            "fill_model": cycle_row[3] if cycle_row else None,
            "execution_allowed": bool(cycle_row[4]) if cycle_row else False,
            "execution_health": cycle_row[5] if cycle_row else None,
            "market_data_health": cycle_row[6] if cycle_row else None,
            "quote_coverage_ratio": float(cycle_row[7] or 0.0) if cycle_row else None,
            "latest_equity_snapshot_at_utc": _isoformat(equity_row[0]) if equity_row else None,
            "latest_realized_pnl_usd": float(equity_row[1] or 0.0) if equity_row else None,
            "latest_unrealized_pnl_usd": float(equity_row[2] or 0.0) if equity_row else None,
            "latest_equity_pnl_usd": float(equity_row[3] or 0.0) if equity_row else None,
            "entry_notional_usd": float(equity_row[4] or 0.0) if equity_row else None,
            "exit_notional_usd": float(equity_row[5] or 0.0) if equity_row else None,
            "open_position_count": int(equity_row[6] or 0) if equity_row else open_positions,
            "mark_method": equity_row[7] if equity_row else None,
            "fill_event_count": int(fill_events or 0),
            "rejected_event_count": int(rejected_events or 0),
            "top_rejection_reasons": top_rejections,
            "summary_data": summary_data or {},
        },
    }
    return report


def _render_markdown(report: dict[str, Any]) -> str:
    paper = report.get("paper")
    if not paper:
        return "# Weather Paper Bot Health\n\nNo paper run found.\n"
    lines = [
        "# Weather Paper Bot Health",
        "",
        f"- Paper run: `{paper['paper_run_id']}`",
        f"- Latest cycle UTC: `{paper['latest_cycle_at_utc'] or 'n/a'}`",
        f"- Cycle freshness minutes: `{paper['cycle_freshness_minutes']}`",
        f"- Strategy: `{paper['strategy_name'] or 'n/a'}`",
        f"- Execution mode: `{paper['execution_mode'] or 'n/a'}`",
        f"- Fill model: `{paper['fill_model'] or 'n/a'}`",
        f"- Market data health: `{paper['market_data_health'] or 'n/a'}`",
        f"- Quote coverage ratio: `{paper['quote_coverage_ratio']}`",
        f"- Latest equity snapshot UTC: `{paper['latest_equity_snapshot_at_utc'] or 'n/a'}`",
        f"- Realized PnL USD: `{paper['latest_realized_pnl_usd']}`",
        f"- Unrealized PnL USD: `{paper['latest_unrealized_pnl_usd']}`",
        f"- Equity PnL USD: `{paper['latest_equity_pnl_usd']}`",
        f"- Entry notional USD: `{paper['entry_notional_usd']}`",
        f"- Exit notional USD: `{paper['exit_notional_usd']}`",
        f"- Open positions: `{paper['open_position_count']}`",
        f"- Fill events: `{paper['fill_event_count']}`",
        f"- Rejected events: `{paper['rejected_event_count']}`",
    ]
    if paper["top_rejection_reasons"]:
        lines.append("- Top rejection reasons: `" + ", ".join(f"{item['reason']}:{item['count']}" for item in paper["top_rejection_reasons"]) + "`")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(args.paper_run_id)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(_render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
