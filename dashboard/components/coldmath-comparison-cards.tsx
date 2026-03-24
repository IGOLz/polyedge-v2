import { GlassPanel } from "@/components/ui/glass-panel";
import type { BotColdmathStats, TrackedUserStats } from "@/lib/wallet-tracker-queries";
import { cn } from "@/lib/utils";

function formatCurrency(value: number) {
  return `${value < 0 ? "-" : ""}$${Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatSignedCurrency(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatCurrency(value)}`;
}

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
}

function BotCard({ stats }: { stats: BotColdmathStats }) {
  const pnlPositive = stats.realizedPnl > 0;
  const pnlNegative = stats.realizedPnl < 0;

  return (
    <GlassPanel variant="glow-tl">
      <div className="flex h-full flex-col p-6 md:p-7">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-primary">
            Our Bot
          </span>
          <span className="rounded-full border border-zinc-800 bg-zinc-900/70 px-3 py-1 text-xs font-medium text-zinc-400">
            Weather Merge
          </span>
        </div>

        <div className="mt-5 rounded-3xl border border-zinc-800/70 bg-zinc-900/55 p-5">
          <p className="text-sm text-zinc-400">Realized P&L</p>
          <p className={cn(
            "mt-2 font-mono text-4xl font-bold tracking-tight",
            pnlPositive && "text-emerald-400",
            pnlNegative && "text-red-400",
            !pnlPositive && !pnlNegative && "text-zinc-100",
          )}>
            {formatSignedCurrency(stats.realizedPnl)}
          </p>
          <p className="mt-3 text-sm leading-7 text-zinc-300">
            {stats.closedPositions} closed out of {stats.totalPositions} total positions.
          </p>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {[
            { label: "Invested", value: formatCurrency(stats.totalEntryCost) },
            { label: "Open", value: stats.openPositions.toLocaleString("en-US") },
            { label: "Avg P&L", value: formatSignedCurrency(stats.avgPnlPerPosition), tone: stats.avgPnlPerPosition > 0 ? "text-emerald-400" : stats.avgPnlPerPosition < 0 ? "text-red-400" : "text-zinc-100" },
            { label: "Merged", value: formatCurrency(stats.totalMergedUsdc) },
            { label: "Redeemed", value: formatCurrency(stats.totalRedeemedUsdc) },
            { label: "Unwind", value: formatCurrency(stats.totalUnwindUsdc) },
          ].map((item) => (
            <div key={item.label} className="rounded-2xl border border-zinc-800/70 bg-zinc-900/70 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
                {item.label}
              </p>
              <p className={cn("mt-2 font-mono text-lg", item.tone ?? "text-zinc-100")}>
                {item.value}
              </p>
            </div>
          ))}
        </div>

        <div className="mt-auto pt-4 text-xs text-zinc-500">
          First: {formatDate(stats.firstTradeAt)} — Last: {formatDate(stats.lastTradeAt)}
        </div>
      </div>
    </GlassPanel>
  );
}

function TrackedUserCard({ stats }: { stats: TrackedUserStats }) {
  const pnlPositive = stats.netPnl > 0;
  const pnlNegative = stats.netPnl < 0;

  const totalReturns = stats.totalSold + stats.totalMergedUsdc + stats.totalRedeemedUsdc;

  return (
    <GlassPanel variant="glow-tr">
      <div className="flex h-full flex-col p-6 md:p-7">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-primary">
            @{stats.profileName}
          </span>
          <span className="rounded-full border border-zinc-800 bg-zinc-900/70 px-3 py-1 text-xs font-medium text-zinc-400">
            Tracked User
          </span>
        </div>

        <div className="mt-5 rounded-3xl border border-zinc-800/70 bg-zinc-900/55 p-5">
          <p className="text-sm text-zinc-400">Net P&L since tracking</p>
          <p className={cn(
            "mt-2 font-mono text-4xl font-bold tracking-tight",
            pnlPositive && "text-emerald-400",
            pnlNegative && "text-red-400",
            !pnlPositive && !pnlNegative && "text-zinc-100",
          )}>
            {formatSignedCurrency(stats.netPnl)}
          </p>
          <p className="mt-3 text-sm leading-7 text-zinc-300">
            Spent {formatCurrency(stats.totalSpent)} — returned {formatCurrency(totalReturns)}
          </p>
        </div>

        <div className="mt-5 grid grid-cols-3 gap-3">
          {[
            { label: "Buys", value: stats.totalBuys.toLocaleString("en-US"), tone: "text-zinc-100" },
            { label: "Sells", value: stats.totalSells.toLocaleString("en-US"), tone: "text-zinc-100" },
            { label: "Merges", value: stats.totalMerges.toLocaleString("en-US"), tone: "text-zinc-100" },
          ].map((item) => (
            <div key={item.label} className="rounded-2xl border border-zinc-800/70 bg-zinc-900/70 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
                {item.label}
              </p>
              <p className={cn("mt-2 font-mono text-lg", item.tone)}>{item.value}</p>
            </div>
          ))}
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {[
            { label: "Redeems", value: stats.totalRedeems.toLocaleString("en-US") },
            { label: "Markets", value: stats.distinctMarkets.toLocaleString("en-US") },
            { label: "Avg Trade", value: formatCurrency(stats.avgTradeSize) },
          ].map((item) => (
            <div key={item.label} className="rounded-2xl border border-zinc-800/70 bg-zinc-900/70 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
                {item.label}
              </p>
              <p className="mt-2 font-mono text-lg text-zinc-100">{item.value}</p>
            </div>
          ))}
        </div>

        <div className="mt-auto pt-4 text-xs text-zinc-500">
          {formatDate(stats.firstActivityAt)} — {formatDate(stats.lastActivityAt)}
          {stats.trackingSince && (
            <span> · Tracking since {formatDate(stats.trackingSince)}</span>
          )}
        </div>
      </div>
    </GlassPanel>
  );
}

interface ColdmathComparisonCardsProps {
  bot: BotColdmathStats | null;
  trackedUser: TrackedUserStats | null;
}

export function ColdmathComparisonCards({ bot, trackedUser }: ColdmathComparisonCardsProps) {
  if (!bot && !trackedUser) {
    return null;
  }

  return (
    <div className="grid items-stretch gap-5 md:grid-cols-2">
      {bot ? (
        <BotCard stats={bot} />
      ) : (
        <GlassPanel variant="subtle">
          <div className="flex h-full items-center justify-center p-10">
            <p className="text-sm text-zinc-500">No bot trading data yet</p>
          </div>
        </GlassPanel>
      )}
      {trackedUser ? (
        <TrackedUserCard stats={trackedUser} />
      ) : (
        <GlassPanel variant="subtle">
          <div className="flex h-full items-center justify-center p-10">
            <p className="text-sm text-zinc-500">No tracked user data yet</p>
          </div>
        </GlassPanel>
      )}
    </div>
  );
}
