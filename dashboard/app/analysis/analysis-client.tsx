"use client";

import { useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/navbar";
import { Badge } from "@/components/ui/badge";
import { SectionHeader } from "@/components/section-header";
import { cn } from "@/lib/utils";
import {
  BarChart, Bar, XAxis, YAxis, ReferenceLine,
  ResponsiveContainer, Tooltip as RechartsTooltip, Cell,
} from "recharts";
import { CalibrationHeatmap } from "@/components/calibration-heatmap";
import { WinRateChart } from "@/components/win-rate-chart";
import { GlassPanel } from "@/components/ui/glass-panel";
import { StreakDetectorLive } from "@/components/streak-detector-live";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AnalysisRun {
  id: number;
  ran_at: string;
  markets_analyzed: number;
  total_ticks?: number;
  date_range_start?: string;
  date_range_end?: string;
}

interface CalibrationRow {
  market_type: string;
  checkpoint_seconds: number;
  price_bucket: number;
  sample_count: number;
  expected_win_rate: number;
  actual_win_rate: number;
  deviation: number;
  significant: boolean;
  p_value?: number;
}

interface TrajectoryRow {
  market_type: string;
  checkpoint_seconds: number;
  outcome: string;
  sample_count: number;
  win_rate: number;
  reversal_count: number;
  reversal_resolved_up_pct: number;
}

interface TimeofdayRow {
  market_type: string;
  hour_utc: number;
  sample_count: number;
  up_win_rate: number;
}

interface SequentialRow {
  market_type: string;
  analysis_type: string;
  key: string;
  sample_count: number;
  value: number;
  up_win_rate?: string;
  notes?: string;
  metadata?: string;
}

interface HeatmapRow {
  market_type: string;
  time_offset: string;
  price_bucket: string;
  sample_count: string;
  up_win_rate: string;
}

export interface AnalysisData {
  run: AnalysisRun | null;
  calibration: CalibrationRow[];
  trajectory: TrajectoryRow[];
  timeofday: TimeofdayRow[];
  sequential: SequentialRow[];
  heatmap: HeatmapRow[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CHECKPOINTS = [30, 60, 120, 180, 240, 300];
const CHECKPOINT_LABELS: Record<number, string> = {
  30: "30s", 60: "60s", 120: "120s", 180: "180s", 240: "240s", 300: "300s",
};
const MARKET_TYPE_TABS = [
  "all", "btc_5m", "btc_15m", "eth_5m", "eth_15m", "sol_5m", "sol_15m", "xrp_5m", "xrp_15m",
];
const MARKET_TYPE_LABELS: Record<string, string> = {
  all: "All", btc_5m: "BTC 5m", btc_15m: "BTC 15m",
  eth_5m: "ETH 5m", eth_15m: "ETH 15m",
  sol_5m: "SOL 5m", sol_15m: "SOL 15m",
  xrp_5m: "XRP 5m", xrp_15m: "XRP 15m",
};
const ASSETS = ["btc", "eth", "sol", "xrp"];
const MARKET_TYPES_8 = [
  "btc_5m", "btc_15m", "eth_5m", "eth_15m", "sol_5m", "sol_15m", "xrp_5m", "xrp_15m",
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatRunDate(dateStr: string): string {
  const d = new Date(dateStr);
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const month = months[d.getUTCMonth()];
  const day = d.getUTCDate();
  const year = d.getUTCFullYear();
  const hh = d.getUTCHours().toString().padStart(2, "0");
  const mm = d.getUTCMinutes().toString().padStart(2, "0");
  return `${month} ${day}, ${year} at ${hh}:${mm} UTC`;
}

function formatShortDate(dateStr: string): string {
  const d = new Date(dateStr);
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[d.getUTCMonth()]} ${d.getUTCDate()} ${d.getUTCHours().toString().padStart(2,"0")}:${d.getUTCMinutes().toString().padStart(2,"0")}`;
}

function formatDateOnly(dateStr: string): string {
  const d = new Date(dateStr);
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

function isStale(dateStr: string): boolean {
  return Date.now() - new Date(dateStr).getTime() > 7 * 24 * 60 * 60 * 1000;
}

function pctColor(val: number, threshold = 5): string {
  if (val > threshold) return "text-emerald-400";
  if (val < -threshold) return "text-red-400";
  return "text-zinc-400";
}

function barColor(winRate: number): string {
  if (winRate > 60) return "#4ade80";
  if (winRate < 40) return "#f87171";
  return "#71717a";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TabRow({
  tabs,
  labels,
  selected,
  onSelect,
}: {
  tabs: (string | number)[];
  labels: Record<string | number, string>;
  selected: string | number;
  onSelect: (v: string | number) => void;
}) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto pb-1 scrollbar-thin">
      {tabs.map((t) => (
        <button
          key={t}
          onClick={() => onSelect(t)}
          className={cn(
            "flex-shrink-0 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
            selected === t
              ? "bg-primary/[0.12] text-primary border border-primary/30"
              : "bg-zinc-900/60 text-zinc-400 border border-zinc-800/40 hover:text-zinc-200 hover:border-zinc-700/60"
          )}
        >
          {labels[t] ?? t}
        </button>
      ))}
    </div>
  );
}

function AnalysisSection({
  title,
  description,
  warning,
  children,
}: {
  title: string;
  description?: string;
  warning?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-8 md:mt-14">
      <SectionHeader title={title} description={description} />
      {warning && (
        <p className="mt-2 text-xs text-yellow-500/80">⚠️ {warning}</p>
      )}
      {children}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section 1 — Calibration
// ---------------------------------------------------------------------------

function CalibrationSection({ data }: { data: CalibrationRow[] }) {
  const [checkpoint, setCheckpoint] = useState<number>(60);
  const [marketType, setMarketType] = useState<string>("btc_5m");

  const isSig = (v: unknown) => v === true || v === "true" || v === "t" || v === 1;

  const filtered = data.filter((r) => {
    const cpMatch = Number(r.checkpoint_seconds) === checkpoint;
    const mtMatch = r.market_type === marketType;
    return cpMatch && mtMatch;
  });

  return (
    <AnalysisSection
      title="Calibration Analysis"
      description="When the market prices a contract at X%, does Up actually win X% of the time? Deviations indicate mispricing."
    >
      <GlassPanel variant="glow-tl">
        {/* Checkpoint filter bar */}
        <div className="relative border-b border-zinc-800/60 px-6 py-3 flex items-center gap-2 flex-wrap">
          {CHECKPOINTS.map((cp) => (
            <button
              key={cp}
              onClick={() => setCheckpoint(cp)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                checkpoint === cp
                  ? "bg-primary/20 text-primary"
                  : "bg-zinc-800/60 text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {CHECKPOINT_LABELS[cp]}
            </button>
          ))}
          <div className="h-4 w-px bg-zinc-800/60 mx-1" />
          {MARKET_TYPES_8.map((mt) => (
            <button
              key={mt}
              onClick={() => setMarketType(mt)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                marketType === mt
                  ? "bg-primary/20 text-primary"
                  : "bg-zinc-800/60 text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {MARKET_TYPE_LABELS[mt]}
            </button>
          ))}
        </div>

        {filtered.length === 0 ? (
          <div className="p-8 text-center text-sm text-zinc-500">
            Not enough data for this combination yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-zinc-800/40">
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Price Bucket</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Samples</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Expected</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Actual</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Deviation</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Significant</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r, i) => {
                  const dev = r.deviation * 100;
                  const actual = r.actual_win_rate * 100;
                  const expected = r.expected_win_rate * 100;
                  const isUp = actual > expected;
                  return (
                    <tr
                      key={i}
                      className={cn(
                        "border-b border-zinc-800/20 hover:bg-zinc-800/20 transition-colors",
                        isSig(r.significant) && "border-l-2 border-l-primary/60"
                      )}
                    >
                      <td className="px-4 py-3">
                        <span className="font-mono text-sm font-semibold tabular-nums text-zinc-200">
                          {(r.price_bucket * 100).toFixed(0)}¢
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs text-zinc-400">{r.sample_count.toLocaleString("en-US")}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs text-zinc-400">{expected.toFixed(0)}%</span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-16 rounded-full bg-zinc-800">
                            <div
                              className={`h-full rounded-full transition-all ${isUp ? "bg-emerald-400" : "bg-red-400"}`}
                              style={{ width: `${Math.min(actual, 100)}%` }}
                            />
                          </div>
                          <span className={`font-mono text-xs font-semibold ${isUp ? "text-emerald-400" : "text-red-400"}`}>
                            {actual.toFixed(1)}%
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`font-mono text-sm font-bold tabular-nums ${dev > 0 ? "text-emerald-400" : dev < 0 ? "text-red-400" : "text-zinc-400"}`}>
                          {dev > 0 ? "+" : ""}{dev.toFixed(1)}%
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {isSig(r.significant) ? (
                          <span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium text-emerald-400 bg-emerald-400/10">
                            Significant
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium text-zinc-500 bg-zinc-800/40">
                            –
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </GlassPanel>
      <p className="mt-3 text-xs text-zinc-500">
        Min 10 samples per bucket required. p &lt; 0.05 threshold for significance.
      </p>
    </AnalysisSection>
  );
}

// ---------------------------------------------------------------------------
// Section C — Edge Scanner (new)
// ---------------------------------------------------------------------------

function EdgeScannerSection({ data }: { data: CalibrationRow[] }) {
  const [marketType, setMarketType] = useState<string>(MARKET_TYPES_8[0]);

  const edges = data
    .filter((r) => {
      const pv = parseFloat(String(r.p_value));
      const sc = Number(r.sample_count);
      return pv < 0.15 && sc >= 5 && r.market_type === marketType;
    })
    .map((r) => ({
      ...r,
      market_type: String(r.market_type),
      price_bucket: parseFloat(String(r.price_bucket)),
      actual_win_rate: parseFloat(String(r.actual_win_rate)),
      expected_win_rate: parseFloat(String(r.expected_win_rate)),
      deviation: parseFloat(String(r.deviation)),
      sample_count: Number(r.sample_count),
      checkpoint_seconds: Number(r.checkpoint_seconds),
    }))
    .sort((a, b) => Math.abs(b.deviation) - Math.abs(a.deviation));

  function formatMarketType(mt: string): string {
    if (!mt) return "Unknown";
    const parts = mt.split("_");
    return `${parts[0].toUpperCase()} ${parts[1] || ""}`.trim();
  }

  function downloadCSV() {
    const headers = ["Market Type", "Checkpoint", "Price Bucket", "Implied Prob", "Actual Win Rate", "Edge", "Strength", "Sample Count", "Action"];
    const rows = edges.map((r) => {
      const absDev = Math.abs(r.deviation);
      const strength = absDev > 0.15 ? "Strong" : absDev >= 0.10 ? "Moderate" : "Slight";
      const action = r.deviation > 0 ? "Bet Up" : "Bet Down";
      return [
        formatMarketType(r.market_type),
        `@ ${r.checkpoint_seconds}s`,
        `${(r.price_bucket * 100).toFixed(1)}¢`,
        `${(r.price_bucket * 100).toFixed(1)}%`,
        `${(r.actual_win_rate * 100).toFixed(1)}%`,
        `${r.deviation > 0 ? "+" : ""}${(r.deviation * 100).toFixed(1)}%`,
        strength,
        r.sample_count,
        action,
      ].join(",");
    });
    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "edge-scanner.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <AnalysisSection
      title="Edge Scanner"
      description="Price buckets where the market is statistically mispricing the contract. Only shows buckets that pass p < 0.15 significance test with at least 5 samples."
      warning="Exploratory mode — low sample sizes mean high noise. Results are indicative only until 500+ markets per type are collected."
    >
      <GlassPanel variant="glow-tr">
        {/* Market type filter bar */}
        <div className="relative border-b border-zinc-800/60 px-6 py-3 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-1 flex-wrap">
            {MARKET_TYPES_8.map((mt) => (
              <button
                key={mt}
                onClick={() => setMarketType(mt)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  marketType === mt
                    ? "bg-primary/20 text-primary"
                    : "bg-zinc-800/60 text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {MARKET_TYPE_LABELS[mt]}
              </button>
            ))}
          </div>
          {edges.length > 0 && (
            <button
              onClick={downloadCSV}
              className="flex items-center gap-1.5 rounded-md border border-zinc-700/60 bg-zinc-800/60 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:border-primary/40 hover:text-primary"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Export CSV
            </button>
          )}
        </div>

        {edges.length === 0 ? (
          <div className="p-8 text-center text-sm text-zinc-500">
            No statistically significant edges found in current dataset. More data needed.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-zinc-800/40">
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Market Type</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Checkpoint</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Price Bucket</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Implied Prob</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Actual Win Rate</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Edge</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Strength</th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">Samples</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Action</th>
                </tr>
              </thead>
              <tbody>
                {edges.map((r, i) => {
                  const absDev = Math.abs(r.deviation);
                  const strength = absDev > 0.15
                    ? { label: "Strong", color: "text-orange-400", bg: "bg-orange-400/10" }
                    : absDev >= 0.10
                      ? { label: "Moderate", color: "text-yellow-400", bg: "bg-yellow-400/10" }
                      : { label: "Slight", color: "text-zinc-400", bg: "bg-zinc-800/40" };
                  const isUp = r.deviation > 0;
                  return (
                    <tr key={i} className="border-b border-zinc-800/20 hover:bg-zinc-800/20 transition-colors">
                      <td className="px-4 py-3">
                        <span className="text-sm font-semibold text-zinc-200">{formatMarketType(r.market_type)}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs text-zinc-400">@ {r.checkpoint_seconds}s</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-sm font-semibold tabular-nums text-zinc-200">
                          {(r.price_bucket * 100).toFixed(1)}¢
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs text-zinc-400">{(r.price_bucket * 100).toFixed(1)}%</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`font-mono text-sm font-semibold ${isUp ? "text-emerald-400" : "text-red-400"}`}>
                          {(r.actual_win_rate * 100).toFixed(1)}%
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`font-mono text-sm font-bold tabular-nums ${isUp ? "text-emerald-400" : "text-red-400"}`}>
                          {isUp ? "+" : ""}{(r.deviation * 100).toFixed(1)}%
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${strength.color} ${strength.bg}`}>
                          {strength.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className="font-mono text-xs text-zinc-400">{r.sample_count.toLocaleString("en-US")}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center rounded-md px-2.5 py-1 text-xs font-medium ${
                          isUp ? "text-emerald-400 bg-emerald-400/10" : "text-red-400 bg-red-400/10"
                        }`}>
                          {isUp ? "Bet Up" : "Bet Down"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </GlassPanel>
    </AnalysisSection>
  );
}

// ---------------------------------------------------------------------------
// Section 2 — Momentum & Trajectory
// ---------------------------------------------------------------------------

function TrajectorySection({ data }: { data: SequentialRow[] }) {
  const momentumData = data.filter((r) => r.analysis_type === "momentum");

  const cardsData = MARKET_TYPES_8.map((mt) => {
    const rising = momentumData.find((r) => r.market_type === mt && r.key === "rising_60s");
    const winRate = rising ? parseFloat(String(rising.up_win_rate ?? rising.value ?? "0")) : null;
    return { market_type: mt, rising, winRate };
  });

  const momentumCount = cardsData.filter(
    (c) => c.winRate !== null && c.winRate > 0.6
  ).length;

  const bannerColor =
    momentumCount >= 5
      ? "border-emerald-500/30 bg-emerald-500/[0.06] text-emerald-400"
      : momentumCount >= 3
        ? "border-yellow-500/30 bg-yellow-500/[0.06] text-yellow-400"
        : "border-red-500/30 bg-red-500/[0.06] text-red-400";

  return (
    <AnalysisSection
      title="Price Trajectory"
      description="Does price direction in the first 60 seconds predict the final outcome?"
    >
      <div className={cn("mb-5 rounded-lg border px-4 py-2.5 text-sm font-medium", bannerColor)}>
        Momentum effect detected in {momentumCount}/8 market types
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {cardsData.map(({ market_type, rising, winRate }) => {
          const label = MARKET_TYPE_LABELS[market_type] || market_type;
          const winPct = winRate !== null ? winRate * 100 : null;
          const badgeVariant = winPct !== null && winPct > 60 ? "up" as const : winPct !== null && winPct < 50 ? "down" as const : "default" as const;
          const badgeText = winPct !== null ? `${winPct.toFixed(0)}% Up` : "–";

          const reversal = data.find(
            (r) => r.analysis_type === "momentum" && r.market_type === market_type && r.key === "reversal_60s"
          );

          return (
            <GlassPanel key={market_type} variant="glow-br" className="p-6">
              <div className="relative">
                <div className="mb-4 flex items-center justify-between">
                  <span className="text-base font-semibold tracking-tight text-zinc-100">{label}</span>
                  <Badge variant={badgeVariant}>{badgeText}</Badge>
                </div>

                {rising ? (
                  <>
                    <p className="text-sm text-zinc-300">
                      <span className="text-emerald-400">↑</span> Rising at 60s → Up wins{" "}
                      <span className={`font-mono text-sm font-bold ${winPct! > 60 ? "text-emerald-400" : winPct! < 50 ? "text-red-400" : "text-zinc-200"}`}>
                        {winPct!.toFixed(1)}%
                      </span>
                    </p>
                    <div className="mt-2 h-1.5 w-full rounded-full bg-zinc-800 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${winPct! > 60 ? "bg-emerald-400" : winPct! < 50 ? "bg-red-400" : "bg-yellow-400"}`}
                        style={{ width: `${Math.min(winPct!, 100)}%` }}
                      />
                    </div>
                    <p className="mt-2 text-xs text-zinc-400">
                      {rising.sample_count.toLocaleString("en-US")} samples
                    </p>
                  </>
                ) : (
                  <p className="text-sm text-zinc-500">No momentum data</p>
                )}
                {reversal && reversal.sample_count > 0 && (
                  <p className="mt-3 text-sm text-zinc-300">
                    <span className="text-yellow-400">↩</span>{" "}
                    {reversal.sample_count.toLocaleString("en-US")} reversals,{" "}
                    <span className="font-mono text-xs font-semibold text-zinc-200">
                      {(parseFloat(String(reversal.up_win_rate ?? reversal.value ?? "0")) * 100).toFixed(1)}%
                    </span>{" "}
                    resolved Up
                  </p>
                )}
              </div>
            </GlassPanel>
          );
        })}
      </div>
    </AnalysisSection>
  );
}

// ---------------------------------------------------------------------------
// Section 3 — Time of Day
// ---------------------------------------------------------------------------

function TimeofdaySection({ data }: { data: TimeofdayRow[] }) {
  const [marketType, setMarketType] = useState<string>("all");

  const filtered =
    marketType === "all"
      ? aggregateTimeofday(data)
      : data.filter((r) => r.market_type === marketType);

  const chartData = Array.from({ length: 24 }, (_, h) => {
    const row = filtered.find((r) => r.hour_utc === h);
    return {
      hour: h,
      winRate: row ? Number((row.up_win_rate * 100).toFixed(1)) : null,
      sampleCount: row ? row.sample_count : 0,
      enough: row ? row.sample_count >= 10 : false,
    };
  });

  const validHours = chartData.filter((h) => h.enough && h.winRate !== null);
  const bullish = validHours.length > 0
    ? validHours.reduce((a, b) => ((b.winRate ?? 0) > (a.winRate ?? 0) ? b : a))
    : null;
  const bearish = validHours.length > 0
    ? validHours.reduce((a, b) => ((b.winRate ?? 0) < (a.winRate ?? 0) ? b : a))
    : null;

  return (
    <AnalysisSection
      title="Time of Day Patterns"
      description="Do certain UTC hours consistently favor Up or Down outcomes?"
    >
      <GlassPanel variant="glow-center" className="p-6">
        <div className="relative">
          {/* Market type selector inside container */}
          <div className="mb-5 flex items-center gap-2 flex-wrap">
            {MARKET_TYPE_TABS.map((mt) => (
              <button
                key={mt}
                onClick={() => setMarketType(mt)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  marketType === mt
                    ? "bg-primary/20 text-primary"
                    : "bg-zinc-800/60 text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {MARKET_TYPE_LABELS[mt]}
              </button>
            ))}
          </div>

          {filtered.length === 0 ? (
            <div className="flex h-40 items-center justify-center text-sm text-zinc-500">
              No time-of-day data available.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: -15 }}>
                <XAxis
                  dataKey="hour"
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
                <ReferenceLine y={50} stroke="#71717a" strokeDasharray="4 4" strokeWidth={1} />
                <RechartsTooltip
                  cursor={{ fill: "rgba(255,255,255,0.03)" }}
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const d = payload[0].payload;
                    if (!d.enough) return null;
                    const isUp = (d.winRate ?? 0) > 50;
                    const edge = (d.winRate ?? 0) - 50;
                    return (
                      <div className="w-44 rounded-lg border border-zinc-700/60 bg-zinc-900/95 backdrop-blur-sm shadow-2xl overflow-hidden">
                        <div className={`px-3 py-1.5 ${isUp ? "bg-emerald-500/15" : "bg-red-500/15"}`}>
                          <span className="text-xs font-semibold text-zinc-200">{d.hour}:00 UTC</span>
                        </div>
                        <div className="px-3 py-2.5 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-zinc-500">Win Rate</span>
                            <span className={`font-mono text-sm font-bold ${isUp ? "text-emerald-400" : "text-red-400"}`}>
                              {(d.winRate ?? 0).toFixed(1)}%
                            </span>
                          </div>
                          <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${isUp ? "bg-emerald-400" : "bg-red-400"}`}
                              style={{ width: `${d.winRate ?? 0}%` }}
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
                            <span className="text-xs text-zinc-500">Samples</span>
                            <span className="font-mono text-xs text-zinc-300">{d.sampleCount}</span>
                          </div>
                        </div>
                      </div>
                    );
                  }}
                />
                <Bar dataKey="winRate" radius={[3, 3, 0, 0]} maxBarSize={18}>
                  {chartData.map((entry, idx) => (
                    <Cell
                      key={idx}
                      fill={!entry.enough ? "#3f3f46" : (entry.winRate ?? 50) > 50 ? "#4ade80" : "#f87171"}
                      fillOpacity={entry.enough ? 0.85 : 0.2}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </GlassPanel>

      {bullish && bearish && (
        <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <GlassPanel variant="glow-tl" className="p-6">
            <div className="relative">
              <p className="text-xs uppercase tracking-wider text-zinc-500 mb-2">
                Most Bullish Hour
              </p>
              <p className="text-2xl font-bold tracking-tight text-emerald-400">
                {bullish.hour}:00 UTC
              </p>
              <p className="mt-1 text-sm text-zinc-300">
                <span className="font-mono font-semibold">{bullish.winRate}%</span> win rate · {bullish.sampleCount} samples
              </p>
            </div>
          </GlassPanel>
          <GlassPanel variant="glow-br" className="p-6">
            <div className="relative">
              <p className="text-xs uppercase tracking-wider text-zinc-500 mb-2">
                Most Bearish Hour
              </p>
              <p className="text-2xl font-bold tracking-tight text-red-400">
                {bearish.hour}:00 UTC
              </p>
              <p className="mt-1 text-sm text-zinc-300">
                <span className="font-mono font-semibold">{bearish.winRate}%</span> win rate · {bearish.sampleCount} samples
              </p>
            </div>
          </GlassPanel>
        </div>
      )}
      <p className="mt-3 text-xs text-zinc-500">
        Only hours with ≥10 samples are shown. Hours with fewer samples are greyed out.
      </p>
    </AnalysisSection>
  );
}

function aggregateTimeofday(data: TimeofdayRow[]): TimeofdayRow[] {
  const byHour = new Map<number, { totalWeighted: number; totalSamples: number }>();
  for (const r of data) {
    const existing = byHour.get(r.hour_utc) || { totalWeighted: 0, totalSamples: 0 };
    existing.totalWeighted += r.up_win_rate * r.sample_count;
    existing.totalSamples += r.sample_count;
    byHour.set(r.hour_utc, existing);
  }
  return Array.from(byHour.entries()).map(([hour, v]) => ({
    market_type: "all",
    hour_utc: hour,
    sample_count: v.totalSamples,
    up_win_rate: v.totalSamples > 0 ? v.totalWeighted / v.totalSamples : 0,
  }));
}

// ---------------------------------------------------------------------------
// Section 4a — Streak Analysis
// ---------------------------------------------------------------------------

function StreakSection({ data }: { data: SequentialRow[] }) {
  const [marketType, setMarketType] = useState<string>(MARKET_TYPES_8[0]);

  const streaks = data
    .filter((r) => r.analysis_type === "streak" && r.market_type === marketType && Number(r.sample_count) >= 15)
    .sort((a, b) => {
      const aRate = parseFloat(String(a.up_win_rate ?? a.value ?? "0"));
      const bRate = parseFloat(String(b.up_win_rate ?? b.value ?? "0"));
      return Math.abs(bRate - 0.5) - Math.abs(aRate - 0.5);
    });

  return (
    <AnalysisSection
      title="Outcome Streaks"
      description="After N consecutive Up or Down outcomes, what happens next?"
    >
      <GlassPanel variant="glow-split">
        {/* Market type filter bar */}
        <div className="relative border-b border-zinc-800/60 px-6 py-3 flex items-center gap-2 flex-wrap">
          {MARKET_TYPES_8.map((mt) => (
            <button
              key={mt}
              onClick={() => setMarketType(mt)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                marketType === mt
                  ? "bg-primary/20 text-primary"
                  : "bg-zinc-800/60 text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {MARKET_TYPE_LABELS[mt]}
            </button>
          ))}
        </div>

        {streaks.length === 0 ? (
          <div className="p-8 text-center text-sm text-zinc-500">
            No streak patterns with ≥15 samples found.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-zinc-800/40">
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Pattern</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Samples</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Next Up Rate</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Edge</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Strength</th>
                </tr>
              </thead>
              <tbody>
                {streaks.map((r, i) => {
                  const rawRate = parseFloat(String(r.up_win_rate ?? r.value ?? "0"));
                  const winRate = rawRate * 100;
                  const edge = (rawRate - 0.5) * 100;
                  const absEdge = Math.abs(edge);
                  const isUp = edge > 0;
                  const arrows = r.key.split("").map((c, j) => (
                    <span key={j} className={c === "U" ? "text-emerald-400" : "text-red-400"}>
                      {c === "U" ? "↑" : "↓"}
                    </span>
                  ));
                  const strength = absEdge >= 15
                    ? { label: isUp ? "Strong Up" : "Strong Down", color: isUp ? "text-emerald-400" : "text-red-400", bg: isUp ? "bg-emerald-400/10" : "bg-red-400/10" }
                    : absEdge >= 8
                      ? { label: isUp ? "Moderate Up" : "Moderate Down", color: isUp ? "text-emerald-300" : "text-red-300", bg: isUp ? "bg-emerald-400/5" : "bg-red-400/5" }
                      : { label: isUp ? "Slight Up" : "Slight Down", color: isUp ? "text-emerald-200" : "text-red-200", bg: "bg-zinc-800/40" };
                  return (
                    <tr key={i} className="border-b border-zinc-800/20 hover:bg-zinc-800/20 transition-colors">
                      <td className="px-4 py-3">
                        <span className="text-xs text-zinc-500 mr-1.5">After</span>
                        <span className="font-mono text-base tracking-wider">{arrows}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs text-zinc-400">{r.sample_count.toLocaleString("en-US")}</span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-16 rounded-full bg-zinc-800">
                            <div
                              className={`h-full rounded-full ${winRate > 50 ? "bg-emerald-400" : "bg-red-400"}`}
                              style={{ width: `${Math.min(winRate, 100)}%` }}
                            />
                          </div>
                          <span className={`font-mono text-xs font-semibold ${winRate > 50 ? "text-emerald-400" : "text-red-400"}`}>
                            {winRate.toFixed(1)}%
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`font-mono text-sm font-bold tabular-nums ${isUp ? "text-emerald-400" : "text-red-400"}`}>
                          {edge > 0 ? "+" : ""}{edge.toFixed(1)}%
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${strength.color} ${strength.bg}`}>
                          {strength.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </GlassPanel>
    </AnalysisSection>
  );
}

// ---------------------------------------------------------------------------
// Section 4b — Cross-Asset Correlation
// ---------------------------------------------------------------------------

function CorrelationSection({ data }: { data: SequentialRow[] }) {
  const [interval, setInterval] = useState<string>("5m");

  const correlations = data.filter((r) => r.analysis_type === "cross_asset");

  const matrix: Record<string, Record<string, number | null>> = {};
  for (const a of ASSETS) {
    matrix[a] = {};
    for (const b of ASSETS) {
      if (a === b) {
        matrix[a][b] = null; // self
      } else {
        // Key format: "btc_5m->eth_5m" — match either direction
        const row = correlations.find((r) => {
          if (!r.key.includes("->")) return false;
          const [src, tgt] = r.key.split("->");
          const srcAsset = src.split("_")[0];
          const tgtAsset = tgt.split("_")[0];
          const srcInterval = src.split("_")[1];
          return srcInterval === interval &&
            ((srcAsset === a && tgtAsset === b) || (srcAsset === b && tgtAsset === a));
        });
        const rate = row ? parseFloat(String(row.up_win_rate ?? row.value ?? "0")) : null;
        matrix[a][b] = rate !== null ? rate * 100 : null;
      }
    }
  }

  function cellColor(val: number | null): string {
    if (val === null) return "bg-zinc-800/30";
    if (val > 80) return "bg-emerald-500/20";
    if (val > 70) return "bg-emerald-500/10";
    if (val > 60) return "bg-yellow-500/10";
    return "bg-zinc-800/30";
  }

  return (
    <AnalysisSection
      title="Cross-Asset Correlation"
      description="When one asset resolves Up, how often does another also resolve Up in the same window?"
    >
      <GlassPanel variant="glow-wide">
        <div className="relative border-b border-zinc-800/60 px-6 py-3 flex items-center gap-2">
          {(["5m", "15m"] as const).map((iv) => (
            <button
              key={iv}
              onClick={() => setInterval(iv)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                interval === iv
                  ? "bg-primary/20 text-primary"
                  : "bg-zinc-800/60 text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {iv === "5m" ? "5 min" : "15 min"}
            </button>
          ))}
        </div>

        <div className="p-6 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500" />
                {ASSETS.map((a) => (
                  <th key={a} className="px-4 py-2.5 text-center text-xs font-semibold uppercase tracking-wider text-zinc-500">
                    {a.toUpperCase()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ASSETS.map((row) => (
                <tr key={row} className="border-b border-zinc-800/20">
                  <td className="px-4 py-3 text-xs font-semibold uppercase text-zinc-300">
                    {row.toUpperCase()}
                  </td>
                  {ASSETS.map((col) => {
                    const val = matrix[row][col];
                    return (
                      <td key={col} className={cn("px-4 py-3 text-center rounded", cellColor(val))}>
                        {val === null ? (
                          <span className="text-zinc-600">—</span>
                        ) : (
                          <span className={`font-mono text-sm font-semibold ${val > 70 ? "text-emerald-400" : val > 60 ? "text-yellow-400" : "text-zinc-300"}`}>
                            {val.toFixed(1)}%
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassPanel>
      <p className="mt-3 text-xs text-zinc-500">
        Percentage of windows where both assets resolved Up simultaneously. High correlation means assets move together.
      </p>
    </AnalysisSection>
  );
}

// ---------------------------------------------------------------------------
// Section 5 — Previous Market Influence
// ---------------------------------------------------------------------------

function PrevInfluenceSection({ data }: { data: SequentialRow[] }) {
  const [marketType, setMarketType] = useState<string>(MARKET_TYPES_8[0]);

  const rows = data.filter(
    (r) => r.analysis_type === "prev_influence" && r.market_type === marketType
  );

  function parseAvgPrice(notes: string | undefined): number | null {
    if (!notes) return null;
    const match = notes.match(/avg 30s price=([0-9.]+)/);
    return match ? parseFloat(match[1]) : null;
  }

  function interpretation(val: number): string {
    if (val > 0.55) return "Bullish carry-over";
    if (val > 0.52) return "Slightly bullish carry-over";
    if (val < 0.45) return "Bearish carry-over";
    if (val < 0.48) return "Slightly bearish carry-over";
    return "No significant effect";
  }

  return (
    <AnalysisSection
      title="Previous Market Influence"
      description="Does the previous market's outcome affect the next market's early price?"
    >
      <GlassPanel variant="subtle">
        {/* Market type filter bar */}
        <div className="relative border-b border-zinc-800/60 px-6 py-3 flex items-center gap-2 flex-wrap">
          {MARKET_TYPES_8.map((mt) => (
            <button
              key={mt}
              onClick={() => setMarketType(mt)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                marketType === mt
                  ? "bg-primary/20 text-primary"
                  : "bg-zinc-800/60 text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {MARKET_TYPE_LABELS[mt]}
            </button>
          ))}
        </div>

        {rows.length === 0 ? (
          <div className="p-8 text-center text-sm text-zinc-500">
            No previous-market influence data available.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-zinc-800/40">
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Previous Outcome</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Avg Price at 30s</th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">Samples</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">Interpretation</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const avgPrice = parseAvgPrice(r.notes ?? r.metadata);
                  const priceForInterpretation = avgPrice ?? r.value;
                  const interp = interpretation(priceForInterpretation);
                  const isBullish = interp.includes("Bullish");
                  const isBearish = interp.includes("Bearish");
                  return (
                    <tr key={i} className="border-b border-zinc-800/20 hover:bg-zinc-800/20 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className={`h-2 w-2 rounded-full ${r.key === "after_up" ? "bg-emerald-400" : "bg-red-400"}`} />
                          <span className="text-sm font-semibold text-zinc-200">
                            {r.key === "after_up" ? "Up" : "Down"}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-sm font-semibold tabular-nums text-zinc-200">
                          {avgPrice !== null ? `${(avgPrice * 100).toFixed(1)}¢` : "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className="font-mono text-xs text-zinc-400">{r.sample_count.toLocaleString("en-US")}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${
                          isBullish ? "text-emerald-400 bg-emerald-400/10"
                          : isBearish ? "text-red-400 bg-red-400/10"
                          : "text-zinc-400 bg-zinc-800/40"
                        }`}>
                          {interp}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </GlassPanel>
    </AnalysisSection>
  );
}

// ---------------------------------------------------------------------------
// Loading Skeleton
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Main Client Component
// ---------------------------------------------------------------------------

export function AnalysisClient({ data }: { data: AnalysisData & { run: AnalysisRun } }) {
  const { run, calibration, trajectory, timeofday, sequential, heatmap } = data;
  const stale = isStale(run.ran_at);

  return (
    <div className="min-h-screen flex flex-col overflow-x-hidden">
      <Navbar />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 md:px-6 py-6 md:py-10">
        {/* Back link */}
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors mb-4"
        >
          <svg className="h-3 w-3" viewBox="0 0 12 12" fill="currentColor">
            <path d="M8 2L4 6l4 4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back to Dashboard
        </Link>

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-zinc-100 mb-1">Lab Analysis</h1>
          <p className="text-sm text-zinc-400 mb-4">
            Statistical analysis of collected market data
          </p>

          {/* Overview cards — matches dashboard style */}
          <div className="relative grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-primary/20 bg-primary/[0.06] sm:grid-cols-4">
            <div className="absolute inset-x-0 top-0 z-10 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />

            <div className="group relative bg-zinc-950 p-4 md:p-6 transition-colors hover:bg-zinc-900/80 animate-slide-up">
              <div className="absolute -top-10 -right-10 h-20 w-20 rounded-full bg-primary/[0.05] blur-2xl" />
              <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.03] to-transparent" />
              <p className="relative text-xs font-semibold uppercase tracking-[0.15em] text-primary/60">Last Run</p>
              <p className="relative mt-2 font-mono text-2xl font-bold tabular-nums text-zinc-50">
                {formatDateOnly(run.ran_at)}
              </p>
            </div>

            <div className="group relative bg-zinc-950 p-4 md:p-6 transition-colors hover:bg-zinc-900/80 animate-slide-up" style={{ animationDelay: "80ms" }}>
              <div className="absolute -top-10 -right-10 h-20 w-20 rounded-full bg-primary/[0.05] blur-2xl" />
              <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.03] to-transparent" />
              <p className="relative text-xs font-semibold uppercase tracking-[0.15em] text-primary/60">Markets</p>
              <p className="relative mt-2 font-mono text-2xl font-bold tabular-nums text-zinc-50">
                {(run.markets_analyzed ?? 0).toLocaleString("en-US")}
              </p>
            </div>

            <div className="group relative bg-zinc-950 p-4 md:p-6 transition-colors hover:bg-zinc-900/80 animate-slide-up" style={{ animationDelay: "160ms" }}>
              <div className="absolute -top-10 -right-10 h-20 w-20 rounded-full bg-primary/[0.05] blur-2xl" />
              <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.03] to-transparent" />
              <p className="relative text-xs font-semibold uppercase tracking-[0.15em] text-primary/60">Edges Found</p>
              <p className="relative mt-2 font-mono text-2xl font-bold tabular-nums text-zinc-50">
                {calibration.filter((r) => {
                  const pv = parseFloat(String(r.p_value));
                  return pv < 0.15 && Number(r.sample_count) >= 5;
                }).length}
              </p>
            </div>

            <div className="group relative bg-zinc-950 p-4 md:p-6 transition-colors hover:bg-zinc-900/80 animate-slide-up" style={{ animationDelay: "240ms" }}>
              <div className="absolute -top-10 -right-10 h-20 w-20 rounded-full bg-primary/[0.05] blur-2xl" />
              <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.03] to-transparent" />
              <p className="relative text-xs font-semibold uppercase tracking-[0.15em] text-primary/60">Date Range</p>
              <p className="relative mt-2 font-mono text-2xl font-bold tabular-nums text-zinc-50">
                {run.date_range_start && run.date_range_end
                  ? `${formatDateOnly(run.date_range_start)} → ${formatDateOnly(run.date_range_end)}`
                  : "—"}
              </p>
            </div>
          </div>

          {stale && (
            <Badge className="mt-3 bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
              Analysis may be outdated
            </Badge>
          )}
        </div>

        {/* Sections */}
        <EdgeScannerSection data={calibration} />
        <CalibrationSection data={calibration} />

        {/* Calibration Heatmap — uses raw tick data like the old dashboard */}
        <AnalysisSection
          title="Calibration Heatmap"
          description="2D grid of actual win rate by price bucket and time into window — find where the edge is strongest"
        >
          <CalibrationHeatmap data={heatmap} />
        </AnalysisSection>

        {/* Win Rate by Price Bucket — derived from raw tick heatmap data */}
        {(() => {
          const TIME_WINDOWS_5M = [30, 60, 90, 120, 150, 180, 240, 300];
          const TIME_WINDOWS_15M = [30, 60, 90, 120, 150, 180, 240, 300];
          const allWindows = [...new Set([...TIME_WINDOWS_5M, ...TIME_WINDOWS_15M])];
          const dataBySeconds: Record<number, { market_type: string; price_bucket: string; sample_count: string; up_win_rate: string }[]> = {};
          for (const s of allWindows) {
            dataBySeconds[s] = heatmap
              .filter((r) => String(Number(r.time_offset)) === String(s))
              .map((r) => ({
                market_type: r.market_type,
                price_bucket: r.price_bucket,
                sample_count: r.sample_count,
                up_win_rate: r.up_win_rate,
              }));
          }
          return (
            <AnalysisSection
              title="Win Rate by Price Bucket"
              description="Actual Up win rate grouped by price bucket at different time windows"
            >
              <WinRateChart
                dataBySeconds={dataBySeconds}
                timeWindows5m={TIME_WINDOWS_5M}
                timeWindows15m={TIME_WINDOWS_15M}
              />
            </AnalysisSection>
          );
        })()}
        <TrajectorySection data={sequential} />
        <TimeofdaySection data={timeofday} />
        <CorrelationSection data={sequential} />
        <PrevInfluenceSection data={sequential} />
        <StreakDetectorLive />
        <StreakSection data={sequential} />

        {/* Footer */}
        <div className="mt-8 border-t border-zinc-800/40 pt-4 pb-8 text-center">
          <p className="text-xs text-zinc-600">
            Run ID: {run.id} — Ran at: {formatRunDate(run.ran_at)}
          </p>
        </div>
      </main>
    </div>
  );
}
