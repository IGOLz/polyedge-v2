"use client";

import { useEffect, useRef } from "react";
import { createChart, LineStyle, LineSeries } from "lightweight-charts";
import type { Market } from "@/types/market";
import { useMultiMarketTicks } from "@/hooks/use-market-ticks";
import { createBaseChartOptions, createLineSeriesOptions, getMaxSeconds } from "@/lib/chart-config";
import { CHART_BASE_TIME } from "@/lib/constants";
import { formatUTCTime, getAssetColor, getOutcomeColors } from "@/lib/formatters";
import { exportMultiMarketCsv } from "@/lib/csv";
import { ChartHeader } from "./chart-header";
import { LoadingSpinner } from "./loading-spinner";

export function MultiMarketChart({ markets }: { markets: Market[] }) {
  const { marketTicks, loading } = useMultiMarketTicks(markets);
  const chartContainerRef = useRef<HTMLDivElement>(null);

  const interval = markets[0]?.market_type?.split("_")[1] || "";
  const startTime = formatUTCTime(markets[0]?.started_at || "");
  const endTime = formatUTCTime(markets[0]?.ended_at || "");

  useEffect(() => {
    if (loading || marketTicks.length === 0 || !chartContainerRef.current) return;

    const container = chartContainerRef.current;
    const chart = createChart(container, createBaseChartOptions());

    const maxSeconds = getMaxSeconds(interval);
    let isFirst = true;

    for (const mt of marketTicks) {
      if (mt.ticks.length === 0) continue;

      const color = getAssetColor(mt.asset);
      const series = chart.addSeries(LineSeries, {
        ...createLineSeriesOptions(color),
        title: mt.asset.toUpperCase(),
      });

      series.setData(
        mt.ticks.map((t) => ({
          time: (CHART_BASE_TIME + t.seconds) as any,
          value: t.up_price,
        }))
      );

      if (isFirst) {
        series.createPriceLine({
          price: 0.5,
          color: "#3f3f46",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: "",
        });
        isFirst = false;
      }
    }

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
    };
  }, [loading, marketTicks, interval]);

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

  const hasAnyTicks = marketTicks.some((mt) => mt.ticks.length > 0);

  const legend = (
    <div className="mt-2 flex items-center gap-4">
      {marketTicks.map((mt) => {
        const color = getAssetColor(mt.asset);
        const { text } = getOutcomeColors(mt.market.final_outcome);
        return (
          <div key={mt.market.market_id} className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-sm font-bold uppercase text-zinc-300">{mt.asset}</span>
            <span className={`text-xs font-semibold uppercase ${text}`}>
              {mt.market.final_outcome || "?"}
            </span>
          </div>
        );
      })}
    </div>
  );

  if (!hasAnyTicks) {
    return (
      <div className="flex flex-1 flex-col">
        <ChartHeader title="ALL ASSETS" interval={interval} startTime={startTime} endTime={endTime}>
          {legend}
        </ChartHeader>
        <div className="flex flex-1 items-center justify-center rounded-lg border border-zinc-800/30 bg-zinc-950/50 mt-4">
          <span className="text-base text-zinc-400">No tick data for these markets</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      <ChartHeader
        title="ALL ASSETS"
        interval={interval}
        startTime={startTime}
        endTime={endTime}
        onExport={() => exportMultiMarketCsv(marketTicks, interval, markets[0]?.started_at)}
      >
        {legend}
      </ChartHeader>

      <div
        ref={chartContainerRef}
        className="mt-4 flex-1 min-h-0 rounded-lg border border-zinc-800/30 bg-zinc-950/50 overflow-hidden"
      />
    </div>
  );
}
