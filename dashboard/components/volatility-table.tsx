import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

interface VolatilityRow {
  market_type: string;
  avg_price_range: string;
  max_range: string;
  min_range: string;
  sample_count: string;
}

interface VolatilityTableProps {
  data: VolatilityRow[];
}

export function VolatilityTable({ data }: VolatilityTableProps) {
  if (data.length === 0) {
    return (
      <Card className="p-8 text-center text-sm text-zinc-500">
        Not enough data yet
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Market Type</TableHead>
            <TableHead className="text-right">Avg Price Range</TableHead>
            <TableHead className="text-right">Max Range</TableHead>
            <TableHead className="text-right">Min Range</TableHead>
            <TableHead className="text-right">Sample Count</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((row) => (
            <TableRow key={row.market_type}>
              <TableCell>
                <Badge>{row.market_type}</Badge>
              </TableCell>
              <TableCell className="text-right font-mono text-xs text-zinc-300">
                {(parseFloat(row.avg_price_range) * 100).toFixed(2)}%
              </TableCell>
              <TableCell className="text-right font-mono text-xs text-zinc-400">
                {(parseFloat(row.max_range) * 100).toFixed(2)}%
              </TableCell>
              <TableCell className="text-right font-mono text-xs text-zinc-400">
                {(parseFloat(row.min_range) * 100).toFixed(2)}%
              </TableCell>
              <TableCell className="text-right font-mono text-xs text-zinc-400">
                {parseInt(row.sample_count).toLocaleString("en-US")}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
