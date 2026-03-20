"use client";

import { useState } from "react";
import { sortMarketTypes } from "@/lib/constants";
import { GlassPanel } from "@/components/ui/glass-panel";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  Cell,
} from "recharts";

interface TimeOfDayRow {
  market_type: string;
  hour_utc: string;
  total: string;
  up_wins: string;
  up_win_rate: string;
}

interface TimeOfDayProps {
  data: TimeOfDayRow[];
}

const ASSET_NAMES: Record<string, string> = {
  btc: "Bitcoin",
  eth: "Ethereum",
  sol: "Solana",
  xrp: "XRP",
};

function assetLabel(marketType: string): string {
  const asset = marketType.split("_")[0];
  return ASSET_NAMES[asset] || asset.toUpperCase();
}


export function TimeOfDay({ data }: TimeOfDayProps) {
  const marketTypes = sortMarketTypes([...new Set(data.map((d) => d.market_type))]);
  const [selectedType, setSelectedType] = useState(marketTypes[0] || "");

  const typeData = data.filter((d) => d.market_type === selectedType);

  // Fill all 24 hours
  const hourlyData = Array.from({ length: 24 }, (_, hour) => {
    const row = typeData.find((d) => parseInt(d.hour_utc) === hour);
    return {
      hour: `${hour.toString().padStart(2, "0")}:00`,
      hourNum: hour,
      winRate: row ? parseFloat(row.up_win_rate) : 0,
      total: row ? parseInt(row.total) : 0,
    };
  });

  if (marketTypes.length === 0) {
    return (
      <GlassPanel variant="glow-center" className="p-8 text-center text-sm text-zinc-500">
        Not enough data yet
      </GlassPanel>
    );
  }

  return (
    <GlassPanel variant="glow-center" className="p-6">
      <div className="relative">
        {/* Market type selector */}
        <div className="mb-5 flex items-center gap-2 flex-wrap">
          {marketTypes.map((type) => {
            const asset = type.split("_")[0];
            const interval = type.split("_")[1];
            return (
              <button
                key={type}
                onClick={() => setSelectedType(type)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  selectedType === type
                    ? "bg-primary/20 text-primary"
                    : "bg-zinc-800/60 text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {assetLabel(type)} {interval}
              </button>
            );
          })}
        </div>

        {/* Chart */}
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={hourlyData} margin={{ top: 5, right: 5, bottom: 5, left: -15 }}>
            <XAxis
              dataKey="hour"
              tick={{ fill: "#71717a", fontSize: 12 }}
              axisLine={{ stroke: "#3f3f46" }}
              tickLine={false}
              interval={2}
            />
            <YAxis
              domain={[30, 70]}
              tick={{ fill: "#71717a", fontSize: 12 }}
              axisLine={{ stroke: "#3f3f46" }}
              tickLine={false}
              tickFormatter={(v) => `${v}%`}
            />
            <ReferenceLine y={50} stroke="#71717a" strokeDasharray="4 4" strokeWidth={1} />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.03)" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0].payload;
                if (d.total === 0) return null;
                const isUp = d.winRate > 50;
                const edge = d.winRate - 50;
                return (
                  <div className="w-44 rounded-lg border border-zinc-700/60 bg-zinc-900/95 backdrop-blur-sm shadow-2xl overflow-hidden">
                    <div className={`px-3 py-1.5 ${isUp ? "bg-emerald-500/15" : "bg-red-500/15"}`}>
                      <span className="text-xs font-semibold text-zinc-200">{d.hour} UTC</span>
                    </div>
                    <div className="px-3 py-2.5 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-500">Win Rate</span>
                        <span className={`font-mono text-sm font-bold ${isUp ? "text-emerald-400" : "text-red-400"}`}>
                          {d.winRate.toFixed(1)}%
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${isUp ? "bg-emerald-400" : "bg-red-400"}`}
                          style={{ width: `${d.winRate}%` }}
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-500">Edge</span>
                        <span className={`font-mono text-xs font-semibold ${isUp ? "text-emerald-400" : "text-red-400"}`}>
                          {edge > 0 ? "+" : ""}{edge.toFixed(1)}%
                        </span>
                      </div>
                      <div className="h-px bg-zinc-800" />
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-500">Markets</span>
                        <span className="font-mono text-xs text-zinc-300">{d.total}</span>
                      </div>
                    </div>
                  </div>
                );
              }}
            />
            <Bar dataKey="winRate" radius={[3, 3, 0, 0]} maxBarSize={18}>
              {hourlyData.map((entry) => (
                <Cell
                  key={entry.hourNum}
                  fill={entry.total === 0 ? "#3f3f46" : entry.winRate > 50 ? "#4ade80" : "#f87171"}
                  fillOpacity={entry.total === 0 ? 0.2 : 0.85}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>

      </div>
    </GlassPanel>
  );
}
