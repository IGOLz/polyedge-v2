"use client";

import { useState, useEffect } from "react";
import { formatClockTime } from "@/lib/formatters";

export function useLiveClock(intervalMs = 1000) {
  const [time, setTime] = useState("");

  useEffect(() => {
    const update = () => setTime(formatClockTime());
    update();
    const id = setInterval(update, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return time;
}
