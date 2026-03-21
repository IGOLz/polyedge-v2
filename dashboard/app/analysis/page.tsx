import { unstable_cache } from "next/cache";
import { Navbar } from "@/components/navbar";
import { getAnalysisData } from "@/lib/queries";
import { AnalysisClient } from "./analysis-client";

export const dynamic = "force-dynamic";

const getCachedAnalysisData = unstable_cache(
  async () => {
    try {
      return await getAnalysisData();
    } catch {
      return { run: null };
    }
  },
  ["analysis-data"],
  { revalidate: 14400 }
);

export default async function AnalysisPage() {
  const data = await getCachedAnalysisData();

  if (!data.run) {
    return (
      <div className="min-h-screen flex flex-col">
        <Navbar />
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 md:px-6 flex items-center justify-center">
          <div className="text-center">
            <div className="mb-4 text-4xl text-zinc-600">&#x2697;&#xFE0F;</div>
            <h2 className="text-lg font-semibold text-zinc-200 mb-2">No analysis runs yet</h2>
            <p className="text-sm text-zinc-500 max-w-md">
              Run <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-primary">python run_analysis.py</code> in polyedge-lab to generate data.
            </p>
          </div>
        </main>
      </div>
    );
  }

  return <AnalysisClient data={data as typeof data & { run: NonNullable<typeof data.run> }} />;
}
