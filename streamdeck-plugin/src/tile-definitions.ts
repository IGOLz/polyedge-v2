import type { JsonObject } from "@elgato/utils";

export const TILE_IDS = [
  "collector_overall",
  "asset_btc",
  "asset_eth",
  "asset_sol",
  "asset_xrp",
  "trading_status",
  "trading_pnl_24h",
  "trading_open",
  "trading_last_trade",
  "trading_alerts",
  "merge_status",
  "merge_positions",
  "clone_status",
  "clone_coverage",
  "ops_alerts",
] as const;

export type TileId = (typeof TILE_IDS)[number];

export type TimezoneMode = "utc" | "local";

export type GlobalSettings = JsonObject & {
  baseUrl: string;
  bearerToken: string;
  pollIntervalSec: number;
  timezoneMode: TimezoneMode;
};

export type TileSettings = JsonObject & {
  tileId: TileId;
  targetPath?: string;
};

export const DEFAULT_GLOBAL_SETTINGS: GlobalSettings = {
  baseUrl: "",
  bearerToken: "",
  pollIntervalSec: 10,
  timezoneMode: "utc",
};

export const DEFAULT_TILE_SETTINGS: TileSettings = {
  tileId: "collector_overall",
  targetPath: "/",
};

export const TILE_DEFINITIONS: Record<TileId, { label: string; targetPath: string }> = {
  collector_overall: { label: "Collector", targetPath: "/" },
  asset_btc: { label: "BTC Feed", targetPath: "/" },
  asset_eth: { label: "ETH Feed", targetPath: "/" },
  asset_sol: { label: "SOL Feed", targetPath: "/" },
  asset_xrp: { label: "XRP Feed", targetPath: "/" },
  trading_status: { label: "Trading", targetPath: "/bot" },
  trading_pnl_24h: { label: "PnL 24h", targetPath: "/bot" },
  trading_open: { label: "Open Trades", targetPath: "/bot" },
  trading_last_trade: { label: "Last Trade", targetPath: "/bot" },
  trading_alerts: { label: "Trade Alerts", targetPath: "/bot" },
  merge_status: { label: "Merge Bot", targetPath: "/bot" },
  merge_positions: { label: "Merge Pos", targetPath: "/bot" },
  clone_status: { label: "Clone Bot", targetPath: "/bot" },
  clone_coverage: { label: "Clone Cover", targetPath: "/bot" },
  ops_alerts: { label: "Ops Alerts", targetPath: "/bot" },
};

export function isTileId(value: unknown): value is TileId {
  return typeof value === "string" && TILE_IDS.includes(value as TileId);
}

export function normalizeGlobalSettings(value: Partial<GlobalSettings> | undefined): GlobalSettings {
  const pollInterval =
    typeof value?.pollIntervalSec === "number"
      ? value.pollIntervalSec
      : Number(value?.pollIntervalSec ?? DEFAULT_GLOBAL_SETTINGS.pollIntervalSec);

  return {
    baseUrl: typeof value?.baseUrl === "string" ? value.baseUrl.trim() : "",
    bearerToken: typeof value?.bearerToken === "string" ? value.bearerToken.trim() : "",
    pollIntervalSec:
      Number.isFinite(pollInterval) && pollInterval > 0
        ? Math.max(5, Math.min(60, Math.round(pollInterval)))
        : DEFAULT_GLOBAL_SETTINGS.pollIntervalSec,
    timezoneMode: value?.timezoneMode === "local" ? "local" : "utc",
  };
}

export function normalizeTileSettings(value: Partial<TileSettings> | undefined): TileSettings {
  const tileId = isTileId(value?.tileId) ? value.tileId : DEFAULT_TILE_SETTINGS.tileId;
  const targetPath =
    typeof value?.targetPath === "string" && value.targetPath.trim().length > 0
      ? value.targetPath.trim()
      : TILE_DEFINITIONS[tileId].targetPath;

  return {
    tileId,
    targetPath,
  };
}
