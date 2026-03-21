"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { BotActivityPoint } from "@/lib/bot-dashboard-data";

function formatPnl(value: number) {
  return `${value < 0 ? "-" : ""}$${Math.abs(value).toFixed(2)}`;
}

function ActivePnlDot(props: unknown) {
  const { cx, cy, stroke } = (props ?? {}) as {
    cx?: number;
    cy?: number;
    stroke?: string;
  };

  if (typeof cx !== "number" || typeof cy !== "number") {
    return <g />;
  }

  return <circle cx={cx} cy={cy} r={5} fill={stroke ?? "hsl(var(--primary))"} stroke="#09090b" strokeWidth={2} />;
}

export function DashboardActivityChart({ data }: { data: BotActivityPoint[] }) {
  if (data.length === 0) {
    return (
      <div className="flex h-[220px] items-center justify-center text-sm text-zinc-500">
        No last-24-hour trade activity yet.
      </div>
    );
  }

  return (
    <div className="h-[220px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
          <XAxis
            dataKey="hour"
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            yAxisId="pnl"
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value: number) => `$${value}`}
          />
          <YAxis
            yAxisId="trades"
            orientation="right"
            tick={{ fill: "#52525b", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
          />
          <Tooltip
            cursor={{ stroke: "#52525b", strokeDasharray: "4 4" }}
            contentStyle={{
              border: "1px solid rgba(63, 63, 70, 0.8)",
              background: "rgba(9, 9, 11, 0.95)",
              borderRadius: 12,
            }}
            formatter={(value: number, name: string) => {
              if (name === "pnl") {
                return [formatPnl(value), "P&L"];
              }
              if (name === "wins") {
                return [value, "Take Profit"];
              }
              return [value, "Resolved Trades"];
            }}
            labelFormatter={(label) => `${label}:00 UTC`}
          />
          <ReferenceLine yAxisId="pnl" y={0} stroke="#3f3f46" strokeDasharray="4 4" />
          <Bar yAxisId="trades" dataKey="trades" fill="rgba(113, 113, 122, 0.28)" radius={[6, 6, 0, 0]} />
          <Line
            yAxisId="pnl"
            type="monotone"
            dataKey="pnl"
            stroke="hsl(var(--primary))"
            strokeWidth={2.5}
            isAnimationActive={false}
            dot={false}
            activeDot={ActivePnlDot}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
