import Link from "next/link";
import { unstable_cache } from "next/cache";
import { getStrategiesOverview } from "@/lib/strategies-overview-queries";
import { SectionHeader } from "@/components/section-header";

const getCachedStrategiesOverview = unstable_cache(
  async () => {
    try {
      return await getStrategiesOverview();
    } catch {
      return { strategies: [] };
    }
  },
  ["strategies-overview"],
  { revalidate: 14400 }
);

export async function StrategiesOverview() {
  const { strategies } = await getCachedStrategiesOverview();

  const hasAnyData = strategies.some((s) => s.total_pnl !== null);

  return (
    <section className="mt-8 md:mt-14">
      <SectionHeader title="Strategy Performance" />

      {!hasAnyData ? (
        <div className="rounded-xl border border-zinc-800/60 bg-zinc-950 p-8 text-center">
          <p className="text-sm text-muted-foreground">
            Strategy backtests run automatically every 4 hours. Check back soon.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {strategies.map((s, i) => {
            const hasData = s.total_pnl !== null;
            const isPositive = hasData && s.total_pnl! > 0;
            const isNegative = hasData && s.total_pnl! < 0;

            const borderColor = isPositive
              ? "border-green-500/20"
              : isNegative
                ? "border-red-500/20"
                : "border-primary/20";

            return (
              <div
                key={s.strategy}
                className={`group relative overflow-hidden rounded-xl border ${borderColor} bg-zinc-950 p-4 md:p-6 transition-all duration-300 animate-slide-up`}
                style={{ animationDelay: `${i * 60}ms` }}
              >
                <div
                  className={`absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent ${
                    isPositive
                      ? "via-green-500/40"
                      : isNegative
                        ? "via-red-500/40"
                        : "via-primary/40"
                  } to-transparent`}
                />
                <div className="absolute -bottom-10 -right-10 h-28 w-28 rounded-full bg-primary/[0.05] blur-3xl pointer-events-none" />
                <div className="absolute inset-0 bg-gradient-to-t from-primary/[0.02] to-transparent pointer-events-none" />

                {/* Header */}
                <div className="relative flex items-center gap-2">
                  <span className="rounded-md bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary border border-primary/20">
                    {s.strategy}
                  </span>
                  <Link
                    href={s.href}
                    className="text-base font-semibold tracking-tight text-zinc-100 truncate hover:text-primary transition-colors"
                  >
                    {s.name}
                  </Link>
                </div>

                {/* Main metric */}
                <div className="relative mt-4">
                  {hasData ? (
                    <p
                      className={`font-mono text-2xl font-bold tabular-nums ${
                        isPositive ? "text-emerald-400" : isNegative ? "text-red-400" : "text-zinc-200"
                      }`}
                    >
                      {isNegative ? "-" : ""}${Math.abs(s.total_pnl!).toFixed(2)}
                    </p>
                  ) : (
                    <p className="text-sm text-muted-foreground">No data yet</p>
                  )}
                </div>

                {/* Stats row */}
                {hasData && (
                  <div className="relative mt-4 flex items-center gap-4">
                    <div>
                      <p className="text-xs uppercase tracking-wider text-zinc-400">ROI</p>
                      <p
                        className={`mt-0.5 font-mono text-sm font-semibold tabular-nums ${
                          s.roi! > 0 ? "text-emerald-400" : s.roi! < 0 ? "text-red-400" : "text-zinc-200"
                        }`}
                      >
                        {(s.roi! * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wider text-zinc-400">Win Rate</p>
                      <p className="mt-0.5 font-mono text-sm font-semibold tabular-nums text-zinc-200">
                        {(s.win_rate! * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wider text-zinc-400">Trades</p>
                      <p className="mt-0.5 font-mono text-sm font-semibold tabular-nums text-zinc-200">
                        {s.trades_taken}
                      </p>
                    </div>
                  </div>
                )}

                {/* Footer link */}
                <div className="relative mt-4 pt-3 border-t border-zinc-800/60">
                  <Link
                    href={s.href}
                    className="text-xs font-medium text-zinc-400 transition-colors hover:text-primary"
                  >
                    View Strategy →
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

export function StrategiesOverviewSkeleton() {
  return (
    <section className="mt-8 md:mt-14">
      <div className="mb-5">
        <div className="flex items-center gap-3">
          <div className="h-3 w-40 animate-pulse rounded bg-zinc-800" />
          <div className="h-px flex-1 bg-gradient-to-r from-zinc-800/60 to-transparent" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-zinc-800/60 bg-zinc-900/50 p-4 md:p-6"
          >
            <div className="flex items-center gap-2">
              <div className="h-5 w-8 animate-pulse rounded-md bg-zinc-800" />
              <div className="h-5 w-20 animate-pulse rounded bg-zinc-800" />
            </div>
            <div className="mt-4 h-8 w-24 animate-pulse rounded bg-zinc-800" />
            <div className="mt-4 flex items-center gap-4">
              <div className="h-8 w-14 animate-pulse rounded bg-zinc-800" />
              <div className="h-8 w-14 animate-pulse rounded bg-zinc-800" />
              <div className="h-8 w-10 animate-pulse rounded bg-zinc-800" />
            </div>
            <div className="mt-4 pt-3 border-t border-zinc-800/60">
              <div className="h-3 w-24 animate-pulse rounded bg-zinc-800" />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
