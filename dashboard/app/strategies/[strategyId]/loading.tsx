import { Navbar } from "@/components/navbar";
import { Skeleton } from "@/components/ui/skeleton";

export default function StrategyDetailLoading() {
  return (
    <div className="min-h-screen flex flex-col overflow-x-hidden">
      <Navbar />

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-6 md:py-10">
        {/* Back link */}
        <Skeleton className="h-4 w-36" />

        {/* Header card */}
        <div className="mt-5 rounded-3xl border border-zinc-800/60 bg-zinc-950/80 p-6 backdrop-blur-xl md:p-8">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div className="space-y-4">
              <div className="flex gap-2">
                <Skeleton className="h-6 w-16 rounded-full" />
                <Skeleton className="h-6 w-24 rounded-full" />
              </div>
              <Skeleton className="h-9 w-64" />
              <Skeleton className="h-4 w-96 max-w-full" />
            </div>
            <Skeleton className="h-20 w-48 rounded-2xl" />
          </div>
        </div>

        {/* Performance Overview */}
        <div className="mt-8">
          <div className="mb-5 flex items-center gap-3">
            <Skeleton className="h-6 w-48" />
            <div className="h-px flex-1 bg-gradient-to-r from-zinc-700/60 to-transparent" />
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="rounded-xl border border-primary/20 bg-zinc-950 p-5">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="mt-3 h-8 w-24" />
              </div>
            ))}
          </div>
        </div>

        {/* Strategy Notes + Current Parameters */}
        <div className="mt-8 grid gap-5 xl:grid-cols-[1.3fr_0.7fr]">
          <div className="rounded-xl border border-primary/20 bg-zinc-950 p-6 md:p-7">
            <Skeleton className="h-4 w-32" />
            <div className="mt-5 grid grid-cols-2 gap-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="rounded-2xl border border-zinc-800/70 bg-zinc-900/55 p-4">
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="mt-2 h-6 w-16" />
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-primary/20 bg-zinc-950 p-6 md:p-7">
            <Skeleton className="h-4 w-40" />
            <div className="mt-5 grid grid-cols-2 gap-3">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div key={i} className="rounded-2xl border border-zinc-800/70 bg-zinc-900/55 p-3">
                  <Skeleton className="h-3 w-20" />
                  <Skeleton className="mt-1.5 h-5 w-12" />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Data Visualizations */}
        <div className="mt-8">
          <div className="mb-5 flex items-center gap-3">
            <Skeleton className="h-6 w-44" />
            <div className="h-px flex-1 bg-gradient-to-r from-zinc-700/60 to-transparent" />
          </div>
          <div className="grid gap-5 xl:grid-cols-2">
            <div className="rounded-xl border border-primary/20 bg-zinc-950 p-6">
              <Skeleton className="h-4 w-36 mb-4" />
              <Skeleton className="h-64 w-full rounded-xl" />
            </div>
            <div className="rounded-xl border border-primary/20 bg-zinc-950 p-6">
              <Skeleton className="h-4 w-36 mb-4" />
              <Skeleton className="h-64 w-full rounded-xl" />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
