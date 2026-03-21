"use client";

import { useEffect, useState } from "react";
import { StreakDetector } from "@/components/streak-detector";
import { SectionHeader } from "@/components/section-header";
import { Skeleton } from "@/components/ui/skeleton";

interface StreakData {
  marketType: string;
  streakLength: number;
  streakDirection: string;
  lastTen: string[];
}

export function StreakDetectorLive() {
  const [data, setData] = useState<StreakData[] | null>(null);

  useEffect(() => {
    fetch("/api/streaks")
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData([]));
  }, []);

  return (
    <section className="mt-8 md:mt-14">
      <SectionHeader
        title="Streak Detector"
        description="Current consecutive outcome streaks per market"
        exportData={data ?? undefined}
      />
      {data === null ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full rounded-xl" />
          ))}
        </div>
      ) : (
        <StreakDetector data={data} />
      )}
    </section>
  );
}
