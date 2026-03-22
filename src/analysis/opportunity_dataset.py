"""Build labeled expert-signal opportunity datasets for meta-model research."""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analysis.backtest import data_loader
from analysis.backtest.engine import make_trade
from analysis.backtest_strategies import market_to_snapshot
from analysis.constants import DEFAULT_ENTRY_SLIPPAGE
from shared.opportunity_features import context_features, numeric_signal_payload
from shared.strategies.base import BaseStrategy, Signal
from shared.strategies.registry import discover_strategies

DEFAULT_EXPERTS = ("S5", "S13", "S14", "S15")
DEFAULT_CONFIG_SOURCE = "candidate"
DEFAULT_DURATIONS = (5,)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _parse_csv_list(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [value.strip() for value in raw.split(",") if value.strip()]


def _parse_duration_list(raw: str | None) -> list[int] | None:
    values = _parse_csv_list(raw)
    if values is None:
        return None
    return [int(value) for value in values]


def _load_strategy_instance(strategy_id: str, source: str) -> BaseStrategy:
    registry = discover_strategies()
    if strategy_id not in registry:
        raise KeyError(
            f"Unknown strategy '{strategy_id}'. Available: {sorted(registry.keys())}"
        )

    config_module = importlib.import_module(f"shared.strategies.{strategy_id}.config")
    if source == "candidate" and hasattr(config_module, "get_candidate_config"):
        config = config_module.get_candidate_config()
    elif source == "baseline" and hasattr(config_module, "get_baseline_config"):
        config = config_module.get_baseline_config()
    else:
        config = config_module.get_default_config()

    return registry[strategy_id](config)


def load_expert_strategies(
    expert_ids: Iterable[str] = DEFAULT_EXPERTS,
    *,
    config_source: str = DEFAULT_CONFIG_SOURCE,
) -> dict[str, BaseStrategy]:
    return {
        strategy_id: _load_strategy_instance(strategy_id, config_source)
        for strategy_id in expert_ids
    }


def _context_features(
    market: dict,
    *,
    second: int,
    second_signals: dict[str, Signal],
) -> dict[str, Any]:
    return context_features(
        prices=market["prices"],
        feature_series=market.get("feature_series"),
        total_seconds=market["total_seconds"],
        second=second,
        second_signals=second_signals,
    )


def _trade_from_signal(
    market: dict,
    signal: Signal,
    *,
    slippage: float,
    base_rate: float | None,
) -> Any:
    return make_trade(
        market,
        int(signal.signal_data.get("entry_second", 0)),
        signal.entry_price,
        signal.direction,
        slippage=slippage,
        base_rate=base_rate,
        stop_loss=signal.signal_data.get("stop_loss_price"),
        take_profit=signal.signal_data.get("take_profit_price"),
    )


def build_opportunity_dataset(
    markets: list[dict],
    *,
    expert_ids: Iterable[str] = DEFAULT_EXPERTS,
    config_source: str = DEFAULT_CONFIG_SOURCE,
    slippage: float = DEFAULT_ENTRY_SLIPPAGE,
    base_rate: float | None = None,
) -> pd.DataFrame:
    """Return a per-signal dataset labeled with realized PnL."""
    strategies = load_expert_strategies(expert_ids, config_source=config_source)
    rows: list[dict[str, Any]] = []

    for market in markets:
        eligible = {
            strategy_id: strategy
            for strategy_id, strategy in strategies.items()
            if strategy.market_is_eligible(market)
        }
        if not eligible:
            continue

        resolved: set[str] = set()
        for second in range(market["total_seconds"]):
            snapshot = market_to_snapshot(market, second)
            second_signals: dict[str, Signal] = {}

            for strategy_id, strategy in eligible.items():
                if strategy_id in resolved:
                    continue

                signal = strategy.evaluate(snapshot)
                if signal is None:
                    continue

                entry_second = int(
                    signal.signal_data.get(
                        "entry_second",
                        signal.signal_data.get("reversion_second", second),
                    )
                )
                if entry_second != second:
                    continue

                second_signals[strategy_id] = signal

            if not second_signals:
                continue

            context = _context_features(
                market,
                second=second,
                second_signals=second_signals,
            )
            started_at = market["started_at"]
            market_day = (
                started_at.astimezone(timezone.utc).date().isoformat()
                if started_at is not None
                else None
            )

            for strategy_id, signal in second_signals.items():
                trade = _trade_from_signal(
                    market,
                    signal,
                    slippage=slippage,
                    base_rate=base_rate,
                )
                direction_sign = 1 if signal.direction == "Up" else -1
                signal_payload = numeric_signal_payload(signal)
                row = {
                    "market_id": market["market_id"],
                    "market_type": market["market_type"],
                    "asset": str(market["asset"]).lower(),
                    "duration_minutes": int(market["duration_minutes"]),
                    "hour": int(market["hour"]),
                    "started_at": started_at,
                    "market_day": market_day,
                    "strategy_id": strategy_id,
                    "strategy_name": signal.strategy_name,
                    "direction": signal.direction,
                    "direction_sign": direction_sign,
                    "expert_config_source": config_source,
                    "signal_entry_price": float(signal.entry_price),
                    "peer_same_direction_count": sum(
                        1
                        for peer_signal in second_signals.values()
                        if peer_signal.direction == signal.direction
                    )
                    - 1,
                    "peer_opposite_direction_count": sum(
                        1
                        for peer_signal in second_signals.values()
                        if peer_signal.direction != signal.direction
                    ),
                    **context,
                    **signal_payload,
                    "realized_pnl": float(trade.pnl),
                    "realized_gross_pnl": float(trade.gross_pnl),
                    "entry_fee_usdc": float(trade.entry_fee_usdc),
                    "exit_fee_usdc": float(trade.exit_fee_usdc),
                    "realized_is_win": 1 if trade.outcome == "win" else 0,
                    "actual_result": trade.actual_result,
                    "exit_reason": trade.exit_reason,
                }
                rows.append(row)
                resolved.add(strategy_id)

            if len(resolved) == len(eligible):
                break

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    frame.sort_values(
        ["started_at", "market_id", "entry_second", "strategy_id"],
        inplace=True,
    )
    frame.reset_index(drop=True, inplace=True)
    return frame


def build_dataset_summary(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {
            "rows": 0,
            "markets": 0,
            "strategies": {},
            "assets": {},
            "date_range_start": None,
            "date_range_end": None,
        }

    started = pd.to_datetime(df["started_at"], utc=True)
    return {
        "rows": int(len(df)),
        "markets": int(df["market_id"].nunique()),
        "strategies": {
            key: int(value)
            for key, value in df["strategy_id"].value_counts().sort_index().items()
        },
        "assets": {
            key: int(value)
            for key, value in df["asset"].value_counts().sort_index().items()
        },
        "date_range_start": started.min().isoformat(),
        "date_range_end": started.max().isoformat(),
        "total_realized_pnl": round(float(df["realized_pnl"].sum()), 4),
        "positive_signal_rate_pct": round(float(df["realized_is_win"].mean() * 100.0), 2),
    }


def _default_output_dir() -> Path:
    return Path("./results/meta_model") / f"dataset_{_timestamp()}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="analysis.opportunity_dataset",
        description="Build a labeled 5m opportunity dataset from expert strategy signals.",
    )
    parser.add_argument(
        "--experts",
        default=",".join(DEFAULT_EXPERTS),
        help="Comma-separated expert strategy IDs (default: S5,S13,S14,S15).",
    )
    parser.add_argument(
        "--config-source",
        choices=("candidate", "default", "baseline"),
        default=DEFAULT_CONFIG_SOURCE,
        help="Config source for the experts (default: candidate).",
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="Optional comma-separated asset filter.",
    )
    parser.add_argument(
        "--durations",
        default=",".join(str(value) for value in DEFAULT_DURATIONS),
        help="Comma-separated duration filter in minutes (default: 5).",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=DEFAULT_ENTRY_SLIPPAGE,
        help=f"Entry slippage for labeling trades (default: {DEFAULT_ENTRY_SLIPPAGE:.2f}).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to ./results/meta_model/dataset_<timestamp>.",
    )
    args = parser.parse_args(argv)

    print("Loading markets...")
    markets = data_loader.load_all_data()
    if not markets:
        raise SystemExit("No markets loaded.")

    assets = _parse_csv_list(args.assets)
    durations = _parse_duration_list(args.durations)
    markets = data_loader.filter_markets(markets, assets=assets, durations=durations)
    if not markets:
        raise SystemExit("No markets remain after applying filters.")

    expert_ids = _parse_csv_list(args.experts) or list(DEFAULT_EXPERTS)
    print(f"Building opportunity dataset from experts: {expert_ids}")
    dataset = build_opportunity_dataset(
        markets,
        expert_ids=expert_ids,
        config_source=args.config_source,
        slippage=args.slippage,
    )
    summary = build_dataset_summary(dataset)

    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "opportunities.csv"
    json_path = output_dir / "summary.json"

    dataset.to_csv(csv_path, index=False)
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")

    print(f"Rows: {summary['rows']}")
    print(f"Markets: {summary['markets']}")
    print(f"Saved CSV: {csv_path.resolve()}")
    print(f"Saved summary: {json_path.resolve()}")


if __name__ == "__main__":
    main()
