import { getOverviewStats } from "@/lib/queries";
import { formatCompactNumber } from "@/lib/formatters";

export async function OverviewCards() {
  const stats = await getOverviewStats();

  const cards = [
    {
      label: "Markets",
      value: stats.totalMarkets.toLocaleString("en-US"),
    },
    {
      label: "Ticks",
      value: formatCompactNumber(stats.totalTicks),
    },
    {
      label: "Days Active",
      value: Math.round(stats.hoursCollected / 24).toString(),
    },
    {
      label: "Since",
      value: stats.startDate
        ? new Date(stats.startDate).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            timeZone: "UTC",
          })
        : "—",
    },
  ];

  return (
    <div className="relative grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-primary/20 bg-primary/[0.06] sm:grid-cols-4">
      <div className="absolute inset-x-0 top-0 z-10 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />

      {cards.map((card, i) => (
        <div
          key={card.label}
          className="group relative bg-zinc-950 p-4 md:p-6 transition-colors hover:bg-zinc-900/80 animate-slide-up"
          style={{ animationDelay: `${i * 80}ms` }}
        >
          <div className="absolute -top-10 -right-10 h-20 w-20 rounded-full bg-primary/[0.05] blur-2xl" />
          <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.03] to-transparent" />
          <p className="relative text-xs font-semibold uppercase tracking-[0.15em] text-primary/60">
            {card.label}
          </p>
          <p className="relative mt-2 font-mono text-2xl font-bold tabular-nums text-zinc-50">
            {card.value}
          </p>
        </div>
      ))}
    </div>
  );
}

export function OverviewCardsSkeleton() {
  return (
    <div className="relative grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-primary/20 bg-primary/[0.06] sm:grid-cols-4">
      <div className="absolute inset-x-0 top-0 z-10 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="bg-zinc-950 p-6">
          <div className="h-2.5 w-16 animate-pulse rounded bg-zinc-800" />
          <div className="mt-3 h-8 w-20 animate-pulse rounded bg-zinc-800" />
        </div>
      ))}
    </div>
  );
}
