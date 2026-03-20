"use client";

import { useEffect, useRef, useState } from "react";
import { createChart, LineStyle, LineSeries, createSeriesMarkers } from "lightweight-charts";
import type { SeriesMarker, Time } from "lightweight-charts";
import type { Market } from "@/types/market";
import { useMarketTicks } from "@/hooks/use-market-ticks";
import { createBaseChartOptions, createLineSeriesOptions, getMaxSeconds } from "@/lib/chart-config";
import { CHART_BASE_TIME } from "@/lib/constants";
import { formatUTCTime, getOutcomeColors, getOutcomeLabel } from "@/lib/formatters";
import { exportSingleMarketCsv } from "@/lib/csv";
import { ChartHeader } from "./chart-header";
import { DownloadButton } from "./download-button";
import { LoadingSpinner } from "./loading-spinner";

// ---------------------------------------------------------------------------
// Trade data fetched from DB for chart markers
// ---------------------------------------------------------------------------

interface MarketTrade {
  id: string;
  direction: string;
  entry_price: string;
  bet_size_usd: string;
  status: string;
  final_outcome: string | null;
  pnl: string | null;
  placed_at: string;
  resolved_at: string | null;
  stop_loss_price: string | null;
  stop_loss_triggered: boolean | null;
  strategy_name: string;
}

function useMarketTrades(marketId: string) {
  const [trades, setTrades] = useState<MarketTrade[]>([]);

  useEffect(() => {
    fetch(`/api/bot-trades-by-market?market_id=${encodeURIComponent(marketId)}`)
      .then((r) => r.json())
      .then((data: MarketTrade[]) => {
        if (Array.isArray(data)) setTrades(data);
      })
      .catch(() => setTrades([]));
  }, [marketId]);

  return trades;
}

function fmtTradeTime(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "UTC" });
}

// ---------------------------------------------------------------------------
// MarketChart
// ---------------------------------------------------------------------------

export function MarketChart({ market }: { market: Market }) {
  const { ticks, loading } = useMarketTicks(market.market_id);
  const trades = useMarketTrades(market.market_id);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const asset = market.market_type?.split("_")[0] || "";
  const interval = market.market_type?.split("_")[1] || "";
  const { line: lineColor, text: outcomeColor } = getOutcomeColors(market.final_outcome);
  const outcomeLabel = getOutcomeLabel(market.final_outcome);

  useEffect(() => {
    if (loading || ticks.length === 0 || !chartContainerRef.current) return;

    const container = chartContainerRef.current;
    const tooltip = tooltipRef.current;
    const chart = createChart(container, createBaseChartOptions());

    const lineSeries = chart.addSeries(LineSeries, createLineSeriesOptions(lineColor));

    lineSeries.setData(
      ticks.map((t) => ({
        time: (CHART_BASE_TIME + t.seconds) as any,
        value: t.up_price,
      }))
    );

    // Build marker time→trade lookup for tooltip
    const markerTradeMap = new Map<number, MarketTrade>();

    if (trades.length > 0) {
      const marketStart = new Date(market.started_at).getTime();
      const markers: SeriesMarker<Time>[] = [];

      for (const trade of trades) {
        const entrySeconds = Math.round((new Date(trade.placed_at).getTime() - marketStart) / 1000);
        const entryPrice = parseFloat(trade.entry_price);

        if (entrySeconds >= 0) {
          const chartTime = CHART_BASE_TIME + entrySeconds;
          markers.push({
            time: chartTime as unknown as Time,
            position: "inBar",
            color: "#ffffff",
            shape: "circle",
            size: 2,
            id: `entry-${trade.id}`,
          });
          markerTradeMap.set(chartTime, trade);
        }

        if (trade.stop_loss_triggered && trade.resolved_at) {
          const slSeconds = Math.round((new Date(trade.resolved_at).getTime() - marketStart) / 1000);
          if (slSeconds >= 0) {
            const chartTime = CHART_BASE_TIME + slSeconds;
            markers.push({
              time: chartTime as unknown as Time,
              position: "aboveBar",
              color: "#f87171",
              shape: "arrowDown",
              size: 2,
              id: `sl-${trade.id}`,
            });
          }
        }
      }

      if (markers.length > 0) {
        markers.sort((a, b) => (a.time as number) - (b.time as number));
        createSeriesMarkers(lineSeries, markers);
      }
    }

    // Crosshair tooltip for trade markers
    if (tooltip && markerTradeMap.size > 0) {
      chart.subscribeCrosshairMove((param) => {
        if (!param.time || !param.point) {
          tooltip.style.display = "none";
          return;
        }

        const crosshairTime = param.time as number;

        // Find closest marker within 3 seconds
        let closestTrade: MarketTrade | null = null;
        let closestDist = Infinity;
        for (const [t, trade] of markerTradeMap) {
          const dist = Math.abs(t - crosshairTime);
          if (dist < closestDist) {
            closestDist = dist;
            closestTrade = trade;
          }
        }

        if (!closestTrade || closestDist > 3) {
          tooltip.style.display = "none";
          return;
        }

        const t = closestTrade;
        const entryPrice = parseFloat(t.entry_price);
        const pnl = t.pnl ? parseFloat(t.pnl) : null;
        const betSize = parseFloat(t.bet_size_usd);

        let outcomeHtml = "";
        if (t.final_outcome === "win") {
          outcomeHtml = `<span style="color:#4ade80">Win</span>`;
        } else if (t.final_outcome === "loss") {
          outcomeHtml = `<span style="color:#f87171">Loss</span>`;
        } else {
          outcomeHtml = `<span style="color:#facc15">Pending</span>`;
        }

        let pnlHtml = "";
        if (pnl != null && t.final_outcome) {
          const pnlColor = pnl >= 0 ? "#4ade80" : "#f87171";
          const pnlPrefix = pnl >= 0 ? "$" : "-$";
          pnlHtml = `<div style="display:flex;justify-content:space-between"><span style="color:#a1a1aa">PnL</span><span style="color:${pnlColor};font-family:ui-monospace,monospace;font-weight:700">${pnlPrefix}${Math.abs(pnl).toFixed(2)}</span></div>`;
        }

        let slHtml = "";
        if (t.stop_loss_triggered) {
          const slPrice = t.stop_loss_price ? `${Math.round(parseFloat(t.stop_loss_price) * 100)}¢` : "—";
          slHtml = `<div style="display:flex;justify-content:space-between"><span style="color:#a1a1aa">Stop Loss</span><span style="color:#f87171">${slPrice}</span></div>`;
        }

        tooltip.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <span style="color:#e4e4e7;font-weight:600;font-size:12px">${t.strategy_name}</span>
            <span style="color:${t.direction === "up" ? "#4ade80" : "#f87171"};font-size:11px;font-weight:500">${t.direction.toUpperCase()}</span>
          </div>
          <div style="height:1px;background:#3f3f46;margin:4px 0"></div>
          <div style="display:flex;justify-content:space-between"><span style="color:#a1a1aa">Entry</span><span style="color:#e4e4e7;font-family:ui-monospace,monospace">${Math.round(entryPrice * 100)}¢</span></div>
          <div style="display:flex;justify-content:space-between"><span style="color:#a1a1aa">Size</span><span style="color:#e4e4e7;font-family:ui-monospace,monospace">$${betSize.toFixed(2)}</span></div>
          <div style="display:flex;justify-content:space-between"><span style="color:#a1a1aa">Outcome</span>${outcomeHtml}</div>
          ${pnlHtml}
          ${slHtml}
          <div style="display:flex;justify-content:space-between"><span style="color:#a1a1aa">Time</span><span style="color:#71717a;font-size:10px">${fmtTradeTime(t.placed_at)}</span></div>
        `;

        // Position tooltip
        const x = param.point.x;
        const y = param.point.y;
        const tooltipWidth = 180;
        const tooltipHeight = tooltip.offsetHeight || 120;
        const containerWidth = container.clientWidth;

        let left = x + 16;
        if (left + tooltipWidth > containerWidth) {
          left = x - tooltipWidth - 16;
        }
        let top = y - tooltipHeight / 2;
        if (top < 0) top = 4;
        if (top + tooltipHeight > container.clientHeight) {
          top = container.clientHeight - tooltipHeight - 4;
        }

        tooltip.style.display = "block";
        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
      });
    }

    lineSeries.createPriceLine({
      price: 0.5,
      color: "#3f3f46",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "",
    });

    const maxSeconds = getMaxSeconds(interval);
    chart.timeScale().setVisibleRange({
      from: CHART_BASE_TIME as any,
      to: (CHART_BASE_TIME + maxSeconds) as any,
    });

    const resizeObserver = new ResizeObserver(() => {
      chart.applyOptions({
        width: container.clientWidth,
        height: container.clientHeight,
      });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      if (tooltip) tooltip.style.display = "none";
    };
  }, [loading, ticks, lineColor, interval, market.started_at, trades]);

  if (loading) {
    return (
      <div className="flex flex-1 flex-col">
        <div className="h-5 w-48 animate-pulse rounded bg-zinc-800/80" />
        <div className="mt-2 h-3 w-32 animate-pulse rounded bg-zinc-800/60" />
        <div className="mt-6 flex flex-1 items-center justify-center rounded-lg border border-zinc-800/30 bg-zinc-950/50">
          <LoadingSpinner label="Loading tick data..." />
        </div>
      </div>
    );
  }

  const startTime = formatUTCTime(market.started_at);
  const endTime = formatUTCTime(market.ended_at);

  if (ticks.length === 0) {
    return (
      <div className="flex flex-1 flex-col">
        <ChartHeader
          title={asset.toUpperCase()}
          interval={interval}
          startTime={startTime}
          endTime={endTime}
        />
        <div className="flex flex-1 items-center justify-center rounded-lg border border-zinc-800/30 bg-zinc-950/50 mt-4">
          <span className="text-base text-zinc-400">No tick data for this market</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      <div className="flex items-start justify-between">
        <ChartHeader
          title={asset.toUpperCase()}
          interval={interval}
          startTime={startTime}
          endTime={endTime}
          tickCount={ticks.length}
        />
        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="text-xs font-semibold uppercase tracking-[0.15em] text-zinc-400">
              Result
            </p>
            <p className={`text-lg font-bold uppercase ${outcomeColor}`}>
              {outcomeLabel}
            </p>
          </div>
          <DownloadButton label="CSV" onClick={() => exportSingleMarketCsv(ticks, market.market_type, market.market_id)} />
        </div>
      </div>

      <div className="relative mt-4 flex-1 min-h-0 rounded-lg border border-zinc-800/30 bg-zinc-950/50 overflow-hidden">
        <div
          ref={chartContainerRef}
          className="h-full w-full"
        />
        {/* Trade marker tooltip */}
        <div
          ref={tooltipRef}
          style={{
            display: "none",
            position: "absolute",
            zIndex: 50,
            width: 180,
            pointerEvents: "none",
            fontSize: 11,
            lineHeight: "18px",
          }}
          className="rounded-lg border border-zinc-700/60 bg-zinc-900/95 px-3 py-2 shadow-xl backdrop-blur-sm"
        />
      </div>
    </div>
  );
}
