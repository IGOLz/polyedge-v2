export const dynamic = 'force-dynamic';

import { Suspense } from "react";
import { Navbar } from "@/components/navbar";
import { Hero } from "@/components/hero";
import { Footer } from "@/components/footer";
import { OverviewCards, OverviewCardsSkeleton } from "@/components/overview-cards";
import { MarketsGrid, MarketsGridSkeleton } from "@/components/markets-grid";
import { AnalyticsSections, AnalyticsSkeleton } from "@/components/analytics-sections";
import { StrategiesOverview, StrategiesOverviewSkeleton } from "@/components/strategies-overview";
import { SectionHeader } from "@/components/section-header";
import { REVALIDATE_SECONDS } from "@/lib/constants";

export const revalidate = REVALIDATE_SECONDS;

export default function Dashboard() {
  return (
    <div className="min-h-screen flex flex-col overflow-x-hidden">
      <Navbar />

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 md:px-6 py-6 md:py-10">
        <Hero />

        <section className="mb-8 md:mb-14">
          <Suspense fallback={<OverviewCardsSkeleton />}>
            <OverviewCards />
          </Suspense>
        </section>

        <Suspense fallback={<StrategiesOverviewSkeleton />}>
          <StrategiesOverview />
        </Suspense>

        <section className="mt-8 md:mt-14">
          <SectionHeader title="Markets" />
          <Suspense fallback={<MarketsGridSkeleton />}>
            <MarketsGrid />
          </Suspense>
        </section>

        <Suspense fallback={<AnalyticsSkeleton />}>
          <AnalyticsSections />
        </Suspense>
      </main>

      <Footer />
    </div>
  );
}
