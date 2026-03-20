import { unstable_cache } from "next/cache";
import Link from "next/link";
import { Navbar } from "@/components/navbar";
import { Footer } from "@/components/footer";
import { SectionHeader } from "@/components/section-header";
import { GlassPanel } from "@/components/ui/glass-panel";
import { getFarmingData, type FarmingResult, type FarmingRun } from "@/lib/farming-queries";
import { StrategyCharts, TopConfigurationsTable } from "./strategy-charts";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

const getCachedFarmingData = unstable_cache(
  async () => {
    try {
      return await getFarmingData();
    } catch {
      return { run: null, results: [] };
    }
  },
  ["farming-data"],
  { revalidate: 14400 }
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDateOnly(dateStr: string): string {
  const d = new Date(dateStr);
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

function pnlColor(val: number): string {
  return val > 0 ? "text-emerald-400" : val < 0 ? "text-red-400" : "text-zinc-400";
}

function formatPnl(val: number): string {
  const prefix = val >= 0 ? "$" : "-$";
  return `${prefix}${Math.abs(val).toFixed(2)}`;
}

function formatCents(val: number): string {
  return `${(val * 100).toFixed(0)}¢`;
}

// ---------------------------------------------------------------------------
// Section 1 — Strategy Explanation
// ---------------------------------------------------------------------------

function StrategyExplanation() {
  return (
    <section className="mb-8 md:mb-14">
      <SectionHeader title="What is Probability Farming?" />
      <GlassPanel variant="glow-tl">
        <div className="relative p-6 space-y-6">
          <div>
            <h3 className="mb-2 text-sm font-semibold text-primary/80">The Idea</h3>
            <p className="text-sm leading-relaxed text-zinc-300">
              This strategy targets 15-minute crypto prediction markets on Polymarket. Instead of entering at the start of a market window, it waits. Once either side (Up or Down) reaches a high probability zone — for example 85¢ — it enters a position on that side and holds until resolution.
            </p>
            <p className="mt-2 text-sm leading-relaxed text-zinc-300">
              The logic: a contract priced at 85¢ implies an 85% chance of winning. If the market is correctly calibrated, entering late at high probability should produce consistent small gains.
            </p>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-semibold text-primary/80">The Parameters</h3>
            <p className="text-sm leading-relaxed text-zinc-300">
              Three values control the strategy. The <span className="text-zinc-100 font-medium">Trigger Point</span> is the price threshold that activates a trade — for example 0.85 means enter when either Up or Down reaches 85¢. The <span className="text-zinc-100 font-medium">Exit Point</span> is the stop-loss — if the price reverses against the position and drops to this level, the trade is closed early to cap the loss. The <span className="text-zinc-100 font-medium">Trigger Minute</span> is the minimum time that must pass before the bot starts watching for an entry — earlier entries have more time for reversals, later entries have less opportunity to find the exact price.
            </p>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-semibold text-primary/80">The Risk</h3>
            <p className="text-sm leading-relaxed text-zinc-300">
              The main risk is reversal. A contract can reach 85¢ and then drop all the way to 0¢ if the underlying asset price moves sharply. The stop-loss (Exit Point) partially manages this by cutting losses early, but in fast markets it may not fill at the exact price.
            </p>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-semibold text-primary/80">What This Page Shows</h3>
            <p className="text-sm leading-relaxed text-zinc-300">
              The backtest below runs all combinations of these three parameters plus a minimum coin delta filter (minimum price movement from the window open before entering) against all historical 15-minute markets collected. The goal is to find which parameter combinations produce positive returns after fees. Fees are calculated at 2% per trade. Results with fewer than 20 trades are excluded from rankings.
            </p>
          </div>

          <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 px-4 py-3">
            <p className="text-xs text-yellow-400/90">
              ⚠️ Backtest results use historical data from a single market period. Results may not reflect future performance. Always test with small amounts.
            </p>
          </div>
        </div>
      </GlassPanel>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section 2 — Run Metadata
// ---------------------------------------------------------------------------

function RunMetadata({ run }: { run: FarmingRun }) {
  return (
    <div className="mb-8">
      <div className="relative grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-primary/20 bg-primary/[0.06] sm:grid-cols-4">
        <div className="absolute inset-x-0 top-0 z-10 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />

        <div className="group relative bg-zinc-950 p-4 md:p-6 transition-colors hover:bg-zinc-900/80 animate-slide-up">
          <div className="absolute -top-10 -right-10 h-20 w-20 rounded-full bg-primary/[0.05] blur-2xl" />
          <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.03] to-transparent" />
          <p className="relative text-xs font-semibold uppercase tracking-[0.15em] text-primary/60">Last Run</p>
          <p className="relative mt-2 font-mono text-2xl font-bold tabular-nums text-zinc-50">
            {formatDateOnly(run.ran_at)}
          </p>
        </div>

        <div className="group relative bg-zinc-950 p-4 md:p-6 transition-colors hover:bg-zinc-900/80 animate-slide-up" style={{ animationDelay: "80ms" }}>
          <div className="absolute -top-10 -right-10 h-20 w-20 rounded-full bg-primary/[0.05] blur-2xl" />
          <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.03] to-transparent" />
          <p className="relative text-xs font-semibold uppercase tracking-[0.15em] text-primary/60">Markets</p>
          <p className="relative mt-2 font-mono text-2xl font-bold tabular-nums text-zinc-50">
            {(run.markets_tested ?? 0).toLocaleString("en-US")}
          </p>
        </div>

        <div className="group relative bg-zinc-950 p-4 md:p-6 transition-colors hover:bg-zinc-900/80 animate-slide-up" style={{ animationDelay: "160ms" }}>
          <div className="absolute -top-10 -right-10 h-20 w-20 rounded-full bg-primary/[0.05] blur-2xl" />
          <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.03] to-transparent" />
          <p className="relative text-xs font-semibold uppercase tracking-[0.15em] text-primary/60">Bet Size</p>
          <p className="relative mt-2 font-mono text-2xl font-bold tabular-nums text-zinc-50">
            $10
          </p>
        </div>

        <div className="group relative bg-zinc-950 p-4 md:p-6 transition-colors hover:bg-zinc-900/80 animate-slide-up" style={{ animationDelay: "240ms" }}>
          <div className="absolute -top-10 -right-10 h-20 w-20 rounded-full bg-primary/[0.05] blur-2xl" />
          <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.03] to-transparent" />
          <p className="relative text-xs font-semibold uppercase tracking-[0.15em] text-primary/60">Date Range</p>
          <p className="relative mt-2 font-mono text-2xl font-bold tabular-nums text-zinc-50">
            {run.date_range_start && run.date_range_end
              ? `${formatDateOnly(run.date_range_start)} → ${formatDateOnly(run.date_range_end)}`
              : "—"}
          </p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 3 — Best Configuration
// ---------------------------------------------------------------------------

function BestConfiguration({ results }: { results: FarmingResult[] }) {
  const eligible = results.filter((r) => r.trades_taken >= 20);
  if (eligible.length === 0) {
    return (
      <section className="mb-8 md:mb-14">
        <SectionHeader title="Best Configuration" description="The single parameter combination with highest total PnL across all 15m markets, minimum 20 trades." />
        <p className="text-sm text-zinc-500">Not enough data to determine a best configuration yet.</p>
      </section>
    );
  }

  const best = eligible.reduce((a, b) => (a.total_pnl > b.total_pnl ? a : b));

  const winRatePct = best.win_rate * 100;

  const statCards = [
    { label: "Total PnL", value: formatPnl(best.total_pnl), color: pnlColor(best.total_pnl), large: true },
    { label: "ROI", value: `${(best.roi * 100).toFixed(1)}%`, color: pnlColor(best.roi), large: true },
    { label: "Win Rate", value: `${winRatePct.toFixed(1)}%`, color: "text-zinc-50", large: true },
    { label: "Total Trades", value: best.trades_taken.toLocaleString("en-US"), color: "text-zinc-50", large: true },
    { label: "Wins", value: best.wins.toLocaleString("en-US"), color: "text-emerald-400", large: false },
    { label: "Stop Losses", value: best.stop_losses.toLocaleString("en-US"), color: "text-yellow-400", large: false },
    { label: "Avg Entry Price", value: formatCents(best.avg_entry_price), color: "text-zinc-50", large: false },
    { label: "Avg Coin Delta", value: best.avg_coin_delta.toFixed(3), color: "text-zinc-50", large: false },
  ];

  return (
    <section className="mb-8 md:mb-14">
      <SectionHeader title="Best Configuration" description="The single parameter combination with highest total PnL across all 15m markets, minimum 20 trades." />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        {statCards.map((card) => (
          <GlassPanel key={card.label} variant="subtle" className={card.large ? "" : "col-span-1"}>
            <div className="relative p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-primary/60">{card.label}</p>
              <p className={cn(
                "mt-1.5 font-mono tabular-nums font-bold",
                card.large ? "text-2xl" : "text-lg",
                card.color
              )}>
                {card.value}
              </p>
            </div>
          </GlassPanel>
        ))}
      </div>

    </section>
  );
}

// Section 4 is in strategy-charts.tsx (client component for expand/collapse)

// ---------------------------------------------------------------------------
// No-data empty state
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 md:px-6 flex items-center justify-center">
        <div className="text-center">
          <div className="mb-4 text-4xl text-zinc-600">🌾</div>
          <h2 className="text-lg font-semibold text-zinc-200 mb-2">No backtest data yet</h2>
          <p className="text-sm text-zinc-500 max-w-md">
            The analysis runs automatically every 4 hours. Check back soon.
          </p>
        </div>
      </main>
      <Footer />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default async function StrategyPage() {
  const data = await getCachedFarmingData();

  if (!data.run) {
    return <EmptyState />;
  }

  const { run, results } = data;

  return (
    <div className="min-h-screen flex flex-col overflow-x-hidden">
      <Navbar />

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 md:px-6 py-6 md:py-10">
        {/* Back link */}
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors mb-4"
        >
          <svg className="h-3 w-3" viewBox="0 0 12 12" fill="currentColor">
            <path d="M8 2L4 6l4 4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back to Dashboard
        </Link>

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-zinc-100 mb-1">Farming Strategy</h1>
          <p className="text-sm text-zinc-400 mb-4">
            Probability farming backtest results across all parameter combinations
          </p>
        </div>

        {/* Section 1 — Strategy explanation */}
        <StrategyExplanation />

        {/* Section 2 — Run metadata */}
        <RunMetadata run={run} />

        {/* Section 3 — Best configuration */}
        <BestConfiguration results={results} />

        {/* Section 4 — Top configurations table (client for expand/collapse) */}
        <TopConfigurationsTable results={results} />

        {/* Sections 5, 6, 7 — Client components (charts) */}
        <StrategyCharts results={results} />
      </main>

      <Footer />
    </div>
  );
}
