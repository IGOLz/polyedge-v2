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
import type { FarmingResult } from "@/lib/farming-queries";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatPnl(val: number): string {
  const prefix = val >= 0 ? "$" : "-$";
  return `${prefix}${Math.abs(val).toFixed(2)}`;
}

function formatCents(val: number): string {
  return `${(val * 100).toFixed(0)}¢`;
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
// Section 5 — Parameter Impact Charts
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Section 4 — Top Configurations Table (expandable)
// ---------------------------------------------------------------------------

const INITIAL_ROWS = 5;

export function TopConfigurationsTable({ results }: { results: FarmingResult[] }) {
  const [expanded, setExpanded] = useState(false);

  const eligible = results.filter((r) => r.trades_taken >= 20);
  const sorted = [...eligible].sort((a, b) => b.total_pnl - a.total_pnl).slice(0, 50);
  const bestPnl = sorted.length > 0 ? sorted[0].total_pnl : 0;
  const visible = expanded ? sorted : sorted.slice(0, INITIAL_ROWS);

  if (sorted.length === 0) {
    return (
      <section className="mb-8 md:mb-14">
        <SectionHeader title="Top Configurations by PnL" description="All parameter combinations sorted by total PnL. Minimum 20 trades required." />
        <p className="text-sm text-zinc-500">Not enough data yet.</p>
      </section>
    );
  }

  return (
    <section className="mb-8 md:mb-14">
      <SectionHeader title="Top Configurations by PnL" description="All parameter combinations sorted by total PnL. Minimum 20 trades required. Green = profitable, red = losing." />

      <GlassPanel variant="glow-wide">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-zinc-800/40">
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Market</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Trigger</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Stop-Loss</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Min Min</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Min Delta</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Trades</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Win Rate</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">W / SL</th>
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
                return (
                  <tr
                    key={i}
                    className={cn(
                      "border-b border-zinc-800/20 hover:bg-zinc-800/20 transition-colors",
                      isBest && "border-l-2 border-l-primary/60"
                    )}
                  >
                    <td className="px-4 py-3 text-sm text-zinc-300">{mtLabel}</td>
                    <td className="px-4 py-3 font-mono text-sm text-zinc-200">{formatCents(r.trigger_point)}</td>
                    <td className="px-4 py-3 font-mono text-sm text-zinc-200">{formatCents(r.exit_point)}</td>
                    <td className="px-4 py-3 font-mono text-sm text-zinc-400">{r.trigger_minutes}</td>
                    <td className="px-4 py-3 font-mono text-sm text-zinc-400">{r.min_coin_delta.toFixed(2)}</td>
                    <td className="px-4 py-3 font-mono text-sm text-zinc-400">{r.trades_taken}</td>
                    <td className={cn("px-4 py-3 font-mono text-sm font-semibold", winRateColor(wrPct))}>
                      {wrPct.toFixed(1)}%
                    </td>
                    <td className="px-4 py-3 font-mono text-sm text-zinc-400">
                      {r.wins} / {r.stop_losses}
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

const TRIGGER_POINTS = [0.65, 0.70, 0.75, 0.80, 0.85, 0.90];
const EXIT_POINTS = [0.30, 0.40, 0.50, 0.60];
const TRIGGER_MINUTES = [1, 2, 3, 5, 7, 10, 14];
const MIN_DELTAS = [0.00, 0.05, 0.10, 0.15];

function groupByParam(
  results: FarmingResult[],
  accessor: (r: FarmingResult) => number,
  buckets: number[]
): { param: string; avgPnl: number; raw: number }[] {
  const map = new Map<number, number[]>();
  for (const b of buckets) map.set(b, []);

  for (const r of results) {
    if (r.trades_taken < 20) continue;
    const val = accessor(r);
    // Find closest bucket
    let closest = buckets[0];
    let minDist = Math.abs(val - closest);
    for (const b of buckets) {
      const dist = Math.abs(val - b);
      if (dist < minDist) { closest = b; minDist = dist; }
    }
    map.get(closest)?.push(r.total_pnl);
  }

  return buckets.map((b) => {
    const values = map.get(b) || [];
    const avg = values.length > 0 ? values.reduce((a, c) => a + c, 0) / values.length : 0;
    return { param: formatCents(b), avgPnl: avg, raw: b };
  });
}

function groupByParamRaw(
  results: FarmingResult[],
  accessor: (r: FarmingResult) => number,
  buckets: number[],
  labelFn: (v: number) => string
): { param: string; avgPnl: number; raw: number }[] {
  const map = new Map<number, number[]>();
  for (const b of buckets) map.set(b, []);

  for (const r of results) {
    if (r.trades_taken < 20) continue;
    const val = accessor(r);
    let closest = buckets[0];
    let minDist = Math.abs(val - closest);
    for (const b of buckets) {
      const dist = Math.abs(val - b);
      if (dist < minDist) { closest = b; minDist = dist; }
    }
    map.get(closest)?.push(r.total_pnl);
  }

  return buckets.map((b) => {
    const values = map.get(b) || [];
    const avg = values.length > 0 ? values.reduce((a, c) => a + c, 0) / values.length : 0;
    return { param: labelFn(b), avgPnl: avg, raw: b };
  });
}

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

function ParameterImpactSection({ results }: { results: FarmingResult[] }) {
  const allResults = results.filter((r) => r.market_type === "all");

  const triggerData = useMemo(() => groupByParam(allResults, (r) => r.trigger_point, TRIGGER_POINTS), [allResults]);
  const exitData = useMemo(() => groupByParam(allResults, (r) => r.exit_point, EXIT_POINTS), [allResults]);
  const minuteData = useMemo(() => groupByParamRaw(allResults, (r) => r.trigger_minutes, TRIGGER_MINUTES, (v) => `${v}m`), [allResults]);
  const deltaData = useMemo(() => groupByParamRaw(allResults, (r) => r.min_coin_delta, MIN_DELTAS, (v) => v.toFixed(2)), [allResults]);

  return (
    <section className="mb-8 md:mb-14">
      <SectionHeader
        title="Parameter Impact"
        description="Average total PnL grouped by each parameter value across all combinations where trades_taken >= 20. Shows which values tend to perform better."
      />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ParameterImpactChart title="Trigger Point" data={triggerData} />
        <ParameterImpactChart title="Stop-Loss (Exit Point)" data={exitData} />
        <ParameterImpactChart title="Trigger Minute" data={minuteData} />
        <ParameterImpactChart title="Min Coin Delta" data={deltaData} />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section 6 — Win Rate vs PnL Scatter
// ---------------------------------------------------------------------------

const MARKET_TYPE_OPTIONS = [
  { value: "all", label: "All" },
  { value: "btc_15m", label: "BTC 15m" },
  { value: "eth_15m", label: "ETH 15m" },
  { value: "sol_15m", label: "SOL 15m" },
  { value: "xrp_15m", label: "XRP 15m" },
];

function ScatterSection({ results }: { results: FarmingResult[] }) {
  const [marketType, setMarketType] = useState("all");

  const filtered = useMemo(() => {
    return results
      .filter((r) => r.trades_taken >= 20)
      .filter((r) => marketType === "all" ? r.market_type === "all" : r.market_type === marketType)
      .map((r) => ({
        win_rate: r.win_rate * 100,
        total_pnl: r.total_pnl,
        trades: r.trades_taken,
        trigger: formatCents(r.trigger_point),
        exit: formatCents(r.exit_point),
        minute: r.trigger_minutes,
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
                        <p className="text-xs text-zinc-400">Trigger: {d.trigger} | Exit: {d.exit} | Min: {d.minute}m</p>
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
// Section 7 — PnL Heatmap
// ---------------------------------------------------------------------------

function HeatmapSection({ results }: { results: FarmingResult[] }) {
  const [marketType, setMarketType] = useState("all");
  const [triggerMinute, setTriggerMinute] = useState(1);
  const [minDelta, setMinDelta] = useState(0.00);

  const minuteOptions = TRIGGER_MINUTES.map((m) => ({ value: String(m), label: String(m) }));
  const deltaOptions = MIN_DELTAS.map((d) => ({ value: d.toFixed(2), label: d.toFixed(2) }));

  const filtered = useMemo(() => {
    return results.filter((r) => {
      const mtMatch = marketType === "all" ? r.market_type === "all" : r.market_type === marketType;
      const minMatch = Math.abs(r.trigger_minutes - triggerMinute) < 0.01;
      const deltaMatch = Math.abs(r.min_coin_delta - minDelta) < 0.001;
      return mtMatch && minMatch && deltaMatch;
    });
  }, [results, marketType, triggerMinute, minDelta]);

  // Build heatmap grid
  const grid = useMemo(() => {
    const cellMap = new Map<string, FarmingResult>();
    for (const r of filtered) {
      const key = `${r.trigger_point.toFixed(2)}_${r.exit_point.toFixed(2)}`;
      cellMap.set(key, r);
    }

    return EXIT_POINTS.map((ep) => ({
      exitPoint: ep,
      cells: TRIGGER_POINTS.map((tp) => {
        const key = `${tp.toFixed(2)}_${ep.toFixed(2)}`;
        const r = cellMap.get(key);
        return {
          triggerPoint: tp,
          exitPoint: ep,
          result: r || null,
          pnl: r ? r.total_pnl : null,
          trades: r ? r.trades_taken : 0,
        };
      }),
    }));
  }, [filtered]);

  // Find min/max PnL for color scale
  const allPnls = grid.flatMap((row) => row.cells.filter((c) => c.pnl !== null && c.trades >= 20).map((c) => c.pnl as number));
  const maxPnl = allPnls.length > 0 ? Math.max(...allPnls) : 1;
  const minPnl = allPnls.length > 0 ? Math.min(...allPnls) : -1;

  function getCellColor(pnl: number | null, trades: number): string {
    if (pnl === null || trades < 20) return "bg-zinc-800/40";
    if (pnl === 0) return "bg-zinc-700/40";
    if (pnl > 0) {
      const intensity = Math.min(pnl / Math.max(maxPnl, 1), 1);
      if (intensity > 0.7) return "bg-emerald-500/60";
      if (intensity > 0.4) return "bg-emerald-500/40";
      return "bg-emerald-500/20";
    } else {
      const intensity = Math.min(Math.abs(pnl) / Math.max(Math.abs(minPnl), 1), 1);
      if (intensity > 0.7) return "bg-red-500/60";
      if (intensity > 0.4) return "bg-red-500/40";
      return "bg-red-500/20";
    }
  }

  return (
    <section className="mb-8 md:mb-14">
      <SectionHeader
        title="PnL Heatmap"
        description="2D view of total PnL for each trigger/stop-loss combination. Green = profitable. Filter by trigger minute to explore different time configurations."
      />
      <GlassPanel variant="glow-br">
        <div className="relative border-b border-zinc-800/60 px-6 py-3 flex flex-wrap items-center gap-3">
          <FilterRow options={MARKET_TYPE_OPTIONS} selected={marketType} onSelect={setMarketType} />
          <div className="h-4 w-px bg-zinc-800/60" />
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-zinc-500">Minute:</span>
            <FilterRow options={minuteOptions} selected={String(triggerMinute)} onSelect={(v) => setTriggerMinute(Number(v))} />
          </div>
          <div className="h-4 w-px bg-zinc-800/60" />
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-zinc-500">Delta:</span>
            <FilterRow options={deltaOptions} selected={minDelta.toFixed(2)} onSelect={(v) => setMinDelta(parseFloat(v))} />
          </div>
        </div>

        <div className="relative p-6">
          {allPnls.length === 0 ? (
            <p className="text-sm text-zinc-500 text-center py-12">No data for this filter combination.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="mx-auto">
                <thead>
                  <tr>
                    <th className="px-2 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">Exit \ Trigger</th>
                    {TRIGGER_POINTS.map((tp) => (
                      <th key={tp} className="px-2 py-2 text-xs font-semibold text-zinc-400 text-center">
                        {formatCents(tp)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {grid.map((row) => (
                    <tr key={row.exitPoint}>
                      <td className="px-2 py-2 text-xs font-semibold text-zinc-400">{formatCents(row.exitPoint)}</td>
                      {row.cells.map((cell) => (
                        <td
                          key={`${cell.triggerPoint}_${cell.exitPoint}`}
                          className={cn(
                            "px-2 py-2 text-center border border-zinc-800/30 min-w-[60px]",
                            getCellColor(cell.pnl, cell.trades)
                          )}
                          title={cell.pnl !== null && cell.trades >= 20
                            ? `Trigger: ${formatCents(cell.triggerPoint)}, Exit: ${formatCents(cell.exitPoint)}, PnL: ${formatPnl(cell.pnl)}, Trades: ${cell.trades}`
                            : "Insufficient data"
                          }
                        >
                          {cell.pnl !== null && cell.trades >= 20 ? (
                            <span className={cn(
                              "font-mono text-xs font-semibold",
                              cell.pnl >= 0 ? "text-emerald-300" : "text-red-300"
                            )}>
                              ${Math.round(cell.pnl)}
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

export function StrategyCharts({ results }: { results: FarmingResult[] }) {
  return (
    <>
      <ParameterImpactSection results={results} />
      <ScatterSection results={results} />
      <HeatmapSection results={results} />
    </>
  );
}
