"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";
import { BarChart3, LayoutDashboard, Settings } from "lucide-react";

import { DownloadButton } from "@/components/download-button";
import { useLiveClock } from "@/hooks/use-live-clock";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/markets", label: "Markets" },
];

const TAB_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/markets", label: "Markets", icon: BarChart3 },
];

function DesktopLinks() {
  const pathname = usePathname();

  return (
    <>
      {NAV_LINKS.map(({ href, label }) => (
        <Link
          key={href}
          href={href}
          className={cn(
            "relative px-2.5 py-3 text-sm font-medium transition-colors duration-200 md:px-3 md:py-4",
            pathname === href ? "text-primary" : "text-zinc-500 hover:text-zinc-200"
          )}
        >
          {label}
          {pathname === href && (
            <span className="absolute inset-x-1 bottom-0 h-0.5 rounded-full bg-primary" />
          )}
        </Link>
      ))}
    </>
  );
}

function MobileBottomNav() {
  const pathname = usePathname();
  const { data: session } = useSession();

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 md:hidden">
      <nav className="safe-bottom border-t border-zinc-800/60 bg-zinc-950/90 backdrop-blur-2xl">
        <div className={cn("grid items-center", session ? "grid-cols-3" : "grid-cols-2")}>
          {TAB_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "relative flex flex-col items-center gap-0.5 py-2 transition-colors duration-200",
                  active ? "text-primary" : "text-zinc-500 active:text-zinc-300"
                )}
              >
                <Icon
                  className={cn("h-5 w-5", active && "drop-shadow-[0_0_6px_hsl(var(--primary)/0.5)]")}
                  strokeWidth={active ? 2.2 : 1.5}
                />
                <span className="text-[10px] font-medium leading-none">{label}</span>
                {active && <span className="absolute top-0 h-0.5 w-8 rounded-b-full bg-primary" />}
              </Link>
            );
          })}

          {session && (
            <Link
              href="/control"
              className={cn(
                "relative flex flex-col items-center gap-0.5 py-2 transition-colors duration-200",
                pathname === "/control" ? "text-primary" : "text-zinc-500 active:text-zinc-300"
              )}
            >
              <Settings
                className={cn("h-5 w-5", pathname === "/control" && "drop-shadow-[0_0_6px_hsl(var(--primary)/0.5)]")}
                strokeWidth={pathname === "/control" ? 2.2 : 1.5}
              />
              <span className="text-[10px] font-medium leading-none">Control</span>
              {pathname === "/control" && <span className="absolute top-0 h-0.5 w-8 rounded-b-full bg-primary" />}
            </Link>
          )}
        </div>
      </nav>
    </div>
  );
}

export function Navbar() {
  const pathname = usePathname();
  const time = useLiveClock();
  const { data: session } = useSession();

  return (
    <>
      <nav className="sticky top-0 z-50 border-b border-zinc-800/40 bg-zinc-950/70 backdrop-blur-2xl">
        <div className="mx-auto flex h-12 max-w-7xl items-center justify-between px-4 md:h-14 md:px-6">
          <div className="flex items-center gap-3 md:gap-4">
            <Link href="/" className="group flex items-center gap-2 md:gap-2.5">
              <div className="relative h-2 w-2 md:h-2.5 md:w-2.5">
                <div className="absolute inset-0 rounded-full bg-primary opacity-20 animate-ping" />
                <div className="relative h-2 w-2 rounded-full bg-primary shadow-sm shadow-primary/50 md:h-2.5 md:w-2.5" />
              </div>
              <span className="text-base font-bold tracking-tight text-primary md:text-lg">PolyEdge</span>
            </Link>

            <div className="hidden h-4 w-px bg-zinc-800/60 md:block" />

            <div className="hidden items-center gap-1 md:flex">
              <DesktopLinks />
              {session && (
                <Link
                  href="/control"
                  className={cn(
                    "relative px-2.5 py-3 text-sm font-medium transition-colors duration-200 md:px-3 md:py-4",
                    pathname === "/control" ? "text-primary" : "text-zinc-500 hover:text-zinc-200"
                  )}
                >
                  Control
                  {pathname === "/control" && (
                    <span className="absolute inset-x-1 bottom-0 h-0.5 rounded-full bg-primary" />
                  )}
                </Link>
              )}
            </div>
          </div>

          <div className="hidden items-center gap-3 md:flex">
            <DownloadButton label="Export Summary" href="/api/export" iconSize={12} />
            <div className="flex items-center gap-2 rounded-lg border border-zinc-800/40 bg-zinc-900/30 px-3 py-1.5">
              <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary/50" />
              <span className="font-mono text-sm tabular-nums text-zinc-400">{time}</span>
              <span className="text-xs font-medium text-zinc-500">UTC</span>
            </div>
          </div>
        </div>
      </nav>
      <MobileBottomNav />
    </>
  );
}
