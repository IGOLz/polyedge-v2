"use client";

import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { RecentTradeRow } from "@/lib/bot-dashboard-data";
import { cn } from "@/lib/utils";

const FILTERS = [
  { value: "all", label: "All" },
  { value: "wins", label: "Wins" },
  { value: "losses", label: "Losses" },
  { value: "stop_loss", label: "Stop Loss" },
  { value: "take_profit", label: "Take Profit" },
] as const;

const BATCH = 50;

function formatTimestamp(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
}

function formatMarketType(value: string) {
  const [asset, interval] = value.split("_");
  if (!asset || !interval) return value;
  return `${asset.toUpperCase()} ${interval}`;
}

function formatPrice(value: number | null) {
  if (value == null) return "—";
  if (value <= 1) return `${(value * 100).toFixed(1)}¢`;
  return `$${value.toFixed(2)}`;
}

function formatCurrency(value: number | null) {
  if (value == null) return "—";
  return `${value < 0 ? "-" : ""}$${Math.abs(value).toFixed(2)}`;
}

function outcomeLabel(outcome: string | null) {
  if (!outcome) return null;
  switch (outcome) {
    case "win":
    case "win_resolution":
      return { text: "Win", className: "text-emerald-400" };
    case "take_profit":
      return {
        text: "Take Profit",
        className:
          "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
      };
    case "loss":
      return { text: "Loss", className: "text-red-400" };
    case "stop_loss":
      return {
        text: "Stop Loss",
        className:
          "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium bg-orange-500/10 text-orange-400 border border-orange-500/20",
      };
    default:
      return { text: outcome, className: "text-zinc-400" };
  }
}

/** Transform snake_case API trade to camelCase RecentTradeRow */
function transformApiTrade(t: Record<string, unknown>): RecentTradeRow {
  const entryPrice = parseFloat(String(t.entry_price ?? "0"));
  const finalOutcome = (t.final_outcome as string) ?? null;
  const stopLossPrice = t.stop_loss_price != null ? Number(t.stop_loss_price) : null;
  const takeProfitPrice = t.take_profit_price != null ? Number(t.take_profit_price) : null;

  let exitPrice: number | null = null;
  if (finalOutcome === "win" || finalOutcome === "win_resolution") exitPrice = 1;
  else if (finalOutcome === "loss") exitPrice = 0;
  else if (finalOutcome === "stop_loss" && stopLossPrice != null) exitPrice = stopLossPrice;
  else if (finalOutcome === "take_profit" && takeProfitPrice != null) exitPrice = takeProfitPrice;

  return {
    id: String(t.id),
    marketType: String(t.market_type),
    strategyName: String(t.strategy_name),
    side: String(t.direction),
    entryPrice,
    exitPrice,
    betSize: parseFloat(String(t.bet_size_usd ?? "0")),
    pnl: t.pnl != null ? parseFloat(String(t.pnl)) : null,
    placedAt: String(t.placed_at),
    resolvedAt: t.resolved_at != null ? String(t.resolved_at) : null,
    status: String(t.status),
    finalOutcome,
  };
}

export function TradeHistoryTable({
  initialTrades,
}: {
  initialTrades: RecentTradeRow[];
}) {
  const [filter, setFilter] = useState("all");
  const [allTrades, setAllTrades] = useState(initialTrades);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const offsetRef = useRef(initialTrades.length);

  useEffect(() => {
    setAllTrades(initialTrades);
    offsetRef.current = initialTrades.length;
    setHasMore(true);
  }, [initialTrades]);

  // Only filled trades
  const filledTrades = useMemo(
    () => allTrades.filter((t) => t.status === "filled"),
    [allTrades],
  );

  const filtered = useMemo(() => {
    if (filter === "wins")
      return filledTrades.filter((t) =>
        ["win", "win_resolution", "take_profit"].includes(t.finalOutcome ?? ""),
      );
    if (filter === "losses")
      return filledTrades.filter((t) => t.finalOutcome === "loss");
    if (filter === "stop_loss")
      return filledTrades.filter((t) => t.finalOutcome === "stop_loss");
    if (filter === "take_profit")
      return filledTrades.filter((t) => t.finalOutcome === "take_profit");
    return filledTrades;
  }, [filledTrades, filter]);

  const fetchMore = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const res = await fetch(
        `/api/bot-activity?type=trades&limit=${BATCH}&offset=${offsetRef.current}`,
      );
      const data = await res.json();
      const raw: Record<string, unknown>[] = data.trades ?? [];
      if (raw.length < BATCH) setHasMore(false);
      if (raw.length > 0) {
        const newTrades = raw.map(transformApiTrade);
        setAllTrades((prev) => {
          const existingIds = new Set(prev.map((t) => t.id));
          const deduped = newTrades.filter((t) => !existingIds.has(t.id));
          return [...prev, ...deduped];
        });
        offsetRef.current += raw.length;
      }
    } catch {
      // silently fail
    } finally {
      setLoadingMore(false);
    }
  }, [loadingMore, hasMore]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) fetchMore();
      },
      { root: scrollRef.current, rootMargin: "200px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [fetchMore]);

  return (
    <>
      {/* Filter tabs */}
      <div className="border-b border-zinc-800/60 px-5 py-3">
        <div className="flex items-center gap-1 overflow-x-auto pb-1 scrollbar-thin">
          {FILTERS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setFilter(opt.value)}
              className={cn(
                "flex-shrink-0 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                filter === opt.value
                  ? "bg-primary/[0.12] text-primary border border-primary/30"
                  : "bg-zinc-900/60 text-zinc-400 border border-zinc-800/40 hover:text-zinc-200 hover:border-zinc-700/60",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Table with scroll */}
      <div className="overflow-x-auto">
        <div className="min-w-[900px]">
          {/* Fixed header */}
          <table className="w-full table-fixed">
            <thead className="bg-zinc-950">
              <tr className="border-b border-zinc-800/40">
                <th className="w-36 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  Date / Time
                </th>
                <th className="w-24 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  Market
                </th>
                <th className="w-32 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  Strategy
                </th>
                <th className="w-16 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  Side
                </th>
                <th className="w-20 px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  Size
                </th>
                <th className="w-24 px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  Outcome
                </th>
                <th className="w-20 px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  Entry
                </th>
                <th className="w-20 px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  Exit
                </th>
                <th className="w-24 px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  P&L
                </th>
              </tr>
            </thead>
          </table>

          {/* Scrollable body */}
          <div
            ref={scrollRef}
            className="max-h-[520px] overflow-y-auto scrollbar-thin"
          >
            <table className="w-full table-fixed">
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td
                      colSpan={9}
                      className="py-12 text-center text-sm text-zinc-500"
                    >
                      No trades to show.
                    </td>
                  </tr>
                ) : (
                  filtered.map((trade, idx) => {
                    const outcome = outcomeLabel(trade.finalOutcome);

                    return (
                      <tr
                        key={trade.id}
                        className={cn(
                          "border-b border-zinc-800/20 transition-colors hover:bg-zinc-800/20",
                          idx % 2 === 1 && "bg-zinc-900/30",
                        )}
                      >
                        {/* Date */}
                        <td className="w-36 px-4 py-3 text-sm text-zinc-300">
                          <div className="font-medium text-zinc-100">
                            {formatTimestamp(trade.placedAt)}
                          </div>
                          <div className="text-xs text-zinc-500">
                            {trade.resolvedAt
                              ? `Resolved ${formatTimestamp(trade.resolvedAt)}`
                              : "Open"}
                          </div>
                        </td>

                        {/* Market */}
                        <td className="w-24 px-4 py-3 text-sm text-zinc-300">
                          {formatMarketType(trade.marketType)}
                        </td>

                        {/* Strategy */}
                        <td className="w-32 px-4 py-3">
                          <span className="inline-flex max-w-full truncate rounded-md border border-primary/20 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                            {trade.strategyName}
                          </span>
                        </td>

                        {/* Side */}
                        <td className="w-16 px-4 py-3">
                          <span
                            className={cn(
                              "inline-flex items-center gap-1 text-sm",
                              trade.side.toLowerCase() === "up"
                                ? "text-emerald-400"
                                : "text-red-400",
                            )}
                          >
                            {trade.side.toLowerCase() === "up" ? (
                              <ArrowUpRight className="h-3.5 w-3.5" />
                            ) : (
                              <ArrowDownRight className="h-3.5 w-3.5" />
                            )}
                            {trade.side}
                          </span>
                        </td>

                        {/* Size */}
                        <td className="w-20 px-4 py-3 text-right font-mono text-sm tabular-nums text-zinc-200">
                          {formatCurrency(trade.betSize)}
                        </td>

                        {/* Outcome */}
                        <td className="w-24 px-4 py-3 text-center">
                          {!trade.finalOutcome ? (
                            <span className="text-xs font-medium text-yellow-400">
                              Pending...
                            </span>
                          ) : outcome ? (
                            <span
                              className={cn("text-xs font-medium", outcome.className)}
                            >
                              {outcome.text}
                            </span>
                          ) : null}
                        </td>

                        {/* Entry */}
                        <td className="w-20 px-4 py-3 text-right font-mono text-sm tabular-nums text-zinc-200">
                          {formatPrice(trade.entryPrice)}
                        </td>

                        {/* Exit */}
                        <td className="w-20 px-4 py-3 text-right font-mono text-sm tabular-nums text-zinc-200">
                          {trade.exitPrice == null
                            ? "Open"
                            : formatPrice(trade.exitPrice)}
                        </td>

                        {/* PnL */}
                        <td
                          className={cn(
                            "w-24 px-4 py-3 text-right font-mono text-sm font-semibold tabular-nums",
                            trade.pnl == null
                              ? "text-zinc-500"
                              : trade.pnl > 0
                                ? "text-emerald-400"
                                : trade.pnl < 0
                                  ? "text-red-400"
                                  : "text-zinc-100",
                          )}
                        >
                          {trade.pnl == null ? "—" : formatCurrency(trade.pnl)}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
            {/* Sentinel for infinite scroll */}
            <div ref={sentinelRef} className="h-1" />
            {loadingMore && (
              <div className="flex items-center justify-center py-4 gap-2">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-primary" />
                <span className="text-xs text-zinc-500">
                  Loading more trades...
                </span>
              </div>
            )}
            {!hasMore && filtered.length > 0 && (
              <div className="py-3 text-center">
                <span className="text-xs text-zinc-600">
                  All trades loaded
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
