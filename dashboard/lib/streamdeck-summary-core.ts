import type {
  StreamDeckAlert,
  StreamDeckAlertSeverity,
  StreamDeckCollectorAssetSummary,
  StreamDeckCollectorIntervalSummary,
  StreamDeckCollectorOverallSummary,
  StreamDeckStatus,
  StreamDeckTradingSummary,
  StreamDeckWeatherCloneSummary,
  StreamDeckWeatherMergeSummary,
} from "../types/streamdeck";

export type AssetKey = "btc" | "eth" | "sol" | "xrp";
export type IntervalKey = "5m" | "15m";

export type CollectorRow = {
  market_type: string;
  last_tick_at: string | null;
  last_5m: string;
  last_15m: string;
};

export type TradingMetricsRow = {
  open_trades: string;
  pnl_24h: string | null;
  last_trade_at: string | null;
};

export type BotLogRow = {
  logged_at: string;
  message: string;
  data: Record<string, unknown> | null;
};

export type CountRow = {
  active_positions: string;
};

export type WeatherCloneCycleRow = {
  captured_at: string;
  summary_data: Record<string, unknown> | null;
  health_data: Record<string, unknown> | null;
};

export const ROOT_TARGET_PATH = "/";
export const BOT_TARGET_PATH = "/bot";
export const ASSETS: AssetKey[] = ["btc", "eth", "sol", "xrp"];
export const INTERVALS: IntervalKey[] = ["5m", "15m"];

const STATUS_WEIGHT: Record<StreamDeckStatus, number> = {
  healthy: 0,
  degraded: 1,
  stale: 2,
  unknown: 3,
  error: 4,
};

const ALERT_WEIGHT: Record<StreamDeckAlertSeverity, number> = {
  info: 0,
  warning: 1,
  critical: 2,
};

export function toNumber(value: unknown): number {
  if (value == null) return 0;
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}

export function toStringOrNull(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function toBoolean(value: unknown): boolean {
  return value === true || value === "true" || value === 1 || value === "1";
}

export function parseIsoDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function ageSec(value: string | null | undefined, now = new Date()): number | null {
  const parsed = parseIsoDate(value);
  if (!parsed) return null;
  return Math.max(0, Math.round((now.getTime() - parsed.getTime()) / 1000));
}

export function pickWorstStatus(...statuses: StreamDeckStatus[]): StreamDeckStatus {
  return statuses.reduce<StreamDeckStatus>((worst, current) => {
    return STATUS_WEIGHT[current] > STATUS_WEIGHT[worst] ? current : worst;
  }, "healthy");
}

export function buildAlert(
  severity: StreamDeckAlertSeverity,
  source: StreamDeckAlert["source"],
  message: string,
  age: number | null,
  targetPath: string
): StreamDeckAlert {
  return {
    severity,
    source,
    message,
    ageSec: age,
    targetPath,
  };
}

export function sortAlerts(alerts: StreamDeckAlert[]) {
  return [...alerts].sort((left, right) => {
    const severityDiff = ALERT_WEIGHT[right.severity] - ALERT_WEIGHT[left.severity];
    if (severityDiff !== 0) return severityDiff;

    const leftAge = left.ageSec ?? Number.MAX_SAFE_INTEGER;
    const rightAge = right.ageSec ?? Number.MAX_SAFE_INTEGER;
    return leftAge - rightAge;
  });
}

export function formatAgeCompact(value: number | null): string {
  if (value == null) return "n/a";
  if (value < 60) return `${value}s`;
  const minutes = Math.round(value / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  return `${hours}h`;
}

export function intervalExpectedTicks(interval: IntervalKey) {
  return interval === "5m" ? 300 : 900;
}

function intervalObservedTicks(row: CollectorRow | undefined, interval: IntervalKey) {
  return interval === "5m" ? toNumber(row?.last_5m) : toNumber(row?.last_15m);
}

export function buildCollectorInterval(
  marketType: string,
  interval: IntervalKey,
  row: CollectorRow | undefined,
  now: Date
): StreamDeckCollectorIntervalSummary {
  const latestTickAt = row?.last_tick_at ?? null;
  const latestTickAgeSec = ageSec(latestTickAt, now);
  const observedTicks = intervalObservedTicks(row, interval);
  const expectedTicks = intervalExpectedTicks(interval);
  const ratio = expectedTicks > 0 ? observedTicks / expectedTicks : 0;

  let status: StreamDeckStatus = "unknown";
  if (latestTickAgeSec != null) {
    if (latestTickAgeSec > 30) {
      status = "stale";
    } else if (ratio >= 0.9) {
      status = "healthy";
    } else if (ratio >= 0.7) {
      status = "degraded";
    } else {
      status = "stale";
    }
  }

  return {
    marketType,
    status,
    latestTickAt,
    latestTickAgeSec,
    observedTicks,
    expectedTicks,
  };
}

export function buildCollectorSummary(rows: CollectorRow[], now: Date): {
  overall: StreamDeckCollectorOverallSummary;
  assets: Record<AssetKey, StreamDeckCollectorAssetSummary>;
  alerts: StreamDeckAlert[];
} {
  const byMarketType = new Map(rows.map((row) => [row.market_type, row]));
  const alerts: StreamDeckAlert[] = [];

  const assets = Object.fromEntries(
    ASSETS.map((asset) => {
      const intervalSummaries = {
        "5m": buildCollectorInterval(`${asset}_5m`, "5m", byMarketType.get(`${asset}_5m`), now),
        "15m": buildCollectorInterval(
          `${asset}_15m`,
          "15m",
          byMarketType.get(`${asset}_15m`),
          now
        ),
      };

      const latestTickAt =
        [intervalSummaries["5m"].latestTickAt, intervalSummaries["15m"].latestTickAt]
          .filter((value): value is string => Boolean(value))
          .sort()
          .at(-1) ?? null;

      const latestTickAgeSec =
        [intervalSummaries["5m"].latestTickAgeSec, intervalSummaries["15m"].latestTickAgeSec]
          .filter((value): value is number => value != null)
          .sort((left, right) => left - right)
          .at(0) ?? null;

      const status = pickWorstStatus(
        intervalSummaries["5m"].status,
        intervalSummaries["15m"].status
      );

      if (status === "stale") {
        alerts.push(
          buildAlert(
            "critical",
            "collector",
            `${asset.toUpperCase()} collector is stale (${formatAgeCompact(latestTickAgeSec)} old)`,
            latestTickAgeSec,
            ROOT_TARGET_PATH
          )
        );
      } else if (status === "degraded") {
        alerts.push(
          buildAlert(
            "warning",
            "collector",
            `${asset.toUpperCase()} collector is degraded`,
            latestTickAgeSec,
            ROOT_TARGET_PATH
          )
        );
      } else if (status === "unknown") {
        alerts.push(
          buildAlert(
            "warning",
            "collector",
            `${asset.toUpperCase()} collector has no recent data`,
            latestTickAgeSec,
            ROOT_TARGET_PATH
          )
        );
      }

      return [
        asset,
        {
          asset,
          status,
          latestTickAt,
          latestTickAgeSec,
          intervals: intervalSummaries,
        } satisfies StreamDeckCollectorAssetSummary,
      ];
    })
  ) as Record<AssetKey, StreamDeckCollectorAssetSummary>;

  const assetSummaries = Object.values(assets);
  const overallStatus = assetSummaries.reduce<StreamDeckStatus>((worst, current) => {
    return STATUS_WEIGHT[current.status] > STATUS_WEIGHT[worst] ? current.status : worst;
  }, "healthy");
  const healthyAssetCount = assetSummaries.filter((asset) => asset.status === "healthy").length;
  const latestTickAt =
    assetSummaries
      .map((asset) => asset.latestTickAt)
      .filter((value): value is string => Boolean(value))
      .sort()
      .at(-1) ?? null;
  const latestTickAgeSec =
    assetSummaries
      .map((asset) => asset.latestTickAgeSec)
      .filter((value): value is number => value != null)
      .sort((left, right) => left - right)
      .at(0) ?? null;

  return {
    overall: {
      status: overallStatus,
      latestTickAt,
      latestTickAgeSec,
      healthyAssetCount,
      totalAssetCount: ASSETS.length,
      message: `${healthyAssetCount}/${ASSETS.length} assets healthy`,
    },
    assets,
    alerts,
  };
}

export function buildTradingSummary(
  metrics: TradingMetricsRow | undefined,
  heartbeat: BotLogRow | undefined,
  recentError: BotLogRow | undefined,
  now: Date
): {
  summary: StreamDeckTradingSummary;
  alerts: StreamDeckAlert[];
} {
  const heartbeatAgeSec = ageSec(heartbeat?.logged_at, now);
  const lastTradeAt = metrics?.last_trade_at ?? null;
  const lastTradeAgeSec = ageSec(lastTradeAt, now);
  const errorAgeSec = ageSec(recentError?.logged_at, now);

  let status: StreamDeckStatus = "unknown";
  if (heartbeatAgeSec != null) {
    if (heartbeatAgeSec > 120) {
      status = "stale";
    } else if (heartbeatAgeSec > 75) {
      status = "degraded";
    } else {
      status = "healthy";
    }
  }

  if (errorAgeSec != null && errorAgeSec <= 300 && status !== "stale") {
    status = pickWorstStatus(status, "degraded");
  }

  const summary: StreamDeckTradingSummary = {
    status,
    heartbeatAt: heartbeat?.logged_at ?? null,
    heartbeatAgeSec,
    pnl24h: toNumber(metrics?.pnl_24h),
    openTrades: toNumber(metrics?.open_trades),
    lastTradeAt,
    lastTradeAgeSec,
    recentError: recentError?.message ?? null,
    targetPath: BOT_TARGET_PATH,
  };

  const alerts: StreamDeckAlert[] = [];
  if (status === "stale") {
    alerts.push(
      buildAlert(
        "critical",
        "trading",
        `Trading heartbeat is stale (${formatAgeCompact(heartbeatAgeSec)} old)`,
        heartbeatAgeSec,
        BOT_TARGET_PATH
      )
    );
  } else if (status === "unknown") {
    alerts.push(
      buildAlert(
        "warning",
        "trading",
        "Trading heartbeat has not been recorded yet",
        heartbeatAgeSec,
        BOT_TARGET_PATH
      )
    );
  }

  if (recentError?.message && errorAgeSec != null && errorAgeSec <= 600) {
    alerts.push(
      buildAlert("warning", "trading", recentError.message, errorAgeSec, BOT_TARGET_PATH)
    );
  }

  return { summary, alerts };
}

export function buildWeatherMergeSummary(
  latestSummary: BotLogRow | undefined,
  activePositionRow: CountRow | undefined,
  now: Date
): {
  summary: StreamDeckWeatherMergeSummary;
  alerts: StreamDeckAlert[];
} {
  const summaryData = latestSummary?.data ?? {};
  const summaryAgeSec = ageSec(latestSummary?.logged_at, now);
  const standDownReason = toStringOrNull(summaryData["stand_down_reason"]);
  const candidateCount = toNumber(summaryData["candidate_count"]);
  const activePositions = toNumber(activePositionRow?.active_positions);

  let status: StreamDeckStatus = "unknown";
  if (summaryAgeSec != null) {
    if (summaryAgeSec > 120) {
      status = "stale";
    } else if (standDownReason || candidateCount === 0) {
      status = "degraded";
    } else {
      status = "healthy";
    }
  }

  const summary: StreamDeckWeatherMergeSummary = {
    status,
    summaryAt: latestSummary?.logged_at ?? null,
    summaryAgeSec,
    activePositions,
    candidateCount,
    standDownReason,
    targetPath: BOT_TARGET_PATH,
  };

  const alerts: StreamDeckAlert[] = [];
  if (status === "stale") {
    alerts.push(
      buildAlert(
        "critical",
        "weather_merge",
        `Weather merge summary is stale (${formatAgeCompact(summaryAgeSec)} old)`,
        summaryAgeSec,
        BOT_TARGET_PATH
      )
    );
  } else if (standDownReason) {
    alerts.push(
      buildAlert(
        "warning",
        "weather_merge",
        `Weather merge standing down: ${standDownReason}`,
        summaryAgeSec,
        BOT_TARGET_PATH
      )
    );
  } else if (summaryAgeSec != null && candidateCount === 0) {
    alerts.push(
      buildAlert(
        "info",
        "weather_merge",
        "Weather merge is alive but has no current candidates",
        summaryAgeSec,
        BOT_TARGET_PATH
      )
    );
  }

  return { summary, alerts };
}

function readNestedStatus(
  value: Record<string, unknown> | null,
  key: string
): string | null {
  if (!value) return null;
  const nested = value[key];
  if (!nested || typeof nested !== "object") return null;
  return toStringOrNull((nested as Record<string, unknown>).status);
}

export function buildWeatherCloneSummary(
  latestCycle: WeatherCloneCycleRow | undefined,
  activePositionRow: CountRow | undefined,
  now: Date
): {
  summary: StreamDeckWeatherCloneSummary;
  alerts: StreamDeckAlert[];
} {
  const summaryData = latestCycle?.summary_data ?? {};
  const capturedAt = latestCycle?.captured_at ?? null;
  const capturedAgeSec = ageSec(capturedAt, now);
  const candidateCount = toNumber(summaryData["candidate_count"]);
  const quoteCoverageRatio = toNumber(summaryData["quote_coverage_ratio"]);
  const executionAllowed = toBoolean(summaryData["execution_allowed"]);
  const marketDataHealth =
    toStringOrNull(summaryData["market_data_health"]) ??
    readNestedStatus(latestCycle?.health_data ?? null, "market_data");
  const activePositions = toNumber(activePositionRow?.active_positions);

  let status: StreamDeckStatus = "unknown";
  if (capturedAgeSec != null) {
    if (capturedAgeSec > 120) {
      status = "stale";
    } else if (marketDataHealth !== "healthy" || !executionAllowed || candidateCount === 0) {
      status = "degraded";
    } else {
      status = "healthy";
    }
  }

  const summary: StreamDeckWeatherCloneSummary = {
    status,
    capturedAt,
    capturedAgeSec,
    activePositions,
    candidateCount,
    quoteCoverageRatio,
    executionAllowed,
    targetPath: BOT_TARGET_PATH,
  };

  const alerts: StreamDeckAlert[] = [];
  if (status === "stale") {
    alerts.push(
      buildAlert(
        "critical",
        "weather_clone",
        `Weather clone cycle is stale (${formatAgeCompact(capturedAgeSec)} old)`,
        capturedAgeSec,
        BOT_TARGET_PATH
      )
    );
  } else {
    if (marketDataHealth && marketDataHealth !== "healthy") {
      alerts.push(
        buildAlert(
          "warning",
          "weather_clone",
          `Weather clone market data is ${marketDataHealth}`,
          capturedAgeSec,
          BOT_TARGET_PATH
        )
      );
    }

    if (!executionAllowed && capturedAgeSec != null) {
      alerts.push(
        buildAlert(
          "warning",
          "weather_clone",
          "Weather clone is running without live execution enabled",
          capturedAgeSec,
          BOT_TARGET_PATH
        )
      );
    }

    if (capturedAgeSec != null && candidateCount === 0) {
      alerts.push(
        buildAlert(
          "info",
          "weather_clone",
          "Weather clone is alive but has no current candidates",
          capturedAgeSec,
          BOT_TARGET_PATH
        )
      );
    }
  }

  return { summary, alerts };
}

export function emptyCollectorSummary(): {
  overall: StreamDeckCollectorOverallSummary;
  assets: Record<AssetKey, StreamDeckCollectorAssetSummary>;
  alerts: StreamDeckAlert[];
} {
  const assets = Object.fromEntries(
    ASSETS.map((asset) => {
      const intervals = Object.fromEntries(
        INTERVALS.map((interval) => [
          interval,
          {
            marketType: `${asset}_${interval}`,
            status: "unknown",
            latestTickAt: null,
            latestTickAgeSec: null,
            observedTicks: 0,
            expectedTicks: intervalExpectedTicks(interval),
          } satisfies StreamDeckCollectorIntervalSummary,
        ])
      ) as StreamDeckCollectorAssetSummary["intervals"];

      return [
        asset,
        {
          asset,
          status: "unknown",
          latestTickAt: null,
          latestTickAgeSec: null,
          intervals,
        } satisfies StreamDeckCollectorAssetSummary,
      ];
    })
  ) as Record<AssetKey, StreamDeckCollectorAssetSummary>;

  return {
    overall: {
      status: "unknown",
      latestTickAt: null,
      latestTickAgeSec: null,
      healthyAssetCount: 0,
      totalAssetCount: ASSETS.length,
      message: "No collector data available",
    },
    assets,
    alerts: [
      buildAlert("critical", "collector", "Collector summary query failed", null, ROOT_TARGET_PATH),
    ],
  };
}
