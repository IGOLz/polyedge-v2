from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from analysis.coldmath_window_compare import (
    _analyze_uptime,
    _derive_weather_trade_metadata,
    _determine_window,
    _load_coldmath_trade_summary,
    _parse_log_line,
    _resolve_log_timezone,
    build_parser,
)


class ColdMathWindowCompareTests(unittest.TestCase):
    def test_resolve_log_timezone_prefers_lxc_date_is(self):
        args = build_parser().parse_args(
            [
                "--lxc-date-is",
                "2026-03-24T20:00:00+01:00",
            ]
        )

        tz, label, source = _resolve_log_timezone(args)

        self.assertEqual(source, "lxc-date-is")
        self.assertEqual(label, "+01:00")
        self.assertEqual(datetime(2026, 3, 24, 12, 0, tzinfo=tz).astimezone(UTC).hour, 11)

    def test_parse_bracket_log_line_uses_default_timezone(self):
        event = _parse_log_line(
            raw_line="[2026-03-23 16:53:46] INFO     [WEATHER-MERGE] Bot started | mode=LIVE | config=x",
            source_path="trading.log",
            line_number=1,
            default_tz=timezone(timedelta(hours=1)),
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.timestamp_utc.isoformat(), "2026-03-23T15:53:46+00:00")
        self.assertIn("mode=LIVE", event.message)

    def test_parse_iso_log_line_keeps_explicit_timezone(self):
        event = _parse_log_line(
            raw_line="2026-03-23T16:53:46.123456789Z polyedge-trading-weather  | [WEATHER-MERGE] Bot started | mode=LIVE",
            source_path="docker.log",
            line_number=8,
            default_tz=timezone(timedelta(hours=1)),
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.timestamp_utc.isoformat(), "2026-03-23T16:53:46.123456+00:00")
        self.assertEqual(event.timestamp_source, "explicit_log")

    def test_determine_window_uses_first_live_start_line(self):
        entries = [
            _parse_log_line(
                raw_line="[2026-03-23 16:53:46] INFO     [WEATHER-MERGE] Bot started | mode=LIVE | config=x",
                source_path="trading.log",
                line_number=2,
                default_tz=UTC,
            ),
            _parse_log_line(
                raw_line="[2026-03-23 17:53:46] INFO     [WEATHER-MERGE] Bot started | mode=LIVE | config=x",
                source_path="trading.log",
                line_number=10,
                default_tz=UTC,
            ),
        ]
        entries = [item for item in entries if item is not None]

        window = _determine_window(log_entries=entries, window_hours=24.0)

        self.assertEqual(window["window_start_utc"].isoformat(), "2026-03-23T16:53:46+00:00")
        self.assertEqual(window["window_end_utc"].isoformat(), "2026-03-24T16:53:46+00:00")
        self.assertEqual(window["start_source_line"], 2)

    def test_analyze_uptime_detects_large_gap_and_restart(self):
        raw_lines = [
            "[2026-03-23 16:53:46] INFO     [WEATHER-MERGE] Bot started | mode=LIVE | config=x",
            "[2026-03-23 16:54:46] INFO     [WEATHER-MERGE] Cycle OK | candidates=0",
            "[2026-03-23 16:55:46] INFO     [WEATHER-MERGE] Summary | candidates=0",
            "[2026-03-23 17:05:46] INFO     [WEATHER-MERGE] Summary | candidates=0",
            "[2026-03-23 17:06:46] INFO     [WEATHER-MERGE] Bot started | mode=LIVE | config=x",
        ]
        entries = [
            _parse_log_line(
                raw_line=line,
                source_path="trading.log",
                line_number=index,
                default_tz=UTC,
            )
            for index, line in enumerate(raw_lines, start=1)
        ]
        entries = [item for item in entries if item is not None]

        uptime = _analyze_uptime(
            log_entries=entries,
            window_start_utc=datetime(2026, 3, 23, 16, 53, 46, tzinfo=UTC),
            window_end_utc=datetime(2026, 3, 23, 17, 10, 46, tzinfo=UTC),
            gap_threshold_seconds=180.0,
        )

        self.assertEqual(uptime["restart_count"], 1)
        self.assertEqual(uptime["gap_count"], 2)
        self.assertEqual(uptime["heartbeat_count"], 3)
        self.assertEqual(uptime["heartbeat_rows"][0]["candidate_count"], 0)

    def test_load_coldmath_trade_summary_correlates_with_last_heartbeat(self):
        fieldnames = [
            "occurred_at",
            "event_type",
            "weather_local_time",
            "event_slug",
            "weather_city",
            "weather_local_date",
            "weather_bucket_label",
            "side",
            "outcome",
            "size",
            "price",
            "transaction_hash",
            "condition_id",
        ]
        rows = [
            {
                "occurred_at": "2026-03-23T17:00:00+00:00",
                "event_type": "trade",
                "weather_local_time": "2026-03-23T18:00:00+01:00",
                "event_slug": "weather-rome",
                "weather_city": "rome",
                "weather_local_date": "2026-03-24",
                "weather_bucket_label": "16C",
                "side": "buy",
                "outcome": "Yes",
                "size": "10",
                "price": "0.49",
                "transaction_hash": "0xabc",
                "condition_id": "cond-1",
            },
            {
                "occurred_at": "2026-03-23T17:10:00+00:00",
                "event_type": "merge",
                "weather_local_time": "",
                "event_slug": "weather-rome",
                "weather_city": "rome",
                "weather_local_date": "2026-03-24",
                "weather_bucket_label": "16C",
                "side": "",
                "outcome": "",
                "size": "10",
                "price": "",
                "transaction_hash": "0xmerge",
                "condition_id": "cond-1",
            },
        ]
        heartbeat_rows = [
            {
                "timestamp_utc": datetime(2026, 3, 23, 16, 59, 0, tzinfo=UTC),
                "candidate_count": 0,
                "message": "Summary | candidates=0",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "wallet_ledger_events.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)

            ledger_rows = []
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    ledger_rows.append(dict(row))

            summary = _load_coldmath_trade_summary(
                ledger_rows=ledger_rows,
                heartbeat_rows=heartbeat_rows,
                heartbeat_gap_seconds=180.0,
            )

        self.assertEqual(summary["trade_count"], 1)
        self.assertEqual(summary["candidate_zero_trade_count"], 1)
        self.assertEqual(summary["distinct_condition_count"], 1)
        self.assertEqual(summary["grouped_rows"][0]["trade_count"], 1)

    def test_derive_weather_trade_metadata_falls_back_to_title_and_slug(self):
        metadata = _derive_weather_trade_metadata(
            {
                "event_slug": "highest-temperature-in-warsaw-on-march-24-2026",
                "payload_json": {
                    "raw_activity": {
                        "title": "Will the highest temperature in Warsaw be 5Â°C on March 24?",
                    }
                },
            }
        )

        self.assertEqual(metadata["city"], "Warsaw")
        self.assertEqual(metadata["local_date"], "2026-03-24")
        self.assertEqual(metadata["bucket_label"], "5°C")


if __name__ == "__main__":
    unittest.main()
