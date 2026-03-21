import { getTickRates } from "@/lib/queries";
import { SectionHeader } from "@/components/section-header";
import { CollectionHealth } from "@/components/collection-health";

export async function AnalyticsSections() {
  const tickRates = await getTickRates();

  return (
    <>
      {/* Collection Health */}
      <section className="mt-8 md:mt-14">
        <SectionHeader
          title="Collection Health"
          description="Tick collection rate compared to expected throughput"
          exportData={tickRates}
        />
        <CollectionHealth tickRates={tickRates} />
      </section>
    </>
  );
}

export function AnalyticsSkeleton() {
  return (
    <section className="mt-8 md:mt-14">
      <div className="mb-5">
        <div className="flex items-center gap-3">
          <div className="h-3 w-32 animate-pulse rounded bg-zinc-800" />
          <div className="h-px flex-1 bg-gradient-to-r from-zinc-800/60 to-transparent" />
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="rounded-xl border border-zinc-800/60 bg-zinc-900/50 p-6">
            <div className="flex items-center justify-between">
              <div className="h-7 w-24 animate-pulse rounded bg-zinc-800" />
              <div className="h-5 w-8 animate-pulse rounded-md bg-zinc-800" />
            </div>
            <div className="mt-5 space-y-2">
              <div className="h-4 w-20 animate-pulse rounded bg-zinc-800" />
              <div className="h-1.5 w-full animate-pulse rounded-full bg-zinc-800" />
              <div className="h-3 w-16 animate-pulse rounded bg-zinc-800 ml-auto" />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
