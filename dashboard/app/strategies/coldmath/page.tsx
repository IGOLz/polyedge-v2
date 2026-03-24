export const dynamic = "force-dynamic";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { ColdmathComparisonCards } from "@/components/coldmath-comparison-cards";
import { Footer } from "@/components/footer";
import { Navbar } from "@/components/navbar";
import { SectionHeader } from "@/components/section-header";
import { GlassPanel } from "@/components/ui/glass-panel";
import { getColdmathComparisonData } from "@/lib/wallet-tracker-queries";

export default async function ColdmathStrategyPage() {
  const comparison = await getColdmathComparisonData();

  const botActive = comparison.bot && comparison.bot.totalPositions > 0;
  const userActive = comparison.trackedUser && comparison.trackedUser.totalActivities > 0;

  return (
    <div className="min-h-screen flex flex-col overflow-x-hidden">
      <Navbar />

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-6 md:py-10">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-xs font-medium text-zinc-500 transition-colors hover:text-zinc-200"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to dashboard
        </Link>

        <header className="mt-5 rounded-3xl border border-zinc-800/60 bg-zinc-950/80 p-6 backdrop-blur-xl md:p-8">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                  ColdMath
                </span>
                <span className="rounded-full border border-zinc-800 bg-zinc-900/70 px-3 py-1 text-xs font-medium text-zinc-300">
                  Copy-Trading
                </span>
              </div>
              <h1 className="mt-4 text-3xl font-semibold tracking-tight text-zinc-50">
                Weather Merge Strategy
              </h1>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-zinc-400">
                Inventory rebalancing merge strategy derived from analyzing @ColdMath&apos;s
                public on-chain activity on Polymarket weather markets. The bot buys both YES
                and NO sides, then merges the paired shares to capture the spread.
              </p>
            </div>

            <div className="rounded-2xl border border-zinc-800/70 bg-zinc-900/70 px-4 py-3 text-sm text-zinc-300">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                Tracker Status
              </p>
              <p className="mt-2 font-medium text-zinc-100">
                {botActive ? "Bot active" : "Bot idle"}
                {" / "}
                {userActive ? "User tracked" : "Awaiting data"}
              </p>
            </div>
          </div>
        </header>

        <section className="mt-8">
          <SectionHeader
            title="Live Copy-Trading Comparison"
            description="Bot performance vs. tracked user activity"
          />
          <ColdmathComparisonCards bot={comparison.bot} trackedUser={comparison.trackedUser} />
        </section>

        {comparison.bot && (
          <section className="mt-8">
            <SectionHeader title="Bot Details" />
            <div className="grid gap-4 md:grid-cols-3">
              <GlassPanel variant="subtle">
                <div className="p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">Strategy</p>
                  <p className="mt-2 text-sm font-medium text-zinc-200">coldmath_inventory_rebalancing_merge_v2</p>
                </div>
              </GlassPanel>
              <GlassPanel variant="subtle">
                <div className="p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">Mechanism</p>
                  <p className="mt-2 text-sm font-medium text-zinc-200">Buy YES + NO, merge paired shares</p>
                </div>
              </GlassPanel>
              <GlassPanel variant="subtle">
                <div className="p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">Market Type</p>
                  <p className="mt-2 text-sm font-medium text-zinc-200">Weather temperature predictions</p>
                </div>
              </GlassPanel>
            </div>
          </section>
        )}
      </main>

      <Footer />
    </div>
  );
}
