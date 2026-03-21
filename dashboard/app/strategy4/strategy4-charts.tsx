"use client";

import { useState, useMemo } from "react";
import { SectionHeader } from "@/components/section-header";
import { GlassPanel } from "@/components/ui/glass-panel";
import { cn } from "@/lib/utils";
import {
  BarChart, Bar, XAxis, YAxis, ReferenceLine,
  ResponsiveContainer, Tooltip as RechartsTooltip, Cell,
  ScatterChart, Scatter, ZAxis,
} from "recharts";
import type { StreakResult } from "@/lib/streak-queries";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatPnl(val: number): string {
  const prefix = val >= 0 ? "$" : "-$";
  return `${prefix}${Math.abs(val).toFixed(2)}`;
}

function pnlColor(val: number): string {
  return val > 0 ? "text-emerald-400" : val < 0 ? "text-red-400" : "text-zinc-400";
}

function winRateColor(pct: number): string {
  if (pct >= 70) return "text-emerald-400";
  if (pct >= 60) return "text-yellow-400";
  return "text-red-400";
}

// ---------------------------------------------------------------------------
// Filter button row
// ---------------------------------------------------------------------------

function FilterRow({
  options,
  selected,
  onSelect,
}: {
  options: { value: string; label: string }[];
  selected: string;
  onSelect: (v: string) => void;
}) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto pb-1 scrollbar-thin">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onSelect(opt.value)}
          className={cn(
            "flex-shrink-0 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
            selected === opt.value
              ? "bg-primary/[0.12] text-primary border border-primary/30"
              : "bg-zinc-900/60 text-zinc-400 border border-zinc-800/40 hover:text-zinc-200 hover:border-zinc-700/60"
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Custom chart tooltip
// ---------------------------------------------------------------------------

function ChartTooltipContent({ active, payload, label, formatter }: {
  active?: boolean;
  payload?: Array<{ value: number; name: string }>;
  label?: string;
  formatter?: (label: string, value: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-zinc-700/60 bg-zinc-900/95 px-3 py-2 shadow-xl backdrop-blur-sm">
      <p className="text-xs font-medium text-zinc-300 mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} className={cn("text-xs font-mono font-semibold", p.value >= 0 ? "text-emerald-400" : "text-red-400")}>
          {formatter ? formatter(String(label), p.value) : formatPnl(p.value)}
        </p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 4 — Top Configurations Table (expandable)
// ---------------------------------------------------------------------------

const INITIAL_ROWS = 5;

export function TopConfigurationsTable({ results }: { results: StreakResult[] }) {
  const [expanded, setExpanded] = useState(false);

  const eligible = results.filter((r) => r.trades_taken >= 10);
  const sorted = [...eligible].sort((a, b) => b.total_pnl - a.total_pnl).slice(0, 50);
  const bestPnl = sorted.length > 0 ? sorted[0].total_pnl : 0;
  const visible = expanded ? sorted : sorted.slice(0, INITIAL_ROWS);

  if (sorted.length === 0) {
    return (
      <section className="mb-8 md:mb-14">
        <SectionHeader title="Top Configurations by PnL" description="All parameter combinations sorted by total PnL. Minimum 10 trades required." />
        <p className="text-sm text-zinc-500">Not enough data yet.</p>
      </section>
    );
  }

  return (
    <section className="mb-8 md:mb-14">
      <SectionHeader title="Top Configurations by PnL" description="All parameter combinations sorted by total PnL. Minimum 10 trades required. Green = profitable, red = losing." />

      <GlassPanel variant="glow-wide">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-zinc-800/40">
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Market</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Streak Len</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Direction</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Trades</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Win Rate</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">W / L</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Total PnL</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">ROI</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Avg PnL</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r, i) => {
                const isBest = r.total_pnl === bestPnl;
                const mtLabel = r.market_type === "all" ? "All" : r.market_type.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
                const wrPct = r.win_rate * 100;
                const dirLabel = r.streak_direction === "both" ? "Both" : r.streak_direction;
                return (
                  <tr
                    key={i}
                    className={cn(
                      "border-b border-zinc-800/20 hover:bg-zinc-800/20 transition-colors",
                      isBest && "border-l-2 border-l-primary/60"
                    )}
                  >
                    <td className="px-4 py-3 text-sm text-zinc-300">{mtLabel}</td>
                    <td className="px-4 py-3 font-mono text-sm text-zinc-200">{r.streak_length}</td>
                    <td className="px-4 py-3 text-sm text-zinc-400">{dirLabel}</td>
                    <td className="px-4 py-3 font-mono text-sm text-zinc-400">{r.trades_taken}</td>
                    <td className={cn("px-4 py-3 font-mono text-sm font-semibold", winRateColor(wrPct))}>
                      {wrPct.toFixed(1)}%
                    </td>
                    <td className="px-4 py-3 font-mono text-sm text-zinc-400">
                      {r.wins} / {r.losses}
                    </td>
                    <td className={cn("px-4 py-3 font-mono text-sm font-bold", pnlColor(r.total_pnl))}>
                      {formatPnl(r.total_pnl)}
                    </td>
                    <td className={cn("px-4 py-3 font-mono text-sm", pnlColor(r.roi))}>
                      {(r.roi * 100).toFixed(1)}%
                    </td>
                    <td className={cn("px-4 py-3 font-mono text-sm", pnlColor(r.avg_pnl_per_trade))}>
                      {formatPnl(r.avg_pnl_per_trade)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {sorted.length > INITIAL_ROWS && (
          <div className="border-t border-zinc-800/40 px-4 py-3 text-center">
            <button
              onClick={() => setExpanded(!expanded)}
              className="rounded-md px-4 py-1.5 text-xs font-medium transition-colors bg-zinc-900/60 text-zinc-400 border border-zinc-800/40 hover:text-zinc-200 hover:border-zinc-700/60"
            >
              {expanded ? `Show less` : `Show all ${sorted.length} configurations`}
            </button>
          </div>
        )}
      </GlassPanel>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section 5 — Parameter Impact Charts
// ---------------------------------------------------------------------------

const STREAK_LENGTHS = [2, 3, 4, 5];
const STREAK_DIRECTIONS = ["Up", "Down", "both"];

const MARKET_TYPE_OPTIONS = [
  { value: "all", label: "All" },
  { value: "btc_5m", label: "BTC 5m" },
  { value: "eth_5m", label: "ETH 5m" },
  { value: "sol_5m", label: "SOL 5m" },
  { value: "xrp_5m", label: "XRP 5m" },
  { value: "btc_15m", label: "BTC 15m" },
  { value: "eth_15m", label: "ETH 15m" },
  { value: "sol_15m", label: "SOL 15m" },
  { value: "xrp_15m", label: "XRP 15m" },
];

function ParameterImpactChart({ title, data }: { title: string; data: { param: string; avgPnl: number }[] }) {
  return (
    <GlassPanel variant="subtle">
      <div className="relative p-4">
        <h4 className="text-base font-semibold text-zinc-100 mb-3">{title}</h4>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data} margin={{ top: 10, right: 10, bottom: 10, left: 0 }}>
            <XAxis dataKey="param" tick={{ fontSize: 11, fill: "#71717a" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: "#71717a" }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} />
            <ReferenceLine y={0} stroke="#3f3f46" strokeDasharray="4 4" />
            <RechartsTooltip content={<ChartTooltipContent />} />
            <Bar dataKey="avgPnl" radius={[4, 4, 0, 0]}>
              {data.map((entry, i) => (
                <Cell key={i} fill={entry.avgPnl >= 0 ? "#4ade80" : "#f87171"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </GlassPanel>
  );
}

function ParameterImpactSection({ results }: { results: StreakResult[] }) {
  const allResults = results.filter((r) => r.market_type === "all");

  // Streak length impact
  const streakLengthData = useMemo(() => {
    const map = new Map<number, number[]>();
    for (const sl of STREAK_LENGTHS) map.set(sl, []);
    for (const r of allResults) {
      if (r.trades_taken < 10) continue;
      map.get(r.streak_length)?.push(r.total_pnl);
    }
    return STREAK_LENGTHS.map((sl) => {
      const values = map.get(sl) || [];
      const avg = values.length > 0 ? values.reduce((a, c) => a + c, 0) / values.length : 0;
      return { param: String(sl), avgPnl: avg, raw: sl };
    });
  }, [allResults]);

  // Streak direction impact
  const directionData = useMemo(() => {
    const map = new Map<string, number[]>();
    for (const d of STREAK_DIRECTIONS) map.set(d, []);
    for (const r of allResults) {
      if (r.trades_taken < 10) continue;
      map.get(r.streak_direction)?.push(r.total_pnl);
    }
    return STREAK_DIRECTIONS.map((d) => {
      const values = map.get(d) || [];
      const avg = values.length > 0 ? values.reduce((a, c) => a + c, 0) / values.length : 0;
      const label = d === "both" ? "Both" : d;
      return { param: label, avgPnl: avg, raw: 0 };
    });
  }, [allResults]);

  // Market type impact
  const marketTypeData = useMemo(() => {
    const types = MARKET_TYPE_OPTIONS.map((o) => o.value);
    return types.map((mt) => {
      const mtResults = results.filter((r) => r.market_type === mt && r.trades_taken >= 10);
      const avg = mtResults.length > 0 ? mtResults.reduce((a, c) => a + c.total_pnl, 0) / mtResults.length : 0;
      const label = MARKET_TYPE_OPTIONS.find((o) => o.value === mt)?.label ?? mt;
      return { param: label, avgPnl: avg, raw: 0 };
    });
  }, [results]);

  return (
    <section className="mb-8 md:mb-14">
      <SectionHeader
        title="Parameter Impact"
        description="Average total PnL grouped by each parameter value across all combinations where trades_taken >= 10. Shows which values tend to perform better."
      />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ParameterImpactChart title="Streak Length" data={streakLengthData} />
        <ParameterImpactChart title="Streak Direction" data={directionData} />
        <ParameterImpactChart title="Market Type" data={marketTypeData} />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section 6 — Win Rate vs PnL Scatter
// ---------------------------------------------------------------------------

function ScatterSection({ results }: { results: StreakResult[] }) {
  const [marketType, setMarketType] = useState("all");

  const filtered = useMemo(() => {
    return results
      .filter((r) => r.trades_taken >= 10)
      .filter((r) => marketType === "all" ? r.market_type === "all" : r.market_type === marketType)
      .map((r) => ({
        win_rate: r.win_rate * 100,
        total_pnl: r.total_pnl,
        trades: r.trades_taken,
        streakLen: r.streak_length,
        direction: r.streak_direction === "both" ? "Both" : r.streak_direction,
      }));
  }, [results, marketType]);

  return (
    <section className="mb-8 md:mb-14">
      <SectionHeader
        title="Win Rate vs Profitability"
        description="Each dot is one parameter combination. High win rate does not always mean positive PnL — fees matter. The best combinations are top-right."
      />
      <GlassPanel variant="glow-center">
        <div className="relative border-b border-zinc-800/60 px-6 py-3">
          <FilterRow options={MARKET_TYPE_OPTIONS} selected={marketType} onSelect={setMarketType} />
        </div>
        <div className="relative p-4">
          {filtered.length === 0 ? (
            <p className="text-sm text-zinc-500 text-center py-12">No data for this filter.</p>
          ) : (
            <ResponsiveContainer width="100%" height={400}>
              <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 10 }}>
                <XAxis
                  type="number"
                  dataKey="win_rate"
                  name="Win Rate"
                  domain={[0, 100]}
                  tick={{ fontSize: 11, fill: "#71717a" }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `${v}%`}
                  label={{ value: "Win Rate", position: "insideBottom", offset: -10, fontSize: 11, fill: "#71717a" }}
                />
                <YAxis
                  type="number"
                  dataKey="total_pnl"
                  name="Total PnL"
                  tick={{ fontSize: 11, fill: "#71717a" }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `$${v}`}
                  label={{ value: "Total PnL", angle: -90, position: "insideLeft", offset: 0, fontSize: 11, fill: "#71717a" }}
                />
                <ZAxis type="number" dataKey="trades" range={[30, 200]} />
                <ReferenceLine x={50} stroke="#3f3f46" strokeDasharray="4 4" />
                <ReferenceLine y={0} stroke="#3f3f46" strokeDasharray="4 4" />
                <RechartsTooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const d = payload[0].payload;
                    return (
                      <div className="rounded-lg border border-zinc-700/60 bg-zinc-900/95 px-3 py-2 shadow-xl backdrop-blur-sm">
                        <p className="text-xs text-zinc-400">Streak: {d.streakLen} | Dir: {d.direction}</p>
                        <p className="text-xs text-zinc-300 mt-1">Win Rate: <span className="font-mono font-semibold">{d.win_rate.toFixed(1)}%</span></p>
                        <p className={cn("text-xs mt-0.5 font-mono font-semibold", d.total_pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                          PnL: {formatPnl(d.total_pnl)}
                        </p>
                        <p className="text-xs text-zinc-500 mt-0.5">Trades: {d.trades}</p>
                      </div>
                    );
                  }}
                />
                <Scatter data={filtered.filter((d) => d.total_pnl >= 0)} fill="#4ade80" fillOpacity={0.7} />
                <Scatter data={filtered.filter((d) => d.total_pnl < 0)} fill="#f87171" fillOpacity={0.7} />
              </ScatterChart>
            </ResponsiveContainer>
          )}
        </div>
      </GlassPanel>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section 7 — Win Rate Heatmap (streak_length x market_type, filter by direction)
// ---------------------------------------------------------------------------

function HeatmapSection({ results }: { results: StreakResult[] }) {
  const [streakDirection, setStreakDirection] = useState("both");

  const directionOptions = [
    { value: "both", label: "Both" },
    { value: "Up", label: "Up" },
    { value: "Down", label: "Down" },
  ];

  const allMarketTypes = useMemo(() => {
    return MARKET_TYPE_OPTIONS.map((o) => o.value);
  }, []);

  const filtered = useMemo(() => {
    return results.filter((r) => r.streak_direction === streakDirection);
  }, [results, streakDirection]);

  // Build heatmap grid: Y = market_type, X = streak_length
  const grid = useMemo(() => {
    const cellMap = new Map<string, StreakResult>();
    for (const r of filtered) {
      const key = `${r.streak_length}_${r.market_type}`;
      cellMap.set(key, r);
    }

    return allMarketTypes.map((mt) => ({
      marketType: mt,
      label: MARKET_TYPE_OPTIONS.find((o) => o.value === mt)?.label ?? mt,
      cells: STREAK_LENGTHS.map((sl) => {
        const key = `${sl}_${mt}`;
        const r = cellMap.get(key);
        return {
          streakLength: sl,
          marketType: mt,
          result: r || null,
          winRate: r ? r.win_rate * 100 : null,
          trades: r ? r.trades_taken : 0,
        };
      }),
    }));
  }, [filtered, allMarketTypes]);

  // Find min/max win rate for color scale
  const allWinRates = grid.flatMap((row) => row.cells.filter((c) => c.winRate !== null && c.trades >= 10).map((c) => c.winRate as number));
  const maxWr = allWinRates.length > 0 ? Math.max(...allWinRates) : 100;
  const minWr = allWinRates.length > 0 ? Math.min(...allWinRates) : 0;

  function getCellColor(winRate: number | null, trades: number): string {
    if (winRate === null || trades < 10) return "bg-zinc-800/40";
    if (Math.abs(winRate - 50) < 2) return "bg-zinc-700/40";
    if (winRate > 50) {
      const intensity = Math.min((winRate - 50) / Math.max(maxWr - 50, 1), 1);
      if (intensity > 0.7) return "bg-emerald-500/60";
      if (intensity > 0.4) return "bg-emerald-500/40";
      return "bg-emerald-500/20";
    } else {
      const intensity = Math.min((50 - winRate) / Math.max(50 - minWr, 1), 1);
      if (intensity > 0.7) return "bg-red-500/60";
      if (intensity > 0.4) return "bg-red-500/40";
      return "bg-red-500/20";
    }
  }

  return (
    <section className="mb-8 md:mb-14">
      <SectionHeader
        title="Win Rate Heatmap"
        description="Win rate for each streak length / market type combination. Green = above 50%, Red = below 50%. Filter by streak direction."
      />
      <GlassPanel variant="glow-br">
        <div className="relative border-b border-zinc-800/60 px-6 py-3 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-zinc-500">Direction:</span>
            <FilterRow options={directionOptions} selected={streakDirection} onSelect={setStreakDirection} />
          </div>
        </div>

        <div className="relative p-6">
          {allWinRates.length === 0 ? (
            <p className="text-sm text-zinc-500 text-center py-12">No data for this filter combination.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="mx-auto">
                <thead>
                  <tr>
                    <th className="px-2 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">Market \ Streak</th>
                    {STREAK_LENGTHS.map((sl) => (
                      <th key={sl} className="px-2 py-2 text-xs font-semibold text-zinc-400 text-center">
                        {sl}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {grid.map((row) => (
                    <tr key={row.marketType}>
                      <td className="px-2 py-2 text-xs font-semibold text-zinc-400">{row.label}</td>
                      {row.cells.map((cell) => (
                        <td
                          key={`${cell.streakLength}_${cell.marketType}`}
                          className={cn(
                            "px-2 py-2 text-center border border-zinc-800/30 min-w-[60px]",
                            getCellColor(cell.winRate, cell.trades)
                          )}
                          title={cell.winRate !== null && cell.trades >= 10
                            ? `Streak: ${cell.streakLength}, Market: ${row.label}, Win Rate: ${cell.winRate.toFixed(1)}%, Trades: ${cell.trades}`
                            : "Insufficient data"
                          }
                        >
                          {cell.winRate !== null && cell.trades >= 10 ? (
                            <span className={cn(
                              "font-mono text-xs font-semibold",
                              cell.winRate >= 50 ? "text-emerald-300" : "text-red-300"
                            )}>
                              {cell.winRate.toFixed(1)}%
                            </span>
                          ) : (
                            <span className="text-xs text-zinc-600">–</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </GlassPanel>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export function Strategy4Charts({ results }: { results: StreakResult[] }) {
  return (
    <>
      <ParameterImpactSection results={results} />
      <ScatterSection results={results} />
      <HeatmapSection results={results} />
    </>
  );
}
