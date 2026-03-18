"""Backtest shared strategies through the analysis engine.

Bridges the shared strategy framework (``shared.strategies``) into the
existing analysis backtest infrastructure (``analysis.backtest``).  Converts
``data_loader`` market dicts into :class:`MarketSnapshot` objects, evaluates
strategies via the shared registry, converts returned :class:`Signal` objects
into :class:`Trade` objects using the existing engine, and computes/saves
performance metrics.

Produces per-strategy reports in both JSON and Markdown via
:class:`StrategyReport` — the same format used by the trading bot — so
agents can compare backtest vs live side-by-side.

Usage::

    cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1
    cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --assets BTC,ETH --durations 5

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
from shared.strategies import MarketSnapshot, StrategyReport, discover_strategies, get_strategy


# ── Conversion ──────────────────────────────────────────────────────


def market_to_snapshot(market: dict) -> MarketSnapshot:
    """Convert a data_loader market dict to a :class:`MarketSnapshot`.

    In backtest mode ``elapsed_seconds`` equals ``total_seconds`` because the
    full price series is available for evaluation.
    """
    return MarketSnapshot(
        market_id=market["market_id"],
        market_type=market["market_type"],
        prices=market["prices"],  # numpy ndarray, seconds-indexed, NaN for missing
        total_seconds=market["total_seconds"],
        elapsed_seconds=market["total_seconds"],  # backtest: full market data
        metadata={
            "asset": market["asset"],
            "hour": market["hour"],
            "started_at": market["started_at"],
            "final_outcome": market["final_outcome"],
            "duration_minutes": market["duration_minutes"],
        },
    )


# ── Strategy runner ─────────────────────────────────────────────────


def run_strategy(
    strategy_id: str,
    strategy,
    markets: list[dict],
    slippage: float = 0.0,
    base_rate: float = 0.063,
    *,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> tuple[list[Trade], dict]:
    """Run a single strategy against all *markets*.

    Returns ``(trades, metrics)`` where *trades* is a list of
    :class:`Trade` objects and *metrics* is a dict produced by
    :func:`engine.compute_metrics`.
    """
    trades: list[Trade] = []

    for market in markets:
        snapshot = market_to_snapshot(market)
        signal = strategy.evaluate(snapshot)

        if signal is not None:
            second_entered = signal.signal_data.get(
                "entry_second", signal.signal_data.get("reversion_second", 0)
            )
            trade = make_trade(
                market,
                second_entered,
                signal.entry_price,
                signal.direction,
                slippage=slippage,
                base_rate=base_rate,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
            trades.append(trade)

    metrics = compute_metrics(trades, config_id=strategy_id)
    
    # Augment metrics with SL/TP parameters if provided
    if stop_loss is not None:
        metrics['stop_loss'] = stop_loss
    if take_profit is not None:
        metrics['take_profit'] = take_profit

    print(
        f"[{strategy_id}] Evaluating {len(markets)} markets "
        f"→ {len(trades)} trades"
    )

    return trades, metrics


# ── Report generation ───────────────────────────────────────────────


def _generate_reports(
    strategies: dict,
    all_metrics: list[dict],
    trades_by_config: dict[str, list[Trade]],
    markets: list[dict],
    df: pd.DataFrame,
    output_dir: str,
) -> None:
    """Generate per-strategy JSON + Markdown reports in the shared format."""
    report_dir = os.path.join(output_dir, "reports", "backtest")

    # Compute date range from market data
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

        # Get ranking score from the DataFrame
        ranking_score = 0.0
        row = df[df["config_id"] == sid]
        if not row.empty and "ranking_score" in row.columns:
            ranking_score = float(row.iloc[0]["ranking_score"])

        # Get strategy config as dict
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
            total_markets=len(markets),
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            config=config_dict,
            ranking_score=ranking_score,
        )

        report.to_json(os.path.join(report_dir, f"{sid}.json"))
        report.to_markdown(os.path.join(report_dir, f"{sid}.md"))

    print(f"  Reports saved to {report_dir}/")


# ── CLI ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``python3 -m analysis.backtest_strategies``."""
    parser = argparse.ArgumentParser(
        prog="analysis.backtest_strategies",
        description="Backtest shared strategies through the analysis engine.",
    )
    parser.add_argument(
        "-s",
        "--strategy",
        default=None,
        help="Run only this strategy ID (e.g. S1). Omit to run all discovered strategies.",
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
        help="Comma-separated asset filter (e.g. BTC,ETH).",
    )
    parser.add_argument(
        "--durations",
        default=None,
        help="Comma-separated duration filter in minutes (e.g. 5,15).",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=0.0,
        help="Slippage penalty in price units (default: 0.0). "
             "Models execution lag — Up bets pay more, Down bets worse fill.",
    )
    parser.add_argument(
        "--fee-base-rate",
        type=float,
        default=0.063,
        help="Polymarket dynamic fee base rate (default: 0.063). "
             "Produces ~3.15%% peak fee at 50/50 prices.",
    )
    args = parser.parse_args(argv)

    # ── Load market data ────────────────────────────────────────────
    print("Loading market data...")
    markets = data_loader.load_all_data()
    if not markets:
        print("No markets loaded. Exiting.")
        sys.exit(1)

    # Apply filters
    asset_list = args.assets.split(",") if args.assets else None
    duration_list = (
        [int(d) for d in args.durations.split(",")]
        if args.durations
        else None
    )
    if asset_list or duration_list:
        markets = data_loader.filter_markets(
            markets, assets=asset_list, durations=duration_list
        )
        print(f"After filtering: {len(markets)} markets")

    # ── Discover / select strategies ────────────────────────────────
    if args.strategy:
        strategy = get_strategy(args.strategy)
        strategies = {args.strategy: strategy}
    else:
        strategy_classes = discover_strategies()
        strategies = {}
        for sid in strategy_classes:
            strategies[sid] = get_strategy(sid)

    print(f"Running {len(strategies)} strategy(ies): {sorted(strategies.keys())}\n")

    # ── Run strategies ──────────────────────────────────────────────
    all_metrics: list[dict] = []
    trades_by_config: dict[str, list[Trade]] = {}

    for sid, strat in sorted(strategies.items()):
        trades, metrics = run_strategy(
            sid, strat, markets, 
            slippage=args.slippage, 
            base_rate=args.fee_base_rate
        )
        all_metrics.append(metrics)
        trades_by_config[sid] = trades

    # ── Build results DataFrame ─────────────────────────────────────
    df = pd.DataFrame(all_metrics)
    df = add_ranking_score(df)

    # ── Save existing results (CSV, best configs, markdown) ─────────
    module_name = "shared_strategies"
    save_module_results(df, trades_by_config, module_name, args.output_dir)

    # ── Save shared-format reports (JSON + Markdown per strategy) ───
    _generate_reports(strategies, all_metrics, trades_by_config, markets, df, args.output_dir)

    # ── Summary ─────────────────────────────────────────────────────
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
