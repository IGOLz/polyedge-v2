"use client";

import { useState, useEffect } from "react";
import type { TickData, Market, MarketTicks } from "@/types/market";

export function useMarketTicks(marketId: string) {
  const [ticks, setTicks] = useState<TickData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/market-ticks?market_id=${encodeURIComponent(marketId)}`)
      .then((r) => r.json())
      .then((data: TickData[]) => {
        if (Array.isArray(data)) setTicks(data);
      })
      .catch(() => setTicks([]))
      .finally(() => setLoading(false));
  }, [marketId]);

  return { ticks, loading };
}

export function useMultiMarketTicks(markets: Market[]) {
  const [marketTicks, setMarketTicks] = useState<MarketTicks[]>([]);
  const [loading, setLoading] = useState(true);

  const marketIds = markets.map((m) => m.market_id).join(",");

  useEffect(() => {
    if (markets.length === 0) return;

    setLoading(true);
    Promise.all(
      markets.map((market) =>
        fetch(`/api/market-ticks?market_id=${encodeURIComponent(market.market_id)}`)
          .then((r) => r.json())
          .then((data: TickData[]) => ({
            market,
            ticks: Array.isArray(data) ? data : [],
            asset: market.market_type?.split("_")[0] || "",
          }))
          .catch(() => ({
            market,
            ticks: [] as TickData[],
            asset: market.market_type?.split("_")[0] || "",
          }))
      )
    ).then((results) => {
      setMarketTicks(results);
      setLoading(false);
    });
  }, [marketIds]);

  return { marketTicks, loading };
}
