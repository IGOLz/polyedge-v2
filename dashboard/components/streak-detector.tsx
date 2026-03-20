import { Badge } from "@/components/ui/badge";
import { GlassPanel } from "@/components/ui/glass-panel";

const ASSET_NAMES: Record<string, string> = {
  btc: "Bitcoin",
  eth: "Ethereum",
  sol: "Solana",
  xrp: "XRP",
};

function assetLabel(marketType: string): string {
  const asset = marketType.split("_")[0];
  return ASSET_NAMES[asset] || asset.toUpperCase();
}

interface StreakData {
  marketType: string;
  streakLength: number;
  streakDirection: string;
  lastTen: string[];
}

interface StreakDetectorProps {
  data: StreakData[];
}

function StreakCard({ streak }: { streak: StreakData }) {
  return (
    <GlassPanel variant="glow-br" className="p-6">
      <div className="relative">
        <div className="mb-4 flex items-center justify-between">
          <span className="text-base font-semibold tracking-tight text-zinc-100">
            {assetLabel(streak.marketType)}
          </span>
          <Badge variant={streak.streakDirection === "Up" ? "up" : "down"}>
            {streak.streakLength}x {streak.streakDirection}
          </Badge>
        </div>

        <div className="mt-5 flex items-center gap-1.5">
          <div
            className="h-2.5 w-2.5 rounded-full bg-primary animate-pulse"
            title="Live"
          />
          {streak.lastTen.map((outcome, i) => (
            <div
              key={i}
              className={`h-2.5 w-2.5 rounded-full ${
                outcome === "Up" ? "bg-emerald-400" : "bg-red-400"
              }`}
              title={outcome}
            />
          ))}
          {streak.lastTen.length === 0 && (
            <span className="text-xs text-zinc-500">No data</span>
          )}
        </div>

        <p className="mt-2 text-xs text-zinc-400">
          Last {streak.lastTen.length} outcomes (newest first)
        </p>
      </div>
    </GlassPanel>
  );
}

export function StreakDetector({ data }: StreakDetectorProps) {
  if (data.length === 0) {
    return (
      <GlassPanel variant="glow-br" className="p-8 text-center text-sm text-zinc-500">
        Not enough data yet
      </GlassPanel>
    );
  }

  const data5m = data.filter((d) => d.marketType.endsWith("_5m"));
  const data15m = data.filter((d) => d.marketType.endsWith("_15m"));

  return (
    <div className="space-y-8">
      <div>
        <p className="mb-4 text-sm font-semibold text-zinc-300">5m Markets</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {data5m.map((streak) => (
            <StreakCard key={streak.marketType} streak={streak} />
          ))}
        </div>
      </div>
      <div>
        <p className="mb-4 text-sm font-semibold text-zinc-300">15m Markets</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {data15m.map((streak) => (
            <StreakCard key={streak.marketType} streak={streak} />
          ))}
        </div>
      </div>
    </div>
  );
}
