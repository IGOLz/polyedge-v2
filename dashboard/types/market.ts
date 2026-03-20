export interface Market {
  market_id: string;
  market_type: string;
  started_at: string;
  ended_at: string;
  final_outcome: string | null;
  resolved: boolean;
  tick_count: string;
}

export interface TickData {
  seconds: number;
  up_price: number;
}

export interface MarketTicks {
  market: Market;
  ticks: TickData[];
  asset: string;
}

export interface TickRate {
  marketType: string;
  last5m: number;
  last15m: number;
  last1h: number;
  last24h: number;
  collecting: boolean;
}

export interface TimeGroup {
  key: string;
  markets: Market[];
  started_at: string;
  ended_at: string;
}

export type Outcome = "Up" | "Down" | null;

export interface FilterOption {
  value: string;
  label: string;
}
