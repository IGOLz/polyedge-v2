"use client";

import { useRef, useState } from "react";
import { sortMarketTypes } from "@/lib/constants";
import { GlassPanel } from "@/components/ui/glass-panel";

interface HeatmapRow {
  market_type: string;
  time_offset: string;
  price_bucket: string;
  sample_count: string;
  up_win_rate: string;
}

interface CalibrationHeatmapProps {
  data: HeatmapRow[];
}

const ASSET_NAMES: Record<string, string> = {
  btc: "Bitcoin",
  eth: "Ethereum",
  sol: "Solana",
  xrp: "XRP",
};

function formatSeconds(s: number): string {
  if (s < 60) return `${s}s`;
  const min = Math.floor(s / 60);
  const sec = s % 60;
  return sec > 0 ? `${min}m${sec}s` : `${min}m`;
}

function getHeatColor(winRate: number): string {
  // Strong Down edge (low win rate) = red, neutral = zinc, strong Up edge = emerald
  const deviation = winRate - 50;
  if (deviation <= -15) return "bg-red-500/80 text-white";
  if (deviation <= -10) return "bg-red-500/50 text-red-100";
  if (deviation <= -5) return "bg-red-500/25 text-red-200";
  if (deviation < 5) return "bg-zinc-800/60 text-zinc-400";
  if (deviation < 10) return "bg-emerald-500/25 text-emerald-200";
  if (deviation < 15) return "bg-emerald-500/50 text-emerald-100";
  return "bg-emerald-500/80 text-white";
}

// Fixed price buckets: 5¢ to 95¢ in 5¢ increments
const PRICE_BUCKETS = Array.from({ length: 19 }, (_, i) => (i + 1) * 0.05);

function HeatmapGrid({ data, marketTypes }: { data: HeatmapRow[]; marketTypes: string[] }) {
  const [selectedAsset, setSelectedAsset] = useState(marketTypes[0] || "");
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    flipBelow: boolean;
    winRate: number;
    edge: number;
    samples: number;
    price: number;
    time: string;
  } | null>(null);

  const assetData = data.filter((d) => d.market_type === selectedAsset);

  // Get unique sorted time offsets
  const timeOffsets = [...new Set(assetData.map((d) => parseInt(d.time_offset)))].sort((a, b) => a - b);

  // Build lookup map — normalize keys to match parsed number toString()
  const lookup = new Map<string, HeatmapRow>();
  for (const row of assetData) {
    lookup.set(`${parseInt(row.time_offset)}_${parseFloat(row.price_bucket)}`, row);
  }

  if (timeOffsets.length === 0) {
    return (
      <GlassPanel variant="glow-wide" className="p-8 text-center text-sm text-zinc-500">
        Not enough data yet
      </GlassPanel>
    );
  }

  return (
    <GlassPanel variant="glow-wide" className="p-6 overflow-visible">

      <div className="relative" ref={containerRef} onMouseLeave={() => setTooltip(null)}>
        {/* Asset selector */}
        <div className="mb-5 flex items-center gap-2">
          {marketTypes.map((type) => {
            const asset = type.split("_")[0];
            const interval = type.split("_")[1];
            return (
              <button
                key={type}
                onClick={() => setSelectedAsset(type)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  selectedAsset === type
                    ? "bg-primary/20 text-primary"
                    : "bg-zinc-800/60 text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {(ASSET_NAMES[asset] || asset.toUpperCase())} {interval}
              </button>
            );
          })}
        </div>

        {/* Heatmap grid */}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className="p-1.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  Time ↓ / Price →
                </th>
                {PRICE_BUCKETS.map((bucket) => (
                  <th key={bucket} className="p-1.5 text-center text-xs font-mono font-medium text-zinc-400">
                    {(bucket * 100).toFixed(0)}¢
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {timeOffsets.map((offset) => (
                <tr key={offset}>
                  <td className="p-1.5 text-xs font-mono font-medium text-zinc-400 whitespace-nowrap">
                    {formatSeconds(offset)}
                  </td>
                  {PRICE_BUCKETS.map((bucket) => {
                    const cell = lookup.get(`${offset}_${bucket}`);
                    if (!cell) {
                      return (
                        <td key={bucket} className="p-1">
                          <div className="flex h-8 items-center justify-center rounded bg-zinc-900/40 text-xs text-zinc-600">
                            —
                          </div>
                        </td>
                      );
                    }
                    const winRate = parseFloat(cell.up_win_rate);
                    const samples = parseInt(cell.sample_count);
                    const edge = winRate - 50;
                    return (
                      <td key={bucket} className="p-1">
                        <div
                          className={`flex h-8 items-center justify-center rounded text-xs font-mono font-semibold cursor-default ${getHeatColor(winRate)}`}
                          onMouseEnter={(e) => {
                            if (!containerRef.current) return;
                            const rect = e.currentTarget.getBoundingClientRect();
                            const parent = containerRef.current.getBoundingClientRect();
                            const cellTop = rect.top - parent.top;
                            const flipBelow = cellTop < 220;
                            setTooltip({
                              x: rect.left - parent.left + rect.width / 2,
                              y: flipBelow ? rect.bottom - parent.top : cellTop,
                              flipBelow,
                              winRate,
                              edge,
                              samples,
                              price: bucket,
                              time: formatSeconds(offset),
                            });
                          }}
                          onMouseLeave={() => setTooltip(null)}
                        >
                          {winRate.toFixed(0)}%
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>

        </div>

        {tooltip && (() => {
          const isUp = tooltip.edge > 0;
          const edgeAbs = Math.abs(tooltip.edge);
          const edgeLabel = edgeAbs >= 15 ? "Strong" : edgeAbs >= 8 ? "Moderate" : "Slight";
          return (
            <div
              className={`pointer-events-none absolute z-50 -translate-x-1/2 w-48 rounded-lg border border-zinc-700/60 bg-zinc-900/95 backdrop-blur-sm shadow-2xl overflow-hidden ${tooltip.flipBelow ? "" : "-translate-y-full"}`}
              style={{ left: tooltip.x, top: tooltip.flipBelow ? tooltip.y + 8 : tooltip.y - 8 }}
            >
              <div className={`px-3 py-1.5 text-xs font-semibold uppercase tracking-wider ${isUp ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"}`}>
                {edgeLabel} {isUp ? "Up" : "Down"} Edge
              </div>
              <div className="px-3 py-2.5 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">Win Rate</span>
                  <span className={`font-mono text-sm font-bold ${isUp ? "text-emerald-400" : "text-red-400"}`}>
                    {tooltip.winRate.toFixed(1)}%
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${isUp ? "bg-emerald-400" : "bg-red-400"}`}
                    style={{ width: `${tooltip.winRate}%` }}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">Edge</span>
                  <span className={`font-mono text-xs font-semibold ${isUp ? "text-emerald-400" : "text-red-400"}`}>
                    {isUp ? "+" : ""}{tooltip.edge.toFixed(1)}%
                  </span>
                </div>
                <div className="h-px bg-zinc-800" />
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">Price</span>
                  <span className="font-mono text-xs font-semibold text-zinc-200">
                    {(tooltip.price * 100).toFixed(0)}¢
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">Time</span>
                  <span className="font-mono text-xs text-zinc-300">{tooltip.time}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">Samples</span>
                  <span className="font-mono text-xs text-zinc-300">{tooltip.samples}</span>
                </div>
              </div>
            </div>
          );
        })()}

        {/* Legend */}
        <div className="mt-4 flex items-center justify-center gap-2">
          <span className="text-xs text-zinc-500">Down edge</span>
          <div className="flex gap-0.5">
            <div className="h-3 w-6 rounded-sm bg-red-500/80" />
            <div className="h-3 w-6 rounded-sm bg-red-500/50" />
            <div className="h-3 w-6 rounded-sm bg-red-500/25" />
            <div className="h-3 w-6 rounded-sm bg-zinc-800/60" />
            <div className="h-3 w-6 rounded-sm bg-emerald-500/25" />
            <div className="h-3 w-6 rounded-sm bg-emerald-500/50" />
            <div className="h-3 w-6 rounded-sm bg-emerald-500/80" />
          </div>
          <span className="text-xs text-zinc-500">Up edge</span>
        </div>
      </div>
    </GlassPanel>
  );
}

export function CalibrationHeatmap({ data }: CalibrationHeatmapProps) {
  const marketTypes = sortMarketTypes([...new Set(data.map((d) => d.market_type))]);

  if (marketTypes.length === 0) {
    return (
      <GlassPanel variant="glow-wide" className="p-8 text-center text-sm text-zinc-500">
        Not enough data yet
      </GlassPanel>
    );
  }

  return <HeatmapGrid data={data} marketTypes={marketTypes} />;
}
