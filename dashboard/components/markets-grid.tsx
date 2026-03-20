import Link from "next/link";
import { getMarketsByType } from "@/lib/queries";
import { parseMarketType } from "@/lib/formatters";

const ASSET_NAMES: Record<string, string> = {
  BTC: "Bitcoin",
  ETH: "Ethereum",
  SOL: "Solana",
  XRP: "XRP",
};

type MarketData = Awaited<ReturnType<typeof getMarketsByType>>[number];

function MarketCard({ market, index }: { market: MarketData; index: number }) {
  const { asset, interval } = parseMarketType(market.marketType);

  return (
    <Link
      href={`/markets?type=${market.marketType}`}
      className="group relative overflow-hidden rounded-xl border border-primary/20 bg-zinc-950 p-4 md:p-6 transition-all duration-300 hover:border-primary/40 hover:bg-zinc-900/80 animate-slide-up cursor-pointer"
      style={{ animationDelay: `${index * 60}ms` }}
    >
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />
      <div className="absolute -bottom-10 -right-10 h-28 w-28 rounded-full bg-primary/[0.05] blur-3xl pointer-events-none" />
      <div className="absolute inset-0 bg-gradient-to-t from-primary/[0.02] to-transparent pointer-events-none" />

      <div className="relative flex items-center justify-between">
        <span className="text-base font-semibold tracking-tight text-zinc-100">
          {ASSET_NAMES[asset] || asset}
        </span>
        <span className="rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary border border-primary/20">
          {interval}
        </span>
      </div>

      <div className="relative mt-5 flex items-center gap-6">
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-400">
            Win Rate 24h
          </p>
          <p className={`mt-0.5 font-mono text-sm font-semibold tabular-nums ${
            market.resolved24h > 0
              ? market.upWinRate24h >= 50 ? "text-emerald-400" : "text-red-400"
              : "text-zinc-200"
          }`}>
            {market.resolved24h > 0 ? `${market.upWinRate24h.toFixed(1)}%` : "—"}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-400">
            Total Markets
          </p>
          <p className="mt-0.5 font-mono text-sm font-semibold tabular-nums text-zinc-200">
            {market.resolved.toLocaleString("en-US")}
          </p>
        </div>
      </div>
    </Link>
  );
}

export async function MarketsGrid() {
  const markets = await getMarketsByType();

  const markets5m = markets.filter((m) => m.marketType.endsWith("_5m"));
  const markets15m = markets.filter((m) => m.marketType.endsWith("_15m"));

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {[...markets5m, ...markets15m].map((market, i) => (
        <MarketCard key={market.marketType} market={market} index={i} />
      ))}
    </div>
  );
}

export function MarketsGridSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl border border-zinc-800/60 bg-zinc-900/50 p-6"
        >
          <div className="flex items-center justify-between">
            <div className="h-7 w-24 animate-pulse rounded bg-zinc-800" />
            <div className="h-5 w-8 animate-pulse rounded-md bg-zinc-800" />
          </div>
          <div className="mt-5 flex items-center gap-6">
            <div>
              <div className="h-2.5 w-16 animate-pulse rounded bg-zinc-800" />
              <div className="mt-1.5 h-4 w-12 animate-pulse rounded bg-zinc-800" />
            </div>
            <div>
              <div className="h-2.5 w-20 animate-pulse rounded bg-zinc-800" />
              <div className="mt-1.5 h-4 w-10 animate-pulse rounded bg-zinc-800" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
