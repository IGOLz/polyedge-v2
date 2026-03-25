import {
  TILE_DEFINITIONS,
  type TileId,
  type TimezoneMode,
} from "./tile-definitions.js";
import type {
  StreamDeckAlert,
  StreamDeckAlertSeverity,
  StreamDeckStatus,
  StreamDeckSummaryPayload,
} from "./types.js";

interface RenderContext {
  isCached: boolean;
  errorMessage: string | null;
  timezoneMode: TimezoneMode;
  now: Date;
}

interface TileViewModel {
  label: string;
  value: string;
  footer: string;
  status: StreamDeckStatus;
}

const STATUS_COLORS: Record<StreamDeckStatus, string> = {
  healthy: "#22c55e",
  degraded: "#f59e0b",
  stale: "#ef4444",
  error: "#ef4444",
  unknown: "#6b7280",
};

const STATUS_TEXT: Record<StreamDeckStatus, string> = {
  healthy: "LIVE",
  degraded: "WARN",
  stale: "STALE",
  error: "ERR",
  unknown: "WAIT",
};

function escapeXml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function truncate(value: string, maxLength: number) {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1)}…`;
}

function formatCurrency(value: number) {
  const prefix = value < 0 ? "-$" : "$";
  return `${prefix}${Math.abs(value).toFixed(Math.abs(value) >= 100 ? 0 : 1)}`;
}

function formatRatioPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function formatAge(value: number | null) {
  if (value == null) return "n/a";
  if (value < 60) return `${value}s`;
  if (value < 3600) return `${Math.round(value / 60)}m`;
  return `${Math.round(value / 3600)}h`;
}

function formatTimestamp(value: string | null, timezoneMode: TimezoneMode) {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "n/a";

  return date.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezoneMode === "utc" ? "UTC" : undefined,
  });
}

function severityToStatus(severity: StreamDeckAlertSeverity): StreamDeckStatus {
  if (severity === "critical") return "error";
  if (severity === "warning") return "degraded";
  return "healthy";
}

function highestAlert(alerts: StreamDeckAlert[]) {
  return [...alerts].sort((left, right) => {
    const rank = { info: 0, warning: 1, critical: 2 };
    return rank[right.severity] - rank[left.severity];
  })[0] ?? null;
}

function filterAlerts(
  payload: StreamDeckSummaryPayload,
  source: StreamDeckAlert["source"]
) {
  return payload.alerts.filter((alert) => alert.source === source);
}

function buildTileModel(
  tileId: TileId,
  payload: StreamDeckSummaryPayload,
  context: RenderContext
): TileViewModel {
  switch (tileId) {
    case "collector_overall":
      return {
        label: "Collector",
        value: `${payload.collector.overall.healthyAssetCount}/${payload.collector.overall.totalAssetCount}`,
        footer: truncate(payload.collector.overall.message, 20),
        status: payload.collector.overall.status,
      };
    case "asset_btc":
    case "asset_eth":
    case "asset_sol":
    case "asset_xrp": {
      const assetKey = tileId.replace("asset_", "") as keyof typeof payload.collector.assets;
      const asset = payload.collector.assets[assetKey];
      return {
        label: TILE_DEFINITIONS[tileId].label,
        value: `5m ${asset.intervals["5m"].observedTicks}`,
        footer: truncate(
          `15m ${asset.intervals["15m"].observedTicks} • ${formatAge(asset.latestTickAgeSec)}`,
          20
        ),
        status: asset.status,
      };
    }
    case "trading_status":
      return {
        label: "Trading",
        value:
          payload.trading.status === "healthy"
            ? "LIVE"
            : payload.trading.status === "degraded"
              ? "WARN"
              : payload.trading.status === "stale"
                ? "STALE"
                : "WAIT",
        footer: truncate(`HB ${formatAge(payload.trading.heartbeatAgeSec)}`, 20),
        status: payload.trading.status,
      };
    case "trading_pnl_24h":
      return {
        label: "PnL 24h",
        value: formatCurrency(payload.trading.pnl24h),
        footer: truncate(`open ${payload.trading.openTrades}`, 20),
        status: payload.trading.status,
      };
    case "trading_open":
      return {
        label: "Open Trades",
        value: String(payload.trading.openTrades),
        footer: truncate(`HB ${formatAge(payload.trading.heartbeatAgeSec)}`, 20),
        status: payload.trading.status,
      };
    case "trading_last_trade":
      return {
        label: "Last Trade",
        value: payload.trading.lastTradeAgeSec == null ? "n/a" : formatAge(payload.trading.lastTradeAgeSec),
        footer: truncate(formatTimestamp(payload.trading.lastTradeAt, context.timezoneMode), 20),
        status: payload.trading.status,
      };
    case "trading_alerts": {
      const alerts = filterAlerts(payload, "trading");
      const topAlert = highestAlert(alerts);
      return {
        label: "Trade Alerts",
        value: String(alerts.length),
        footer: truncate(topAlert?.message ?? "no active alerts", 20),
        status: topAlert ? severityToStatus(topAlert.severity) : "healthy",
      };
    }
    case "merge_status":
      return {
        label: "Merge Bot",
        value:
          payload.weatherMerge.status === "healthy"
            ? "LIVE"
            : payload.weatherMerge.standDownReason
              ? "STAND"
              : payload.weatherMerge.status === "stale"
                ? "STALE"
                : "IDLE",
        footer: truncate(
          payload.weatherMerge.standDownReason
            ? payload.weatherMerge.standDownReason
            : `cand ${payload.weatherMerge.candidateCount}`,
          20
        ),
        status: payload.weatherMerge.status,
      };
    case "merge_positions":
      return {
        label: "Merge Pos",
        value: String(payload.weatherMerge.activePositions),
        footer: truncate(`cand ${payload.weatherMerge.candidateCount}`, 20),
        status: payload.weatherMerge.status,
      };
    case "clone_status":
      return {
        label: "Clone Bot",
        value:
          payload.weatherClone.status === "healthy"
            ? "LIVE"
            : payload.weatherClone.status === "stale"
              ? "STALE"
              : payload.weatherClone.executionAllowed
                ? "WARN"
                : "SHDW",
        footer: truncate(`cand ${payload.weatherClone.candidateCount}`, 20),
        status: payload.weatherClone.status,
      };
    case "clone_coverage":
      return {
        label: "Clone Cover",
        value: formatRatioPercent(payload.weatherClone.quoteCoverageRatio),
        footer: truncate(
          `${payload.weatherClone.executionAllowed ? "live" : "shadow"} • ${payload.weatherClone.candidateCount} cand`,
          20
        ),
        status: payload.weatherClone.status,
      };
    case "ops_alerts": {
      const topAlert = highestAlert(payload.alerts);
      return {
        label: "Ops Alerts",
        value: String(payload.alerts.length),
        footer: truncate(topAlert?.message ?? "no active alerts", 20),
        status: topAlert ? severityToStatus(topAlert.severity) : "healthy",
      };
    }
    default:
      return {
        label: "Monitor Tile",
        value: "n/a",
        footer: "unsupported tile",
        status: "unknown",
      };
  }
}

function wrapCachedState(view: TileViewModel, context: RenderContext): TileViewModel {
  if (!context.isCached) return view;

  return {
    ...view,
    footer: truncate(`cached • ${view.footer}`, 20),
    status: view.status === "error" ? "error" : "stale",
  };
}

function buildPlaceholderTile(tileId: TileId, context: RenderContext): TileViewModel {
  if (!context.errorMessage) {
    return {
      label: TILE_DEFINITIONS[tileId].label,
      value: "SETUP",
      footer: "set URL + token",
      status: "unknown",
    };
  }

  return {
    label: TILE_DEFINITIONS[tileId].label,
    value: "ERROR",
    footer: truncate(context.errorMessage, 20),
    status: "error",
  };
}

export function renderTileImage(
  tileId: TileId,
  payload: StreamDeckSummaryPayload | null,
  context: RenderContext
) {
  const view = payload
    ? wrapCachedState(buildTileModel(tileId, payload, context), context)
    : buildPlaceholderTile(tileId, context);

  const accent = STATUS_COLORS[view.status];
  const statusText = STATUS_TEXT[view.status];
  const label = escapeXml(truncate(view.label, 18));
  const value = escapeXml(truncate(view.value, 12));
  const footer = escapeXml(truncate(view.footer, 22));
  const valueFontSize = value.length >= 10 ? 18 : value.length >= 7 ? 22 : 28;

  return `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 144 144">
  <defs>
    <linearGradient id="accent" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="${accent}" stop-opacity="0.95" />
      <stop offset="100%" stop-color="#0b1220" stop-opacity="0.95" />
    </linearGradient>
  </defs>
  <rect width="144" height="144" rx="20" fill="#0a0f1a" />
  <rect x="0" y="0" width="144" height="22" rx="20" fill="url(#accent)" />
  <circle cx="122" cy="11" r="5" fill="#f8fafc" fill-opacity="0.95" />
  <text x="12" y="40" fill="#cbd5e1" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="700">${label}</text>
  <text x="12" y="84" fill="#f8fafc" font-family="Arial, Helvetica, sans-serif" font-size="${valueFontSize}" font-weight="700">${value}</text>
  <text x="12" y="118" fill="#94a3b8" font-family="Arial, Helvetica, sans-serif" font-size="11" font-weight="600">${footer}</text>
  <text x="12" y="132" fill="${accent}" font-family="Arial, Helvetica, sans-serif" font-size="10" font-weight="700">${statusText}</text>
</svg>`.trim();
}
