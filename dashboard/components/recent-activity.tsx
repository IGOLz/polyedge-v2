import { getRecentActivity } from "@/lib/queries";
import { shortenId, formatISOTime } from "@/lib/formatters";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card } from "@/components/ui/card";

export async function RecentActivity() {
  const rows = await getRecentActivity();

  return (
    <Card className="overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="border-zinc-800/60 hover:bg-transparent">
            <TableHead>Market</TableHead>
            <TableHead>ID</TableHead>
            <TableHead>Window</TableHead>
            <TableHead>Outcome</TableHead>
            <TableHead className="text-right">Up Price</TableHead>
            <TableHead className="text-right">Ticks</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.market_id} className="group">
              <TableCell>
                <Badge>{row.market_type}</Badge>
              </TableCell>
              <TableCell className="font-mono text-sm text-zinc-500 group-hover:text-zinc-400 transition-colors">
                {shortenId(row.market_id)}
              </TableCell>
              <TableCell className="font-mono text-sm tabular-nums text-zinc-400">
                {formatISOTime(row.started_at)} — {formatISOTime(row.ended_at)}
              </TableCell>
              <TableCell>
                <Badge variant={row.final_outcome === "Up" ? "up" : "down"}>
                  {row.final_outcome}
                </Badge>
              </TableCell>
              <TableCell className="text-right font-mono text-sm tabular-nums text-zinc-300">
                {parseFloat(row.final_up_price).toFixed(4)}
              </TableCell>
              <TableCell className="text-right font-mono text-sm tabular-nums text-zinc-400">
                {parseInt(row.tick_count).toLocaleString("en-US")}
              </TableCell>
            </TableRow>
          ))}
          {rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={6} className="py-12 text-center text-zinc-500">
                No resolved markets yet
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </Card>
  );
}

export function RecentActivitySkeleton() {
  return (
    <Card className="overflow-hidden">
      <div className="p-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="flex gap-4 py-3 border-b border-zinc-800/50 last:border-0"
          >
            <div className="h-5 w-16 animate-pulse rounded bg-zinc-800" />
            <div className="h-5 w-20 animate-pulse rounded bg-zinc-800" />
            <div className="h-5 w-12 animate-pulse rounded bg-zinc-800" />
            <div className="h-5 w-12 animate-pulse rounded bg-zinc-800" />
            <div className="h-5 w-12 animate-pulse rounded bg-zinc-800" />
            <div className="ml-auto h-5 w-14 animate-pulse rounded bg-zinc-800" />
          </div>
        ))}
      </div>
    </Card>
  );
}
