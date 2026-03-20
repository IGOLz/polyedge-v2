"use client";

import { useRef, useState, useCallback, useMemo } from "react";
import { cn } from "@/lib/utils";

interface TimelineDot {
  id: string;
  time: string; // formatted display time like "14:30"
  /** Minutes from midnight UTC (0–1440) */
  minuteOfDay: number;
  dotClasses: string[];
}

interface MiniTimelineProps {
  dots: TimelineDot[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const HOUR_LABELS = [0, 3, 6, 9, 12, 15, 18, 21, 24];

export function MiniTimeline({ dots, selectedId, onSelect }: MiniTimelineProps) {
  const barRef = useRef<HTMLDivElement>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; label: string } | null>(null);
  const isDragging = useRef(false);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingId = useRef<string | null>(null);

  const sortedDots = useMemo(
    () => [...dots].sort((a, b) => a.minuteOfDay - b.minuteOfDay),
    [dots]
  );

  // Find the nearest dot to a cursor position
  const findNearestDot = useCallback(
    (clientX: number) => {
      const bar = barRef.current;
      if (!bar || sortedDots.length === 0) return null;
      const rect = bar.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      const minuteTarget = pct * 1440;

      let nearest = sortedDots[0];
      let bestDist = Math.abs(nearest.minuteOfDay - minuteTarget);
      for (let i = 1; i < sortedDots.length; i++) {
        const dist = Math.abs(sortedDots[i].minuteOfDay - minuteTarget);
        if (dist < bestDist) {
          bestDist = dist;
          nearest = sortedDots[i];
        }
      }
      return nearest;
    },
    [sortedDots]
  );

  // Commit selection (debounced during drag, immediate on click/release)
  const commitSelection = useCallback(
    (id: string) => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      debounceTimer.current = null;
      pendingId.current = null;
      onSelect(id);
    },
    [onSelect]
  );

  const scheduleSelection = useCallback(
    (id: string) => {
      if (pendingId.current === id) return; // already scheduled
      pendingId.current = id;
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      debounceTimer.current = setTimeout(() => commitSelection(id), 150);
    },
    [commitSelection]
  );

  // Update visual feedback instantly, debounce the actual selection
  const scrubTo = useCallback(
    (clientX: number, immediate: boolean) => {
      const nearest = findNearestDot(clientX);
      if (!nearest) return;

      // Tooltip + highlight update instantly
      const bar = barRef.current!;
      const rect = bar.getBoundingClientRect();
      const dotPct = nearest.minuteOfDay / 1440;
      setTooltipPos({ x: dotPct * rect.width, label: nearest.time });
      setHoveredId(nearest.id);
      setDraggingId(nearest.id);

      if (immediate) {
        commitSelection(nearest.id);
      } else {
        scheduleSelection(nearest.id);
      }
    },
    [findNearestDot, commitSelection, scheduleSelection]
  );

  // Drag handlers
  const handleBarPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      isDragging.current = true;
      (e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId);
      scrubTo(e.clientX, true); // immediate on first click
    },
    [scrubTo]
  );

  const handleBarPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!isDragging.current) return;
      scrubTo(e.clientX, false); // debounced while dragging
    },
    [scrubTo]
  );

  const handleBarPointerUp = useCallback(() => {
    isDragging.current = false;
    // Commit whatever is pending immediately on release
    if (pendingId.current) {
      commitSelection(pendingId.current);
    }
    setDraggingId(null);
    setHoveredId(null);
    setTooltipPos(null);
  }, [commitSelection]);

  const handleMouseEnter = useCallback(
    (dot: TimelineDot, e: React.MouseEvent<HTMLButtonElement>) => {
      if (isDragging.current) return;
      setHoveredId(dot.id);
      const bar = barRef.current;
      if (!bar) return;
      const barRect = bar.getBoundingClientRect();
      const btnRect = e.currentTarget.getBoundingClientRect();
      setTooltipPos({
        x: btnRect.left + btnRect.width / 2 - barRect.left,
        label: dot.time,
      });
    },
    []
  );

  const handleMouseLeave = useCallback(() => {
    if (isDragging.current) return;
    setHoveredId(null);
    setTooltipPos(null);
  }, []);

  if (dots.length === 0) return null;

  return (
    <div className="relative select-none">
      {/* Hour labels */}
      <div className="relative h-4 mb-1">
        {HOUR_LABELS.map((h) => (
          <span
            key={h}
            className="absolute text-xs font-mono text-zinc-500 -translate-x-1/2 tabular-nums"
            style={{ left: `${(h / 24) * 100}%` }}
          >
            {String(h).padStart(2, "0")}:00
          </span>
        ))}
      </div>

      {/* Timeline bar */}
      <div
        ref={barRef}
        onPointerDown={handleBarPointerDown}
        onPointerMove={handleBarPointerMove}
        onPointerUp={handleBarPointerUp}
        onPointerCancel={handleBarPointerUp}
        className="relative h-8 rounded-full bg-zinc-900/80 border border-zinc-800/60 overflow-visible cursor-grab active:cursor-grabbing touch-none"
      >
        {/* Hour tick marks */}
        {HOUR_LABELS.map((h) => (
          <div
            key={h}
            className="absolute top-0 bottom-0 w-px bg-zinc-800/80"
            style={{ left: `${(h / 24) * 100}%` }}
          />
        ))}

        {/* Dots */}
        {sortedDots.map((dot) => {
          const pct = (dot.minuteOfDay / 1440) * 100;
          // When dragging, only the drag target looks selected; the old selectedId shrinks
          const activeId = draggingId ?? selectedId;
          const isSelected = dot.id === activeId;
          const isHovered = !isSelected && dot.id === hoveredId;
          // Pick primary dot color
          const primaryDot = dot.dotClasses[0] || "bg-zinc-500";
          // Map bg class to ring color
          const ringColor = primaryDot
            .replace("bg-emerald-400", "ring-emerald-400/60")
            .replace("bg-red-400", "ring-red-400/60")
            .replace("bg-amber-400", "ring-amber-400/60")
            .replace("bg-zinc-500", "ring-zinc-500/60");

          return (
            <button
              key={dot.id}
              onMouseEnter={(e) => handleMouseEnter(dot, e)}
              onMouseLeave={handleMouseLeave}
              onClick={() => onSelect(dot.id)}
              className={cn(
                "absolute top-1/2 -translate-y-1/2 -translate-x-1/2 rounded-full transition-all duration-150 focus:outline-none",
                primaryDot,
                isSelected
                  ? "h-4 w-4 ring-2 z-20 scale-110"
                  : isHovered
                    ? "h-3 w-3 z-10 brightness-125"
                    : "h-2 w-2 hover:h-3 hover:w-3",
                isSelected && ringColor
              )}
              style={{ left: `${pct}%` }}
              aria-label={`Market at ${dot.time}`}
            />
          );
        })}

        {/* Tooltip */}
        {tooltipPos && (
          <div
            className="absolute -top-8 -translate-x-1/2 pointer-events-none z-30"
            style={{ left: tooltipPos.x }}
          >
            <div className="rounded bg-zinc-800 border border-zinc-700 px-2 py-0.5 text-xs font-mono text-zinc-200 whitespace-nowrap shadow-lg">
              {tooltipPos.label}
            </div>
          </div>
        )}
      </div>

      {/* Density indicator */}
      <div className="mt-1.5 flex items-center justify-between">
        <span className="text-xs text-zinc-500">
          {dots.length} market{dots.length !== 1 ? "s" : ""}
        </span>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1 text-xs text-zinc-500">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Up
          </span>
          <span className="flex items-center gap-1 text-xs text-zinc-500">
            <span className="h-1.5 w-1.5 rounded-full bg-red-400" /> Down
          </span>
          <span className="flex items-center gap-1 text-xs text-zinc-500">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" /> Pending
          </span>
        </div>
      </div>
    </div>
  );
}
