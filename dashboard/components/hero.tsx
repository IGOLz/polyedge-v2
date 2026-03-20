export function Hero() {
  return (
    <div className="mb-8 md:mb-14 flex flex-col items-center text-center">
      <div className="relative mb-4">
        <div className="absolute -inset-4 rounded-full bg-primary/10 blur-2xl" />
        <div className="relative h-3 w-3 rounded-full bg-primary shadow-lg shadow-primary/40 animate-pulse" />
      </div>
      <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
        PolyEdge
      </h1>
      <p className="mt-1.5 text-sm text-zinc-500">
        Polymarket prediction analytics
      </p>
    </div>
  );
}
