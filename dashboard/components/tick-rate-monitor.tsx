"use client";

import type { TickRate } from "@/types/market";
import { usePollingFetch } from "@/hooks/use-polling-fetch";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const COLUMNS = [
  { label: "Market Type", align: "left" as const },
  { label: "5 min", align: "right" as const },
  { label: "1 hour", align: "right" as const },
  { label: "24 hours", align: "right" as const },
  { label: "Status", align: "right" as const },
];

function TickRateSkeleton() {
  return (
    <Card className="overflow-hidden">
      <div className="p-6">
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex gap-4">
              <div className="h-5 w-16 animate-pulse rounded bg-zinc-800" />
              <div className="h-5 w-12 animate-pulse rounded bg-zinc-800" />
              <div className="h-5 w-12 animate-pulse rounded bg-zinc-800" />
              <div className="h-5 w-12 animate-pulse rounded bg-zinc-800" />
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

export function TickRateMonitor() {
  const { data: rates, loading, lastUpdated } = usePollingFetch<TickRate[]>("/api/tick-rate");

  if (loading) return <TickRateSkeleton />;

  const filteredRates = rates?.filter((rate) => rate.marketType) ?? [];

  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800/60">
              {COLUMNS.map((col) => (
                <th
                  key={col.label}
                  className={`px-4 py-3 text-${col.align} text-xs font-semibold uppercase tracking-wider text-zinc-500`}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredRates.map((rate) => (
              <tr
                key={rate.marketType}
                className="group border-b border-zinc-800/30 transition-colors hover:bg-zinc-800/20"
              >
                <td className="px-4 py-2.5">
                  <Badge>{rate.marketType}</Badge>
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-zinc-400 group-hover:text-zinc-200 transition-colors">
                  {rate.last5m.toLocaleString("en-US")}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-zinc-400 group-hover:text-zinc-200 transition-colors">
                  {rate.last1h.toLocaleString("en-US")}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-zinc-400 group-hover:text-zinc-200 transition-colors">
                  {rate.last24h.toLocaleString("en-US")}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <Badge variant={rate.collecting ? "up" : "down"}>
                    {rate.collecting ? "Active" : "Stopped"}
                  </Badge>
                </td>
              </tr>
            ))}
            {filteredRates.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center text-zinc-500">
                  No tick data available
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {lastUpdated && (
        <div className="border-t border-zinc-800/30 px-4 py-2.5 flex items-center justify-between">
          <p className="text-xs text-zinc-500">Updated {lastUpdated} UTC</p>
          <p className="text-xs text-zinc-500">Auto-refresh 60s</p>
        </div>
      )}
    </Card>
  );
}
