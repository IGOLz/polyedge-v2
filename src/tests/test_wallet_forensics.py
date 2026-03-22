from __future__ import annotations

import unittest
import asyncio
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from analysis.wallet_forensics.constants import (
    CTF_ADDRESS,
    CTF_EXCHANGE_ADDRESS,
    CTF_MERGE_TOPIC,
    CTF_REDEEM_TOPIC,
    CTF_SPLIT_TOPIC,
    ERC20_TRANSFER_TOPIC,
    ERC1155_TRANSFER_SINGLE_TOPIC,
    EXCHANGE_TRADE_TOPICS,
    USDC_ADDRESS,
)
from analysis.wallet_forensics.decoder import decode_receipt_for_wallet
from analysis.wallet_forensics.fetchers import WalletForensicsClient, collect_offset_pages, collect_time_sliced_pages
from analysis.wallet_forensics.fill_context import (
    build_fill_context_row,
    _fetch_price_history_range,
    _normalize_price_history_points,
)
from analysis.wallet_forensics.inference import build_shadow_replay, infer_strategies
from analysis.wallet_forensics.ledger import build_wallet_ledger
from analysis.wallet_forensics.main import _receipt_map, _should_persist_derived_rows
from analysis.wallet_forensics.backtest import (
    build_inventory_merge_bot_config,
    build_inventory_merge_grid,
    evaluate_inventory_merge_grid,
    rank_inventory_merge_results,
    select_best_inventory_merge_config,
    select_inventory_merge_sequences,
)
from analysis.wallet_forensics.paper_scan import build_paper_scan_markdown, scan_inventory_merge_candidates
from analysis.wallet_forensics.playbooks import build_strategy_blueprints, extract_playbook_sequences
from analysis.wallet_forensics.report import (
    build_fill_context_markdown,
    build_fill_context_summary,
    build_rule_summary,
    build_rule_summary_markdown,
    build_strategy_blueprint_markdown,
    export_fill_context_artifacts,
    export_artifacts,
)
from analysis.wallet_forensics.state import (
    backfill_state_path,
    event_context_pending,
    finalize_backfill_state,
    load_or_create_backfill_state,
    mark_event_context_completed,
    mark_market_stage,
    mark_stage_completed,
    pending_markets,
    save_backfill_state,
    summarize_backfill_state,
    sync_market_universe,
    update_receipt_progress,
)
from analysis.wallet_forensics.weather_enrichment import enrich_ledger_with_weather
from weather.models import WeatherBucketMarket, WeatherMarketContext


def _padded_topic(address: str) -> str:
    return "0x" + ("0" * 24) + address.lower().removeprefix("0x")


def _uint256(value: int) -> str:
    return "0x" + f"{value:064x}"


def _erc1155_single_data(token_id: int, amount: int) -> str:
    return "0x" + f"{token_id:064x}" + f"{amount:064x}"


class WalletForensicsFetchersTests(unittest.TestCase):
    def test_collect_offset_pages_deduplicates_rows_across_pages(self):
        pages = {
            0: [{"id": 1}, {"id": 2}],
            2: [{"id": 2}, {"id": 3}],
            4: [],
        }

        rows = collect_offset_pages(lambda offset, limit: pages.get(offset, []), limit=2)

        self.assertEqual([row["id"] for row in rows], [1, 2, 3])

    def test_collect_time_sliced_pages_splits_when_offset_cap_is_hit(self):
        rows = [
            {"timestamp": ts, "transactionHash": f"0x{ts}"}
            for ts in range(1, 7)
        ]

        def fetch_page(offset: int, limit: int, start: int, end: int):
            window_rows = [row for row in rows if start <= row["timestamp"] <= end]
            return window_rows[offset: offset + limit]

        with patch("analysis.wallet_forensics.fetchers.MAX_OFFSET", 2), patch(
            "analysis.wallet_forensics.fetchers.MIN_SPLIT_WINDOW_SECONDS", 1
        ):
            result = collect_time_sliced_pages(fetch_page=fetch_page, start_ts=1, end_ts=6, limit=2)

        self.assertEqual([row["timestamp"] for row in result], [1, 2, 3, 4, 5, 6])

    def test_collect_time_sliced_pages_splits_on_api_offset_error(self):
        rows = [
            {"timestamp": ts, "transactionHash": f"0x{ts}"}
            for ts in range(1, 7)
        ]

        def fetch_page(offset: int, limit: int, start: int, end: int):
            if offset >= 4:
                request = httpx.Request("GET", "https://data-api.polymarket.com/trades")
                response = httpx.Response(
                    400,
                    request=request,
                    json={"error": "max historical activity offset of 3000 exceeded"},
                )
                raise httpx.HTTPStatusError("offset cap", request=request, response=response)
            window_rows = [row for row in rows if start <= row["timestamp"] <= end]
            return window_rows[offset: offset + limit]

        with patch("analysis.wallet_forensics.fetchers.MIN_SPLIT_WINDOW_SECONDS", 1):
            result = collect_time_sliced_pages(fetch_page=fetch_page, start_ts=1, end_ts=6, limit=2)

        self.assertEqual([row["timestamp"] for row in result], [1, 2, 3, 4, 5, 6])

    def test_fetch_positions_uses_endpoint_specific_sorting(self):
        client = WalletForensicsClient()
        calls: list[tuple[str, dict[str, object]]] = []

        def fake_get_json(url: str, **kwargs):
            calls.append((url, kwargs["params"]))
            return []

        client._get_json = fake_get_json  # type: ignore[method-assign]
        try:
            client.fetch_positions("0xwallet", closed=False)
            client.fetch_positions("0xwallet", closed=True)
        finally:
            client.close()

        self.assertEqual(calls[0][0], "https://data-api.polymarket.com/positions")
        self.assertEqual(calls[0][1]["sortBy"], "TOKENS")
        self.assertEqual(calls[1][0], "https://data-api.polymarket.com/closed-positions")
        self.assertEqual(calls[1][1]["sortBy"], "TIMESTAMP")

    def test_client_retries_rate_limits_before_returning_json(self):
        client = WalletForensicsClient()
        request = httpx.Request("GET", "https://example.test")
        responses = [
            httpx.Response(429, request=request, headers={"Retry-After": "0"}, json={"error": "slow down"}),
            httpx.Response(200, request=request, json={"ok": True}),
        ]

        def fake_request(method: str, url: str, **kwargs):
            return responses.pop(0)

        client._http.request = fake_request  # type: ignore[method-assign]
        try:
            with patch("analysis.wallet_forensics.fetchers.time.sleep") as sleep_mock:
                payload = client._get_json("https://example.test")
        finally:
            client.close()

        self.assertEqual(payload, {"ok": True})
        sleep_mock.assert_called_once()

    def test_fetch_activity_and_trades_apply_market_filters(self):
        client = WalletForensicsClient()
        calls: list[tuple[str, dict[str, object]]] = []

        def fake_get_json(url: str, **kwargs):
            calls.append((url, kwargs["params"]))
            return []

        client._get_json = fake_get_json  # type: ignore[method-assign]
        try:
            client.fetch_activity("0xwallet", markets=["market-a", "market-b"])
            client.fetch_trades("0xwallet", markets=["market-a"])
        finally:
            client.close()

        self.assertEqual(calls[0][0], "https://data-api.polymarket.com/activity")
        self.assertEqual(calls[0][1]["market"], "market-a")
        self.assertEqual(calls[1][1]["market"], "market-b")
        self.assertEqual(calls[2][0], "https://data-api.polymarket.com/trades")
        self.assertEqual(calls[2][1]["market"], "market-a")

    def test_fetch_prices_history_uses_clob_history_endpoint(self):
        client = WalletForensicsClient()
        calls: list[tuple[str, dict[str, object]]] = []

        def fake_get_json(url: str, **kwargs):
            calls.append((url, kwargs["params"]))
            return {"history": [{"t": 1, "p": 0.42}]}

        client._get_json = fake_get_json  # type: ignore[method-assign]
        try:
            rows = client.fetch_prices_history("token-1", start_ts=10, end_ts=20, fidelity=5)
        finally:
            client.close()

        self.assertEqual(rows, [{"t": 1, "p": 0.42}])
        self.assertEqual(calls[0][0], "https://clob.polymarket.com/prices-history")
        self.assertEqual(calls[0][1]["market"], "token-1")
        self.assertEqual(calls[0][1]["startTs"], 10)
        self.assertEqual(calls[0][1]["endTs"], 20)
        self.assertEqual(calls[0][1]["fidelity"], 5)

    def test_fetch_transaction_receipts_batches_and_maps_results(self):
        client = WalletForensicsClient()

        def fake_post_json(url: str, payload):
            self.assertEqual(url, "https://polygon-bor-rpc.publicnode.com")
            self.assertEqual(len(payload), 2)
            return [
                {"jsonrpc": "2.0", "id": "0xbbb", "result": {"transactionHash": "0xbbb"}},
                {"jsonrpc": "2.0", "id": "0xaaa", "result": {"transactionHash": "0xaaa"}},
            ]

        client._post_json = fake_post_json  # type: ignore[method-assign]
        try:
            receipts = client.fetch_transaction_receipts(["0xaaa", "0xbbb"])
        finally:
            client.close()

        self.assertEqual(receipts["0xaaa"], {"transactionHash": "0xaaa"})
        self.assertEqual(receipts["0xbbb"], {"transactionHash": "0xbbb"})

    def test_fetch_transaction_receipts_falls_back_for_missing_batch_items(self):
        client = WalletForensicsClient()

        def fake_post_json(url: str, payload):
            return [{"jsonrpc": "2.0", "id": "0xaaa", "result": {"transactionHash": "0xaaa"}}]

        def fake_single(tx_hash: str):
            return {"transactionHash": tx_hash, "via": "single"}

        client._post_json = fake_post_json  # type: ignore[method-assign]
        client.fetch_transaction_receipt = fake_single  # type: ignore[method-assign]
        try:
            receipts = client.fetch_transaction_receipts(["0xaaa", "0xbbb"])
        finally:
            client.close()

        self.assertEqual(receipts["0xaaa"], {"transactionHash": "0xaaa"})
        self.assertEqual(receipts["0xbbb"], {"transactionHash": "0xbbb", "via": "single"})

    def test_fetch_activity_falls_back_to_time_sliced_pagination_on_offset_cap(self):
        client = WalletForensicsClient()
        with patch(
            "analysis.wallet_forensics.fetchers.collect_offset_pages",
            side_effect=RuntimeError("Offset pagination exceeded public API limit"),
        ), patch(
            "analysis.wallet_forensics.fetchers.collect_time_sliced_pages",
            return_value=[{"timestamp": 10, "transactionHash": "0x10"}],
        ) as sliced_mock:
            try:
                rows = client.fetch_activity(
                    "0xwallet",
                    markets=["market-a"],
                    start_ts=1,
                    end_ts=20,
                )
            finally:
                client.close()

        self.assertEqual(rows, [{"timestamp": 10, "transactionHash": "0x10"}])
        sliced_mock.assert_called_once()

    def test_fetch_trades_falls_back_to_activity_trade_reconstruction_on_offset_cap(self):
        client = WalletForensicsClient()

        def fake_fetch_activity(*args, **kwargs):
            return [
                {
                    "type": "TRADE",
                    "timestamp": 10,
                    "transactionHash": "0x10",
                    "conditionId": "cond-1",
                    "asset": "yes-1",
                    "side": "BUY",
                    "outcome": "Yes",
                    "size": 5.0,
                    "price": 0.22,
                    "eventSlug": "weather-a",
                    "slug": "weather-a",
                    "title": "Weather A",
                    "usdcSize": 1.1,
                },
                {
                    "type": "MERGE",
                    "timestamp": 11,
                    "transactionHash": "0x11",
                },
            ]

        client.fetch_activity = fake_fetch_activity  # type: ignore[method-assign]
        with patch(
            "analysis.wallet_forensics.fetchers.collect_offset_pages",
            side_effect=RuntimeError("Offset pagination exceeded public API limit"),
        ):
            try:
                rows = client.fetch_trades(
                    "0xwallet",
                    markets=["market-a"],
                    start_ts=1,
                    end_ts=20,
                )
            finally:
                client.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["transactionHash"], "0x10")
        self.assertNotIn("type", rows[0])
        self.assertNotIn("usdcSize", rows[0])


class WalletForensicsDecoderTests(unittest.TestCase):
    def test_decode_receipt_classifies_trade_and_wallet_flows(self):
        wallet = "0x1111111111111111111111111111111111111111"
        token_id = 123456789
        receipt = {
            "transactionHash": "0xtrade",
            "blockNumber": "0x10",
            "logs": [
                {
                    "address": USDC_ADDRESS,
                    "topics": [
                        ERC20_TRANSFER_TOPIC,
                        _padded_topic(wallet),
                        _padded_topic(CTF_EXCHANGE_ADDRESS),
                    ],
                    "data": _uint256(1_500_000),
                    "blockTimestamp": "0x65",
                },
                {
                    "address": CTF_ADDRESS,
                    "topics": [
                        ERC1155_TRANSFER_SINGLE_TOPIC,
                        _padded_topic("0x2222222222222222222222222222222222222222"),
                        _padded_topic("0x0000000000000000000000000000000000000000"),
                        _padded_topic(wallet),
                    ],
                    "data": _erc1155_single_data(token_id, 10),
                    "blockTimestamp": "0x65",
                },
                {
                    "address": CTF_EXCHANGE_ADDRESS,
                    "topics": [next(iter(EXCHANGE_TRADE_TOPICS))],
                    "data": "0x",
                    "blockTimestamp": "0x65",
                },
            ],
        }

        decoded = decode_receipt_for_wallet(receipt, wallet, activity_types=("TRADE",))

        self.assertIn("trade", decoded["classifications"])
        self.assertEqual(decoded["usdc_out"], 1_500_000.0)
        self.assertEqual(decoded["usdc_in"], 0.0)
        self.assertEqual(len(decoded["wallet_token_ids_in"]), 1)
        self.assertEqual(decoded["block_number"], 16)
        self.assertEqual(decoded["block_timestamp"], 101)

    def test_decode_receipt_classifies_split_merge_redeem_and_conversion(self):
        wallet = "0x1111111111111111111111111111111111111111"
        split_receipt = {
            "transactionHash": "0xsplit",
            "blockNumber": "0x11",
            "logs": [{"address": CTF_ADDRESS, "topics": [CTF_SPLIT_TOPIC], "data": "0x"}],
        }
        merge_receipt = {
            "transactionHash": "0xmerge",
            "blockNumber": "0x12",
            "logs": [{"address": CTF_ADDRESS, "topics": [CTF_MERGE_TOPIC], "data": "0x"}],
        }
        redeem_receipt = {
            "transactionHash": "0xredeem",
            "blockNumber": "0x13",
            "logs": [{"address": CTF_ADDRESS, "topics": [CTF_REDEEM_TOPIC], "data": "0x"}],
        }

        self.assertIn("split", decode_receipt_for_wallet(split_receipt, wallet)["classifications"])
        self.assertIn("merge", decode_receipt_for_wallet(merge_receipt, wallet)["classifications"])
        self.assertIn("redeem", decode_receipt_for_wallet(redeem_receipt, wallet)["classifications"])
        self.assertIn(
            "conversion",
            decode_receipt_for_wallet(None, wallet, activity_types=("CONVERSION",))["classifications"],
        )


class WalletForensicsLedgerTests(unittest.TestCase):
    def test_build_wallet_ledger_final_snapshot_mode_only_keeps_terminal_positions(self):
        activity_rows = [
            {
                "timestamp": 1,
                "transaction_hash": "0x1",
                "condition_id": "cond-1",
                "event_type": "TRADE",
                "asset": "yes-1",
                "side": "BUY",
                "outcome": "Yes",
                "size": 10.0,
                "price": 0.30,
                "usdc_size": 3.0,
                "event_slug": "weather-a",
            },
            {
                "timestamp": 2,
                "transaction_hash": "0x2",
                "condition_id": "cond-1",
                "event_type": "TRADE",
                "asset": "yes-1",
                "side": "SELL",
                "outcome": "Yes",
                "size": 4.0,
                "price": 0.40,
                "usdc_size": 1.6,
                "event_slug": "weather-a",
            },
        ]

        _, history_snapshots = build_wallet_ledger(
            proxy_wallet="0xwallet",
            activity_rows=activity_rows,
            receipt_rows={},
            market_context={},
            closed_positions_rows=[],
        )
        _, final_snapshots = build_wallet_ledger(
            proxy_wallet="0xwallet",
            activity_rows=activity_rows,
            receipt_rows={},
            market_context={},
            closed_positions_rows=[],
            snapshot_mode="final",
        )

        self.assertGreater(len(history_snapshots), len(final_snapshots))
        self.assertEqual(len(final_snapshots), 1)
        self.assertEqual(final_snapshots[0]["ledger_event_id"], history_snapshots[-1]["ledger_event_id"])
        self.assertAlmostEqual(final_snapshots[0]["position_size"], 6.0)

    def test_build_wallet_ledger_keeps_compact_source_details(self):
        activity_rows = [
            {
                "timestamp": 1,
                "transaction_hash": "0x1",
                "condition_id": "cond-1",
                "event_type": "TRADE",
                "asset": "yes-1",
                "side": "BUY",
                "outcome": "Yes",
                "size": 10.0,
                "price": 0.30,
                "usdc_size": 3.0,
                "event_slug": "weather-a",
            },
        ]
        receipt_rows = {
            "0x1": {
                "transaction_hash": "0x1",
                "block_number": 42,
                "block_timestamp": 123,
                "classifications": ["trade"],
                "touched_contracts": ["0xabc"],
                "usdc_in": 0.0,
                "usdc_out": 3.0,
            }
        }

        ledger_rows, _ = build_wallet_ledger(
            proxy_wallet="0xwallet",
            activity_rows=activity_rows,
            receipt_rows=receipt_rows,
            market_context={},
            closed_positions_rows=[],
        )

        row = ledger_rows[0]
        self.assertIn("receipt_summary", row["payload_json"])
        self.assertNotIn("payload_json", row["payload_json"]["receipt_summary"])
        self.assertEqual(row["source_details_json"]["receipt_classifications"], ["trade"])
        self.assertEqual(row["source_details_json"]["touched_contracts"], ["0xabc"])
        self.assertNotEqual(row["payload_json"], row["source_details_json"])

    def test_build_wallet_ledger_handles_both_side_buys_and_merge(self):
        activity_rows = [
            {
                "timestamp": 1,
                "transaction_hash": "0x1",
                "condition_id": "cond-1",
                "event_type": "TRADE",
                "asset": "yes-1",
                "side": "BUY",
                "outcome": "Yes",
                "size": 10.0,
                "price": 0.30,
                "usdc_size": 3.0,
                "event_slug": "highest-temperature-in-chengdu-on-august-16",
            },
            {
                "timestamp": 2,
                "transaction_hash": "0x2",
                "condition_id": "cond-1",
                "event_type": "TRADE",
                "asset": "no-1",
                "side": "BUY",
                "outcome": "No",
                "size": 10.0,
                "price": 0.60,
                "usdc_size": 6.0,
                "event_slug": "highest-temperature-in-chengdu-on-august-16",
            },
            {
                "timestamp": 3,
                "transaction_hash": "0x3",
                "condition_id": "cond-1",
                "event_type": "MERGE",
                "size": 10.0,
                "usdc_size": 10.0,
                "event_slug": "highest-temperature-in-chengdu-on-august-16",
            },
        ]
        market_context = {
            "cond-1": {
                "market_id": "cond-1",
                "event_slug": "highest-temperature-in-chengdu-on-august-16",
                "yes_token_id": "yes-1",
                "no_token_id": "no-1",
            }
        }

        ledger_rows, snapshots = build_wallet_ledger(
            proxy_wallet="0xwallet",
            activity_rows=activity_rows,
            receipt_rows={},
            market_context=market_context,
            closed_positions_rows=[],
        )

        merge_row = next(row for row in ledger_rows if row["event_type"] == "merge")
        final_snapshots = [row for row in snapshots if row["ledger_event_id"] == merge_row["ledger_event_id"]]

        self.assertAlmostEqual(merge_row["realized_pnl"], 1.0)
        self.assertTrue(final_snapshots)
        self.assertTrue(all(abs(row["position_size"]) < 1e-9 for row in final_snapshots))

    def test_build_wallet_ledger_handles_conversion_and_rewards(self):
        activity_rows = [
            {
                "timestamp": 1,
                "transaction_hash": "0xa1",
                "condition_id": "cond-a",
                "event_type": "TRADE",
                "asset": "no-a",
                "side": "BUY",
                "outcome": "No",
                "size": 5.0,
                "price": 0.40,
                "usdc_size": 2.0,
                "event_slug": "weather-a",
            },
            {
                "timestamp": 2,
                "transaction_hash": "0xa2",
                "condition_id": "cond-a",
                "event_type": "CONVERSION",
                "size": 5.0,
                "event_slug": "weather-a",
            },
            {
                "timestamp": 3,
                "transaction_hash": "0xa3",
                "condition_id": "cond-a",
                "event_type": "REWARD",
                "usdc_size": 0.25,
                "event_slug": "weather-a",
            },
        ]
        market_context = {
            "cond-a": {
                "market_id": "cond-a",
                "event_slug": "weather-a",
                "no_token_id": "no-a",
                "sibling_market_ids": ["cond-a", "cond-b", "cond-c"],
            },
            "cond-b": {"market_id": "cond-b", "event_slug": "weather-a", "yes_token_id": "yes-b"},
            "cond-c": {"market_id": "cond-c", "event_slug": "weather-a", "yes_token_id": "yes-c"},
        }

        ledger_rows, snapshots = build_wallet_ledger(
            proxy_wallet="0xwallet",
            activity_rows=activity_rows,
            receipt_rows={},
            market_context=market_context,
            closed_positions_rows=[],
        )

        mint_legs = [row for row in ledger_rows if row["event_type"] == "conversion_mint_leg"]
        reward_row = next(row for row in ledger_rows if row["event_type"] == "reward")
        reward_snapshots = [row for row in snapshots if row["ledger_event_id"] == reward_row["ledger_event_id"]]

        self.assertEqual(len(mint_legs), 2)
        self.assertAlmostEqual(reward_row["realized_pnl"], 0.25)
        self.assertEqual({row["asset"] for row in reward_snapshots}, {"yes-b", "yes-c", "no-a"})
        yes_b = next(row for row in reward_snapshots if row["asset"] == "yes-b")
        yes_c = next(row for row in reward_snapshots if row["asset"] == "yes-c")
        self.assertAlmostEqual(yes_b["cost_basis"], 1.0)
        self.assertAlmostEqual(yes_c["cost_basis"], 1.0)


class WalletForensicsWeatherTests(unittest.TestCase):
    def test_weather_enrichment_attaches_latest_forecast_observation_and_rounds_negative_values(self):
        ledger_rows = [
            {
                "ledger_event_id": "ledger-1",
                "condition_id": "market-1",
                "occurred_at": datetime(2026, 3, 22, 13, 30, tzinfo=UTC),
                "event_slug": "highest-temperature-in-berlin-on-march-22-2026",
                "event_type": "trade",
                "asset": "yes-1",
                "outcome": "Yes",
                "side": "buy",
                "size": 1.0,
                "price": 0.20,
                "realized_pnl": 0.0,
            }
        ]
        market_context = {
            "market-1": {
                "event_slug": "highest-temperature-in-berlin-on-march-22-2026",
                "question": "Highest temperature in Berlin on March 22, 2026",
                "end_date": datetime(2026, 3, 22, 18, 0, tzinfo=UTC),
            }
        }
        weather_market_rows = {
            "market-1": {
                "city": "Berlin",
                "station_code": "EDDB",
                "timezone": "Europe/Berlin",
                "local_date": date(2026, 3, 22),
                "bucket_label": "-1C or below",
                "bucket_low": None,
                "bucket_high": -1.0,
                "resolution_precision_scale": 0,
            }
        }
        forecast_rows_by_market = {
            "market-1": [
                {
                    "run_at": datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
                    "captured_at": datetime(2026, 3, 22, 12, 5, tzinfo=UTC),
                    "payload_json": {
                        "hourly": {
                            "temperature_2m_member01": [-0.2],
                            "temperature_2m_member02": [-1.2],
                            "temperature_2m_member03": [-1.4],
                        }
                    },
                },
                {
                    "run_at": datetime(2026, 3, 22, 13, 0, tzinfo=UTC),
                    "captured_at": datetime(2026, 3, 22, 13, 5, tzinfo=UTC),
                    "payload_json": {
                        "hourly": {
                            "temperature_2m_member01": [-0.4],
                            "temperature_2m_member02": [-0.6],
                            "temperature_2m_member03": [-1.2],
                        }
                    },
                },
            ]
        }
        observations_by_station = {
            "EDDB": [
                {"observed_at": datetime(2026, 3, 22, 13, 20, tzinfo=UTC), "temperature": -0.5},
                {"observed_at": datetime(2026, 3, 22, 12, 20, tzinfo=UTC), "temperature": -1.2},
            ]
        }

        enriched = enrich_ledger_with_weather(
            ledger_rows=ledger_rows,
            market_context=market_context,
            weather_market_rows=weather_market_rows,
            forecast_rows_by_market=forecast_rows_by_market,
            observations_by_station=observations_by_station,
        )
        row = enriched[0]

        self.assertTrue(row["is_weather"])
        self.assertEqual(row["weather_forecast_run_at"], datetime(2026, 3, 22, 13, 0, tzinfo=UTC))
        self.assertEqual(row["weather_observed_temperature"], -0.5)
        self.assertAlmostEqual(row["weather_fair_yes_probability"], 2 / 3)
        self.assertIn("+01:00", row["weather_local_time"])


class WalletForensicsStateTests(unittest.TestCase):
    def test_receipt_map_omits_raw_receipt_payload(self):
        mapped = _receipt_map(
            [
                {
                    "transaction_hash": "0xabc",
                    "block_number": 10,
                    "block_timestamp": 20,
                    "classifications_json": ["trade"],
                    "touched_contracts_json": ["0xcontract"],
                    "usdc_in": 1.0,
                    "usdc_out": 2.0,
                    "payload_json": {"logs": ["big"]},
                }
            ]
        )

        self.assertEqual(mapped["0xabc"]["classifications"], ["trade"])
        self.assertNotIn("payload_json", mapped["0xabc"])

    def test_should_persist_derived_rows_skips_incomplete_resume(self):
        self.assertTrue(_should_persist_derived_rows(completeness={}))
        self.assertTrue(_should_persist_derived_rows(completeness={"resume_required": False}))
        self.assertFalse(_should_persist_derived_rows(completeness={"resume_required": True}))

    def test_open_ended_state_path_is_stable_and_reload_updates_end_ts(self):
        target = {"proxy_wallet": "0xwallet", "profile_name": "ColdMath"}
        with TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            path_one = backfill_state_path(base_path, proxy_wallet=target["proxy_wallet"], start_ts=100, end_ts=None)
            path_two = backfill_state_path(base_path, proxy_wallet=target["proxy_wallet"], start_ts=100, end_ts=None)
            self.assertEqual(path_one, path_two)

            initial = load_or_create_backfill_state(
                path_one,
                target=target,
                start_ts=100,
                end_ts=200,
                open_ended=True,
            )
            save_backfill_state(path_one, initial)
            reloaded = load_or_create_backfill_state(
                path_two,
                target=target,
                start_ts=100,
                end_ts=250,
                open_ended=True,
            )

        self.assertTrue(reloaded["scope"]["open_ended"])
        self.assertEqual(reloaded["scope"]["end_ts"], 250)

    def test_backfill_state_round_trips_and_marks_completion(self):
        target = {"proxy_wallet": "0xwallet", "profile_name": "ColdMath"}
        with TemporaryDirectory() as temp_dir:
            state_path = backfill_state_path(
                Path(temp_dir),
                proxy_wallet=target["proxy_wallet"],
                start_ts=100,
                end_ts=200,
            )
            state = load_or_create_backfill_state(
                state_path,
                target=target,
                start_ts=100,
                end_ts=200,
                open_ended=False,
            )
            sync_market_universe(state, ["mkt-a", "mkt-b"])
            mark_stage_completed(state, "value_snapshot")
            mark_stage_completed(state, "positions", row_count=2)
            mark_stage_completed(state, "closed_positions", row_count=1)
            mark_market_stage(
                state,
                "mkt-a",
                stage_name="activity",
                row_count=3,
                event_slugs=["event-a"],
            )
            mark_market_stage(
                state,
                "mkt-b",
                stage_name="activity",
                row_count=2,
                event_slugs=["event-b"],
            )
            mark_market_stage(
                state,
                "mkt-a",
                stage_name="trade",
                row_count=3,
                event_slugs=["event-a"],
            )
            mark_market_stage(
                state,
                "mkt-b",
                stage_name="trade",
                row_count=2,
                event_slugs=["event-b"],
            )
            mark_event_context_completed(state, "event-a", market_ids=["mkt-a"])
            mark_event_context_completed(state, "event-b", market_ids=["mkt-b"])
            update_receipt_progress(
                state,
                completed_count=5,
                pending_count=0,
                last_transaction_hash="0xabc",
                completed=True,
            )
            finalize_backfill_state(state)
            save_backfill_state(state_path, state)

            reloaded = load_or_create_backfill_state(
                state_path,
                target=target,
                start_ts=100,
                end_ts=200,
                open_ended=False,
            )

        self.assertTrue(reloaded["complete"])
        self.assertEqual(pending_markets(reloaded, stage_name="activity"), [])
        self.assertEqual(pending_markets(reloaded, stage_name="trade"), [])
        self.assertFalse(event_context_pending(reloaded, "event-a"))
        self.assertEqual(reloaded["receipts"]["last_transaction_hash"], "0xabc")
        self.assertEqual(summarize_backfill_state(reloaded)["receipt_pending"], 0)


class WalletForensicsReportTests(unittest.TestCase):
    def test_export_artifacts_can_skip_parquet(self):
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            export_artifacts(
                output_dir=output_dir,
                ledger_rows=[{"ledger_event_id": "ledger-1", "event_type": "trade"}],
                inferred_rules=[{"rule_id": "rule-1", "strategy_key": "test"}],
                playbook_sequences=[{"sequence_id": "seq-1", "strategy_key": "test"}],
                strategy_blueprints=[{"blueprint_id": "bp-1", "strategy_key": "test"}],
                shadow_rows=[{"shadow_trade_id": "shadow-1", "condition_id": "cond-1"}],
                rule_summary={"total_rules": 1},
                export_parquet=False,
            )

            self.assertTrue((output_dir / "wallet_ledger_events.csv").exists())
            self.assertTrue((output_dir / "wallet_inferred_rules.csv").exists())
            self.assertTrue((output_dir / "wallet_playbook_sequences.csv").exists())
            self.assertTrue((output_dir / "wallet_strategy_blueprints.csv").exists())
            self.assertTrue((output_dir / "wallet_strategy_blueprints.json").exists())
            self.assertTrue((output_dir / "wallet_shadow_replay.csv").exists())
            self.assertTrue((output_dir / "wallet_rule_summary.json").exists())
            self.assertFalse((output_dir / "wallet_ledger_events.parquet").exists())

    def test_export_fill_context_artifacts_can_skip_parquet(self):
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            export_fill_context_artifacts(
                output_dir=output_dir,
                fill_context_rows=[{"fill_context_id": "fill-1", "context_source": "prices_history"}],
                fill_context_summary={"total_fills": 1},
                export_parquet=False,
            )

            self.assertTrue((output_dir / "wallet_fill_context.csv").exists())
            self.assertTrue((output_dir / "wallet_fill_context_summary.json").exists())
            self.assertFalse((output_dir / "wallet_fill_context.parquet").exists())

    def test_build_rule_summary_aggregates_playbooks_and_candidates(self):
        target = {"proxy_wallet": "0xwallet", "profile_name": "ColdMath"}
        ledger_rows = [
            {
                "condition_id": "cond-1",
                "event_slug": "weather-a",
                "event_type": "trade",
                "realized_pnl": 0.0,
                "is_weather": True,
            },
            {
                "condition_id": "cond-1",
                "event_slug": "weather-a",
                "event_type": "merge",
                "realized_pnl": 1.5,
                "is_weather": True,
            },
            {
                "condition_id": "cond-2",
                "event_slug": "weather-b",
                "event_type": "redeem",
                "realized_pnl": 0.4,
                "is_weather": False,
            },
        ]
        inferred_rules = [
            {
                "rule_id": "rule-1",
                "strategy_key": "inventory_rebalancing_merge",
                "condition_id": "cond-1",
                "confidence": 0.91,
                "summary": "Paired both sides then merged.",
                "trade_ids_json": ["tx-1", "tx-2"],
                "event_slug": "weather-a",
            },
            {
                "rule_id": "rule-2",
                "strategy_key": "inventory_rebalancing_merge",
                "condition_id": "cond-1",
                "confidence": 0.74,
                "summary": "Repeated merge loop.",
                "trade_ids_json": ["tx-3"],
                "event_slug": "weather-a",
            },
            {
                "rule_id": "rule-3",
                "strategy_key": "late_resolution_capture",
                "condition_id": "cond-2",
                "confidence": 0.66,
                "summary": "Held for redemption.",
                "trade_ids_json": ["tx-4"],
                "event_slug": "weather-b",
            },
        ]
        shadow_rows = [
            {
                "rule_id": "rule-1",
                "condition_id": "cond-1",
                "asset": "yes-1",
                "size": 3.0,
                "entry_price": 0.21,
                "exit_mark_price": 0.52,
                "pnl_slippage_free": 0.93,
                "pnl_conservative": 0.71,
            },
            {
                "rule_id": "rule-2",
                "condition_id": "cond-1",
                "asset": "no-1",
                "size": 2.0,
                "entry_price": 0.62,
                "exit_mark_price": 0.49,
                "pnl_slippage_free": 0.26,
                "pnl_conservative": 0.13,
            },
        ]

        summary = build_rule_summary(
            target=target,
            ledger_rows=ledger_rows,
            inferred_rules=inferred_rules,
            shadow_rows=shadow_rows,
            strategy_blueprints=[
                {
                    "strategy_key": "inventory_rebalancing_merge",
                    "status": "ready_for_backtest",
                    "confidence": 0.93,
                    "priority_score": 42.0,
                    "support_count": 12,
                    "summary": "Use matched both-side inventory and merge.",
                }
            ],
        )
        markdown = build_rule_summary_markdown(target=target, rule_summary=summary)

        self.assertEqual(summary["total_rules"], 3)
        self.assertEqual(summary["high_confidence_rules"], 2)
        self.assertEqual(summary["strategies"][0]["strategy_key"], "inventory_rebalancing_merge")
        self.assertEqual(summary["strategies"][0]["shadow_trade_count"], 2)
        self.assertEqual(summary["strategy_blueprints"][0]["strategy_key"], "inventory_rebalancing_merge")
        self.assertEqual(summary["top_conditions"][0]["condition_id"], "cond-1")
        self.assertEqual(summary["bot_candidates"][0]["strategy_key"], "inventory_rebalancing_merge")
        self.assertIn("Dominant Playbooks", markdown)
        self.assertIn("Executable Blueprints", markdown)
        self.assertIn("inventory_rebalancing_merge", markdown)

    def test_build_fill_context_summary_and_markdown_capture_coverage(self):
        target = {"proxy_wallet": "0xwallet", "profile_name": "ColdMath"}
        fill_context_rows = [
            {
                "condition_id": "cond-1",
                "event_slug": "highest-temperature-in-rome-on-march-22-2026",
                "question": "Rome bucket",
                "token_mapping_found": True,
                "is_weather": True,
                "context_source": "mixed",
                "local_quote_coverage": "full_pair",
                "price_history_coverage": "full_pair",
                "local_execution_label": "aggressive_taker_like",
                "price_history_execution_label": "better_than_nearby_trade",
                "local_execution_edge_bps": 5.0,
                "price_history_execution_edge_bps": 15.0,
                "price_history_pair_under_par": True,
                "local_pair_under_par": False,
            },
            {
                "condition_id": "cond-1",
                "event_slug": "highest-temperature-in-rome-on-march-22-2026",
                "question": "Rome bucket",
                "token_mapping_found": True,
                "is_weather": True,
                "context_source": "prices_history",
                "local_quote_coverage": "none",
                "price_history_coverage": "executed_only",
                "local_execution_label": "unknown",
                "price_history_execution_label": "nearby_trade_aligned",
                "local_execution_edge_bps": None,
                "price_history_execution_edge_bps": 1.0,
                "price_history_pair_under_par": False,
                "local_pair_under_par": None,
            },
        ]

        summary = build_fill_context_summary(target=target, fill_context_rows=fill_context_rows)
        markdown = build_fill_context_markdown(
            target=target,
            fill_context_summary=summary,
            fill_context_rows=fill_context_rows,
        )

        self.assertEqual(summary["total_fills"], 2)
        self.assertEqual(summary["fills_with_price_history_pair"], 1)
        self.assertEqual(summary["fills_with_price_history_under_par_pair"], 1)
        self.assertEqual(summary["context_source_counts"][0]["label"], "mixed")
        self.assertEqual(summary["top_conditions"][0]["condition_id"], "cond-1")
        self.assertIn("Fill Context Report", markdown)
        self.assertIn("Pair-Cost Signals", markdown)
        self.assertIn("cond-1", markdown)

    def test_strategy_blueprint_markdown_renders_rules(self):
        markdown = build_strategy_blueprint_markdown(
            target={"proxy_wallet": "0xwallet", "profile_name": "ColdMath"},
            strategy_blueprints=[
                {
                    "strategy_key": "inventory_rebalancing_merge",
                    "status": "ready_for_backtest",
                    "confidence": 0.94,
                    "priority_score": 44.0,
                    "support_count": 20,
                    "summary": "Pair both sides and merge.",
                    "entry_rule_json": {"complete_set_cost_lte": 0.97},
                    "sizing_rule_json": {"matched_size_target": 10},
                    "exit_rule_json": {"action": "merge"},
                    "risk_rule_json": {"avoid_unmatched_inventory": True},
                }
            ],
        )

        self.assertIn("Strategy Blueprints", markdown)
        self.assertIn("inventory_rebalancing_merge", markdown)
        self.assertIn("complete_set_cost_lte", markdown)


class WalletForensicsPlaybookTests(unittest.TestCase):
    def test_extract_playbook_sequences_and_blueprints_identify_merge_loop(self):
        market_context = {
            "cond-1": {
                "market_id": "cond-1",
                "event_slug": "highest-temperature-in-chengdu-on-august-16-2025",
                "question": "Highest temperature in Chengdu on August 16, 2025",
                "yes_token_id": "yes-1",
                "no_token_id": "no-1",
                "closed": False,
            }
        }
        activity_rows = [
            {
                "timestamp": 1,
                "transaction_hash": "0x1",
                "condition_id": "cond-1",
                "event_type": "TRADE",
                "asset": "yes-1",
                "side": "BUY",
                "outcome": "Yes",
                "size": 10.0,
                "price": 0.22,
                "usdc_size": 2.2,
                "event_slug": "highest-temperature-in-chengdu-on-august-16-2025",
            },
            {
                "timestamp": 2,
                "transaction_hash": "0x2",
                "condition_id": "cond-1",
                "event_type": "TRADE",
                "asset": "no-1",
                "side": "BUY",
                "outcome": "No",
                "size": 10.0,
                "price": 0.71,
                "usdc_size": 7.1,
                "event_slug": "highest-temperature-in-chengdu-on-august-16-2025",
            },
            {
                "timestamp": 3,
                "transaction_hash": "0x3",
                "condition_id": "cond-1",
                "event_type": "MERGE",
                "size": 10.0,
                "usdc_size": 10.0,
                "event_slug": "highest-temperature-in-chengdu-on-august-16-2025",
            },
        ]

        ledger_rows, _ = build_wallet_ledger(
            proxy_wallet="0xwallet",
            activity_rows=activity_rows,
            receipt_rows={},
            market_context=market_context,
            closed_positions_rows=[],
        )
        enriched_rows = enrich_ledger_with_weather(
            ledger_rows=ledger_rows,
            market_context=market_context,
            weather_market_rows={},
            forecast_rows_by_market={},
            observations_by_station={},
        )
        inferred_rules = infer_strategies(
            proxy_wallet="0xwallet",
            ledger_rows=ledger_rows,
            enriched_rows=enriched_rows,
            market_context=market_context,
        )
        sequences = extract_playbook_sequences(
            proxy_wallet="0xwallet",
            ledger_rows=enriched_rows,
            inferred_rules=inferred_rules,
            market_context=market_context,
        )
        blueprints = build_strategy_blueprints(
            proxy_wallet="0xwallet",
            playbook_sequences=sequences,
        )

        self.assertTrue(any(row["strategy_key"] == "inventory_rebalancing_merge" for row in sequences))
        blueprint = next(row for row in blueprints if row["strategy_key"] == "inventory_rebalancing_merge")
        self.assertEqual(blueprint["status"], "ready_for_backtest")
        self.assertIn("merge", blueprint["exit_rule_json"]["action"])

    def test_extract_playbook_sequences_identifies_neg_risk_basket(self):
        base_time = datetime(2026, 3, 22, 12, 0, tzinfo=UTC)
        ledger_rows = [
            {
                "ledger_event_id": f"ledger-{index}",
                "proxy_wallet": "0xwallet",
                "occurred_at": base_time,
                "transaction_hash": f"0x{index}",
                "condition_id": condition_id,
                "event_slug": "weather-basket",
                "asset": f"asset-{index}",
                "outcome": "Yes",
                "side": "buy",
                "event_type": "trade",
                "size": 5.0,
                "token_delta": 5.0,
                "usdc_delta": -1.5,
                "price": 0.30,
                "realized_pnl": 0.0,
                "source_confidence": 0.9,
            }
            for index, condition_id in enumerate(["cond-a", "cond-b", "cond-c"], start=1)
        ]
        market_context = {
            condition_id: {
                "market_id": condition_id,
                "event_slug": "weather-basket",
                "neg_risk": True,
                "sibling_market_ids": ["cond-a", "cond-b", "cond-c"],
            }
            for condition_id in ["cond-a", "cond-b", "cond-c"]
        }

        sequences = extract_playbook_sequences(
            proxy_wallet="0xwallet",
            ledger_rows=ledger_rows,
            inferred_rules=[],
            market_context=market_context,
        )
        blueprints = build_strategy_blueprints(
            proxy_wallet="0xwallet",
            playbook_sequences=sequences,
        )

        self.assertTrue(any(row["strategy_key"] == "neg_risk_basket" for row in sequences))
        blueprint = next(row for row in blueprints if row["strategy_key"] == "neg_risk_basket")
        self.assertEqual(blueprint["status"], "ready_for_backtest")
        self.assertGreaterEqual(blueprint["support_count"], 1)


class WalletForensicsBacktestTests(unittest.TestCase):
    def test_inventory_merge_backtest_grid_prefers_profitable_supported_config(self):
        sequences = [
            {
                "sequence_id": "seq-1",
                "condition_id": "cond-1",
                "started_at": datetime(2026, 3, 20, 10, 0, tzinfo=UTC),
                "ended_at": datetime(2026, 3, 20, 10, 2, tzinfo=UTC),
                "realized_pnl": 4.0,
                "payload_json": {
                    "complete_set_cost": 0.97,
                    "inventory_imbalance_ratio": 0.10,
                    "matched_size": 10.0,
                    "merge_delay_minutes": 1.0,
                    "buy_usdc": 9.7,
                },
            },
            {
                "sequence_id": "seq-2",
                "condition_id": "cond-2",
                "started_at": datetime(2026, 3, 20, 11, 0, tzinfo=UTC),
                "ended_at": datetime(2026, 3, 20, 11, 3, tzinfo=UTC),
                "realized_pnl": 3.0,
                "payload_json": {
                    "complete_set_cost": 0.985,
                    "inventory_imbalance_ratio": 0.20,
                    "matched_size": 8.0,
                    "merge_delay_minutes": 2.0,
                    "buy_usdc": 7.88,
                },
            },
            {
                "sequence_id": "seq-3",
                "condition_id": "cond-3",
                "started_at": datetime(2026, 3, 20, 12, 0, tzinfo=UTC),
                "ended_at": datetime(2026, 3, 20, 12, 10, tzinfo=UTC),
                "realized_pnl": -6.0,
                "payload_json": {
                    "complete_set_cost": 1.02,
                    "inventory_imbalance_ratio": 0.45,
                    "matched_size": 6.0,
                    "merge_delay_minutes": 20.0,
                    "buy_usdc": 6.12,
                },
            },
        ]
        blueprint = {
            "entry_rule_json": {
                "complete_set_cost_lte": 0.995,
                "max_inventory_imbalance_ratio": 0.35,
            }
        }

        grid = build_inventory_merge_grid(blueprint=blueprint, sequences=sequences)
        results = evaluate_inventory_merge_grid(sequences=sequences, config_rows=grid)
        ranked = rank_inventory_merge_results(results)
        best = select_best_inventory_merge_config(ranked)
        selected = select_inventory_merge_sequences(sequences, best)

        self.assertGreater(best["support_count"], 0)
        self.assertGreater(best["total_realized_pnl"], 0.0)
        self.assertTrue(all(row["sequence_id"] != "seq-3" for row in selected))

    def test_inventory_merge_bot_config_uses_best_config_and_sequence_stats(self):
        best_config = {
            "config_id": "cfg-1",
            "complete_set_cost_lte": 0.995,
            "max_inventory_imbalance_ratio": 0.25,
            "min_matched_size": 5.0,
            "max_merge_delay_minutes": 5.0,
            "support_count": 2,
            "total_realized_pnl": 7.0,
            "roi_pct": 41.2,
            "win_rate_pct": 100.0,
            "ranking_score": 88.0,
        }
        selected_sequences = [
            {"payload_json": {"matched_size": 8.0, "buy_usdc": 7.8}},
            {"payload_json": {"matched_size": 12.0, "buy_usdc": 11.6}},
        ]

        config = build_inventory_merge_bot_config(
            target={"proxy_wallet": "0xwallet", "profile_name": "ColdMath"},
            best_config=best_config,
            selected_sequences=selected_sequences,
            source_blueprint={"blueprint_id": "bp-1"},
        )

        self.assertEqual(config["strategy_name"], "coldmath_inventory_rebalancing_merge_v1")
        self.assertEqual(config["entry_rule"]["complete_set_cost_lte"], 0.995)
        self.assertEqual(config["source_blueprint_id"], "bp-1")
        self.assertGreater(config["sizing_rule"]["matched_size_target"], 0.0)


class WalletForensicsPaperScanTests(unittest.TestCase):
    def test_paper_scan_filters_candidates_by_complete_set_cost(self):
        context = WeatherMarketContext(
            event_id="event-1",
            event_slug="weather-test",
            title="Weather Test",
            city="Rome",
            city_key="rome",
            station_code=None,
            station_name=None,
            lat=None,
            lon=None,
            timezone="Europe/Rome",
            local_date=date(2026, 3, 22),
            unit="C",
            rule_family=None,
            resolution_source_url=None,
            verified_station=True,
            observation_provider=None,
            forecast_provider=None,
            markets=[
                WeatherBucketMarket(
                    market_id="mkt-good",
                    event_id="event-1",
                    event_slug="weather-test",
                    market_slug="weather-test-good",
                    question="Good bucket",
                    city="Rome",
                    city_key="rome",
                    station_code=None,
                    station_name=None,
                    lat=None,
                    lon=None,
                    timezone="Europe/Rome",
                    local_date=date(2026, 3, 22),
                    unit="C",
                    bucket_label="10C to 11C",
                    bucket_low=10.0,
                    bucket_high=11.0,
                    bucket_order=1,
                    rule_family=None,
                    resolution_source_url=None,
                    resolution_precision_scale=0,
                    neg_risk=False,
                    active=True,
                    eligible=True,
                    eligibility_reason=None,
                    yes_token_id="yes-1",
                    no_token_id="no-1",
                    started_at=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
                    ended_at=datetime(2026, 3, 22, 18, 0, tzinfo=UTC),
                    yes_ask=0.47,
                    no_ask=0.50,
                    yes_ask_size=120.0,
                    no_ask_size=80.0,
                    latest_quote_time=datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
                ),
                WeatherBucketMarket(
                    market_id="mkt-bad",
                    event_id="event-1",
                    event_slug="weather-test",
                    market_slug="weather-test-bad",
                    question="Bad bucket",
                    city="Rome",
                    city_key="rome",
                    station_code=None,
                    station_name=None,
                    lat=None,
                    lon=None,
                    timezone="Europe/Rome",
                    local_date=date(2026, 3, 22),
                    unit="C",
                    bucket_label="12C to 13C",
                    bucket_low=12.0,
                    bucket_high=13.0,
                    bucket_order=2,
                    rule_family=None,
                    resolution_source_url=None,
                    resolution_precision_scale=0,
                    neg_risk=False,
                    active=True,
                    eligible=True,
                    eligibility_reason=None,
                    yes_token_id="yes-2",
                    no_token_id="no-2",
                    started_at=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
                    ended_at=datetime(2026, 3, 22, 18, 0, tzinfo=UTC),
                    yes_ask=0.60,
                    no_ask=0.45,
                    yes_ask_size=50.0,
                    no_ask_size=40.0,
                    latest_quote_time=datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
                ),
            ],
        )

        async def fake_fetch_active_weather_contexts(*, eligible_only=True):
            return [context]

        with patch("analysis.wallet_forensics.paper_scan.fetch_active_weather_contexts", fake_fetch_active_weather_contexts):
            candidates = asyncio.run(scan_inventory_merge_candidates(complete_set_cost_lte=0.995))

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["market_id"], "mkt-good")

    def test_paper_scan_markdown_lists_top_candidates(self):
        markdown = build_paper_scan_markdown(
            target={"proxy_wallet": "0xwallet", "profile_name": "ColdMath"},
            bot_config={"entry_rule": {"complete_set_cost_lte": 0.995}},
            candidates=[
                {
                    "city": "Rome",
                    "local_date": "2026-03-22",
                    "bucket_label": "10C to 11C",
                    "combined_cost": 0.97,
                    "merge_edge": 0.03,
                    "yes_ask": 0.47,
                    "no_ask": 0.50,
                    "max_mergeable_size": 80.0,
                }
            ],
        )

        self.assertIn("Inventory Merge Paper Scan", markdown)
        self.assertIn("Rome", markdown)
        self.assertIn("0.9700", markdown)


class WalletForensicsFillContextTests(unittest.TestCase):
    def test_normalize_price_history_points_deduplicates_and_sorts(self):
        normalized = _normalize_price_history_points(
            [
                {"t": 3, "p": 0.43},
                {"t": 1, "p": 0.41},
                {"t": 3, "p": 0.44},
            ]
        )

        self.assertEqual(normalized, [{"timestamp": 1, "price": 0.41}, {"timestamp": 3, "price": 0.44}])

    def test_fetch_price_history_range_splits_after_range_error(self):
        calls: list[tuple[int, int]] = []

        class DummyClient:
            def fetch_prices_history(self, asset_id: str, *, start_ts: int, end_ts: int, fidelity: int):
                calls.append((start_ts, end_ts))
                if end_ts - start_ts > 12 * 60 * 60:
                    request = httpx.Request("GET", "https://clob.polymarket.com/prices-history")
                    response = httpx.Response(400, request=request, json={"error": "range too wide"})
                    raise httpx.HTTPStatusError("range too wide", request=request, response=response)
                return [{"t": start_ts, "p": 0.41}]

        rows = _fetch_price_history_range(
            client=DummyClient(),  # type: ignore[arg-type]
            asset_id="asset-1",
            start_ts=0,
            end_ts=2 * 24 * 60 * 60,
            fidelity_minutes=1,
            max_chunk_seconds=2 * 24 * 60 * 60,
        )

        self.assertGreater(len(calls), 1)
        self.assertEqual(rows[0]["t"], calls[1][0])

    def test_build_fill_context_row_classifies_quote_and_pair_cost(self):
        fill = {
            "ledger_event_id": "ledger-1",
            "proxy_wallet": "0xwallet",
            "occurred_at": datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
            "transaction_hash": "0xfill",
            "condition_id": "cond-1",
            "event_slug": "highest-temperature-in-rome-on-march-22-2026",
            "question": "Rome bucket",
            "asset": "yes-1",
            "opposite_asset": "no-1",
            "yes_token_id": "yes-1",
            "no_token_id": "no-1",
            "executed_token_role": "yes",
            "outcome": "Yes",
            "side": "buy",
            "price": 0.47,
            "size": 10.0,
            "token_mapping_found": True,
            "is_weather": True,
        }
        local_quote = {
            "time": datetime(2026, 3, 22, 12, 0, 2, tzinfo=UTC),
            "distance_seconds": 2.0,
            "best_bid": 0.46,
            "best_ask": 0.47,
            "mid": 0.465,
            "best_bid_size": 100.0,
            "best_ask_size": 50.0,
        }
        opposite_local_quote = {
            "time": datetime(2026, 3, 22, 12, 0, 3, tzinfo=UTC),
            "distance_seconds": 3.0,
            "best_bid": 0.51,
            "best_ask": 0.52,
            "mid": 0.515,
        }
        history_point = {
            "time": datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
            "distance_seconds": 0.0,
            "price": 0.463,
        }
        opposite_history_point = {
            "time": datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
            "distance_seconds": 0.0,
            "price": 0.52,
        }

        row = build_fill_context_row(
            fill=fill,
            local_quote=local_quote,
            opposite_local_quote=opposite_local_quote,
            history_point=history_point,
            opposite_history_point=opposite_history_point,
        )

        self.assertEqual(row["local_execution_label"], "aggressive_taker_like")
        self.assertEqual(row["price_history_execution_label"], "worse_than_nearby_trade")
        self.assertEqual(row["local_quote_coverage"], "full_pair")
        self.assertEqual(row["price_history_coverage"], "full_pair")
        self.assertEqual(row["context_source"], "mixed")
        self.assertAlmostEqual(row["executed_plus_opposite_local_best_ask"], 0.99)
        self.assertTrue(row["local_pair_under_par"])


class WalletForensicsAcceptanceTests(unittest.TestCase):
    def test_chengdu_style_sequence_rebuilds_merge_strategy_and_shadow_replay(self):
        market_context = {
            "chengdu-11c": {
                "market_id": "chengdu-11c",
                "event_slug": "highest-temperature-in-chengdu-on-august-16-2025",
                "question": "Highest temperature in Chengdu on August 16, 2025",
                "yes_token_id": "chengdu-yes",
                "no_token_id": "chengdu-no",
                "yes_price": 0.82,
                "no_price": 0.18,
                "closed": False,
            }
        }
        activity_rows = [
            {
                "timestamp": 1,
                "transaction_hash": "0xc1",
                "condition_id": "chengdu-11c",
                "event_type": "TRADE",
                "asset": "chengdu-yes",
                "side": "BUY",
                "outcome": "Yes",
                "size": 20.0,
                "price": 0.22,
                "usdc_size": 4.4,
                "event_slug": "highest-temperature-in-chengdu-on-august-16-2025",
            },
            {
                "timestamp": 2,
                "transaction_hash": "0xc2",
                "condition_id": "chengdu-11c",
                "event_type": "TRADE",
                "asset": "chengdu-no",
                "side": "BUY",
                "outcome": "No",
                "size": 12.0,
                "price": 0.71,
                "usdc_size": 8.52,
                "event_slug": "highest-temperature-in-chengdu-on-august-16-2025",
            },
            {
                "timestamp": 3,
                "transaction_hash": "0xc3",
                "condition_id": "chengdu-11c",
                "event_type": "MERGE",
                "size": 12.0,
                "usdc_size": 12.0,
                "event_slug": "highest-temperature-in-chengdu-on-august-16-2025",
            },
        ]

        ledger_rows, _ = build_wallet_ledger(
            proxy_wallet="0xwallet",
            activity_rows=activity_rows,
            receipt_rows={},
            market_context=market_context,
            closed_positions_rows=[],
        )
        enriched_rows = enrich_ledger_with_weather(
            ledger_rows=ledger_rows,
            market_context=market_context,
            weather_market_rows={},
            forecast_rows_by_market={},
            observations_by_station={},
        )
        inferred_rules = infer_strategies(
            proxy_wallet="0xwallet",
            ledger_rows=ledger_rows,
            enriched_rows=enriched_rows,
            market_context=market_context,
        )
        shadow_rows = build_shadow_replay(
            proxy_wallet="0xwallet",
            inferred_rules=inferred_rules,
            ledger_rows=enriched_rows,
            market_context=market_context,
        )

        self.assertTrue(any(rule["strategy_key"] == "inventory_rebalancing_merge" for rule in inferred_rules))
        self.assertEqual(len(shadow_rows), 2)
        self.assertTrue(all(row["condition_id"] == "chengdu-11c" for row in shadow_rows))


if __name__ == "__main__":
    unittest.main()
