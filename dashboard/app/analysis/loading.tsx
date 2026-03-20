import { Navbar } from "@/components/navbar";
import { Skeleton } from "@/components/ui/skeleton";

export default function AnalysisLoading() {
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 md:px-6 py-6 md:py-10">
        <Skeleton className="h-8 w-48 mb-2" />
        <Skeleton className="h-4 w-80 mb-6" />
        <Skeleton className="h-10 w-full mb-8" />
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="mb-10">
            <Skeleton className="h-6 w-56 mb-4" />
            <Skeleton className="h-64 w-full" />
          </div>
        ))}
      </main>
    </div>
  );
}
