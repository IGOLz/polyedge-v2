export type StreamDeckStatus = "healthy" | "degraded" | "stale" | "error" | "unknown";

export type StreamDeckAlertSeverity = "info" | "warning" | "critical";

export type StreamDeckAlertSource =
  | "collector"
  | "trading"
  | "weather_merge"
  | "weather_clone";

export interface StreamDeckAlert {
  severity: StreamDeckAlertSeverity;
  source: StreamDeckAlertSource;
  message: string;
  ageSec: number | null;
  targetPath: string;
}

export interface StreamDeckCollectorIntervalSummary {
  marketType: string;
  status: StreamDeckStatus;
  latestTickAt: string | null;
  latestTickAgeSec: number | null;
  observedTicks: number;
  expectedTicks: number;
}

export interface StreamDeckCollectorAssetSummary {
  asset: "btc" | "eth" | "sol" | "xrp";
  status: StreamDeckStatus;
  latestTickAt: string | null;
  latestTickAgeSec: number | null;
  intervals: {
    "5m": StreamDeckCollectorIntervalSummary;
    "15m": StreamDeckCollectorIntervalSummary;
  };
}

export interface StreamDeckCollectorOverallSummary {
  status: StreamDeckStatus;
  latestTickAt: string | null;
  latestTickAgeSec: number | null;
  healthyAssetCount: number;
  totalAssetCount: number;
  message: string;
}

export interface StreamDeckTradingSummary {
  status: StreamDeckStatus;
  heartbeatAt: string | null;
  heartbeatAgeSec: number | null;
  pnl24h: number;
  openTrades: number;
  lastTradeAt: string | null;
  lastTradeAgeSec: number | null;
  recentError: string | null;
  targetPath: string;
}

export interface StreamDeckWeatherMergeSummary {
  status: StreamDeckStatus;
  summaryAt: string | null;
  summaryAgeSec: number | null;
  activePositions: number;
  candidateCount: number;
  standDownReason: string | null;
  targetPath: string;
}

export interface StreamDeckWeatherCloneSummary {
  status: StreamDeckStatus;
  capturedAt: string | null;
  capturedAgeSec: number | null;
  activePositions: number;
  candidateCount: number;
  quoteCoverageRatio: number;
  executionAllowed: boolean;
  targetPath: string;
}

export interface StreamDeckSummaryPayload {
  version: number;
  generatedAt: string;
  collector: {
    overall: StreamDeckCollectorOverallSummary;
    assets: Record<"btc" | "eth" | "sol" | "xrp", StreamDeckCollectorAssetSummary>;
  };
  trading: StreamDeckTradingSummary;
  weatherMerge: StreamDeckWeatherMergeSummary;
  weatherClone: StreamDeckWeatherCloneSummary;
  alerts: StreamDeckAlert[];
}
