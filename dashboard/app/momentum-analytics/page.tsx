"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Navbar } from "@/components/navbar";
import { SectionHeader } from "@/components/section-header";
import { GlassPanel } from "@/components/ui/glass-panel";
import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  LineChart,
  Line,
} from "recharts";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MomentumTrade {
  id: string;
  market_id: string | null;
  market_type: string;
  strategy_name: string;
  direction: string;
  entry_price: string;
  bet_size_usd: string;
  status: string;
  final_outcome: string | null;
  pnl: string | null;
  placed_at: string;
  resolved_at: string | null;
  stop_loss_price: string | null;
  stop_loss_triggered: boolean | null;
  notes: string | null;
}

interface TierStatus {
  broad: boolean;
  filtered: boolean;
  aggressive: boolean;
}

type Tier = "broad" | "filtered" | "aggressive";
type TimeRange = "24h" | "7d" | "30d" | "all";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TIERS: Tier[] = ["broad", "filtered", "aggressive"];

const TIER_LABELS: Record<Tier, string> = {
  broad: "Broad",
  filtered: "Filtered",
  aggressive: "Aggressive",
};

const TIER_COLORS: Record<Tier, string> = {
  broad: "#60a5fa",     // blue-400
  filtered: "#fbbf24",  // amber-400
  aggressive: "#fb7185", // rose-400
};

const TIER_BADGE_CLASSES: Record<Tier, string> = {
  broad: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  filtered: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  aggressive: "bg-rose-500/10 text-rose-400 border-rose-500/20",
};

const TIME_RANGES: { value: TimeRange; label: string }[] = [
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "all", label: "All time" },
];

const ROWS_PER_PAGE = 50;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pf(val: string | null | undefined): number {
  if (val == null) return 0;
  const n = parseFloat(val);
  return isNaN(n) ? 0 : n;
}

function fmtPnl(val: number): string {
  if (val === 0) return "$0.00";
  const prefix = val >= 0 ? "$" : "-$";
  return `${prefix}${Math.abs(val).toFixed(2)}`;
}

function fmtPercent(val: number): string {
  return `${val.toFixed(1)}%`;
}

function fmtPrice(price: number): string {
  if (price >= 1) return `$${price.toFixed(2)}`;
  return `${Math.round(price * 100)}¢`;
}

function fmtDateTime(ts: string): string {
  const d = new Date(ts);
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "UTC" });
  const date = d.toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit", timeZone: "UTC" });
  return `${time} ${date}`;
}

function parseSignalData(data: string | null): Record<string, unknown> | null {
  if (!data) return null;
  try {
    return typeof data === "object" ? data : JSON.parse(data);
  } catch {
    return null;
  }
}

function getTier(strategyName: string, notes?: string | null): Tier {
  if (strategyName === "momentum_broad") return "broad";
  if (strategyName === "momentum_filtered") return "filtered";
  if (strategyName === "momentum_aggressive") return "aggressive";
  // Plain "momentum" trades — check notes JSON for tier info
  if (notes) {
    const parsed = parseSignalData(notes);
    if (parsed) {
      const tier = (parsed.tier ?? parsed.momentum_tier ?? "") as string;
      if (tier === "broad" || tier === "filtered" || tier === "aggressive") return tier;
    }
  }
  return "broad";
}

function pnlColor(val: number): string {
  return val > 0 ? "text-emerald-400" : val < 0 ? "text-red-400" : "text-zinc-400";
}

function outcomeLabel(trade: MomentumTrade): string {
  if (trade.stop_loss_triggered || trade.final_outcome === "stop_loss") return "Stop-loss";
  if (trade.final_outcome === "win") return "Win";
  if (trade.final_outcome === "loss") return "Loss";
  return "Pending";
}

function outcomeBadge(trade: MomentumTrade): string {
  if (trade.stop_loss_triggered || trade.final_outcome === "stop_loss") return "bg-amber-500/10 text-amber-400";
  if (trade.final_outcome === "win") return "bg-emerald-500/10 text-emerald-400";
  if (trade.final_outcome === "loss") return "bg-red-500/10 text-red-400";
  return "bg-zinc-500/10 text-zinc-400";
}

// ---------------------------------------------------------------------------
// Tier summary computation
// ---------------------------------------------------------------------------

interface TierSummary {
  totalTrades: number;
  wins: number;
  losses: number;
  stopLosses: number;
  totalPnl: number;
  totalWagered: number;
  winRate: number;
  roi: number;
  avgPnl: number;
  avgEntryPrice: number;
}

/** PnL with stop-loss fallback: if DB pnl is missing but stop-loss fired, calculate from prices × shares */
function tradePnl(t: MomentumTrade): number {
  let val = pf(t.pnl);
  const isStopLoss = t.stop_loss_triggered || t.final_outcome === "stop_loss";
  if ((!t.pnl || val === 0) && isStopLoss && t.stop_loss_price) {
    val = (parseFloat(t.stop_loss_price) - parseFloat(t.entry_price)) * pf(t.bet_size_usd);
  }

  return val;
}

function isResolved(t: MomentumTrade): boolean {
  return t.final_outcome === "win" || t.final_outcome === "loss" || t.final_outcome === "stop_loss" || !!t.stop_loss_triggered;
}

function computeTierSummary(trades: MomentumTrade[]): TierSummary {
  if (trades.length === 0) {
    return { totalTrades: 0, wins: 0, losses: 0, stopLosses: 0, totalPnl: 0, totalWagered: 0, winRate: 0, roi: 0, avgPnl: 0, avgEntryPrice: 0 };
  }
  const resolved = trades.filter(isResolved);
  const wins = trades.filter((t) => t.final_outcome === "win").length;
  const losses = trades.filter((t) => t.final_outcome === "loss").length;
  const stopLosses = trades.filter((t) => t.stop_loss_triggered || t.final_outcome === "stop_loss").length;
  const resolvedCount = wins + losses + stopLosses;
  const totalPnl = resolved.reduce((s, t) => s + tradePnl(t), 0);
  const totalWagered = resolved.reduce((s, t) => s + pf(t.entry_price) * pf(t.bet_size_usd), 0);
  const avgEntryPrice = resolved.length > 0 ? resolved.reduce((s, t) => s + pf(t.entry_price), 0) / resolved.length : 0;
  return {
    totalTrades: trades.length,
    wins,
    losses,
    stopLosses,
    totalPnl,
    totalWagered,
    winRate: resolvedCount > 0 ? (wins / resolvedCount) * 100 : 0,
    roi: totalWagered > 0 ? (totalPnl / totalWagered) * 100 : 0,
    avgPnl: resolvedCount > 0 ? totalPnl / resolvedCount : 0,
    avgEntryPrice,
  };
}

// ---------------------------------------------------------------------------
// Custom tooltip for recharts
// ---------------------------------------------------------------------------

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-zinc-800/60 bg-zinc-950/95 px-3 py-2 shadow-xl backdrop-blur-xl">
      {label && <p className="text-xs text-zinc-500 mb-1">{label}</p>}
      {payload.map((p) => (
        <p key={p.name} className="text-xs font-medium" style={{ color: p.color }}>
          {p.name}: {typeof p.value === "number" ? p.value.toFixed(2) : p.value}
        </p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function MomentumAnalyticsPage() {
  const [trades, setTrades] = useState<MomentumTrade[]>([]);
  const [tierStatus, setTierStatus] = useState<TierStatus>({ broad: false, filtered: false, aggressive: false });
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<TimeRange>("7d");
  const [tableFilter, setTableFilter] = useState<Tier | "all">("all");
  const [visibleCount, setVisibleCount] = useState(ROWS_PER_PAGE);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [countdown, setCountdown] = useState(60);
  const countdownRef = useRef(60);

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await fetch(`/api/momentum-analytics?range=${range}`);
      if (res.ok) {
        const data = await res.json();
        setTrades(data.trades);
        setTierStatus(data.tierStatus);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, [range]);

  useEffect(() => {
    fetchData();
    countdownRef.current = 60;
    setCountdown(60);
    const tick = setInterval(() => {
      countdownRef.current -= 1;
      if (countdownRef.current <= 0) {
        fetchData(true);
        countdownRef.current = 60;
      }
      setCountdown(countdownRef.current);
    }, 1000);
    return () => clearInterval(tick);
  }, [fetchData]);

  // Reset visible count when range or filter changes
  useEffect(() => {
    setVisibleCount(ROWS_PER_PAGE);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }, [range, tableFilter]);

  // Group trades by tier
  const tradesByTier = useMemo(() => {
    const grouped: Record<Tier, MomentumTrade[]> = { broad: [], filtered: [], aggressive: [] };
    trades.forEach((t) => {
      const tier = getTier(t.strategy_name, t.notes);
      grouped[tier].push(t);
    });
    return grouped;
  }, [trades]);

  // Tier summaries
  const summaries = useMemo(() => {
    const result: Record<Tier, TierSummary> = {} as Record<Tier, TierSummary>;
    TIERS.forEach((tier) => {
      result[tier] = computeTierSummary(tradesByTier[tier]);
    });
    return result;
  }, [tradesByTier]);

  // Bar chart data
  const barChartData = useMemo(() => {
    return TIERS.map((tier) => ({
      name: TIER_LABELS[tier],
      winRate: summaries[tier].winRate,
      roi: summaries[tier].roi,
      totalPnl: summaries[tier].totalPnl,
      totalTrades: summaries[tier].totalTrades,
    }));
  }, [summaries]);

  // Cumulative PnL over time
  const cumulativePnlData = useMemo(() => {
    const tierTrades: Record<Tier, { time: number; pnl: number; placed_at: string }[]> = { broad: [], filtered: [], aggressive: [] };
    TIERS.forEach((tier) => {
      // Trades are DESC from API, reverse for chronological
      const sorted = [...tradesByTier[tier]].reverse();
      let cumPnl = 0;
      sorted.forEach((t) => {
        cumPnl += pf(t.pnl);
        tierTrades[tier].push({ time: new Date(t.placed_at).getTime(), pnl: cumPnl, placed_at: t.placed_at });
      });
    });

    // Merge all timestamps and create unified data points
    const allTimestamps = new Set<number>();
    TIERS.forEach((tier) => tierTrades[tier].forEach((p) => allTimestamps.add(p.time)));
    const sortedTimes = Array.from(allTimestamps).sort((a, b) => a - b);

    const cumState: Record<Tier, number> = { broad: 0, filtered: 0, aggressive: 0 };
    const tierIdx: Record<Tier, number> = { broad: 0, filtered: 0, aggressive: 0 };

    return sortedTimes.map((time) => {
      TIERS.forEach((tier) => {
        const arr = tierTrades[tier];
        while (tierIdx[tier] < arr.length && arr[tierIdx[tier]].time <= time) {
          cumState[tier] = arr[tierIdx[tier]].pnl;
          tierIdx[tier]++;
        }
      });
      const d = new Date(time);
      return {
        time: d.toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit", timeZone: "UTC" }) + " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }),
        broad: cumState.broad,
        filtered: cumState.filtered,
        aggressive: cumState.aggressive,
      };
    });
  }, [tradesByTier]);

  // Rolling win rate (last 20 trades)
  const rollingWinRateData = useMemo(() => {
    const tierData: Record<Tier, { time: number; winRate: number; label: string }[]> = { broad: [], filtered: [], aggressive: [] };
    const WINDOW = 20;

    TIERS.forEach((tier) => {
      const sorted = [...tradesByTier[tier]].reverse();
      const outcomes: boolean[] = [];
      sorted.forEach((t) => {
        if (t.final_outcome === "win" || t.final_outcome === "loss") {
          outcomes.push(t.final_outcome === "win");
          if (outcomes.length >= 2) {
            const window = outcomes.slice(-WINDOW);
            const wr = (window.filter(Boolean).length / window.length) * 100;
            const d = new Date(t.placed_at);
            tierData[tier].push({
              time: d.getTime(),
              winRate: wr,
              label: d.toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit", timeZone: "UTC" }) + " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }),
            });
          }
        }
      });
    });

    // Merge timestamps
    const allTimestamps = new Set<number>();
    TIERS.forEach((tier) => tierData[tier].forEach((p) => allTimestamps.add(p.time)));
    const sortedTimes = Array.from(allTimestamps).sort((a, b) => a - b);

    const lastVal: Record<Tier, number | null> = { broad: null, filtered: null, aggressive: null };
    const tierIdx: Record<Tier, number> = { broad: 0, filtered: 0, aggressive: 0 };

    return sortedTimes.map((time) => {
      TIERS.forEach((tier) => {
        const arr = tierData[tier];
        while (tierIdx[tier] < arr.length && arr[tierIdx[tier]].time <= time) {
          lastVal[tier] = arr[tierIdx[tier]].winRate;
          tierIdx[tier]++;
        }
      });
      const d = new Date(time);
      return {
        time: d.toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit", timeZone: "UTC" }) + " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }),
        broad: lastVal.broad,
        filtered: lastVal.filtered,
        aggressive: lastVal.aggressive,
      };
    });
  }, [tradesByTier]);

  // Tier data point counts for line chart legend notes
  const tierDataPoints = useMemo(() => {
    const counts: Record<Tier, number> = { broad: 0, filtered: 0, aggressive: 0 };
    TIERS.forEach((tier) => { counts[tier] = tradesByTier[tier].length; });
    return counts;
  }, [tradesByTier]);

  // Trade log (filtered + paginated)
  const filteredTrades = useMemo(() => {
    if (tableFilter === "all") return trades;
    return trades.filter((t) => getTier(t.strategy_name, t.notes) === tableFilter);
  }, [trades, tableFilter]);

  const visibleTrades = filteredTrades.slice(0, visibleCount);

  // IntersectionObserver for infinite scroll
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setVisibleCount((prev) => Math.min(prev + ROWS_PER_PAGE, filteredTrades.length));
        }
      },
      { root: scrollRef.current, rootMargin: "200px" }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [filteredTrades.length]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <>
      <Navbar />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 md:px-6 py-6 md:py-10">
        {/* Header */}
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-zinc-50">Momentum Strategy Analytics</h1>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {TIERS.map((tier) => (
                <span
                  key={tier}
                  className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs font-medium ${TIER_BADGE_CLASSES[tier]}`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${tierStatus[tier] ? "bg-emerald-400" : "bg-zinc-600"}`}
                  />
                  {TIER_LABELS[tier]} — {tierStatus[tier] ? "Enabled" : "Disabled"}
                </span>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground tabular-nums">
              <span className="h-1.5 w-1.5 rounded-full bg-primary/50 animate-pulse" />
              {countdown}s
            </span>
            <select
              value={range}
              onChange={(e) => setRange(e.target.value as TimeRange)}
              className="w-44 rounded-lg border border-zinc-800/60 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100 outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/30"
            >
              {TIME_RANGES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>
        </div>

        {loading ? (
          <p className="text-sm text-muted-foreground">Loading analytics...</p>
        ) : (
          <>
            {/* Section 1: Per-tier summary cards */}
            <SectionHeader title="Tier Performance" description="Key metrics for each momentum tier" />
            <div className="mb-10 grid grid-cols-1 md:grid-cols-3 gap-4">
              {TIERS.map((tier) => {
                const s = summaries[tier];
                const empty = s.totalTrades === 0;
                return (
                  <GlassPanel key={tier} variant="subtle" className="p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: TIER_COLORS[tier] }}
                      />
                      <h3 className="text-base font-semibold text-zinc-100">{TIER_LABELS[tier]}</h3>
                    </div>
                    {empty ? (
                      <p className="text-sm text-muted-foreground">No trades yet</p>
                    ) : (
                      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                        <div>
                          <p className="text-xs uppercase tracking-wider text-zinc-500">Trades</p>
                          <p className="text-2xl font-bold text-zinc-100">{s.totalTrades}</p>
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-wider text-zinc-500">Win Rate</p>
                          <p className="text-2xl font-bold text-zinc-100">{fmtPercent(s.winRate)}</p>
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-wider text-zinc-500">Total PnL</p>
                          <p className={`text-2xl font-bold ${pnlColor(s.totalPnl)}`}>{fmtPnl(s.totalPnl)}</p>
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-wider text-zinc-500">ROI</p>
                          <p className={`text-2xl font-bold ${pnlColor(s.roi)}`}>{fmtPercent(s.roi)}</p>
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-wider text-zinc-500">Avg PnL</p>
                          <p className={`text-sm font-medium ${pnlColor(s.avgPnl)}`}>{fmtPnl(s.avgPnl)}</p>
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-wider text-zinc-500">Wagered</p>
                          <p className="text-sm font-medium text-zinc-300">{fmtPnl(s.totalWagered)}</p>
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-wider text-zinc-500">Wins / Losses</p>
                          <p className="text-sm font-medium text-zinc-300">{s.wins} / {s.losses}</p>
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-wider text-zinc-500">Stop-losses</p>
                          <p className="text-sm font-medium text-zinc-300">{s.stopLosses}</p>
                        </div>
                        <div className="col-span-2">
                          <p className="text-xs uppercase tracking-wider text-zinc-500">Avg Entry Price</p>
                          <p className="text-sm font-medium text-zinc-300">{fmtPrice(s.avgEntryPrice)}</p>
                        </div>
                      </div>
                    )}
                  </GlassPanel>
                );
              })}
            </div>

            {/* Section 2: Comparison bar charts */}
            <SectionHeader title="Tier Comparison" description="Side-by-side comparison across all tiers" />
            <div className="mb-10 grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                { key: "winRate", label: "Win Rate (%)", fmt: (v: number) => `${v.toFixed(1)}%` },
                { key: "roi", label: "ROI (%)", fmt: (v: number) => `${v.toFixed(1)}%` },
                { key: "totalPnl", label: "Total PnL ($)", fmt: (v: number) => fmtPnl(v) },
                { key: "totalTrades", label: "Total Trades", fmt: (v: number) => String(v) },
              ].map((chart) => (
                <GlassPanel key={chart.key} variant="subtle" className="p-4">
                  <p className="text-sm font-semibold text-zinc-300 mb-3">{chart.label}</p>
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart data={barChartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="name" tick={{ fill: "#71717a", fontSize: 12 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: "#71717a", fontSize: 12 }} axisLine={false} tickLine={false} />
                      <RechartsTooltip content={<ChartTooltip />} />
                      <Bar
                        dataKey={chart.key}
                        radius={[4, 4, 0, 0]}
                        maxBarSize={48}
                      >
                        {barChartData.map((_, idx) => (
                          <Cell key={idx} fill={TIER_COLORS[TIERS[idx]]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </GlassPanel>
              ))}
            </div>

            {/* Section 3: Cumulative PnL over time */}
            <SectionHeader title="Cumulative PnL Over Time" description="Running total PnL per tier" />
            <GlassPanel variant="glow-tl" className="p-4 mb-10">
              {cumulativePnlData.length < 2 ? (
                <p className="text-sm text-muted-foreground py-8 text-center">Not enough data points to render chart</p>
              ) : (
                <>
                  <div className="flex flex-wrap gap-3 mb-3">
                    {TIERS.map((tier) => (
                      <span key={tier} className="flex items-center gap-1.5 text-xs text-zinc-400">
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: TIER_COLORS[tier] }} />
                        {TIER_LABELS[tier]}
                        {tierDataPoints[tier] < 2 && <span className="text-zinc-600">(insufficient data)</span>}
                      </span>
                    ))}
                  </div>
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={cumulativePnlData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="time" tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                      <YAxis tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} />
                      <RechartsTooltip content={<ChartTooltip />} />
                      {TIERS.map((tier) =>
                        tierDataPoints[tier] >= 2 ? (
                          <Line
                            key={tier}
                            type="monotone"
                            dataKey={tier}
                            name={TIER_LABELS[tier]}
                            stroke={TIER_COLORS[tier]}
                            strokeWidth={2}
                            dot={false}
                            connectNulls
                          />
                        ) : null
                      )}
                    </LineChart>
                  </ResponsiveContainer>
                </>
              )}
            </GlassPanel>

            {/* Section 4: Rolling win rate */}
            <SectionHeader title="Win Rate Over Time" description="Rolling win rate (last 20 trades) per tier" />
            <GlassPanel variant="glow-br" className="p-4 mb-10">
              {rollingWinRateData.length < 2 ? (
                <p className="text-sm text-muted-foreground py-8 text-center">Not enough data points to render chart</p>
              ) : (
                <>
                  <div className="flex flex-wrap gap-3 mb-3">
                    {TIERS.map((tier) => (
                      <span key={tier} className="flex items-center gap-1.5 text-xs text-zinc-400">
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: TIER_COLORS[tier] }} />
                        {TIER_LABELS[tier]}
                        {tierDataPoints[tier] < 2 && <span className="text-zinc-600">(insufficient data)</span>}
                      </span>
                    ))}
                  </div>
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={rollingWinRateData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="time" tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                      <YAxis tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} domain={[0, 100]} />
                      <RechartsTooltip content={<ChartTooltip />} />
                      {TIERS.map((tier) =>
                        tierDataPoints[tier] >= 2 ? (
                          <Line
                            key={tier}
                            type="monotone"
                            dataKey={tier}
                            name={TIER_LABELS[tier]}
                            stroke={TIER_COLORS[tier]}
                            strokeWidth={2}
                            dot={false}
                            connectNulls
                          />
                        ) : null
                      )}
                    </LineChart>
                  </ResponsiveContainer>
                </>
              )}
            </GlassPanel>

            {/* Section 5: Trade log table */}
            <SectionHeader title="Trade Log" description="Individual momentum trades, most recent first" />
            <GlassPanel variant="subtle" className="p-4">
              {/* Tier filter */}
              <div className="flex items-center gap-2 mb-4">
                <span className="text-sm text-zinc-400">Filter:</span>
                {(["all", ...TIERS] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTableFilter(t)}
                    className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                      tableFilter === t
                        ? "bg-zinc-800 text-zinc-100"
                        : "text-zinc-500 hover:text-zinc-300"
                    }`}
                  >
                    {t === "all" ? "All Tiers" : TIER_LABELS[t]}
                  </button>
                ))}
                <div className="ml-auto flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">
                    {filteredTrades.length} trades
                  </span>
                  <button
                    onClick={() => {
                      const rows = filteredTrades.map((t) => {
                        const tier = getTier(t.strategy_name, t.notes);
                        const parsed = parseSignalData(t.notes);
                        return {
                          time: t.placed_at,
                          tier,
                          market: t.market_type,
                          direction: t.direction,
                          entry_price: t.entry_price,
                          cost: (pf(t.entry_price) * pf(t.bet_size_usd)).toFixed(2),
                          outcome: outcomeLabel(t),
                          pnl: tradePnl(t).toFixed(2),
                          momentum_value: parsed?.momentum_value ?? "",
                          entry_seconds: parsed?.seconds_elapsed ?? "",
                        };
                      });
                      const headers = Object.keys(rows[0] ?? {});
                      const csv = [
                        headers.join(","),
                        ...rows.map((r) =>
                          headers.map((h) => {
                            const val = String((r as Record<string, unknown>)[h] ?? "");
                            return val.includes(",") ? `"${val}"` : val;
                          }).join(",")
                        ),
                      ].join("\n");
                      const blob = new Blob([csv], { type: "text/csv" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `momentum-trades-${range}.csv`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                    disabled={filteredTrades.length === 0}
                    className="rounded-lg bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/20 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Export CSV
                  </button>
                </div>
              </div>

              {/* Table — fixed header + scrollable body */}
              <div className="overflow-x-auto">
                <div className="min-w-[900px]">
                  <table className="w-full table-fixed">
                    <thead className="bg-zinc-950">
                      <tr className="border-b border-zinc-800/40">
                        <th className="w-32 px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Time</th>
                        <th className="w-20 px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Tier</th>
                        <th className="w-20 px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Market</th>
                        <th className="w-16 px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Dir</th>
                        <th className="w-20 px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">Entry</th>
                        <th className="w-20 px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">Cost</th>
                        <th className="w-20 px-3 py-2.5 text-center text-xs font-semibold uppercase tracking-wider text-zinc-500">Outcome</th>
                        <th className="w-20 px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">PnL</th>
                        <th className="w-20 px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">Momentum</th>
                        <th className="w-20 px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">Entry (s)</th>
                      </tr>
                    </thead>
                  </table>
                  <div ref={scrollRef} className="h-[520px] overflow-y-auto scrollbar-thin">
                    <table className="w-full table-fixed">
                      <tbody>
                        {visibleTrades.length === 0 ? (
                          <tr>
                            <td colSpan={10} className="py-12 text-center text-sm text-zinc-500">
                              No trades to show.
                            </td>
                          </tr>
                        ) : (
                          visibleTrades.map((trade, idx) => {
                            const tier = getTier(trade.strategy_name, trade.notes);
                            const signal = parseSignalData(trade.notes);
                            const momentumValue = signal?.momentum_value != null ? Number(signal.momentum_value).toFixed(4) : "—";
                            const secondsElapsed = signal?.seconds_elapsed != null ? String(signal.seconds_elapsed) : "—";
                            const tPnl = tradePnl(trade);
                            return (
                              <tr
                                key={trade.id}
                                className={`border-b border-zinc-800/20 hover:bg-zinc-800/20 transition-colors ${idx % 2 === 1 ? "bg-zinc-900/30" : ""}`}
                              >
                                <td className="w-32 px-3 py-3 text-sm tabular-nums text-zinc-400 truncate">{fmtDateTime(trade.placed_at)}</td>
                                <td className="w-20 px-3 py-3">
                                  <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium border ${TIER_BADGE_CLASSES[tier]}`}>
                                    {TIER_LABELS[tier]}
                                  </span>
                                </td>
                                <td className="w-20 px-3 py-3 text-sm text-zinc-300 truncate">{trade.market_type || "—"}</td>
                                <td className="w-16 px-3 py-3 text-sm text-zinc-300">{trade.direction}</td>
                                <td className="w-20 px-3 py-3 text-right font-mono text-sm tabular-nums text-zinc-200">{fmtPrice(pf(trade.entry_price))}</td>
                                <td className="w-20 px-3 py-3 text-right font-mono text-sm tabular-nums text-zinc-200">${(pf(trade.entry_price) * pf(trade.bet_size_usd)).toFixed(2)}</td>
                                <td className="w-20 px-3 py-3 text-center">
                                  <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${outcomeBadge(trade)}`}>
                                    {outcomeLabel(trade)}
                                  </span>
                                </td>
                                <td className={`w-20 px-3 py-3 text-right font-mono text-sm tabular-nums font-medium ${pnlColor(tPnl)}`}>
                                  {tPnl !== 0 || trade.pnl != null || trade.stop_loss_triggered || trade.final_outcome === "stop_loss" ? fmtPnl(tPnl) : "—"}
                                </td>
                                <td className="w-20 px-3 py-3 text-right text-sm text-zinc-300">{momentumValue}</td>
                                <td className="w-20 px-3 py-3 text-right text-sm text-zinc-300">{secondsElapsed}</td>
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                    <div ref={sentinelRef} className="h-1" />
                  </div>
                </div>
              </div>
            </GlassPanel>
          </>
        )}
      </main>
    </>
  );
}
