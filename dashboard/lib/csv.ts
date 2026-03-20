import type { TickData, MarketTicks } from "@/types/market";

function triggerDownload(content: string, filename: string) {
  const blob = new Blob([content], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function exportSingleMarketCsv(
  ticks: TickData[],
  marketType: string,
  marketId: string
) {
  const csv = [
    "seconds,up_price",
    ...ticks.map((t) => `${t.seconds},${t.up_price}`),
  ].join("\n");
  triggerDownload(csv, `${marketType}-${marketId.slice(0, 8)}.csv`);
}

export function exportMultiMarketCsv(
  marketTicks: MarketTicks[],
  interval: string,
  dateStr: string
) {
  const headers = ["seconds", ...marketTicks.map((mt) => `${mt.asset}_up_price`)];

  const allSeconds = new Set<number>();
  for (const mt of marketTicks) {
    for (const t of mt.ticks) allSeconds.add(t.seconds);
  }
  const sortedSeconds = Array.from(allSeconds).sort((a, b) => a - b);

  const tickMaps = marketTicks.map((mt) => {
    const map = new Map<number, number>();
    for (const t of mt.ticks) map.set(t.seconds, t.up_price);
    return map;
  });

  const rows = sortedSeconds.map((s) => [
    s,
    ...tickMaps.map((map) => map.get(s) ?? ""),
  ]);

  const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
  triggerDownload(csv, `all-assets-${interval}-${dateStr?.slice(0, 10)}.csv`);
}
