export function LoadingSpinner({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center gap-3">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-zinc-700 border-t-primary" />
      {label && <span className="text-sm text-zinc-400">{label}</span>}
    </div>
  );
}
