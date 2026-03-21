import type { Outcome } from "@/types/market";
import { ASSET_COLORS, OUTCOME_COLORS } from "./constants";

export function formatUTCTime(dateStr: string): string {
  const d = new Date(dateStr);
  return `${d.getUTCHours().toString().padStart(2, "0")}:${d.getUTCMinutes().toString().padStart(2, "0")}`;
}

export function formatUTCDate(dateStr: string): string {
  const d = new Date(dateStr);
  return `${(d.getUTCMonth() + 1).toString().padStart(2, "0")}/${d.getUTCDate().toString().padStart(2, "0")}`;
}

export function formatISOTime(dateStr: string): string {
  return new Date(dateStr).toISOString().slice(11, 16);
}

export function formatClockTime(): string {
  return new Date().toISOString().slice(11, 19);
}

export function shortenId(id: string): string {
  if (id.length <= 9) return id;
  return `${id.slice(0, 6)}…${id.slice(-3)}`;
}

export function formatCompactNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  return n.toLocaleString("en-US");
}

export function parseMarketType(type: string) {
  const [asset, interval] = type.split("_");
  return { asset: asset.toUpperCase(), interval };
}

export function getAssetColor(asset: string): string {
  return ASSET_COLORS[asset.toLowerCase()] || "#e4f600";
}

export function getOutcomeColors(outcome: string | null) {
  if (outcome === "Up") return OUTCOME_COLORS.Up;
  if (outcome === "Down") return OUTCOME_COLORS.Down;
  return OUTCOME_COLORS.Unknown;
}

export function getOutcomeLabel(outcome: string | null): string {
  if (outcome === "Up") return "Up";
  if (outcome === "Down") return "Down";
  return "Unknown";
}
