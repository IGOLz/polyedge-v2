"use client";

import { useState, useEffect, useCallback } from "react";
import { formatClockTime } from "@/lib/formatters";
import { POLLING_INTERVAL_MS } from "@/lib/constants";

export function usePollingFetch<T>(
  url: string,
  intervalMs = POLLING_INTERVAL_MS
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState("");

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(url);
      if (res.ok) {
        const json = await res.json();
        setData(json);
        setLastUpdated(formatClockTime());
      }
    } catch {
      // silently fail, will retry
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, intervalMs);
    return () => clearInterval(id);
  }, [fetchData, intervalMs]);

  return { data, loading, lastUpdated };
}
