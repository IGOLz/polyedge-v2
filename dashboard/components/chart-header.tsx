import { DownloadButton } from "./download-button";

interface ChartHeaderProps {
  title: string;
  interval: string;
  startTime: string;
  endTime: string;
  tickCount?: number;
  onExport?: () => void;
  children?: React.ReactNode;
}

export function ChartHeader({
  title,
  interval,
  startTime,
  endTime,
  tickCount,
  onExport,
  children,
}: ChartHeaderProps) {
  return (
    <div className="flex items-start justify-between">
      <div>
        <div className="flex items-center gap-2.5">
          <span className="text-base font-semibold text-primary">{title}</span>
          <span className="rounded-md border border-primary/20 bg-primary/10 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-primary/70">
            {interval}
          </span>
        </div>
        <p className="mt-1 font-mono text-sm text-zinc-300">
          {startTime} → {endTime}
          {tickCount != null && tickCount > 0 && (
            <span className="hidden md:inline text-zinc-400"> · {tickCount} ticks</span>
          )}
        </p>
        {children}
      </div>
      <div className="hidden md:flex items-center gap-3">
        {onExport && <DownloadButton label="CSV" onClick={onExport} />}
      </div>
    </div>
  );
}
