"use client";

import { useState } from "react";
import { parseMarketType, getAssetColor } from "@/lib/formatters";
import { sortMarketTypes } from "@/lib/constants";
import { GlassPanel } from "@/components/ui/glass-panel";

interface EdgeRow {
  market_type: string;
  time_window: string;
  price_bucket: string;
  implied_prob: string;
  actual_win_rate: string;
  edge: string;
  sample_count: string;
  direction: string;
}

const COLLAPSED_COUNT = 5;

function formatSeconds(s: number): string {
  if (s < 60) return `${s}s`;
  const min = Math.floor(s / 60);
  return `${min}m`;
}

function getEdgeStrength(edge: number): { label: string; color: string; bg: string } {
  const abs = Math.abs(edge);
  const dir = edge > 0 ? "Up" : "Down";
  if (abs >= 15) return { label: `Strong ${dir}`, color: dir === "Up" ? "text-emerald-400" : "text-red-400", bg: dir === "Up" ? "bg-emerald-400/10" : "bg-red-400/10" };
  if (abs >= 8) return { label: `Moderate ${dir}`, color: dir === "Up" ? "text-emerald-300" : "text-red-300", bg: dir === "Up" ? "bg-emerald-400/5" : "bg-red-400/5" };
  return { label: `Slight ${dir}`, color: dir === "Up" ? "text-emerald-200" : "text-red-200", bg: "bg-zinc-800/40" };
}

export function EdgeScanner({ data }: { data: EdgeRow[] }) {
  const [expanded, setExpanded] = useState(false);
  const [selectedMarket, setSelectedMarket] = useState("all");

  const marketTypes = sortMarketTypes([...new Set(data.map((d) => d.market_type))]);
  const filteredData = selectedMarket === "all" ? data : data.filter((d) => d.market_type === selectedMarket);

  if (data.length === 0) {
    return (
      <GlassPanel variant="glow-tr" className="p-8 text-center">
        <div className="relative flex flex-col items-center gap-2">
          <p className="text-sm text-zinc-400">No significant edges detected</p>
          <p className="text-xs text-zinc-500">Not enough data or no price buckets deviate from implied probability</p>
        </div>
      </GlassPanel>
    );
  }

  const visibleData = expanded ? filteredData : filteredData.slice(0, COLLAPSED_COUNT);
  const hasMore = filteredData.length > COLLAPSED_COUNT;

  return (
    <GlassPanel variant="glow-tr">
      <div className="relative border-b border-zinc-800/60 px-6 py-3 flex items-center gap-2">
        <button
          onClick={() => { setSelectedMarket("all"); setExpanded(false); }}
          className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
            selectedMarket === "all" ? "bg-primary/20 text-primary" : "bg-zinc-800/60 text-zinc-500 hover:text-zinc-300"
          }`}
        >
          All
        </button>
        {marketTypes.map((type) => {
          const asset = type.split("_")[0];
          const interval = type.split("_")[1];
          return (
            <button
              key={type}
              onClick={() => { setSelectedMarket(type); setExpanded(false); }}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                selectedMarket === type ? "bg-primary/20 text-primary" : "bg-zinc-800/60 text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {asset.toUpperCase()} {interval}
            </button>
          );
        })}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-zinc-800/40">
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Market</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Time</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Price Bucket</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Implied</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Actual</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Edge</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Strength</th>
              <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">Samples</th>
            </tr>
          </thead>
          <tbody>
            {visibleData.map((row, i) => {
              const { asset, interval } = parseMarketType(row.market_type);
              const edge = parseFloat(row.edge);
              const implied = parseFloat(row.implied_prob);
              const actual = parseFloat(row.actual_win_rate);
              const strength = getEdgeStrength(edge);
              const assetColor = getAssetColor(asset);

              return (
                <tr key={i} className="border-b border-zinc-800/20 hover:bg-zinc-800/20 transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-2 rounded-full" style={{ backgroundColor: assetColor }} />
                      <span className="text-sm font-semibold text-zinc-200">{asset}</span>
                      <span className="text-xs text-zinc-500">{interval}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-xs text-zinc-300">
                      {formatSeconds(parseInt(row.time_window))}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-sm font-semibold tabular-nums text-zinc-200">
                      {(parseFloat(row.price_bucket) * 100).toFixed(0)}¢
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-xs text-zinc-400">
                      {implied.toFixed(0)}% Up
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 rounded-full bg-zinc-800">
                        <div
                          className={`h-full rounded-full transition-all ${actual > implied ? "bg-emerald-400" : "bg-red-400"}`}
                          style={{ width: `${actual}%` }}
                        />
                      </div>
                      <span className={`font-mono text-xs font-semibold ${actual > implied ? "text-emerald-400" : "text-red-400"}`}>
                        {actual.toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`font-mono text-sm font-bold tabular-nums ${edge > 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {edge > 0 ? "+" : ""}{edge.toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${strength.color} ${strength.bg}`}>
                      {strength.label}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="font-mono text-xs text-zinc-400">{row.sample_count}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {hasMore && (
        <button
          onClick={() => setExpanded((e) => !e)}
          className="w-full border-t border-zinc-800/40 px-6 py-2.5 text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/20 transition-colors"
        >
          {expanded ? "Show less" : `Show ${filteredData.length - COLLAPSED_COUNT} more`}
        </button>
      )}
    </GlassPanel>
  );
}
