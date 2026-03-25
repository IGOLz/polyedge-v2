import test from "node:test";
import assert from "node:assert/strict";

import {
  BOT_TARGET_PATH,
  ROOT_TARGET_PATH,
  buildCollectorSummary,
  buildTradingSummary,
  buildWeatherCloneSummary,
  buildWeatherMergeSummary,
  emptyCollectorSummary,
  pickWorstStatus,
  sortAlerts,
} from "../lib/streamdeck-summary-core";

const NOW = new Date("2026-03-25T12:00:00.000Z");

test("collector summary marks recent full feeds as healthy", () => {
  const summary = buildCollectorSummary(
    [
      {
        market_type: "btc_5m",
        last_tick_at: "2026-03-25T11:59:50.000Z",
        last_5m: "295",
        last_15m: "0",
      },
      {
        market_type: "btc_15m",
        last_tick_at: "2026-03-25T11:59:48.000Z",
        last_5m: "0",
        last_15m: "895",
      },
    ],
    NOW
  );

  assert.equal(summary.assets.btc.status, "healthy");
  assert.equal(summary.overall.healthyAssetCount, 1);
  assert.equal(summary.overall.status, "unknown");
});

test("collector summary marks stale feeds as critical alerts", () => {
  const summary = buildCollectorSummary(
    [
      {
        market_type: "eth_5m",
        last_tick_at: "2026-03-25T11:58:00.000Z",
        last_5m: "280",
        last_15m: "0",
      },
      {
        market_type: "eth_15m",
        last_tick_at: "2026-03-25T11:58:00.000Z",
        last_5m: "0",
        last_15m: "840",
      },
    ],
    NOW
  );

  const ethAlert = summary.alerts.find((alert) => alert.message.includes("ETH collector is stale"));

  assert.equal(summary.assets.eth.status, "stale");
  assert.ok(ethAlert);
  assert.equal(ethAlert.severity, "critical");
  assert.equal(ethAlert.targetPath, ROOT_TARGET_PATH);
});

test("trading summary marks stale heartbeat red within two intervals", () => {
  const { summary, alerts } = buildTradingSummary(
    {
      open_trades: "3",
      pnl_24h: "42.5",
      last_trade_at: "2026-03-25T11:45:00.000Z",
    },
    {
      logged_at: "2026-03-25T11:57:30.000Z",
      message: "heartbeat",
      data: { heartbeat_at: "2026-03-25T11:57:30.000Z" },
    },
    undefined,
    NOW
  );

  assert.equal(summary.status, "stale");
  assert.equal(summary.heartbeatAgeSec, 150);
  assert.equal(summary.pnl24h, 42.5);
  assert.equal(alerts[0]?.severity, "critical");
  assert.equal(alerts[0]?.targetPath, BOT_TARGET_PATH);
});

test("weather merge summary degrades on stand-down reason", () => {
  const { summary, alerts } = buildWeatherMergeSummary(
    {
      logged_at: "2026-03-25T11:59:10.000Z",
      message: "merge summary",
      data: {
        candidate_count: 0,
        stand_down_reason: "wallet guard active",
      },
    },
    { active_positions: "2" },
    NOW
  );

  assert.equal(summary.status, "degraded");
  assert.equal(summary.standDownReason, "wallet guard active");
  assert.equal(summary.activePositions, 2);
  assert.match(alerts[0]?.message ?? "", /standing down/);
});

test("weather clone summary degrades when execution is disabled", () => {
  const { summary, alerts } = buildWeatherCloneSummary(
    {
      captured_at: "2026-03-25T11:59:30.000Z",
      summary_data: {
        candidate_count: 4,
        quote_coverage_ratio: 0.82,
        execution_allowed: false,
      },
      health_data: {
        market_data: {
          status: "healthy",
        },
      },
    },
    { active_positions: "1" },
    NOW
  );

  assert.equal(summary.status, "degraded");
  assert.equal(summary.quoteCoverageRatio, 0.82);
  assert.equal(summary.executionAllowed, false);
  assert.match(alerts[0]?.message ?? "", /without live execution enabled/);
});

test("empty collector summary preserves payload shape", () => {
  const summary = emptyCollectorSummary();

  assert.equal(summary.overall.totalAssetCount, 4);
  assert.equal(summary.assets.btc.intervals["5m"].expectedTicks, 300);
  assert.equal(summary.assets.xrp.intervals["15m"].expectedTicks, 900);
  assert.equal(summary.alerts[0]?.severity, "critical");
});

test("alerts are sorted by severity then freshness", () => {
  const alerts = sortAlerts([
    { severity: "warning", source: "trading", message: "warning old", ageSec: 50, targetPath: "/bot" },
    { severity: "critical", source: "collector", message: "critical newer", ageSec: 20, targetPath: "/" },
    { severity: "critical", source: "weather_clone", message: "critical older", ageSec: 80, targetPath: "/bot" },
  ]);

  assert.deepEqual(
    alerts.map((alert) => alert.message),
    ["critical newer", "critical older", "warning old"]
  );
});

test("error status outranks unknown when combining states", () => {
  assert.equal(pickWorstStatus("unknown", "error"), "error");
});
