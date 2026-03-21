import { ColorType } from "lightweight-charts";
import { CHART_BASE_TIME } from "./constants";

function formatElapsed(seconds: number, includeSeconds = false): string {
  if (seconds <= 0) return "0s";
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (!includeSeconds || secs === 0) return `${mins}m`;
  return `${mins}m ${secs}s`;
}

export function createBaseChartOptions() {
  return {
    layout: {
      background: { type: ColorType.Solid, color: "transparent" } as const,
      textColor: "#52525b",
      fontSize: 11,
      fontFamily: "ui-monospace, SFMono-Regular, monospace",
    },
    grid: {
      vertLines: { visible: false },
      horzLines: { visible: false },
    },
    crosshair: {
      vertLine: {
        color: "rgba(228, 246, 0, 0.3)",
        labelBackgroundColor: "#18181b",
      },
      horzLine: {
        color: "rgba(228, 246, 0, 0.3)",
        labelBackgroundColor: "#18181b",
      },
    },
    rightPriceScale: {
      borderColor: "#27272a",
      scaleMargins: { top: 0, bottom: 0 },
    },
    timeScale: {
      borderColor: "#27272a",
      timeVisible: true,
      secondsVisible: true,
      fixLeftEdge: true,
      fixRightEdge: true,
      uniformDistribution: true,
      tickMarkFormatter: (time: number) => formatElapsed(time - CHART_BASE_TIME),
    },
    localization: {
      priceFormatter: (price: number) => `${(price * 100).toFixed(0)}%`,
      timeFormatter: (time: number) => formatElapsed(time - CHART_BASE_TIME, true),
    },
    handleScale: false,
    handleScroll: false,
  };
}

export function createLineSeriesOptions(color: string) {
  return {
    color,
    lineWidth: 2 as const,
    crosshairMarkerRadius: 4,
    crosshairMarkerBackgroundColor: color,
    crosshairMarkerBorderColor: "#09090b",
    priceLineVisible: false,
    lastValueVisible: true,
    autoscaleInfoProvider: () => ({
      priceRange: { minValue: 0, maxValue: 1 },
    }),
  };
}

export function getMaxSeconds(interval: string): number {
  return interval === "15m" ? 900 : 300;
}

export function toChartTime(seconds: number) {
  return (CHART_BASE_TIME + seconds) as unknown as Parameters<never>[0];
}
