"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { GlassPanel } from "@/components/ui/glass-panel";
import type {
  StrategyConfigComparisonPoint,
  StrategyDetail,
  StrategyNeighborPoint,
  StrategySeriesPoint,
  StrategySweepPoint,
} from "@/lib/strategy-artifacts";

function formatPnl(value: number | null) {
  if (value == null) {
    return "—";
  }
  return `${value < 0 ? "-" : ""}$${Math.abs(value).toFixed(2)}`;
}

function ChartPanel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <GlassPanel variant="subtle">
      <div className="p-5">
        <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-primary/65">
          {title}
        </h3>
        <div className="mt-4 h-[280px]">{children}</div>
      </div>
    </GlassPanel>
  );
}

function SeriesTooltip() {
  return (
    <Tooltip
      contentStyle={{
        border: "1px solid rgba(63, 63, 70, 0.8)",
        background: "rgba(9, 9, 11, 0.95)",
        borderRadius: 12,
      }}
      formatter={(value: number, name: string) => {
        if (name.toLowerCase().includes("pnl")) {
          return [formatPnl(value), "P&L"];
        }
        if (name.toLowerCase().includes("win")) {
          return [`${value.toFixed(1)}%`, "Win Rate"];
        }
        return [value.toFixed(2), name];
      }}
    />
  );
}

function hasSeriesPoints(points: Array<{ totalPnl: number | null }>) {
  return points.some((point) => point.totalPnl != null);
}

function TopConfigurationsChart({ points }: { points: StrategyConfigComparisonPoint[] }) {
  const chartData = points.filter((point) => point.totalPnl != null);
  if (chartData.length < 2) {
    return null;
  }

  return (
    <ChartPanel title="Top Configuration Comparison">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData}>
          <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fill: "#71717a", fontSize: 11 }} tickLine={false} axisLine={false} />
          <YAxis
            yAxisId="pnl"
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value: number) => `$${value}`}
          />
          <YAxis
            yAxisId="winRate"
            orientation="right"
            tick={{ fill: "#52525b", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value: number) => `${value.toFixed(0)}%`}
          />
          <SeriesTooltip />
          <ReferenceLine yAxisId="pnl" y={0} stroke="#3f3f46" strokeDasharray="4 4" />
          <Bar yAxisId="pnl" dataKey="totalPnl" fill="rgba(228, 246, 0, 0.55)" radius={[8, 8, 0, 0]} />
          <Line yAxisId="winRate" dataKey="winRate" stroke="#4ade80" strokeWidth={2.5} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartPanel>
  );
}

function WinRateScatterChart({ points }: { points: StrategyConfigComparisonPoint[] }) {
  const chartData = points.filter((point) => point.totalPnl != null && point.winRate != null);
  if (chartData.length < 2) {
    return null;
  }

  return (
    <ChartPanel title="Win Rate vs P&L">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 20, right: 20, bottom: 10, left: 0 }}>
          <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="winRate"
            name="winRate"
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickFormatter={(value: number) => `${value.toFixed(0)}%`}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="number"
            dataKey="totalPnl"
            name="totalPnl"
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickFormatter={(value: number) => `$${value}`}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            contentStyle={{
              border: "1px solid rgba(63, 63, 70, 0.8)",
              background: "rgba(9, 9, 11, 0.95)",
              borderRadius: 12,
            }}
            formatter={(value: number, name: string) => {
              if (name === "winRate") {
                return [`${value.toFixed(1)}%`, "Win Rate"];
              }
              return [formatPnl(value), "P&L"];
            }}
          />
          <ReferenceLine y={0} stroke="#3f3f46" strokeDasharray="4 4" />
          <Scatter data={chartData} fill="hsl(var(--primary))" />
        </ScatterChart>
      </ResponsiveContainer>
    </ChartPanel>
  );
}

function SeriesBarChart({
  title,
  points,
  secondaryLabel,
}: {
  title: string;
  points: StrategySeriesPoint[];
  secondaryLabel?: string;
}) {
  const chartData = points.filter((point) => point.totalPnl != null);
  if (chartData.length < 1) {
    return null;
  }

  return (
    <ChartPanel title={title}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData}>
          <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fill: "#71717a", fontSize: 11 }} tickLine={false} axisLine={false} />
          <YAxis
            yAxisId="pnl"
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value: number) => `$${value}`}
          />
          {chartData.some((point) => point.winRate != null) && (
            <YAxis
              yAxisId="secondary"
              orientation="right"
              tick={{ fill: "#52525b", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value: number) =>
                secondaryLabel === "Profit Factor" ? value.toFixed(1) : `${value.toFixed(0)}%`
              }
            />
          )}
          <SeriesTooltip />
          <ReferenceLine yAxisId="pnl" y={0} stroke="#3f3f46" strokeDasharray="4 4" />
          <Bar yAxisId="pnl" dataKey="totalPnl" fill="rgba(228, 246, 0, 0.55)" radius={[8, 8, 0, 0]} />
          {chartData.some((point) => point.secondaryValue != null) && (
            <Line
              yAxisId="secondary"
              dataKey="secondaryValue"
              stroke="#60a5fa"
              strokeWidth={2.4}
              dot={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </ChartPanel>
  );
}

function SweepChart({ title, points }: { title: string; points: StrategySweepPoint[] }) {
  const chartData = points.filter((point) => point.totalPnl != null);
  if (chartData.length < 2) {
    return null;
  }

  return (
    <ChartPanel title={title}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData}>
          <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fill: "#71717a", fontSize: 11 }} tickLine={false} axisLine={false} />
          <YAxis
            yAxisId="pnl"
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value: number) => `$${value}`}
          />
          <YAxis
            yAxisId="winRate"
            orientation="right"
            tick={{ fill: "#52525b", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value: number) => `${value.toFixed(0)}%`}
          />
          <SeriesTooltip />
          <ReferenceLine yAxisId="pnl" y={0} stroke="#3f3f46" strokeDasharray="4 4" />
          <Line yAxisId="pnl" dataKey="totalPnl" stroke="hsl(var(--primary))" strokeWidth={2.5} />
          <Line yAxisId="winRate" dataKey="winRate" stroke="#4ade80" strokeWidth={2.2} />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartPanel>
  );
}

function NeighborImpactChart({ points }: { points: StrategyNeighborPoint[] }) {
  const chartData = points
    .filter((point) => point.deltaTotalPnl != null)
    .map((point) => ({
      label: point.parameter,
      deltaTotalPnl: point.deltaTotalPnl,
    }))
    .slice(0, 8);

  if (chartData.length < 1) {
    return null;
  }

  return (
    <ChartPanel title="Parameter Neighbor Impact">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} layout="vertical" margin={{ left: 30 }}>
          <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
          <XAxis
            type="number"
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value: number) => `$${value}`}
          />
          <YAxis
            type="category"
            dataKey="label"
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={120}
          />
          <Tooltip
            contentStyle={{
              border: "1px solid rgba(63, 63, 70, 0.8)",
              background: "rgba(9, 9, 11, 0.95)",
              borderRadius: 12,
            }}
            formatter={(value: number) => [formatPnl(value), "Delta P&L"]}
          />
          <ReferenceLine x={0} stroke="#3f3f46" strokeDasharray="4 4" />
          <Bar dataKey="deltaTotalPnl" fill="rgba(96, 165, 250, 0.65)" radius={[0, 8, 8, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartPanel>
  );
}

export function StrategyDetailCharts({ detail }: { detail: StrategyDetail }) {
  const panels = [
    TopConfigurationsChart({ points: detail.topConfigurations }),
    WinRateScatterChart({ points: detail.topConfigurations }),
    hasSeriesPoints(detail.chronologicalFolds)
      ? SeriesBarChart({
          title: "Chronological Fold Performance",
          points: detail.chronologicalFolds,
          secondaryLabel: "Profit Factor",
        })
      : null,
    hasSeriesPoints(detail.assetBreakdown)
      ? SeriesBarChart({
          title: "Validation by Asset",
          points: detail.assetBreakdown,
          secondaryLabel: "Profit Factor",
        })
      : null,
    hasSeriesPoints(detail.durationBreakdown)
      ? SeriesBarChart({
          title: "Validation by Duration",
          points: detail.durationBreakdown,
          secondaryLabel: "Profit Factor",
        })
      : null,
    hasSeriesPoints(detail.dayBreakdown)
      ? SeriesBarChart({
          title: "Daily P&L",
          points: detail.dayBreakdown,
          secondaryLabel: "Profit Factor",
        })
      : null,
    hasSeriesPoints(detail.quarterlyPerformance)
      ? SeriesBarChart({
          title: "Quarterly / Period P&L",
          points: detail.quarterlyPerformance,
        })
      : null,
    SweepChart({ title: "Slippage Sensitivity", points: detail.slippageSweep }),
    SweepChart({ title: "Entry Delay Sensitivity", points: detail.entryDelaySweep }),
    NeighborImpactChart({ points: detail.parameterNeighbors }),
  ].filter(Boolean);

  if (panels.length === 0) {
    return null;
  }

  return <div className="grid gap-5 lg:grid-cols-2">{panels}</div>;
}
