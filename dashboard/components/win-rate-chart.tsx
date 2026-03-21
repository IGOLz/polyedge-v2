"use client";

import { useState } from "react";
import { GlassPanel } from "@/components/ui/glass-panel";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

interface CalibrationRow {
  market_type: string;
  price_bucket: string;
  sample_count: string;
  up_win_rate: string;
}

interface WinRateChartProps {
  dataBySeconds: Record<number, CalibrationRow[]>;
  timeWindows5m: number[];
  timeWindows15m: number[];
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

function formatSeconds(s: number): string {
  if (s < 60) return `${s}s`;
  const min = Math.floor(s / 60);
  const sec = s % 60;
  return sec > 0 ? `${min}m ${sec}s` : `${min}m`;
}

export function WinRateChart({
  dataBySeconds,
  timeWindows5m,
  timeWindows15m,
}: WinRateChartProps) {
  const [selected5m, setSelected5m] = useState(timeWindows5m[0]);
  const [selected15m, setSelected15m] = useState(timeWindows15m[0]);

  const data5m = dataBySeconds[selected5m] || [];
  const data15m = dataBySeconds[selected15m] || [];

  const markets5m = data5m.filter((d) => d.market_type.endsWith("_5m"));
  const markets15m = data15m.filter((d) => d.market_type.endsWith("_15m"));

  return (
    <div className="space-y-8">
      {/* 5m Markets */}
      <div>
        <div className="mb-4 flex items-center gap-2">
          <span className="text-sm font-semibold text-zinc-300">5m Markets</span>
          <div className="flex gap-1">
            {timeWindows5m.map((s) => (
              <button
                key={s}
                onClick={() => setSelected5m(s)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  selected5m === s
                    ? "bg-primary/20 text-primary"
                    : "bg-zinc-800/60 text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {formatSeconds(s)}
              </button>
            ))}
          </div>
        </div>
        <ChartGrid data={markets5m} />
      </div>

      {/* 15m Markets */}
      <div>
        <div className="mb-4 flex items-center gap-2">
          <span className="text-sm font-semibold text-zinc-300">15m Markets</span>
          <div className="flex gap-1">
            {timeWindows15m.map((s) => (
              <button
                key={s}
                onClick={() => setSelected15m(s)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  selected15m === s
                    ? "bg-primary/20 text-primary"
                    : "bg-zinc-800/60 text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {formatSeconds(s)}
              </button>
            ))}
          </div>
        </div>
        <ChartGrid data={markets15m} />
      </div>
    </div>
  );
}

function ChartGrid({ data }: { data: CalibrationRow[] }) {
  const marketTypes = [...new Set(data.map((d) => d.market_type))];

  if (marketTypes.length === 0) {
    return (
      <GlassPanel variant="glow-center" className="p-8 text-center text-sm text-zinc-500">
        Not enough data yet
      </GlassPanel>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {marketTypes.map((type) => {
        const typeData = data
          .filter((d) => d.market_type === type && parseInt(d.sample_count) >= 5)
          .map((d) => ({
            bucket: `${(parseFloat(d.price_bucket) * 100).toFixed(0)}%`,
            winRate: parseFloat(d.up_win_rate),
          }));

        return (
          <GlassPanel key={type} variant="glow-tl" className="p-6">
            <div className="relative">
              <h4 className="mb-4 text-base font-semibold tracking-tight text-zinc-100">
                {assetLabel(type)}
              </h4>
              {typeData.length === 0 ? (
                <div className="flex h-40 items-center justify-center text-xs text-zinc-500">
                  Not enough data
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={typeData} margin={{ top: 5, right: 5, bottom: 5, left: -15 }}>
                    <XAxis
                      dataKey="bucket"
                      tick={{ fill: "#71717a", fontSize: 12 }}
                      axisLine={{ stroke: "#3f3f46" }}
                      tickLine={false}
                    />
                    <YAxis
                      domain={[0, 100]}
                      tick={{ fill: "#71717a", fontSize: 12 }}
                      axisLine={{ stroke: "#3f3f46" }}
                      tickLine={false}
                      tickFormatter={(v) => `${v}%`}
                    />
                    <ReferenceLine
                      y={50}
                      stroke="#71717a"
                      strokeDasharray="4 4"
                      strokeWidth={1}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#18181b",
                        border: "1px solid #3f3f46",
                        borderRadius: "8px",
                        fontSize: "12px",
                        color: "#e4e4e7",
                      }}
                      formatter={(value: number) => [`${value.toFixed(1)}%`, "Win Rate"]}
                    />
                    <Bar
                      dataKey="winRate"
                      fill="#e4f600"
                      radius={[3, 3, 0, 0]}
                      maxBarSize={24}
                    />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </GlassPanel>
        );
      })}
    </div>
  );
}
