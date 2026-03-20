export function Footer() {
  return (
    <footer className="border-t border-zinc-800/30 py-6">
      <div className="mx-auto max-w-7xl px-4 md:px-6 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-1.5 rounded-full bg-primary/40" />
          <span className="text-xs font-medium text-zinc-500">PolyEdge</span>
        </div>
        <span className="text-xs text-zinc-500">Data refreshes every 60s</span>
      </div>
    </footer>
  );
}
