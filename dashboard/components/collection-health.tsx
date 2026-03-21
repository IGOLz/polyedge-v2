import { GlassPanel } from "@/components/ui/glass-panel";

const ASSET_NAMES: Record<string, string> = {
  btc: "Bitcoin",
  eth: "Ethereum",
  sol: "Solana",
  xrp: "XRP",
};

function assetLabel(marketType: string): string {
  const asset = marketType.split("_")[0];
  return ASSET_NAMES[asset] || asset.toUpperCase();
}

interface TickRate {
  marketType: string;
  last5m: number;
  last15m: number;
  last1h: number;
  last24h: number;
  collecting: boolean;
}

interface CollectionHealthProps {
  tickRates: TickRate[];
}

function getExpectedAndActual(rate: TickRate): { expected: number; actual: number; label: string } {
  if (rate.marketType.endsWith("_15m")) {
    const avg15m = Math.round(rate.last1h / 4);
    return { expected: 900, actual: avg15m, label: "avg 15m (1h)" };
  }
  const avg5m = Math.round(rate.last1h / 12);
  return { expected: 300, actual: avg5m, label: "avg 5m (1h)" };
}

function getHealthStatus(actual: number, expected: number) {
  if (expected === 0) return { label: "Unknown", color: "text-zinc-400", bg: "bg-zinc-600" };
  const ratio = actual / expected;
  if (ratio >= 0.9) return { label: "Healthy", color: "text-emerald-400", bg: "bg-emerald-400" };
  if (ratio >= 0.7) return { label: "Degraded", color: "text-yellow-400", bg: "bg-yellow-400" };
  return { label: "Critical", color: "text-red-400", bg: "bg-red-400" };
}

function intervalLabel(marketType: string): string {
  return marketType.split("_")[1] || "";
}

function HealthCard({ rate }: { rate: TickRate }) {
  const { expected, actual } = getExpectedAndActual(rate);
  const status = getHealthStatus(actual, expected);
  const pct = expected > 0 ? ((actual / expected) * 100).toFixed(0) : "—";

  return (
    <GlassPanel variant="glow-tl" className="p-6">
      <div className="relative">
        <div className="mb-4 flex items-center justify-between">
          <span className="text-base font-semibold tracking-tight text-zinc-100">
            {assetLabel(rate.marketType)}
          </span>
          <span className="rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary border border-primary/20">
            {intervalLabel(rate.marketType)}
          </span>
        </div>

        <div className="mt-5 space-y-2">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-1.5">
              <div className={`h-2 w-2 rounded-full ${status.bg}`} />
              <span className={`text-xs font-medium ${status.color}`}>
                {status.label}
              </span>
            </div>
            <span className="font-mono text-sm font-semibold tabular-nums text-zinc-200">
              {actual} / {expected}
            </span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-zinc-800">
            <div
              className={`h-full rounded-full transition-all ${status.bg}`}
              style={{ width: `${Math.min(parseFloat(pct) || 0, 100)}%` }}
            />
          </div>
          <p className="text-right text-xs text-zinc-400">{pct}% of expected</p>
        </div>
      </div>
    </GlassPanel>
  );
}

export function CollectionHealth({ tickRates }: CollectionHealthProps) {
  if (tickRates.length === 0) {
    return (
      <GlassPanel variant="glow-tl" className="p-8 text-center text-sm text-zinc-500">
        Not enough data yet
      </GlassPanel>
    );
  }

  const rates5m = tickRates.filter((r) => r.marketType.endsWith("_5m"));
  const rates15m = tickRates.filter((r) => r.marketType.endsWith("_15m"));

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {[...rates5m, ...rates15m].map((rate) => (
        <HealthCard key={rate.marketType} rate={rate} />
      ))}
    </div>
  );
}
