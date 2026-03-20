"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";
import { useLiveClock } from "@/hooks/use-live-clock";
import { DownloadButton } from "./download-button";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  BarChart3,
  FlaskConical,
  Bot,
  Layers,
  Settings,
} from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

const NAV_LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/markets", label: "Markets" },
  { href: "/analysis", label: "Lab Analysis" },
  { href: "/bot", label: "Bot" },
];

const STRATEGY_LINKS = [
  { href: "/strategy", label: "Strategy 1 — Farming" },
  { href: "/strategy2", label: "Strategy 2 — Calibration" },
  { href: "/strategy3", label: "Strategy 3 — Momentum" },
  { href: "/strategy4", label: "Strategy 4 — Streak Reversal" },
  { href: "/momentum-analytics", label: "Momentum Tier Analytics" },
];

// ---------------------------------------------------------------------------
// Strategies dropdown (desktop: hover, mobile: tap)
// ---------------------------------------------------------------------------

function StrategiesDropdown() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const timeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isStrategyActive = STRATEGY_LINKS.some((s) => pathname === s.href);

  // Close on outside click (mobile tap-away)
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Close on route change
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  const handleMouseEnter = () => {
    if (timeout.current) clearTimeout(timeout.current);
    setOpen(true);
  };
  const handleMouseLeave = () => {
    timeout.current = setTimeout(() => setOpen(false), 150);
  };

  return (
    <div
      ref={ref}
      className="relative"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* Trigger */}
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "relative flex items-center gap-1 px-2.5 md:px-3 py-3 md:py-4 text-sm font-medium transition-colors duration-200",
          isStrategyActive ? "text-primary" : "text-zinc-500 hover:text-zinc-200"
        )}
      >
        Strategies
        <svg
          className={cn(
            "h-3 w-3 transition-transform duration-200",
            open && "rotate-180"
          )}
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 5l3 3 3-3" />
        </svg>
        {isStrategyActive && (
          <span className="absolute inset-x-1 bottom-0 h-0.5 rounded-full bg-primary" />
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute left-0 top-full z-50 min-w-[220px] pt-1">
          <div className="rounded-lg border border-zinc-800/60 bg-zinc-950/95 backdrop-blur-xl shadow-xl shadow-black/40 overflow-hidden">
            {STRATEGY_LINKS.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2.5 px-4 py-2.5 text-sm font-medium transition-colors duration-150",
                  pathname === href
                    ? "bg-primary/[0.08] text-primary"
                    : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
                )}
              >
                {pathname === href && (
                  <span className="h-1.5 w-1.5 rounded-full bg-primary flex-shrink-0" />
                )}
                <span className={pathname !== href ? "pl-4" : ""}>{label}</span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mobile bottom tab bar
// ---------------------------------------------------------------------------

const TAB_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/markets", label: "Markets", icon: BarChart3 },
  { href: "/analysis", label: "Lab", icon: FlaskConical },
  { href: "/bot", label: "Bot", icon: Bot },
];

function MobileBottomNav() {
  const pathname = usePathname();
  const { data: session } = useSession();
  const [strategiesOpen, setStrategiesOpen] = useState(false);
  const isStrategyActive = STRATEGY_LINKS.some((s) => pathname === s.href);

  // Close sheet on route change
  useEffect(() => {
    setStrategiesOpen(false);
  }, [pathname]);

  return (
    <div className="fixed bottom-0 inset-x-0 z-50 md:hidden">
      {/* Frosted glass bar */}
      <nav className="border-t border-zinc-800/60 bg-zinc-950/90 backdrop-blur-2xl safe-bottom">
        <div className={cn("grid items-center", session ? "grid-cols-6" : "grid-cols-5")}>
          {TAB_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "relative flex flex-col items-center gap-0.5 py-2 transition-colors duration-200",
                  active
                    ? "text-primary"
                    : "text-zinc-500 active:text-zinc-300"
                )}
              >
                <Icon className={cn("h-5 w-5", active && "drop-shadow-[0_0_6px_hsl(var(--primary)/0.5)]")} strokeWidth={active ? 2.2 : 1.5} />
                <span className="text-[10px] font-medium leading-none">{label}</span>
                {active && (
                  <span className="absolute top-0 h-0.5 w-8 rounded-b-full bg-primary" />
                )}
              </Link>
            );
          })}

          {/* Strategies tab with Sheet */}
          <Sheet open={strategiesOpen} onOpenChange={setStrategiesOpen}>
            <SheetTrigger asChild>
              <button
                className={cn(
                  "relative flex flex-col items-center gap-0.5 py-2 transition-colors duration-200",
                  isStrategyActive
                    ? "text-primary"
                    : "text-zinc-500 active:text-zinc-300"
                )}
              >
                <Layers className={cn("h-5 w-5", isStrategyActive && "drop-shadow-[0_0_6px_hsl(var(--primary)/0.5)]")} strokeWidth={isStrategyActive ? 2.2 : 1.5} />
                <span className="text-[10px] font-medium leading-none">Strategies</span>
                {isStrategyActive && (
                  <span className="absolute top-0 h-0.5 w-8 rounded-b-full bg-primary" />
                )}
              </button>
            </SheetTrigger>
            <SheetContent side="bottom" className="rounded-t-2xl border-t border-zinc-800/60 bg-zinc-950/95 backdrop-blur-2xl px-0 pb-8">
              <SheetHeader className="px-6 pb-2">
                <SheetTitle className="text-base font-semibold text-zinc-100">Strategies</SheetTitle>
              </SheetHeader>
              <div className="space-y-1 px-4">
                {STRATEGY_LINKS.map(({ href, label }) => {
                  const active = pathname === href;
                  return (
                    <Link
                      key={href}
                      href={href}
                      className={cn(
                        "flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-colors",
                        active
                          ? "bg-primary/[0.08] text-primary"
                          : "text-zinc-400 active:bg-zinc-800/50 active:text-zinc-200"
                      )}
                    >
                      {active && (
                        <span className="h-2 w-2 rounded-full bg-primary flex-shrink-0" />
                      )}
                      <span className={!active ? "pl-5" : ""}>{label}</span>
                    </Link>
                  );
                })}
              </div>
            </SheetContent>
          </Sheet>

          {/* Control tab — only when logged in */}
          {session && (
            <Link
              href="/control"
              className={cn(
                "relative flex flex-col items-center gap-0.5 py-2 transition-colors duration-200",
                pathname === "/control"
                  ? "text-primary"
                  : "text-zinc-500 active:text-zinc-300"
              )}
            >
              <Settings className={cn("h-5 w-5", pathname === "/control" && "drop-shadow-[0_0_6px_hsl(var(--primary)/0.5)]")} strokeWidth={pathname === "/control" ? 2.2 : 1.5} />
              <span className="text-[10px] font-medium leading-none">Control</span>
              {pathname === "/control" && (
                <span className="absolute top-0 h-0.5 w-8 rounded-b-full bg-primary" />
              )}
            </Link>
          )}
        </div>
      </nav>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Navbar
// ---------------------------------------------------------------------------

export function Navbar() {
  const pathname = usePathname();
  const time = useLiveClock();
  const { data: session } = useSession();

  return (
    <>
    <nav className="sticky top-0 z-50 border-b border-zinc-800/40 bg-zinc-950/70 backdrop-blur-2xl">
      <div className="mx-auto flex h-12 md:h-14 max-w-7xl items-center justify-between px-4 md:px-6">
        <div className="flex items-center gap-3 md:gap-4">
          <Link href="/" className="flex items-center gap-2 md:gap-2.5 group">
            <div className="relative h-2 w-2 md:h-2.5 md:w-2.5">
              <div className="absolute inset-0 rounded-full bg-primary animate-ping opacity-20" />
              <div className="relative h-2 w-2 md:h-2.5 md:w-2.5 rounded-full bg-primary shadow-sm shadow-primary/50" />
            </div>
            <span className="text-base md:text-lg font-bold tracking-tight text-primary">
              PolyEdge
            </span>
          </Link>

          <div className="hidden md:block h-4 w-px bg-zinc-800/60" />

          {/* Desktop nav */}
          <div className="hidden md:flex items-center gap-1">
            {NAV_LINKS.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  "relative px-2.5 md:px-3 py-3 md:py-4 text-sm font-medium transition-colors duration-200",
                  pathname === href
                    ? "text-primary"
                    : "text-zinc-500 hover:text-zinc-200"
                )}
              >
                {label}
                {pathname === href && (
                  <span className="absolute inset-x-1 bottom-0 h-0.5 rounded-full bg-primary" />
                )}
              </Link>
            ))}
            <StrategiesDropdown />
            {session && (
              <Link
                href="/control"
                className={cn(
                  "relative px-2.5 md:px-3 py-3 md:py-4 text-sm font-medium transition-colors duration-200",
                  pathname === "/control"
                    ? "text-primary"
                    : "text-zinc-500 hover:text-zinc-200"
                )}
              >
                Control
                {pathname === "/control" && (
                  <span className="absolute inset-x-1 bottom-0 h-0.5 rounded-full bg-primary" />
                )}
              </Link>
            )}
          </div>

          {/* Mobile: show brand only, bottom nav handles navigation */}
        </div>

        <div className="hidden md:flex items-center gap-3">
          <DownloadButton label="Export Summary" href="/api/export" iconSize={12} />
          <div className="flex items-center gap-2 rounded-lg border border-zinc-800/40 bg-zinc-900/30 px-3 py-1.5">
            <div className="h-1.5 w-1.5 rounded-full bg-primary/50 animate-pulse" />
            <span className="font-mono text-sm tabular-nums text-zinc-400">
              {time}
            </span>
            <span className="text-xs text-zinc-500 font-medium">UTC</span>
          </div>
        </div>
      </div>
    </nav>
    <MobileBottomNav />
    </>
  );
}
