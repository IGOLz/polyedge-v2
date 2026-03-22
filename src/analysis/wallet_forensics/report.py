"""Markdown report and artifact export helpers."""

from __future__ import annotations

import importlib.util
import json
import logging
from collections import defaultdict
from statistics import mean
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.wallet_forensics.constants import HIGH_CONFIDENCE_THRESHOLD
from analysis.wallet_forensics.utils import ensure_dir, utc_now

logger = logging.getLogger(__name__)
_PARQUET_ENGINE_UNSET = object()
_PARQUET_ENGINE: object | str | None = _PARQUET_ENGINE_UNSET
_PARQUET_WARNING_EMITTED = False


def export_artifacts(
    *,
    output_dir: Path,
    ledger_rows: list[dict[str, Any]],
    inferred_rules: list[dict[str, Any]],
    shadow_rows: list[dict[str, Any]],
    playbook_sequences: list[dict[str, Any]] | None = None,
    strategy_blueprints: list[dict[str, Any]] | None = None,
    rule_summary: dict[str, Any] | None = None,
    export_parquet: bool = True,
) -> None:
    ensure_dir(output_dir)
    _export_frame(pd.DataFrame(ledger_rows), output_dir / "wallet_ledger_events", export_parquet=export_parquet)
    _export_frame(pd.DataFrame(inferred_rules), output_dir / "wallet_inferred_rules", export_parquet=export_parquet)
    _export_frame(pd.DataFrame(shadow_rows), output_dir / "wallet_shadow_replay", export_parquet=export_parquet)
    if playbook_sequences is not None:
        _export_frame(
            pd.DataFrame(playbook_sequences),
            output_dir / "wallet_playbook_sequences",
            export_parquet=export_parquet,
        )
    if strategy_blueprints is not None:
        _export_frame(
            pd.DataFrame(strategy_blueprints),
            output_dir / "wallet_strategy_blueprints",
            export_parquet=export_parquet,
        )
        (output_dir / "wallet_strategy_blueprints.json").write_text(
            json.dumps(strategy_blueprints, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
    if rule_summary is not None:
        (output_dir / "wallet_rule_summary.json").write_text(
            json.dumps(rule_summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _export_frame(frame: pd.DataFrame, base_path: Path, *, export_parquet: bool) -> None:
    if frame.empty:
        frame = pd.DataFrame()
    frame.to_csv(base_path.with_suffix(".csv"), index=False)
    if not export_parquet:
        return
    parquet_engine = _available_parquet_engine()
    if parquet_engine is None:
        _warn_missing_parquet_engine_once()
        return
    try:
        frame.to_parquet(base_path.with_suffix(".parquet"), index=False, engine=parquet_engine)
    except Exception as exc:
        logger.warning("Parquet export skipped for %s: %s", base_path.name, exc)


def _available_parquet_engine() -> str | None:
    global _PARQUET_ENGINE
    if _PARQUET_ENGINE is not _PARQUET_ENGINE_UNSET:
        return _PARQUET_ENGINE if isinstance(_PARQUET_ENGINE, str) else None

    for engine_name in ("pyarrow", "fastparquet"):
        if importlib.util.find_spec(engine_name) is not None:
            _PARQUET_ENGINE = engine_name
            return engine_name

    _PARQUET_ENGINE = None
    return None


def _warn_missing_parquet_engine_once() -> None:
    global _PARQUET_WARNING_EMITTED
    if _PARQUET_WARNING_EMITTED:
        return
    logger.warning(
        "Parquet export skipped because no parquet engine is installed. "
        "Install `pyarrow` or run with `--skip-parquet` to silence this warning."
    )
    _PARQUET_WARNING_EMITTED = True


def build_markdown_report(
    *,
    target: dict[str, Any],
    ledger_rows: list[dict[str, Any]],
    inferred_rules: list[dict[str, Any]],
    shadow_rows: list[dict[str, Any]],
    strategy_blueprints: list[dict[str, Any]] | None = None,
    completeness: dict[str, Any],
    scope_label: str = "all_markets",
) -> str:
    total_realized = sum(float(row.get("realized_pnl") or 0.0) for row in ledger_rows)
    top_rules = sorted(inferred_rules, key=lambda item: item.get("confidence", 0), reverse=True)[:10]
    top_shadow = sorted(shadow_rows, key=lambda item: item.get("pnl_slippage_free", 0), reverse=True)[:10]
    top_blueprints = sorted(
        strategy_blueprints or [],
        key=lambda item: (item.get("priority_score") or 0.0, item.get("confidence") or 0.0),
        reverse=True,
    )[:5]

    lines = [
        f"# Wallet Forensics Report: {target.get('profile_name') or target['proxy_wallet']}",
        "",
        "## Wallet Identity",
        f"- Proxy wallet: `{target['proxy_wallet']}`",
        f"- Profile name: `{target.get('profile_name') or ''}`",
        f"- Pseudonym: `{target.get('pseudonym') or ''}`",
        f"- Bio: `{target.get('bio') or ''}`",
        f"- Total traded markets: `{target.get('total_traded_markets')}`",
        f"- Report scope: `{scope_label}`",
        "",
        "## Completeness",
        f"- Raw trades fetched: `{completeness.get('trade_count', 0)}`",
        f"- Raw activity rows fetched: `{completeness.get('activity_count', 0)}`",
        f"- Distinct receipts fetched: `{completeness.get('receipt_count', 0)}`",
        f"- Market contexts fetched: `{completeness.get('market_context_count', 0)}`",
        f"- Ledger events rebuilt: `{len(ledger_rows)}`",
        f"- Playbook sequences extracted: `{completeness.get('playbook_sequence_count', 0)}`",
        f"- Strategy blueprints generated: `{completeness.get('strategy_blueprint_count', 0)}`",
        f"- Backfill complete: `{completeness.get('complete', True)}`",
        "",
        "## PnL Attribution",
        f"- Rebuilt realized PnL: `{total_realized:.2f}`",
        f"- Trade events: `{sum(1 for row in ledger_rows if row.get('event_type') == 'trade')}`",
        f"- Merge events: `{sum(1 for row in ledger_rows if row.get('event_type') == 'merge')}`",
        f"- Redeem events: `{sum(1 for row in ledger_rows if row.get('event_type') == 'redeem')}`",
        "",
        "## Playbook Catalog",
    ]

    if not top_rules:
        lines.append("- No rules inferred.")
    else:
        for rule in top_rules:
            lines.append(f"- `{rule['strategy_key']}` at `{rule['confidence']:.2f}`: {rule['summary']}")

    lines.extend(["", "## Executable Blueprints"])
    if not top_blueprints:
        lines.append("- No executable blueprints generated yet.")
    else:
        for blueprint in top_blueprints:
            lines.append(
                "- "
                f"`{blueprint['strategy_key']}` "
                f"status `{blueprint['status']}`, "
                f"confidence `{blueprint['confidence']:.2f}`, "
                f"support `{blueprint['support_count']}`, "
                f"priority `{blueprint['priority_score']:.2f}`: "
                f"{blueprint['summary']}"
            )

    lines.extend(["", "## Replay Results"])
    if not shadow_rows:
        lines.append("- No high-confidence shadow trades were generated.")
    else:
        total_shadow = sum(float(row.get("pnl_slippage_free") or 0.0) for row in shadow_rows)
        total_conservative = sum(float(row.get("pnl_conservative") or 0.0) for row in shadow_rows)
        lines.append(f"- Shadow trades: `{len(shadow_rows)}`")
        lines.append(f"- Slippage-free replay PnL: `{total_shadow:.2f}`")
        lines.append(f"- Conservative replay PnL: `{total_conservative:.2f}`")
        for row in top_shadow:
            lines.append(
                f"- `{row.get('condition_id')}` `{row.get('asset')}` size `{row.get('size')}` from `{row.get('entry_price')}` to `{row.get('exit_mark_price')}` => `{row.get('pnl_slippage_free'):.2f}`"
            )

    lines.extend(
        [
            "",
            "## Limitations",
            "- Public reconstruction cannot observe canceled orders, resting quotes, or private intent.",
            "- Offchain order placement is inferred only through observed fills and onchain settlement traces.",
            "- Conversion support is implemented, but this wallet currently exposes few or no public conversion fixtures.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_rule_summary(
    *,
    target: dict[str, Any],
    ledger_rows: list[dict[str, Any]],
    inferred_rules: list[dict[str, Any]],
    shadow_rows: list[dict[str, Any]],
    strategy_blueprints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    strategy_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    condition_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    shadow_by_rule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ledger_by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in inferred_rules:
        strategy_groups[str(row.get("strategy_key") or "unknown")].append(row)
        condition_groups[str(row.get("condition_id") or "")].append(row)
    for row in shadow_rows:
        shadow_by_rule[str(row.get("rule_id") or "")].append(row)
    for row in ledger_rows:
        condition_groups.setdefault(str(row.get("condition_id") or ""), condition_groups.get(str(row.get("condition_id") or ""), []))
        ledger_by_condition[str(row.get("condition_id") or "")].append(row)

    strategy_summaries: list[dict[str, Any]] = []
    for strategy_key, rows in strategy_groups.items():
        confidences = [float(row.get("confidence") or 0.0) for row in rows]
        rule_ids = {str(row.get("rule_id") or "") for row in rows}
        trade_ids = {
            str(trade_id)
            for row in rows
            for trade_id in (row.get("trade_ids_json") or [])
            if str(trade_id)
        }
        strategy_shadows = [
            shadow
            for rule_id in rule_ids
            for shadow in shadow_by_rule.get(rule_id, [])
        ]
        strategy_summaries.append(
            {
                "strategy_key": strategy_key,
                "rule_count": len(rows),
                "high_confidence_rule_count": sum(1 for value in confidences if value >= HIGH_CONFIDENCE_THRESHOLD),
                "avg_confidence": round(mean(confidences), 4) if confidences else 0.0,
                "max_confidence": round(max(confidences), 4) if confidences else 0.0,
                "distinct_conditions": len({str(row.get("condition_id") or "") for row in rows if str(row.get("condition_id") or "")}),
                "supporting_trade_count": len(trade_ids),
                "shadow_trade_count": len(strategy_shadows),
                "shadow_pnl_slippage_free": round(
                    sum(float(item.get("pnl_slippage_free") or 0.0) for item in strategy_shadows),
                    4,
                ),
                "shadow_pnl_conservative": round(
                    sum(float(item.get("pnl_conservative") or 0.0) for item in strategy_shadows),
                    4,
                ),
                "sample_summaries": list(dict.fromkeys(str(row.get("summary") or "") for row in rows if row.get("summary")))[:3],
            }
        )
    strategy_summaries.sort(
        key=lambda item: (
            item["high_confidence_rule_count"],
            item["rule_count"],
            item["avg_confidence"],
            item["shadow_pnl_slippage_free"],
        ),
        reverse=True,
    )

    condition_summaries: list[dict[str, Any]] = []
    for condition_id, rows in condition_groups.items():
        if not condition_id:
            continue
        ledger = ledger_by_condition.get(condition_id, [])
        event_slug = next(
            (
                str(item.get("event_slug") or "")
                for item in [*rows, *ledger]
                if str(item.get("event_slug") or "")
            ),
            "",
        )
        condition_summaries.append(
            {
                "condition_id": condition_id,
                "event_slug": event_slug,
                "rule_count": len(rows),
                "strategy_keys": sorted({str(row.get("strategy_key") or "") for row in rows if str(row.get("strategy_key") or "")}),
                "max_confidence": round(
                    max(float(row.get("confidence") or 0.0) for row in rows),
                    4,
                ) if rows else 0.0,
                "trade_event_count": sum(1 for item in ledger if item.get("event_type") == "trade"),
                "merge_event_count": sum(1 for item in ledger if item.get("event_type") == "merge"),
                "redeem_event_count": sum(1 for item in ledger if item.get("event_type") == "redeem"),
                "realized_pnl": round(sum(float(item.get("realized_pnl") or 0.0) for item in ledger), 4),
                "is_weather": any(bool(item.get("is_weather")) for item in ledger),
            }
        )
    condition_summaries.sort(
        key=lambda item: (
            item["rule_count"],
            item["max_confidence"],
            abs(item["realized_pnl"]),
        ),
        reverse=True,
    )

    blueprint_summaries = [
        {
            "strategy_key": str(item.get("strategy_key") or ""),
            "status": str(item.get("status") or ""),
            "confidence": round(float(item.get("confidence") or 0.0), 4),
            "priority_score": round(float(item.get("priority_score") or 0.0), 4),
            "support_count": int(item.get("support_count") or 0),
            "summary": str(item.get("summary") or ""),
        }
        for item in (strategy_blueprints or [])
    ]
    bot_candidates = [
        {
            "strategy_key": item["strategy_key"],
            "candidate_score": round(
                item["high_confidence_rule_count"] * 2
                + item["rule_count"]
                + item["avg_confidence"]
                + max(0.0, item["shadow_pnl_conservative"]),
                4,
            ),
            "why": (
                f"{item['rule_count']} rules, {item['high_confidence_rule_count']} high-confidence, "
                f"avg confidence {item['avg_confidence']:.2f}, conservative replay {item['shadow_pnl_conservative']:.2f}"
            ),
        }
        for item in strategy_summaries[:5]
    ]
    for item in blueprint_summaries:
        bot_candidates.append(
            {
                "strategy_key": item["strategy_key"],
                "candidate_score": round(item["priority_score"] + item["confidence"] * 2, 4),
                "why": (
                    f"blueprint status {item['status']}, support {item['support_count']}, "
                    f"priority {item['priority_score']:.2f}"
                ),
            }
        )
    bot_candidates.sort(key=lambda item: item["candidate_score"], reverse=True)

    return {
        "generated_at": utc_now().isoformat(),
        "proxy_wallet": target["proxy_wallet"],
        "profile_name": target.get("profile_name"),
        "total_rules": len(inferred_rules),
        "high_confidence_rules": sum(
            1 for row in inferred_rules if float(row.get("confidence") or 0.0) >= HIGH_CONFIDENCE_THRESHOLD
        ),
        "total_shadow_trades": len(shadow_rows),
        "strategies": strategy_summaries,
        "strategy_blueprints": blueprint_summaries[:10],
        "top_conditions": condition_summaries[:15],
        "bot_candidates": bot_candidates[:5],
    }


def build_rule_summary_markdown(
    *,
    target: dict[str, Any],
    rule_summary: dict[str, Any],
) -> str:
    strategies = rule_summary.get("strategies") or []
    strategy_blueprints = rule_summary.get("strategy_blueprints") or []
    top_conditions = rule_summary.get("top_conditions") or []
    bot_candidates = rule_summary.get("bot_candidates") or []

    lines = [
        f"# Rule Summary: {target.get('profile_name') or target['proxy_wallet']}",
        "",
        "## Overview",
        f"- Proxy wallet: `{target['proxy_wallet']}`",
        f"- Total inferred rules: `{rule_summary.get('total_rules', 0)}`",
        f"- High-confidence rules: `{rule_summary.get('high_confidence_rules', 0)}`",
        f"- Shadow trades linked to rules: `{rule_summary.get('total_shadow_trades', 0)}`",
        "",
        "## Dominant Playbooks",
    ]
    if not strategies:
        lines.append("- No strategies summarized.")
    else:
        for item in strategies[:10]:
            lines.append(
                "- "
                f"`{item['strategy_key']}`: `{item['rule_count']}` rules, "
                f"`{item['high_confidence_rule_count']}` high-confidence, "
                f"`{item['avg_confidence']:.2f}` avg confidence, "
                f"`{item['shadow_pnl_conservative']:.2f}` conservative replay"
            )

    lines.extend(["", "## Executable Blueprints"])
    if not strategy_blueprints:
        lines.append("- No executable blueprints summarized.")
    else:
        for item in strategy_blueprints[:10]:
            lines.append(
                "- "
                f"`{item['strategy_key']}`: status `{item['status']}`, "
                f"confidence `{item['confidence']:.2f}`, "
                f"priority `{item['priority_score']:.2f}`, "
                f"support `{item['support_count']}`"
            )

    lines.extend(["", "## Bot Candidates"])
    if not bot_candidates:
        lines.append("- No bot candidates available yet.")
    else:
        for item in bot_candidates:
            lines.append(f"- `{item['strategy_key']}` score `{item['candidate_score']:.2f}`: {item['why']}")

    lines.extend(["", "## Top Conditions"])
    if not top_conditions:
        lines.append("- No condition-level summary available.")
    else:
        for item in top_conditions[:10]:
            lines.append(
                "- "
                f"`{item['condition_id']}` "
                f"({item.get('event_slug') or 'no-event-slug'}) "
                f"rules `{item['rule_count']}`, max confidence `{item['max_confidence']:.2f}`, "
                f"realized PnL `{item['realized_pnl']:.2f}`"
            )

    return "\n".join(lines) + "\n"


def build_strategy_blueprint_markdown(
    *,
    target: dict[str, Any],
    strategy_blueprints: list[dict[str, Any]],
) -> str:
    lines = [
        f"# Strategy Blueprints: {target.get('profile_name') or target['proxy_wallet']}",
        "",
        "## Overview",
        f"- Proxy wallet: `{target['proxy_wallet']}`",
        f"- Blueprint count: `{len(strategy_blueprints)}`",
        "",
        "## Blueprints",
    ]
    if not strategy_blueprints:
        lines.append("- No blueprints available.")
        return "\n".join(lines) + "\n"

    for item in strategy_blueprints:
        lines.extend(
            [
                f"### {item['strategy_key']}",
                f"- Status: `{item['status']}`",
                f"- Confidence: `{float(item.get('confidence') or 0.0):.2f}`",
                f"- Priority: `{float(item.get('priority_score') or 0.0):.2f}`",
                f"- Support count: `{int(item.get('support_count') or 0)}`",
                f"- Summary: {item.get('summary') or ''}",
                f"- Entry: `{json.dumps(item.get('entry_rule_json') or {}, sort_keys=True)}`",
                f"- Sizing: `{json.dumps(item.get('sizing_rule_json') or {}, sort_keys=True)}`",
                f"- Exit: `{json.dumps(item.get('exit_rule_json') or {}, sort_keys=True)}`",
                f"- Risk: `{json.dumps(item.get('risk_rule_json') or {}, sort_keys=True)}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def export_fill_context_artifacts(
    *,
    output_dir: Path,
    fill_context_rows: list[dict[str, Any]],
    fill_context_summary: dict[str, Any],
    export_parquet: bool = True,
) -> None:
    ensure_dir(output_dir)
    _export_frame(
        pd.DataFrame(fill_context_rows),
        output_dir / "wallet_fill_context",
        export_parquet=export_parquet,
    )
    (output_dir / "wallet_fill_context_summary.json").write_text(
        json.dumps(fill_context_summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def build_fill_context_summary(
    *,
    target: dict[str, Any],
    fill_context_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    def _label_counts_from_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        counts: dict[str, int] = defaultdict(int)
        for row in rows:
            label = str(row.get(key) or "")
            if not label:
                continue
            counts[label] += 1
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [{"label": label, "count": count} for label, count in ranked]

    def _count_if(key: str, value: str) -> int:
        return sum(1 for row in fill_context_rows if str(row.get(key) or "") == value)

    def _label_counts(key: str) -> list[dict[str, Any]]:
        return _label_counts_from_rows(fill_context_rows, key)

    def _avg(key: str) -> float | None:
        values = [float(row[key]) for row in fill_context_rows if row.get(key) is not None]
        if not values:
            return None
        return round(mean(values), 4)

    top_conditions_map: dict[str, dict[str, Any]] = {}
    for row in fill_context_rows:
        condition_id = str(row.get("condition_id") or "")
        if not condition_id:
            continue
        entry = top_conditions_map.setdefault(
            condition_id,
            {
                "condition_id": condition_id,
                "event_slug": row.get("event_slug"),
                "question": row.get("question"),
                "fill_count": 0,
                "price_history_under_par_count": 0,
                "local_under_par_count": 0,
                "quote_labeled_count": 0,
                "price_history_labeled_count": 0,
                "history_edges": [],
                "local_edges": [],
            },
        )
        entry["fill_count"] += 1
        if bool(row.get("price_history_pair_under_par")):
            entry["price_history_under_par_count"] += 1
        if bool(row.get("local_pair_under_par")):
            entry["local_under_par_count"] += 1
        if str(row.get("local_execution_label") or "") != "unknown":
            entry["quote_labeled_count"] += 1
        if str(row.get("price_history_execution_label") or "") != "unknown":
            entry["price_history_labeled_count"] += 1
        if row.get("price_history_execution_edge_bps") is not None:
            entry["history_edges"].append(float(row["price_history_execution_edge_bps"]))
        if row.get("local_execution_edge_bps") is not None:
            entry["local_edges"].append(float(row["local_execution_edge_bps"]))

    top_conditions: list[dict[str, Any]] = []
    for entry in top_conditions_map.values():
        top_conditions.append(
            {
                "condition_id": entry["condition_id"],
                "event_slug": entry.get("event_slug"),
                "question": entry.get("question"),
                "fill_count": entry["fill_count"],
                "price_history_under_par_count": entry["price_history_under_par_count"],
                "local_under_par_count": entry["local_under_par_count"],
                "quote_labeled_count": entry["quote_labeled_count"],
                "price_history_labeled_count": entry["price_history_labeled_count"],
                "avg_price_history_edge_bps": round(mean(entry["history_edges"]), 4)
                if entry["history_edges"] else None,
                "avg_local_edge_bps": round(mean(entry["local_edges"]), 4)
                if entry["local_edges"] else None,
            }
        )
    top_conditions.sort(
        key=lambda item: (
            item["fill_count"],
            item["price_history_under_par_count"],
            item["quote_labeled_count"],
        ),
        reverse=True,
    )

    buy_rows = [row for row in fill_context_rows if str(row.get("side") or "") == "buy"]
    under_par_buy_rows = [row for row in buy_rows if bool(row.get("price_history_pair_under_par"))]
    non_under_par_buy_rows = [row for row in buy_rows if row.get("price_history_pair_under_par") is False]

    return {
        "generated_at": utc_now().isoformat(),
        "proxy_wallet": target["proxy_wallet"],
        "profile_name": target.get("profile_name"),
        "total_fills": len(fill_context_rows),
        "buy_fills": len(buy_rows),
        "token_mapped_fills": sum(1 for row in fill_context_rows if bool(row.get("token_mapping_found"))),
        "weather_fills": sum(1 for row in fill_context_rows if bool(row.get("is_weather"))),
        "context_source_counts": _label_counts("context_source"),
        "local_quote_coverage_counts": _label_counts("local_quote_coverage"),
        "price_history_coverage_counts": _label_counts("price_history_coverage"),
        "local_execution_label_counts": _label_counts("local_execution_label"),
        "price_history_execution_label_counts": _label_counts("price_history_execution_label"),
        "fills_with_any_context": sum(1 for row in fill_context_rows if str(row.get("context_source") or "") != "none"),
        "fills_with_local_quote_pair": _count_if("local_quote_coverage", "full_pair"),
        "fills_with_price_history_pair": _count_if("price_history_coverage", "full_pair"),
        "fills_with_price_history_under_par_pair": sum(
            1 for row in fill_context_rows if bool(row.get("price_history_pair_under_par"))
        ),
        "fills_with_local_under_par_pair": sum(
            1 for row in fill_context_rows if bool(row.get("local_pair_under_par"))
        ),
        "buy_fills_with_price_history_under_par_pair": len(under_par_buy_rows),
        "buy_fills_with_price_history_under_par_pair_pct": round(
            (len(under_par_buy_rows) / len(buy_rows) * 100.0),
            4,
        ) if buy_rows else None,
        "under_par_buy_execution_labels": _label_counts_from_rows(
            under_par_buy_rows,
            "price_history_execution_label",
        ),
        "non_under_par_buy_execution_labels": _label_counts_from_rows(
            non_under_par_buy_rows,
            "price_history_execution_label",
        ),
        "avg_local_execution_edge_bps": _avg("local_execution_edge_bps"),
        "avg_price_history_execution_edge_bps": _avg("price_history_execution_edge_bps"),
        "top_conditions": top_conditions[:15],
    }


def build_fill_context_markdown(
    *,
    target: dict[str, Any],
    fill_context_summary: dict[str, Any],
    fill_context_rows: list[dict[str, Any]],
) -> str:
    def _format_counts(items: list[dict[str, Any]], *, limit: int = 5) -> list[str]:
        if not items:
            return ["- None"]
        return [
            f"- `{item['label']}`: `{item['count']}`"
            for item in items[:limit]
        ]

    lines = [
        f"# Fill Context Report: {target.get('profile_name') or target['proxy_wallet']}",
        "",
        "## Coverage",
        f"- Total fills analyzed: `{fill_context_summary.get('total_fills', 0)}`",
        f"- Token-mapped fills: `{fill_context_summary.get('token_mapped_fills', 0)}`",
        f"- Weather fills: `{fill_context_summary.get('weather_fills', 0)}`",
        f"- Fills with any context: `{fill_context_summary.get('fills_with_any_context', 0)}`",
        f"- Full local quote pairs: `{fill_context_summary.get('fills_with_local_quote_pair', 0)}`",
        f"- Full price-history pairs: `{fill_context_summary.get('fills_with_price_history_pair', 0)}`",
        "",
        "## Context Sources",
        *_format_counts(fill_context_summary.get("context_source_counts") or []),
        "",
        "## Execution Labels",
        "### Quote-Based",
        *_format_counts(fill_context_summary.get("local_execution_label_counts") or []),
        "### Price-History-Based",
        *_format_counts(fill_context_summary.get("price_history_execution_label_counts") or []),
        "",
        "## Pair-Cost Signals",
        f"- Fills with `executed + opposite history price < 1`: `{fill_context_summary.get('fills_with_price_history_under_par_pair', 0)}`",
        f"- Buy fills with `executed + opposite history price < 1`: `{fill_context_summary.get('buy_fills_with_price_history_under_par_pair', 0)}`",
        f"- Buy-fill under-par rate: `{fill_context_summary.get('buy_fills_with_price_history_under_par_pair_pct')}`%",
        f"- Fills with `executed + opposite local ask < 1`: `{fill_context_summary.get('fills_with_local_under_par_pair', 0)}`",
        f"- Avg local execution edge (bps): `{fill_context_summary.get('avg_local_execution_edge_bps')}`",
        f"- Avg price-history execution edge (bps): `{fill_context_summary.get('avg_price_history_execution_edge_bps')}`",
        "",
        "### Under-Par Buy Labels",
        *_format_counts(fill_context_summary.get("under_par_buy_execution_labels") or []),
        "### Non-Under-Par Buy Labels",
        *_format_counts(fill_context_summary.get("non_under_par_buy_execution_labels") or []),
        "",
        "## Top Conditions",
    ]

    top_conditions = fill_context_summary.get("top_conditions") or []
    if not top_conditions:
        lines.append("- None")
    else:
        for item in top_conditions[:10]:
            lines.append(
                "- "
                f"`{item['condition_id']}` "
                f"fills `{item['fill_count']}`, "
                f"history under-par `{item['price_history_under_par_count']}`, "
                f"quote-labeled `{item['quote_labeled_count']}`, "
                f"history-labeled `{item['price_history_labeled_count']}`"
            )

    lines.extend(
        [
            "",
            "## Limitations",
            "- Local `market_quotes` only cover the periods we personally collected, so true quote snapshots may be sparse for older fills.",
            "- Historical `prices-history` points are nearby trade prices, not guaranteed bid/ask snapshots, so maker-vs-taker inference remains approximate without quote coverage.",
            "- A fill can still be strategically correct even if its isolated execution looks aggressive; sequence-level inventory management still matters.",
        ]
    )
    return "\n".join(lines) + "\n"
