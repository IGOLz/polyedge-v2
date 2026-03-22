"""Paper scanner for live weather merge candidates derived from wallet forensics."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.wallet_forensics.fetchers import WalletForensicsClient
from analysis.wallet_forensics.utils import ensure_dir, safe_float
from shared.db import close_pool, init_pool
from weather.storage import fetch_active_weather_contexts

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Paper scan current weather markets for merge candidates")
    identity_group = parser.add_mutually_exclusive_group(required=True)
    identity_group.add_argument("--profile", type=str, help="Polymarket profile name, for example ColdMath")
    identity_group.add_argument("--wallet", type=str, help="Proxy wallet address to analyze")
    parser.add_argument(
        "--config-path",
        type=str,
        default=None,
        help="Optional explicit path to wallet_inventory_rebalancing_merge_backtest_bot_config.json",
    )
    parser.add_argument("--output-dir", type=str, default=None, help="Artifact output directory")
    parser.add_argument("--verbose", action="store_true", help="Enable info logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = run_paper_scan(args)
    logger.info("Paper scan complete for %s with %d candidates", result["target"]["proxy_wallet"], result["candidate_count"])
    return 0


def run_paper_scan(args: argparse.Namespace | list[str] | None = None) -> dict[str, Any]:
    if not isinstance(args, argparse.Namespace):
        args = build_parser().parse_args(args)

    client = WalletForensicsClient()
    try:
        target = _resolve_target(client, args)
        output_dir = _resolve_output_dir(args, target)
        config_path = _resolve_config_path(args, target, output_dir)
        bot_config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        candidates = asyncio.run(
            scan_inventory_merge_candidates(
                complete_set_cost_lte=float(bot_config["entry_rule"]["complete_set_cost_lte"]),
            )
        )
        export_paper_scan_artifacts(
            output_dir=output_dir,
            target=target,
            bot_config=bot_config,
            candidates=candidates,
        )
        return {
            "target": target,
            "output_dir": str(output_dir),
            "config_path": str(config_path),
            "candidate_count": len(candidates),
        }
    finally:
        client.close()


async def scan_inventory_merge_candidates(
    *,
    complete_set_cost_lte: float,
) -> list[dict[str, Any]]:
    await init_pool()
    contexts = await fetch_active_weather_contexts(eligible_only=True)
    candidates: list[dict[str, Any]] = []
    try:
        for context in contexts:
            for market in context.markets:
                yes_ask = safe_float(market.yes_ask)
                no_ask = safe_float(market.no_ask)
                yes_ask_size = safe_float(market.yes_ask_size)
                no_ask_size = safe_float(market.no_ask_size)
                if yes_ask is None or no_ask is None:
                    continue
                combined_cost = yes_ask + no_ask
                if combined_cost > complete_set_cost_lte:
                    continue
                candidates.append(
                    {
                        "event_id": context.event_id,
                        "event_slug": context.event_slug,
                        "city": context.city,
                        "local_date": context.local_date.isoformat() if context.local_date else None,
                        "market_id": market.market_id,
                        "bucket_label": market.bucket_label,
                        "yes_ask": yes_ask,
                        "no_ask": no_ask,
                        "yes_ask_size": yes_ask_size,
                        "no_ask_size": no_ask_size,
                        "combined_cost": combined_cost,
                        "merge_edge": 1.0 - combined_cost,
                        "max_mergeable_size": min(yes_ask_size or 0.0, no_ask_size or 0.0),
                        "latest_quote_time": market.latest_quote_time,
                    }
                )
    finally:
        await close_pool()
    candidates.sort(
        key=lambda item: (item["merge_edge"], item["max_mergeable_size"]),
        reverse=True,
    )
    return candidates


def export_paper_scan_artifacts(
    *,
    output_dir: Path,
    target: dict[str, Any],
    bot_config: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> None:
    ensure_dir(output_dir)
    base_name = "wallet_inventory_rebalancing_merge_paper_scan"
    pd.DataFrame(candidates).to_csv(output_dir / f"{base_name}.csv", index=False)
    (output_dir / f"{base_name}.md").write_text(
        build_paper_scan_markdown(
            target=target,
            bot_config=bot_config,
            candidates=candidates,
        ),
        encoding="utf-8",
    )


def build_paper_scan_markdown(
    *,
    target: dict[str, Any],
    bot_config: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> str:
    threshold = bot_config["entry_rule"]["complete_set_cost_lte"]
    lines = [
        "# Inventory Merge Paper Scan",
        "",
        "## Overview",
        f"- Profile: `{target.get('profile_name') or target['proxy_wallet']}`",
        f"- Proxy wallet: `{target['proxy_wallet']}`",
        f"- Complete set threshold: `{threshold}`",
        f"- Candidate count: `{len(candidates)}`",
        "",
        "## Top Candidates",
    ]
    if not candidates:
        lines.append("- No current weather markets satisfy the merge threshold.")
        return "\n".join(lines) + "\n"

    for row in candidates[:20]:
        lines.append(
            "- "
            f"`{row['city']}` `{row['local_date']}` `{row['bucket_label']}` | "
            f"cost `{row['combined_cost']:.4f}` | edge `{row['merge_edge']:.4f}` | "
            f"yes ask `{row['yes_ask']:.4f}` | no ask `{row['no_ask']:.4f}` | "
            f"mergeable size `{row['max_mergeable_size']:.2f}`"
        )
    return "\n".join(lines) + "\n"


def _resolve_target(client: WalletForensicsClient, args: argparse.Namespace) -> dict[str, Any]:
    if args.profile:
        resolved = client.resolve_wallet(args.profile)
        wallet = _extract_wallet(resolved)
        if not wallet:
            raise RuntimeError(f"Could not resolve proxy wallet for profile {args.profile!r}")
        profile_name = resolved.get("name") or args.profile
    else:
        wallet = str(args.wallet or "").strip().lower()
        if not wallet:
            raise RuntimeError("Wallet address is required")
        profile_name = None
    return {
        "proxy_wallet": wallet,
        "profile_name": profile_name,
    }


def _extract_wallet(payload: dict[str, Any]) -> str | None:
    for key in ("proxyWallet", "proxy_wallet", "walletAddress", "wallet", "address"):
        value = payload.get(key)
        if value:
            return str(value).strip().lower()
    return None


def _resolve_output_dir(args: argparse.Namespace, target: dict[str, Any]) -> Path:
    if args.output_dir:
        return ensure_dir(Path(args.output_dir).resolve())
    label = str(target.get("profile_name") or target["proxy_wallet"]).lower().replace("/", "-")
    return ensure_dir(Path(__file__).resolve().parents[2] / "results" / "wallet_forensics" / label)


def _resolve_config_path(args: argparse.Namespace, target: dict[str, Any], output_dir: Path) -> Path:
    if args.config_path:
        return Path(args.config_path).resolve()
    default_path = output_dir / "wallet_inventory_rebalancing_merge_backtest_bot_config.json"
    if default_path.exists():
        return default_path
    label = str(target.get("profile_name") or target["proxy_wallet"]).lower().replace("/", "-")
    fallback = Path(__file__).resolve().parents[2] / "results" / "wallet_forensics" / label / default_path.name
    if fallback.exists():
        return fallback
    raise RuntimeError("Could not find inventory merge bot config JSON; run the merge backtest first or pass --config-path")


if __name__ == "__main__":
    raise SystemExit(main())
