"""Backtest shared strategies through the analysis engine.

Bridges the shared strategy framework (``shared.strategies``) into the
existing analysis backtest infrastructure (``analysis.backtest``). Converts
``data_loader`` market dicts into causal ``MarketSnapshot`` objects, evaluates
strategies second by second, converts returned ``Signal`` objects into
``Trade`` objects using the existing engine, and computes performance metrics.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import asdict

import pandas as pd

from analysis.backtest import data_loader
from analysis.backtest.engine import (
    Trade,
    add_ranking_score,
    compute_metrics,
    make_trade,
    save_module_results,
)
from analysis.constants import DEFAULT_ENTRY_SLIPPAGE
from shared.strategies import (
    MarketSnapshot,
    StrategyReport,
    discover_strategies,
    get_strategy,
)


def market_to_snapshot(market: dict, current_second: int) -> MarketSnapshot:
    """Convert a market dict to a causal ``MarketSnapshot``."""
    history_end = current_second + 1
    feature_series = {
        name: values[:history_end].copy()
        for name, values in market.get("feature_series", {}).items()
    }

    return MarketSnapshot(
        market_id=market["market_id"],
        market_type=market["market_type"],
        prices=market["prices"][:history_end].copy(),
        total_seconds=market["total_seconds"],
        elapsed_seconds=current_second,
        feature_series=feature_series,
        metadata={
            "asset": market["asset"],
            "hour": market["hour"],
            "started_at": market["started_at"],
            "duration_minutes": market["duration_minutes"],
            "prior_market_type_streak_direction": market.get(
                "prior_market_type_streak_direction"
            ),
            "prior_market_type_streak_length": market.get(
                "prior_market_type_streak_length", 0
            ),
        },
    )


def run_strategy(
    strategy_id: str,
    strategy,
    markets: list[dict],
    slippage: float = DEFAULT_ENTRY_SLIPPAGE,
    base_rate: float | None = None,
    *,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    log_summary: bool = True,
) -> tuple[list[Trade], dict]:
    """Run a single strategy against all eligible markets."""
    trades: list[Trade] = []
    eligible_markets = [
        market for market in markets if strategy.market_is_eligible(market)
    ]
    skipped_markets = len(markets) - len(eligible_markets)

    for market in eligible_markets:
        total_seconds = market["total_seconds"]

        for current_second in range(total_seconds):
            snapshot = market_to_snapshot(market, current_second)
            signal = strategy.evaluate(snapshot)
            if signal is None:
                continue

            second_entered = int(
                signal.signal_data.get(
                    "entry_second",
                    signal.signal_data.get("reversion_second", current_second),
                )
            )
            if second_entered != current_second:
                continue

            signal_stop_loss = signal.signal_data.get("stop_loss_price")
            signal_take_profit = signal.signal_data.get("take_profit_price")
            trade_stop_loss = stop_loss if stop_loss is not None else signal_stop_loss
            trade_take_profit = take_profit if take_profit is not None else signal_take_profit

            trade = make_trade(
                market,
                second_entered,
                signal.entry_price,
                signal.direction,
                slippage=slippage,
                base_rate=base_rate,
                stop_loss=trade_stop_loss,
                take_profit=trade_take_profit,
            )
            trades.append(trade)
            break

    metrics = compute_metrics(trades, config_id=strategy_id)
    metrics["eligible_markets"] = len(eligible_markets)
    metrics["skipped_markets_missing_features"] = skipped_markets

    resolved_stop_loss = stop_loss
    if resolved_stop_loss is None:
        resolved_stop_loss = getattr(strategy.config, "live_stop_loss_price", None)
    if resolved_stop_loss is not None:
        metrics["stop_loss"] = resolved_stop_loss

    resolved_take_profit = take_profit
    if resolved_take_profit is None:
        resolved_take_profit = getattr(strategy.config, "live_take_profit_price", None)
    if resolved_take_profit is not None:
        metrics["take_profit"] = resolved_take_profit

    if log_summary:
        print(
            f"[{strategy_id}] Evaluating {len(eligible_markets)} markets "
            f"(skipped {skipped_markets} without required feature data) "
            f"-> {len(trades)} trades"
        )

    return trades, metrics


def _generate_reports(
    strategies: dict,
    all_metrics: list[dict],
    trades_by_config: dict[str, list[Trade]],
    markets: list[dict],
    df: pd.DataFrame,
    output_dir: str,
) -> None:
    """Generate per-strategy JSON and Markdown reports."""
    report_dir = os.path.join(output_dir, "reports", "backtest")

    date_range_start = ""
    date_range_end = ""
    if markets:
        starts = [m["started_at"] for m in markets if m.get("started_at")]
        ends = [m.get("ended_at") or m["started_at"] for m in markets if m.get("started_at")]
        if starts:
            date_range_start = str(min(starts))
        if ends:
            date_range_end = str(max(ends))

    for metrics in all_metrics:
        sid = metrics.get("config_id", "")
        if not sid or sid not in strategies:
            continue

        strategy = strategies[sid]
        trades = trades_by_config.get(sid, [])

        ranking_score = 0.0
        row = df[df["config_id"] == sid]
        if not row.empty and "ranking_score" in row.columns:
            ranking_score = float(row.iloc[0]["ranking_score"])

        config_dict = {}
        if hasattr(strategy, "config"):
            try:
                config_dict = asdict(strategy.config)
            except Exception:
                config_dict = {}

        report = StrategyReport.from_metrics(
            metrics,
            trades,
            strategy_id=sid,
            strategy_name=strategy.config.strategy_name if hasattr(strategy, "config") else sid,
            context="backtest",
            total_markets=int(metrics.get("eligible_markets", len(markets))),
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            config=config_dict,
            ranking_score=ranking_score,
        )

        report.to_json(os.path.join(report_dir, f"{sid}.json"))
        report.to_markdown(os.path.join(report_dir, f"{sid}.md"))

    print(f"  Reports saved to {report_dir}/")


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``python -m analysis.backtest_strategies``."""
    parser = argparse.ArgumentParser(
        prog="analysis.backtest_strategies",
        description="Backtest shared strategies through the analysis engine.",
    )
    parser.add_argument(
        "-s",
        "--strategy",
        default=None,
        help="Run only this strategy ID (for example S1).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default="./results/shared_strategies",
        help="Directory for results (default: ./results/shared_strategies).",
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="Comma-separated asset filter (for example BTC,ETH).",
    )
    parser.add_argument(
        "--durations",
        default=None,
        help="Comma-separated duration filter in minutes (for example 5,15).",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=DEFAULT_ENTRY_SLIPPAGE,
        help=(
            "Slippage penalty in price units "
            f"(default: {DEFAULT_ENTRY_SLIPPAGE:.2f}). "
            "Models execution lag and adverse fills."
        ),
    )
    parser.add_argument(
        "--fee-base-rate",
        type=float,
        default=None,
        help=(
            "Optional fee-rate override. By default the engine uses the "
            "official market-aware Polymarket crypto fee schedule automatically."
        ),
    )
    args = parser.parse_args(argv)

    print("Loading market data...")
    markets = data_loader.load_all_data()
    if not markets:
        print("No markets loaded. Exiting.")
        sys.exit(1)

    asset_list = args.assets.split(",") if args.assets else None
    duration_list = [int(d) for d in args.durations.split(",")] if args.durations else None
    if asset_list or duration_list:
        markets = data_loader.filter_markets(
            markets, assets=asset_list, durations=duration_list
        )
        print(f"After filtering: {len(markets)} markets")

    if args.strategy:
        strategies = {args.strategy: get_strategy(args.strategy)}
    else:
        strategies = {sid: get_strategy(sid) for sid in discover_strategies()}

    print(f"Running {len(strategies)} strategy(ies): {sorted(strategies.keys())}\n")

    all_metrics: list[dict] = []
    trades_by_config: dict[str, list[Trade]] = {}

    for sid, strat in sorted(strategies.items()):
        trades, metrics = run_strategy(
            sid,
            strat,
            markets,
            slippage=args.slippage,
            base_rate=args.fee_base_rate,
        )
        all_metrics.append(metrics)
        trades_by_config[sid] = trades

    df = pd.DataFrame(all_metrics)
    df = add_ranking_score(df)

    module_name = "shared_strategies"
    save_module_results(df, trades_by_config, module_name, args.output_dir)
    _generate_reports(
        strategies,
        all_metrics,
        trades_by_config,
        markets,
        df,
        args.output_dir,
    )

    print("\n=== Summary ===")
    for _, row in df.iterrows():
        print(
            f"  {row['config_id']}: "
            f"{row['total_bets']} bets, "
            f"WR={row['win_rate_pct']:.1f}%, "
            f"PnL={row['total_pnl']:.4f}, "
            f"Sharpe={row['sharpe_ratio']:.3f}, "
            f"Score={row['ranking_score']:.1f}"
        )
    print(f"\nResults saved to {args.output_dir}/")


if __name__ == "__main__":
    main()
