"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import type { Market, TimeGroup } from "@/types/market";

function getUTCDateString(d: Date): string {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
}

function getTargetDateString(daysAgo: number): string {
  const now = new Date();
  const target = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - daysAgo)
  );
  return getUTCDateString(target);
}

const SHORT_MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export interface DateOption {
  key: string;
  label: string;
  dateString: string;
  count: number;
}

export function useMarkets(initialAsset: string, initialInterval: string, initialMarketId?: string | null) {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(initialMarketId ?? null);
  const [assetFilter, setAssetFilter] = useState(initialAsset);
  const [intervalFilter, setIntervalFilter] = useState(initialInterval);
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState("today");
  const [customDate, setCustomDate] = useState("");
  const [didAutoSelect, setDidAutoSelect] = useState(false);

  useEffect(() => {
    fetch("/api/markets")
      .then((r) => r.json())
      .then((data: Market[]) => {
        setMarkets(data);
        // Auto-select market from URL param
        if (initialMarketId && !didAutoSelect) {
          const target = data.find((m) => m.market_id === initialMarketId);
          if (target) {
            const targetDate = getUTCDateString(new Date(target.started_at));
            const todayStr = getTargetDateString(0);
            const yesterdayStr = getTargetDateString(1);
            if (targetDate === todayStr) {
              setSelectedDate("today");
            } else if (targetDate === yesterdayStr) {
              setSelectedDate("yesterday");
            } else {
              // Check days 2-6
              let found = false;
              for (let i = 2; i < 7; i++) {
                if (targetDate === getTargetDateString(i)) {
                  setSelectedDate(String(i));
                  found = true;
                  break;
                }
              }
              if (!found) {
                setSelectedDate("custom");
                setCustomDate(targetDate);
              }
            }
            setSelectedId(target.market_id);
            setDidAutoSelect(true);
          }
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const isAllAssets = assetFilter === "all";

  // Filter by asset + interval only (no date filter)
  const filteredByAssetInterval = useMemo(
    () =>
      markets.filter((m) => {
        const [mAsset, mInterval] = m.market_type?.split("_") || [];
        if (assetFilter !== "all" && mAsset !== assetFilter) return false;
        if (mInterval !== intervalFilter) return false;
        return true;
      }),
    [markets, assetFilter, intervalFilter]
  );

  // Build date options with counts
  const dateOptions = useMemo<DateOption[]>(() => {
    const countMap = new Map<string, number>();
    for (const m of filteredByAssetInterval) {
      const ds = getUTCDateString(new Date(m.started_at));
      countMap.set(ds, (countMap.get(ds) || 0) + 1);
    }

    const options: DateOption[] = [];
    for (let i = 0; i < 7; i++) {
      const ds = getTargetDateString(i);
      let label: string;
      if (i === 0) label = "Today";
      else if (i === 1) label = "Yesterday";
      else {
        const d = new Date(ds + "T00:00:00Z");
        label = `${SHORT_MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
      }
      options.push({
        key: i === 0 ? "today" : i === 1 ? "yesterday" : String(i),
        label,
        dateString: ds,
        count: countMap.get(ds) || 0,
      });
    }

    return options;
  }, [filteredByAssetInterval]);

  // Resolve the actual date string for the current selection
  const activeDateString = useMemo(() => {
    if (selectedDate === "custom") return customDate;
    const opt = dateOptions.find((o) => o.key === selectedDate);
    return opt?.dateString || getTargetDateString(0);
  }, [selectedDate, customDate, dateOptions]);

  // Count for custom date
  const customDateCount = useMemo(() => {
    if (selectedDate !== "custom" || !customDate) return 0;
    return filteredByAssetInterval.filter(
      (m) => getUTCDateString(new Date(m.started_at)) === customDate
    ).length;
  }, [filteredByAssetInterval, selectedDate, customDate]);

  // Markets for the selected date, reverse chronological
  const filteredMarkets = useMemo(() => {
    if (!activeDateString) return [];
    return filteredByAssetInterval
      .filter((m) => getUTCDateString(new Date(m.started_at)) === activeDateString)
      .sort(
        (a, b) =>
          new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
      );
  }, [filteredByAssetInterval, activeDateString]);

  // Time groups (for isAllAssets mode)
  const timeGroups = useMemo<TimeGroup[]>(() => {
    if (!isAllAssets) return [];
    const groups = new Map<string, Market[]>();
    for (const m of filteredMarkets) {
      const key = m.started_at;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(m);
    }
    return Array.from(groups.entries())
      .map(([key, mkts]) => ({
        key,
        markets: mkts,
        started_at: mkts[0].started_at,
        ended_at: mkts[0].ended_at,
      }))
      .sort(
        (a, b) =>
          new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
      );
  }, [isAllAssets, filteredMarkets]);

  // Auto-select first item when filter/date changes (skip if URL-based selection is active)
  useEffect(() => {
    const items = isAllAssets ? timeGroups : filteredMarkets;
    const getId = isAllAssets
      ? (item: TimeGroup) => item.key
      : (item: Market) => item.market_id;

    if (items.length > 0) {
      const exists = items.some((item: any) => getId(item) === selectedId);
      if (!selectedId || !exists) {
        setSelectedId(getId(items[0] as any));
      }
    } else {
      setSelectedId(null);
    }
  }, [filteredMarkets, timeGroups, selectedId, isAllAssets]);

  const selectedMarket = !isAllAssets
    ? filteredMarkets.find((m) => m.market_id === selectedId) || null
    : null;

  const selectedGroup = isAllAssets
    ? timeGroups.find((g) => g.key === selectedId) || null
    : null;

  const handleAssetFilter = useCallback((f: string) => {
    setAssetFilter(f);
    setSelectedId(null);
  }, []);

  const handleIntervalFilter = useCallback((f: string) => {
    setIntervalFilter(f);
    setSelectedId(null);
  }, []);

  const handleDateSelect = useCallback((key: string) => {
    setSelectedDate(key);
    setSelectedId(null);
  }, []);

  const handleCustomDate = useCallback((date: string) => {
    setCustomDate(date);
    setSelectedId(null);
  }, []);

  return {
    loading,
    filteredMarkets,
    timeGroups,
    isAllAssets,
    selectedId,
    setSelectedId,
    selectedMarket,
    selectedGroup,
    assetFilter,
    intervalFilter,
    handleAssetFilter,
    handleIntervalFilter,
    dateOptions,
    selectedDate,
    handleDateSelect,
    customDate,
    handleCustomDate,
    customDateCount,
    activeDateString,
  };
}
