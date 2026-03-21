"use client";

import { useState } from "react";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

interface CalibrationRow {
  market_type: string;
  price_bucket: string;
  sample_count: string;
  up_win_rate: string;
}

interface CalibrationTableProps {
  data: CalibrationRow[];
}

export function CalibrationTable({ data }: CalibrationTableProps) {
  const marketTypes = [...new Set(data.map((d) => d.market_type))];
  const [activeTab, setActiveTab] = useState(marketTypes[0] || "");

  const filtered = data.filter(
    (d) => d.market_type === activeTab && parseInt(d.sample_count) >= 5
  );

  if (data.length === 0) {
    return (
      <Card className="p-8 text-center text-sm text-zinc-500">
        Not enough data yet
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      {/* Tabs */}
      <div className="flex gap-0 border-b border-zinc-800/60 overflow-x-auto">
        {marketTypes.map((type) => (
          <button
            key={type}
            onClick={() => setActiveTab(type)}
            className={`px-4 py-2.5 text-xs font-medium uppercase tracking-wider transition-colors whitespace-nowrap ${
              activeTab === type
                ? "text-primary border-b-2 border-primary bg-zinc-800/30"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {type}
          </button>
        ))}
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <div className="p-8 text-center text-sm text-zinc-500">
          Not enough data yet (minimum 5 samples per bucket)
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Price Bucket</TableHead>
              <TableHead className="text-right">Sample Count</TableHead>
              <TableHead className="text-right">Up Win Rate</TableHead>
              <TableHead className="text-right">Deviation</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((row) => {
              const bucket = parseFloat(row.price_bucket) * 100;
              const winRate = parseFloat(row.up_win_rate);
              const deviation = winRate - bucket;
              const deviationStr =
                deviation >= 0 ? `+${deviation.toFixed(1)}%` : `${deviation.toFixed(1)}%`;

              let colorClass = "text-zinc-400";
              if (deviation > 5) colorClass = "text-emerald-400";
              else if (deviation < -5) colorClass = "text-red-400";

              return (
                <TableRow key={row.price_bucket}>
                  <TableCell className="font-mono text-xs text-zinc-300">
                    {(parseFloat(row.price_bucket) * 100).toFixed(0)}%
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs text-zinc-400">
                    {parseInt(row.sample_count).toLocaleString("en-US")}
                  </TableCell>
                  <TableCell className={`text-right font-mono text-xs ${colorClass}`}>
                    {winRate.toFixed(1)}%
                  </TableCell>
                  <TableCell className={`text-right font-mono text-xs ${colorClass}`}>
                    {deviationStr}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}

      <div className="border-t border-zinc-800/30 px-4 py-2.5">
        <p className="text-xs text-zinc-500">
          Based on price at 60 seconds into window. Updates every 5 minutes.
        </p>
      </div>
    </Card>
  );
}
