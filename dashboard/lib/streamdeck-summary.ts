import "server-only";

import { query } from "@/lib/db";
import { PNL_SQL } from "@/lib/pnl";
import type {
  StreamDeckAlert,
  StreamDeckSummaryPayload,
  StreamDeckTradingSummary,
  StreamDeckWeatherCloneSummary,
  StreamDeckWeatherMergeSummary,
} from "@/types/streamdeck";
import {
  BOT_TARGET_PATH,
  buildAlert,
  buildCollectorSummary,
  buildTradingSummary,
  buildWeatherCloneSummary,
  buildWeatherMergeSummary,
  emptyCollectorSummary,
  sortAlerts,
  type BotLogRow,
  type CollectorRow,
  type CountRow,
  type TradingMetricsRow,
  type WeatherCloneCycleRow,
} from "@/lib/streamdeck-summary-core";

const STREAMDECK_VERSION = 1;

async function fetchCollectorSummary(now: Date) {
  const rows = await query<CollectorRow>(`
    SELECT
      market_type,
      MAX(time) AS last_tick_at,
      COUNT(*) FILTER (WHERE time > NOW() - INTERVAL '5 minutes') AS last_5m,
      COUNT(*) FILTER (WHERE time > NOW() - INTERVAL '15 minutes') AS last_15m
    FROM market_ticks
    WHERE time > NOW() - INTERVAL '24 hours'
      AND market_type IS NOT NULL
    GROUP BY market_type
  `);

  return buildCollectorSummary(rows, now);
}

async function fetchTradingSummary(now: Date): Promise<{
  summary: StreamDeckTradingSummary;
  alerts: StreamDeckAlert[];
}> {
  const [metricsRows, heartbeatRows, errorRows] = await Promise.all([
    query<TradingMetricsRow>(`
      SELECT
        COUNT(*) FILTER (WHERE status = 'filled' AND final_outcome IS NULL) AS open_trades,
        SUM(${PNL_SQL}) FILTER (
          WHERE placed_at > NOW() - INTERVAL '24 hours'
            AND final_outcome IN ('win_resolution', 'take_profit', 'loss', 'stop_loss')
        ) AS pnl_24h,
        MAX(placed_at) AS last_trade_at
      FROM bot_trades
    `),
    query<BotLogRow>(`
      SELECT logged_at, message, data
      FROM bot_logs
      WHERE log_type = 'trading_heartbeat'
      ORDER BY logged_at DESC
      LIMIT 1
    `),
    query<BotLogRow>(`
      SELECT logged_at, message, data
      FROM bot_logs
      WHERE log_type = 'bot_error'
      ORDER BY logged_at DESC
      LIMIT 1
    `),
  ]);

  return buildTradingSummary(metricsRows[0], heartbeatRows[0], errorRows[0], now);
}

async function fetchWeatherMergeSummary(now: Date): Promise<{
  summary: StreamDeckWeatherMergeSummary;
  alerts: StreamDeckAlert[];
}> {
  const [summaryRows, activePositionRows] = await Promise.all([
    query<BotLogRow>(`
      SELECT logged_at, message, data
      FROM bot_logs
      WHERE log_type = 'weather_merge_summary'
      ORDER BY logged_at DESC
      LIMIT 1
    `),
    query<CountRow>(`
      SELECT COUNT(*) FILTER (WHERE closed_at IS NULL) AS active_positions
      FROM weather_merge_positions
    `),
  ]);

  return buildWeatherMergeSummary(summaryRows[0], activePositionRows[0], now);
}

async function fetchWeatherCloneSummary(now: Date): Promise<{
  summary: StreamDeckWeatherCloneSummary;
  alerts: StreamDeckAlert[];
}> {
  const [cycleRows, activePositionRows] = await Promise.all([
    query<WeatherCloneCycleRow>(`
      SELECT captured_at, summary_data, health_data
      FROM weather_clone_cycles
      ORDER BY captured_at DESC
      LIMIT 1
    `),
    query<CountRow>(`
      SELECT COUNT(*) FILTER (WHERE closed_at IS NULL) AS active_positions
      FROM weather_clone_positions
    `),
  ]);

  return buildWeatherCloneSummary(cycleRows[0], activePositionRows[0], now);
}

export async function getStreamDeckSummary(): Promise<StreamDeckSummaryPayload> {
  const now = new Date();

  const [collectorResult, tradingResult, mergeResult, cloneResult] = await Promise.all([
    fetchCollectorSummary(now).catch((error) => {
      console.error("[streamdeck] collector summary failed:", error);
      return emptyCollectorSummary();
    }),
    fetchTradingSummary(now).catch((error) => {
      console.error("[streamdeck] trading summary failed:", error);
      return {
        summary: {
          status: "error",
          heartbeatAt: null,
          heartbeatAgeSec: null,
          pnl24h: 0,
          openTrades: 0,
          lastTradeAt: null,
          lastTradeAgeSec: null,
          recentError: "Trading summary query failed",
          targetPath: BOT_TARGET_PATH,
        } satisfies StreamDeckTradingSummary,
        alerts: [
          buildAlert("critical", "trading", "Trading summary query failed", null, BOT_TARGET_PATH),
        ],
      };
    }),
    fetchWeatherMergeSummary(now).catch((error) => {
      console.error("[streamdeck] weather merge summary failed:", error);
      return {
        summary: {
          status: "error",
          summaryAt: null,
          summaryAgeSec: null,
          activePositions: 0,
          candidateCount: 0,
          standDownReason: null,
          targetPath: BOT_TARGET_PATH,
        } satisfies StreamDeckWeatherMergeSummary,
        alerts: [
          buildAlert(
            "critical",
            "weather_merge",
            "Weather merge summary query failed",
            null,
            BOT_TARGET_PATH
          ),
        ],
      };
    }),
    fetchWeatherCloneSummary(now).catch((error) => {
      console.error("[streamdeck] weather clone summary failed:", error);
      return {
        summary: {
          status: "error",
          capturedAt: null,
          capturedAgeSec: null,
          activePositions: 0,
          candidateCount: 0,
          quoteCoverageRatio: 0,
          executionAllowed: false,
          targetPath: BOT_TARGET_PATH,
        } satisfies StreamDeckWeatherCloneSummary,
        alerts: [
          buildAlert(
            "critical",
            "weather_clone",
            "Weather clone summary query failed",
            null,
            BOT_TARGET_PATH
          ),
        ],
      };
    }),
  ]);

  const alerts = sortAlerts([
    ...collectorResult.alerts,
    ...tradingResult.alerts,
    ...mergeResult.alerts,
    ...cloneResult.alerts,
  ]);

  return {
    version: STREAMDECK_VERSION,
    generatedAt: now.toISOString(),
    collector: {
      overall: collectorResult.overall,
      assets: collectorResult.assets,
    },
    trading: tradingResult.summary,
    weatherMerge: mergeResult.summary,
    weatherClone: cloneResult.summary,
    alerts,
  };
}
