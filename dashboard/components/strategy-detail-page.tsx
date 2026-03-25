import Link from "next/link";
import { ArrowLeft, Clock3 } from "lucide-react";

import { Footer } from "@/components/footer";
import { Navbar } from "@/components/navbar";
import { SectionHeader } from "@/components/section-header";
import { SectionInfoButton, type SectionInfo } from "@/components/section-info-modal";
import { StrategyDetailCharts } from "@/components/strategy-detail-charts";
import { GlassPanel } from "@/components/ui/glass-panel";
import type { StrategyDetail } from "@/lib/strategy-artifacts";
import { cn } from "@/lib/utils";

const STRATEGY_NOTES_INFO: SectionInfo = {
  title: "Strategy Notes",
  sections: [
    {
      heading: "What is this?",
      content:
        "Strategy Notes summarize the optimization run that produced this strategy's current parameters. The numbers are pulled directly from the latest result artifacts on disk.",
    },
    {
      heading: "How to read it",
      content: "Each stat box shows a key metric from the optimization run:",
      bullets: [
        "Configurations tested — Total number of parameter combinations evaluated during the grid search",
        "With trades — How many of those configurations generated at least one trade (configurations with zero trades are excluded from ranking)",
        "Profitable — Number of configurations that ended with a positive total PnL",
        "Unprofitable — Number of configurations that ended with a negative total PnL",
      ],
    },
    {
      heading: "Why it matters",
      content:
        "A strategy where only a small fraction of tested configurations are profitable may be fragile — the winning parameters could be the result of overfitting. Conversely, a strategy where a large share of configurations are profitable suggests a robust edge that isn't overly sensitive to exact parameter choices.",
    },
  ],
};

const CURRENT_PARAMETERS_INFO: SectionInfo = {
  title: "Current Parameters",
  sections: [
    {
      heading: "What is this?",
      content:
        "The active parameter set that the strategy uses for live trading or the latest backtest. These values were selected as the best-performing combination from the most recent optimization run.",
    },
    {
      heading: "How to read it",
      content: "Each card shows one parameter and its current value:",
      bullets: [
        "Feature Window — Number of seconds of price history used to compute input features",
        "Entry Window Start / End — The time range (in seconds from market open) during which the strategy is allowed to enter a trade",
        "Min Market Delta Abs — Minimum absolute price movement from market open required before an entry is considered",
        "Max Underlying Return Abs — Maximum allowed underlying asset return; filters out extreme moves that distort signals",
        "Extreme Price Low / High — Price boundaries outside which the strategy will not enter (avoids very cheap or very expensive contracts)",
        "Require Direction Mismatch — When True, the strategy only enters when its signal disagrees with the current market direction",
      ],
    },
    {
      heading: "Default Drift",
      content:
        "If present, the Default Drift subsection shows how far each current parameter has moved from its default or baseline value. Large drift may indicate the optimizer found an edge in an unusual part of the parameter space.",
    },
    {
      heading: "Bootstrap Check",
      content:
        "If present, the Bootstrap Check shows statistical confidence metrics: Positive Probability is the percentage of bootstrap resamples that produced a positive PnL, and Mean P&L is the average PnL across all resamples. Higher positive probability indicates greater statistical confidence that the strategy's edge is real.",
    },
  ],
};

function formatTimestamp(value: string | null) {
  if (!value) {
    return "Unknown";
  }

  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
}

function metricToneClass(tone: "positive" | "negative" | "neutral") {
  if (tone === "positive") {
    return "text-emerald-400";
  }
  if (tone === "negative") {
    return "text-red-400";
  }
  return "text-zinc-100";
}

export function StrategyDetailPage({ detail }: { detail: StrategyDetail }) {
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
                  {detail.strategyId}
                </span>
                <span className="rounded-full border border-zinc-800 bg-zinc-900/70 px-3 py-1 text-xs font-medium text-zinc-300">
                  {detail.statusLabel}
                </span>
              </div>
              <h1 className="mt-4 text-3xl font-semibold tracking-tight text-zinc-50">
                {detail.displayName}
              </h1>
              {detail.description && (
                <p className="mt-3 max-w-3xl text-sm leading-7 text-zinc-400">
                  {detail.description}
                </p>
              )}
            </div>

            <div className="rounded-2xl border border-zinc-800/70 bg-zinc-900/70 px-4 py-3 text-sm text-zinc-300">
              <div className="flex items-center gap-2 text-zinc-400">
                <Clock3 className="h-4 w-4" />
                Latest artifact
              </div>
              <p className="mt-2 font-medium text-zinc-100">{formatTimestamp(detail.lastUpdatedAt)}</p>
              <p className="mt-1 text-xs uppercase tracking-[0.18em] text-zinc-500">
                {detail.latestSourceLabel}
              </p>
            </div>
          </div>
        </header>

        <section className="mt-8">
          <SectionHeader title="Performance Overview" />
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            {detail.summaryMetrics.map((metric) => (
              <GlassPanel key={metric.key} variant="subtle">
                <div className="p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary/65">
                    {metric.label}
                  </p>
                  <p className={cn("mt-3 font-mono text-2xl font-bold", metricToneClass(metric.tone))}>
                    {metric.displayValue}
                  </p>
                </div>
              </GlassPanel>
            ))}
          </div>
        </section>

        <section className="mt-8 grid gap-5 xl:grid-cols-[1.3fr_0.7fr]">
          <GlassPanel variant="glow-wide">
            <div className="p-6 md:p-7">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-primary/65">
                  Current Parameters
                </h2>
                <SectionInfoButton sectionTitle="Current Parameters" info={CURRENT_PARAMETERS_INFO} />
              </div>
              <div className="mt-5 grid grid-cols-2 gap-3">
                {detail.parameterChips.map((chip) => (
                  <div
                    key={chip.key}
                    className="rounded-2xl border border-zinc-800/70 bg-zinc-900/55 p-3"
                  >
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
                      {chip.label}
                    </p>
                    <p className="mt-1.5 font-mono text-base text-zinc-100">{chip.value}</p>
                  </div>
                ))}
                {detail.parameterChips.length === 0 && (
                  <p className="col-span-2 text-sm text-zinc-500">No parameter metadata was found for this strategy.</p>
                )}
              </div>

              {detail.defaultDrift.length > 0 && (
                <div className="mt-6 border-t border-zinc-800/70 pt-5">
                  <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                    Default Drift
                  </h3>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    {detail.defaultDrift.slice(0, 6).map((chip) => (
                      <div key={chip.key} className="rounded-2xl border border-zinc-800/70 bg-zinc-900/70 p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">{chip.label}</p>
                        <p className="mt-1.5 font-mono text-base text-zinc-100">{chip.value}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {detail.bootstrapSummary && (
                <div className="mt-6 border-t border-zinc-800/70 pt-5">
                  <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                    Bootstrap Check
                  </h3>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <div className="rounded-2xl border border-zinc-800/70 bg-zinc-900/70 p-3">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">Positive probability</p>
                      <p className="mt-1.5 font-mono text-lg text-zinc-100">
                        {detail.bootstrapSummary.probabilityPositivePct?.toFixed(1) ?? "—"}%
                      </p>
                    </div>
                    <div className="rounded-2xl border border-zinc-800/70 bg-zinc-900/70 p-3">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">Mean P&L</p>
                      <p className="mt-1.5 font-mono text-lg text-zinc-100">
                        {detail.bootstrapSummary.meanTotalPnl == null
                          ? "—"
                          : `${detail.bootstrapSummary.meanTotalPnl < 0 ? "-" : ""}$${Math.abs(
                              detail.bootstrapSummary.meanTotalPnl
                            ).toFixed(2)}`}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </GlassPanel>

          <GlassPanel variant="glow-tl">
            <div className="p-6 md:p-7">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-primary/65">
                  Strategy Notes
                </h2>
                <SectionInfoButton sectionTitle="Strategy Notes" info={STRATEGY_NOTES_INFO} />
              </div>
              {detail.sourceSummary.length > 0 ? (
                <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-2">
                  {detail.sourceSummary
                    .filter((line) => line.includes(":"))
                    .map((line) => {
                      const idx = line.indexOf(":");
                      const label = line.slice(0, idx).trim();
                      const value = line.slice(idx + 1).trim();
                      return (
                        <div key={line} className="rounded-2xl border border-zinc-800/70 bg-zinc-900/55 p-4">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
                            {label}
                          </p>
                          <p className="mt-2 font-mono text-lg text-zinc-100">{value}</p>
                        </div>
                      );
                    })}
                </div>
              ) : (
                <p className="mt-4 text-sm leading-7 text-zinc-400">
                  Latest detail view is being built directly from the current result artifacts on disk.
                </p>
              )}
              {detail.sourceSummary.filter((line) => !line.includes(":")).length > 0 && (
                <div className="mt-4 space-y-1">
                  {detail.sourceSummary
                    .filter((line) => !line.includes(":"))
                    .map((line) => (
                      <p key={line} className="text-xs text-zinc-500">{line}</p>
                    ))}
                </div>
              )}
            </div>
          </GlassPanel>
        </section>

        <section className="mt-8">
          <SectionHeader title="Data Visualizations" />
          <StrategyDetailCharts detail={detail} />
        </section>
      </main>

      <Footer />
    </div>
  );
}
