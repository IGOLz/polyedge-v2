"use client";

import React, {
	useEffect,
	useState,
	useCallback,
	useMemo,
	useRef,
} from "react";
import { useRouter } from "next/navigation";
import {
	XAxis,
	YAxis,
	ReferenceLine,
	Area,
	ComposedChart,
	ResponsiveContainer,
	Tooltip as RechartsTooltip,
	CartesianGrid,
	Line,
} from "recharts";
import {
	ArrowUpRight,
	ArrowDownRight,
	Trophy,
	X,
	AlertTriangle,
	Circle,
	SkipForward,
	Clock,
	Power,
	AlertCircle,
	Ghost,
	ChevronDown,
	ChevronRight,
} from "lucide-react";
import { SectionHeader } from "@/components/section-header";
import { DownloadButton } from "@/components/download-button";
import { GlassPanel } from "@/components/ui/glass-panel";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface OverviewData {
	overall: {
		total_trades: string;
		wins: string;
		losses: string;
		pending: string;
		no_fills: string;
		skipped: string;
		total_pnl: string | null;
		total_bet: string | null;
		avg_pnl_per_trade: string | null;
	} | null;
	last24h: {
		trades_24h: string;
		wins_24h: string;
		losses_24h: string;
		pnl_24h: string | null;
		bet_24h: string | null;
	} | null;
	yesterday: {
		trades_yesterday: string;
		wins_yesterday: string;
		losses_yesterday: string;
		pnl_yesterday: string | null;
	} | null;
}

interface TradeRow {
	id: string;
	market_id: string | null;
	market_type: string;
	strategy_name: string;
	direction: string;
	entry_price: string;
	bet_size_usd: string;
	status: string;
	final_outcome: string | null;
	pnl: string | null;
	placed_at: string;
	resolved_at: string | null;
	confidence_multiplier: string | null;
	shares: string | null;
	stop_loss_price: string | null;
	take_profit_price: string | null;
	stop_loss_triggered: boolean | null;
	stop_loss_order_id: string | null;
	notes: string | null;
	signal_data: Record<string, unknown> | null;
}

interface ActivityData {
	trades: TradeRow[];
	logs: {
		id: string;
		log_type: string;
		message: string;
		data: string | null;
		logged_at: string;
	}[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pf(val: string | null | undefined): number {
	if (val == null) return 0;
	const n = parseFloat(val);
	return isNaN(n) ? 0 : n;
}

function fmtPnl(val: number): string {
	if (val === 0) return "$0.00";
	const prefix = val >= 0 ? "$" : "-$";
	return `${prefix}${Math.abs(val).toFixed(2)}`;
}

/** Recalculate PnL from trade parameters (Polymarket binary options). */
function calcPnl(t: TradeRow): number | null {
	if (!t.final_outcome) return null;
	const entry = parseFloat(t.entry_price);
	const betSize = parseFloat(t.bet_size_usd);
	if (Number.isNaN(entry) || Number.isNaN(betSize) || entry === 0) return null;
	const shares = t.shares ? parseFloat(t.shares) : betSize / entry;

	if (t.final_outcome === "win" || t.final_outcome === "win_resolution") {
		return shares * (1.0 - entry);
	} else if (t.final_outcome === "loss") {
		return -betSize;
	} else if (t.final_outcome === "stop_loss") {
		const slPrice = t.stop_loss_price ? parseFloat(t.stop_loss_price) : 0;
		return (slPrice - entry) * shares;
	} else if (t.final_outcome === "take_profit") {
		const tpPrice = t.take_profit_price ? parseFloat(t.take_profit_price) : 0;
		return (tpPrice - entry) * shares;
	}
	return null;
}

function fmtDollar(val: number): string {
	return `$${val.toFixed(2)}`;
}

function fmtPercent(val: number): string {
	return `${val.toFixed(1)}%`;
}

function fmtMarket(mt: string): string {
	const parts = mt.split("_");
	if (parts.length === 2) return `${parts[0].toUpperCase()} ${parts[1]}`;
	return mt;
}

function fmtPrice(price: number): string {
	if (price >= 1) return `$${price.toFixed(2)}`;
	return `${Math.round(price * 100)}¢`;
}

function fmtTime(ts: string): string {
	const d = new Date(ts);
	return d.toLocaleTimeString("en-GB", {
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
		timeZone: "UTC",
	});
}

function fmtDateTime(ts: string): string {
	const d = new Date(ts);
	const time = d.toLocaleTimeString("en-GB", {
		hour: "2-digit",
		minute: "2-digit",
		timeZone: "UTC",
	});
	const date = d.toLocaleDateString("en-GB", {
		day: "2-digit",
		month: "2-digit",
		timeZone: "UTC",
	});
	return `${time} ${date}`;
}

function parseJsonSafe(
	data: string | null | undefined,
): Record<string, unknown> | null {
	if (!data) return null;
	try {
		return typeof data === "object" ? data : JSON.parse(data);
	} catch {
		return null;
	}
}

function pnlColor(val: number): string {
	return val > 0
		? "text-emerald-400"
		: val < 0
			? "text-red-400"
			: "text-zinc-400";
}

const STRATEGY_COLORS: Record<
	string,
	{ badge: string; border: string; glow: string }
> = {
	// Active strategies
	spike_reversion: {
		badge: "bg-amber-500/10 text-amber-400 border-amber-500/20",
		border: "border-amber-500/20",
		glow: "via-amber-500/40",
	},
	m3: {
		badge: "bg-amber-500/10 text-amber-400 border-amber-500/20",
		border: "border-amber-500/20",
		glow: "via-amber-500/40",
	},
	volatility: {
		badge: "bg-violet-500/10 text-violet-400 border-violet-500/20",
		border: "border-violet-500/20",
		glow: "via-violet-500/40",
	},
	m4: {
		badge: "bg-violet-500/10 text-violet-400 border-violet-500/20",
		border: "border-violet-500/20",
		glow: "via-violet-500/40",
	},
	// Legacy strategies (for historical trades)
	momentum: {
		badge: "bg-blue-500/10 text-blue-400 border-blue-500/20",
		border: "border-blue-500/20",
		glow: "via-blue-500/40",
	},
};

function getStrategyStyle(name: string) {
	const key = name.toLowerCase();
	for (const [k, v] of Object.entries(STRATEGY_COLORS)) {
		if (key.includes(k)) return v;
	}
	return {
		badge: "bg-primary/10 text-primary border-primary/20",
		border: "border-primary/20",
		glow: "via-primary/40",
	};
}

// ---------------------------------------------------------------------------
// Filter button row (matches strategy3 exactly)
// ---------------------------------------------------------------------------

function FilterRow({
	options,
	selected,
	onSelect,
}: {
	options: { value: string; label: string }[];
	selected: string;
	onSelect: (v: string) => void;
}) {
	return (
		<div className="flex items-center gap-1 overflow-x-auto pb-1 scrollbar-thin">
			{options.map((opt) => (
				<button
					key={opt.value}
					onClick={() => onSelect(opt.value)}
					className={cn(
						"flex-shrink-0 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
						selected === opt.value
							? "bg-primary/[0.12] text-primary border border-primary/30"
							: "bg-zinc-900/60 text-zinc-400 border border-zinc-800/40 hover:text-zinc-200 hover:border-zinc-700/60",
					)}
				>
					{opt.label}
				</button>
			))}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Chart tooltip (matches strategy3 exactly)
// ---------------------------------------------------------------------------

function ChartTooltipContent({
	active,
	payload,
	label,
}: {
	active?: boolean;
	payload?: Array<{ value: number; name: string }>;
	label?: string;
}) {
	if (!active || !payload?.length) return null;
	return (
		<div className="rounded-lg border border-zinc-700/60 bg-zinc-900/95 px-3 py-2 shadow-xl backdrop-blur-sm">
			<p className="text-xs font-medium text-zinc-300 mb-1">{label}</p>
			{payload.map((p, i) => (
				<p
					key={i}
					className={cn(
						"text-xs font-mono font-semibold",
						p.value >= 0 ? "text-emerald-400" : "text-red-400",
					)}
				>
					{fmtPnl(p.value)}
				</p>
			))}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Status dot for bot health
// ---------------------------------------------------------------------------

function BotStatusDot({ lastTradeAt }: { lastTradeAt: string | null }) {
	if (!lastTradeAt)
		return <span className="h-3 w-3 rounded-full bg-zinc-600" />;
	const diffMs = Date.now() - new Date(lastTradeAt).getTime();
	const diffMin = diffMs / 60000;

	if (diffMin <= 10) {
		return (
			<span className="relative flex h-3 w-3">
				<span className="absolute inset-0 rounded-full bg-emerald-400 animate-ping opacity-40" />
				<span className="relative h-3 w-3 rounded-full bg-emerald-400 shadow-lg shadow-emerald-400/40" />
			</span>
		);
	}
	if (diffMin <= 60) {
		return (
			<span className="h-3 w-3 rounded-full bg-yellow-400 shadow-lg shadow-yellow-400/40" />
		);
	}
	return (
		<span className="h-3 w-3 rounded-full bg-red-400 shadow-lg shadow-red-400/40" />
	);
}

// ---------------------------------------------------------------------------
// Log type icon
// ---------------------------------------------------------------------------

function LogIcon({ logType }: { logType: string }) {
	const size = 14;
	switch (logType) {
		case "trade_placed":
			return <ArrowUpRight size={size} className="text-emerald-400" />;
		case "trade_win":
		case "trade_win_resolution":
		case "trade_take_profit":
			return <Trophy size={size} className="text-emerald-400" />;
		case "trade_loss":
			return <X size={size} className="text-red-400" />;
		case "trade_stop_loss":
			return <AlertTriangle size={size} className="text-yellow-400" />;
		case "trade_fok_no_fill":
			return <Circle size={size} className="text-zinc-500" />;
		case "trade_skipped":
			return <SkipForward size={size} className="text-zinc-500" />;
		case "hourly_summary":
			return <Clock size={size} className="text-blue-400" />;
		case "bot_start":
			return <Power size={size} className="text-zinc-300" />;
		case "bot_error":
			return <AlertCircle size={size} className="text-red-400" />;
		case "trade_dry_run":
			return <Ghost size={size} className="text-yellow-400" />;
		default:
			return <Circle size={size} className="text-zinc-500" />;
	}
}

function logRowBg(logType: string): string {
	switch (logType) {
		case "trade_win":
		case "trade_win_resolution":
		case "trade_take_profit":
			return "bg-emerald-500/[0.04]";
		case "trade_loss":
			return "bg-red-500/[0.04]";
		case "trade_stop_loss":
			return "bg-yellow-500/[0.04]";
		case "hourly_summary":
			return "bg-blue-500/[0.04]";
		default:
			return "";
	}
}

// ---------------------------------------------------------------------------
// Section 1 — Overview Cards (dashboard grid style)
// ---------------------------------------------------------------------------

function OverviewCards({ overview }: { overview: OverviewData }) {
	const o = overview.overall;
	const h = overview.last24h;
	const y = overview.yesterday;

	const STARTING_BALANCE = 199.16;
	const totalPnl = pf(o?.total_pnl);
	const currentBalance = STARTING_BALANCE + totalPnl;
	const wins = pf(o?.wins);
	const losses = pf(o?.losses);
	const winRate = wins + losses > 0 ? (wins / (wins + losses)) * 100 : 0;

	// Today
	const pnl24h = pf(h?.pnl_24h);
	const trades24h = pf(h?.trades_24h);
	const wins24h = pf(h?.wins_24h);
	const losses24h = pf(h?.losses_24h);

	// Yesterday
	const pnlYesterday = pf(y?.pnl_yesterday);
	const tradesYesterday = pf(y?.trades_yesterday);
	const winsYesterday = pf(y?.wins_yesterday);
	const lossesYesterday = pf(y?.losses_yesterday);

	const topCards = [
		{ label: "Total PnL", value: fmtPnl(totalPnl), color: pnlColor(totalPnl) },
		{
			label: "Win Rate",
			value: wins + losses > 0 ? fmtPercent(winRate) : "—",
			color:
				winRate > 55
					? "text-emerald-400"
					: winRate >= 45
						? "text-yellow-400"
						: wins + losses > 0
							? "text-red-400"
							: "text-zinc-50",
		},
		{
			label: "Starting Balance",
			value: fmtDollar(STARTING_BALANCE),
			color: "text-zinc-50",
		},
		{
			label: "Current Balance",
			value: fmtDollar(currentBalance),
			color: "text-zinc-50",
		},
	];

	return (
		<section className="mb-8 md:mb-14">
			<SectionHeader title="Bot Overview" />

			{/* Top row — 4 main stat cards */}
			<div className="relative grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-primary/20 bg-primary/[0.06] sm:grid-cols-4">
				<div className="absolute inset-x-0 top-0 z-10 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />
				{topCards.map((card, i) => (
					<div
						key={card.label}
						className="group relative bg-zinc-950 p-4 md:p-6 transition-colors hover:bg-zinc-900/80 animate-slide-up"
						style={{ animationDelay: `${i * 80}ms` }}
					>
						<div className="absolute -top-10 -right-10 h-20 w-20 rounded-full bg-primary/[0.05] blur-2xl" />
						<div className="absolute inset-0 bg-gradient-to-b from-primary/[0.03] to-transparent" />
						<p className="relative text-xs font-semibold uppercase tracking-[0.15em] text-primary/60">
							{card.label}
						</p>
						<p
							className={cn(
								"relative mt-2 font-mono text-2xl font-bold tabular-nums",
								card.color,
							)}
						>
							{card.value}
						</p>
					</div>
				))}
			</div>

			{/* Today vs Yesterday comparison */}
			<div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
				{/* Today */}
				<GlassPanel variant="glow-tl">
					<div className="relative p-5">
						<p className="text-xs font-semibold uppercase tracking-[0.15em] text-primary/60 mb-4">
							Today (24h)
						</p>
						<div className="grid grid-cols-3 gap-6">
							<div>
								<p className="text-xs uppercase tracking-wider text-zinc-400">
									PnL
								</p>
								<p
									className={cn(
										"mt-1 font-mono text-2xl font-bold tabular-nums",
										pnlColor(pnl24h),
									)}
								>
									{fmtPnl(pnl24h)}
								</p>
							</div>
							<div>
								<p className="text-xs uppercase tracking-wider text-zinc-400">
									Trades
								</p>
								<p className="mt-1 font-mono text-2xl font-bold tabular-nums text-zinc-200">
									{trades24h}
								</p>
							</div>
							<div>
								<p className="text-xs uppercase tracking-wider text-zinc-400">
									W / L
								</p>
								<p className="mt-1 font-mono text-2xl font-bold tabular-nums text-zinc-200">
									<span className="text-emerald-400">{wins24h}</span>
									{" / "}
									<span className="text-red-400">{losses24h}</span>
								</p>
							</div>
						</div>
					</div>
				</GlassPanel>

				{/* Yesterday */}
				<GlassPanel variant="glow-tr">
					<div className="relative p-5">
						<p className="text-xs font-semibold uppercase tracking-[0.15em] text-primary/60 mb-4">
							Yesterday
						</p>
						<div className="grid grid-cols-3 gap-6">
							<div>
								<p className="text-xs uppercase tracking-wider text-zinc-400">
									PnL
								</p>
								<p
									className={cn(
										"mt-1 font-mono text-2xl font-bold tabular-nums",
										pnlColor(pnlYesterday),
									)}
								>
									{fmtPnl(pnlYesterday)}
								</p>
							</div>
							<div>
								<p className="text-xs uppercase tracking-wider text-zinc-400">
									Trades
								</p>
								<p className="mt-1 font-mono text-2xl font-bold tabular-nums text-zinc-200">
									{tradesYesterday}
								</p>
							</div>
							<div>
								<p className="text-xs uppercase tracking-wider text-zinc-400">
									W / L
								</p>
								<p className="mt-1 font-mono text-2xl font-bold tabular-nums text-zinc-200">
									<span className="text-emerald-400">{winsYesterday}</span>
									{" / "}
									<span className="text-red-400">{lossesYesterday}</span>
								</p>
							</div>
						</div>
					</div>
				</GlassPanel>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Section 4 — Cumulative PnL Chart (GlassPanel)
// ---------------------------------------------------------------------------

function PnlChart() {
	const [chartData, setChartData] = useState<
		{ time: string; pnl: number }[] | null
	>(null);

	useEffect(() => {
		fetch("/api/bot-pnl-chart")
			.then((res) => res.json())
			.then((data) => {
				const trades: { placed_at: string; pnl: string }[] = data.trades ?? [];
				if (trades.length < 2) {
					setChartData(null);
					return;
				}
				let cumulative = 0;
				setChartData(
					trades.map((t) => {
						cumulative += pf(t.pnl);
						return {
							time: fmtDateTime(t.placed_at),
							pnl: parseFloat(cumulative.toFixed(2)),
						};
					}),
				);
			})
			.catch(() => setChartData(null));
	}, []);

	return (
		<section className="mb-8 md:mb-14">
			<SectionHeader
				title="Cumulative PnL"
				description="Running profit/loss across all resolved trades over time."
			/>
			<GlassPanel variant="glow-center">
				<div className="relative p-4">
					{!chartData ? (
						<p className="text-sm text-zinc-500 text-center py-12">
							Not enough resolved trades yet.
						</p>
					) : (
						<ResponsiveContainer width="100%" height={300}>
							<ComposedChart
								data={chartData}
								margin={{ top: 10, right: 10, bottom: 10, left: 0 }}
							>
								<CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
								<XAxis
									dataKey="time"
									tick={{ fontSize: 11, fill: "#71717a" }}
									tickLine={false}
									axisLine={false}
									interval="preserveStartEnd"
								/>
								<YAxis
									tick={{ fontSize: 11, fill: "#71717a" }}
									tickLine={false}
									axisLine={false}
									tickFormatter={(v: number) => `$${v}`}
								/>
								<RechartsTooltip content={<ChartTooltipContent />} />
								<ReferenceLine y={0} stroke="#3f3f46" strokeDasharray="4 4" />
								<defs>
									<linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
										<stop
											offset="0%"
											stopColor={
												chartData[chartData.length - 1].pnl >= 0
													? "#4ade80"
													: "#f87171"
											}
											stopOpacity={0.45}
										/>
										<stop
											offset="100%"
											stopColor={
												chartData[chartData.length - 1].pnl >= 0
													? "#4ade80"
													: "#f87171"
											}
											stopOpacity={0.05}
										/>
									</linearGradient>
								</defs>
								<Area
									type="monotone"
									dataKey="pnl"
									fill="url(#pnlGradient)"
									stroke="none"
								/>
								<Line
									type="monotone"
									dataKey="pnl"
									stroke="hsl(var(--primary))"
									strokeWidth={2.5}
									dot={false}
									activeDot={{ r: 4, fill: "hsl(var(--primary))" }}
								/>
							</ComposedChart>
						</ResponsiveContainer>
					)}
				</div>
			</GlassPanel>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Section 5 — Live Activity Feed (GlassPanel, fixed-height scroll)
// ---------------------------------------------------------------------------

const LOG_FILTERS = [
	{ value: "all", label: "All" },
	{ value: "trades", label: "Trades" },
	{ value: "wins_losses", label: "Wins/Losses" },
	{ value: "summaries", label: "Summaries" },
	{ value: "errors", label: "Errors" },
];

const LOG_PAGE_SIZE = 50;
const LOG_MAX = 1000;

function ActivityFeed({ logs }: { logs: ActivityData["logs"] }) {
	const [filter, setFilter] = useState("all");
	const [visibleCount, setVisibleCount] = useState(LOG_PAGE_SIZE);

	const filtered = useMemo(() => {
		if (filter === "all") return logs;
		if (filter === "trades")
			return logs.filter((l) =>
				[
					"trade_placed",
					"trade_win",
					"trade_win_resolution",
					"trade_take_profit",
					"trade_loss",
					"trade_stop_loss",
					"trade_redeemed",
					"trade_fok_no_fill",
					"trade_skipped",
					"trade_dry_run",
				].includes(l.log_type),
			);
		if (filter === "wins_losses")
			return logs.filter((l) =>
				["trade_win", "trade_win_resolution", "trade_take_profit", "trade_loss", "trade_stop_loss"].includes(l.log_type),
			);
		if (filter === "summaries")
			return logs.filter((l) => l.log_type === "hourly_summary");
		if (filter === "errors")
			return logs.filter((l) => l.log_type === "bot_error");
		return logs;
	}, [logs, filter]);

	const visible = filtered.slice(0, visibleCount);
	const hasMore = visibleCount < filtered.length && visibleCount < LOG_MAX;

	const handleScroll = useCallback(
		(e: React.UIEvent<HTMLDivElement>) => {
			const el = e.currentTarget;
			if (el.scrollHeight - el.scrollTop - el.clientHeight < 80 && hasMore) {
				setVisibleCount((c) => Math.min(c + LOG_PAGE_SIZE, LOG_MAX));
			}
		},
		[hasMore],
	);

	return (
		<section className="mb-8 md:mb-14">
			<SectionHeader
				title="Live Activity"
				description="Most recent bot log entries."
			/>
			<GlassPanel variant="glow-tl">
				<div className="relative border-b border-zinc-800/60 px-6 py-3">
					<FilterRow
						options={LOG_FILTERS}
						selected={filter}
						onSelect={(v) => {
							setFilter(v);
							setVisibleCount(LOG_PAGE_SIZE);
						}}
					/>
				</div>
				<div
					className="relative h-[480px] overflow-y-auto scrollbar-thin"
					onScroll={handleScroll}
				>
					{visible.length === 0 ? (
						<p className="text-sm text-zinc-500 text-center py-12">
							No activity to show.
						</p>
					) : (
						<div className="divide-y divide-zinc-800/20">
							{visible.map((log) => {
								const data = parseJsonSafe(log.data);
								const showBadge =
									["trade_placed", "trade_win", "trade_win_resolution", "trade_take_profit", "trade_loss"].includes(
										log.log_type,
									) && data;

								return (
									<div
										key={log.id}
										className={cn(
											"flex items-start gap-3 px-6 py-3 transition-colors",
											logRowBg(log.log_type),
										)}
									>
										<div className="mt-0.5 flex-shrink-0">
											<LogIcon logType={log.log_type} />
										</div>
										<div className="min-w-0 flex-1">
											<p className="text-sm text-zinc-200 truncate">
												{log.message}
											</p>
											{showBadge && data && (
												<div className="mt-1 flex gap-1.5">
													{typeof data.market_type === "string" && (
														<Badge variant="default">
															{fmtMarket(data.market_type)}
														</Badge>
													)}
													{typeof data.direction === "string" && (
														<Badge
															variant={String(data.direction).toLowerCase() === "up" ? "up" : "down"}
														>
															{data.direction.toUpperCase()}
														</Badge>
													)}
												</div>
											)}
										</div>
										<span className="flex-shrink-0 text-xs text-zinc-500 tabular-nums">
											{fmtTime(log.logged_at)}
										</span>
									</div>
								);
							})}
							{hasMore && (
								<div className="py-3 text-center">
									<span className="text-xs text-zinc-600">
										Scroll for more...
									</span>
								</div>
							)}
							{visibleCount >= LOG_MAX && filtered.length > LOG_MAX && (
								<div className="py-3 text-center">
									<span className="text-xs text-zinc-500">
										Showing max {LOG_MAX} entries
									</span>
								</div>
							)}
						</div>
					)}
				</div>
			</GlassPanel>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Section 6 — Trade History Table (GlassPanel, infinite scroll)
// ---------------------------------------------------------------------------

const TRADE_FILTERS = [
	{ value: "all", label: "All" },
	{ value: "wins", label: "Wins" },
	{ value: "losses", label: "Losses" },
	{ value: "stop_loss", label: "Stop Loss" },
	{ value: "live", label: "Live" },
];

const TRADE_BATCH = 100;

/** Extract the primary signal metric for table display. */
function getSignalMetric(trade: TradeRow): {
	value: string;
	color: string;
} | null {
	const sd = trade.signal_data;
	if (sd) {
		// M4: volatility
		if (sd.volatility_avg != null) {
			const vol = Number(sd.volatility_avg);
			return {
				value: `σ ${vol.toFixed(4)}`,
				color: vol >= 0.05 ? "text-yellow-400" : "text-zinc-400",
			};
		}
		// M3: spike info
		if (sd.spike_price != null) {
			const spike = Number(sd.spike_price);
			const dir = sd.spike_direction === "Up" ? "↑" : "↓";
			return {
				value: `${dir} ${spike.toFixed(2)}`,
				color:
					sd.spike_direction === "Up" ? "text-emerald-400" : "text-red-400",
			};
		}
	}
	// Legacy: momentum from notes
	const parsed = parseJsonSafe(trade.notes);
	if (parsed?.momentum_value != null) {
		const m = Number(parsed.momentum_value);
		if (!Number.isNaN(m)) {
			return {
				value: `${m >= 0 ? "+" : ""}${m.toFixed(3)}`,
				color: m >= 0 ? "text-emerald-400" : "text-red-400",
			};
		}
	}
	return null;
}

/** Extract secondary signal detail for table display. */
function getSignalDetail(trade: TradeRow): {
	value: string;
	color: string;
} | null {
	const sd = trade.signal_data;
	if (sd) {
		// M4: spread
		if (sd.spread != null) {
			return { value: Number(sd.spread).toFixed(3), color: "text-zinc-300" };
		}
		// M3: reversion ticks
		if (sd.reversion_ticks_elapsed != null) {
			return {
				value: `${sd.reversion_ticks_elapsed}t`,
				color: "text-zinc-300",
			};
		}
	}
	// Legacy: confidence multiplier
	const cm =
		trade.confidence_multiplier != null
			? parseFloat(trade.confidence_multiplier)
			: null;
	if (cm != null && !Number.isNaN(cm)) {
		return { value: `${cm.toFixed(1)}x`, color: "text-zinc-400" };
	}
	return null;
}

function SignalTooltip({ trade }: { trade: TradeRow }) {
	const sd = trade.signal_data;
	if (!sd) return null;

	const isM4 = sd.volatility_avg != null;
	const isM3 = sd.spike_price != null;
	if (!isM4 && !isM3) return null;

	return (
		<div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 hidden group-hover:block pointer-events-none">
			<div className="rounded-lg border border-zinc-700/60 bg-zinc-900/95 px-3 py-2 shadow-xl backdrop-blur-sm whitespace-nowrap">
				<p className="text-xs font-medium text-zinc-300 mb-1">
					{isM3 ? "M3 Spike Reversion" : "M4 Volatility"}
				</p>
				{isM4 && (
					<>
						<p className="text-xs text-zinc-400">
							Volatility:{" "}
							<span className="text-yellow-400 font-mono">
								σ {Number(sd.volatility_avg).toFixed(4)}
							</span>
						</p>
						<p className="text-xs text-zinc-400">
							Spread:{" "}
							<span className="text-zinc-200 font-mono">
								{Number(sd.spread).toFixed(3)}
							</span>
						</p>
						{sd.up_price != null && (
							<p className="text-xs text-zinc-400">
								Up/Down:{" "}
								<span className="text-zinc-200 font-mono">
									{fmtPrice(Number(sd.up_price))} /{" "}
									{fmtPrice(Number(sd.down_price))}
								</span>
							</p>
						)}
					</>
				)}
				{isM3 && (
					<>
						<p className="text-xs text-zinc-400">
							Spike:{" "}
							<span
								className={cn(
									"font-mono",
									sd.spike_direction === "Up"
										? "text-emerald-400"
										: "text-red-400",
								)}
							>
								{String(sd.spike_direction)} → {Number(sd.spike_price).toFixed(2)}
							</span>
						</p>
						<p className="text-xs text-zinc-400">
							Reversion:{" "}
							<span className="text-zinc-200 font-mono">
								{Number(sd.reversion_target).toFixed(2)} ({String(sd.reversion_ticks_elapsed)}t)
							</span>
						</p>
					</>
				)}
				{sd.entry_price != null && (
					<p className="text-xs text-zinc-400">
						Entry:{" "}
						<span className="text-zinc-200 font-mono">
							{fmtPrice(Number(sd.entry_price))}
						</span>
					</p>
				)}
			</div>
			<div className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-l-transparent border-r-transparent border-t-zinc-700/60" />
		</div>
	);
}

function buildMarketUrl(t: TradeRow): string {
	if (!t.market_id) return "";
	return `/markets?type=${encodeURIComponent(t.market_type)}&market_id=${encodeURIComponent(t.market_id)}`;
}

function SignalDataPanel({ data }: { data: Record<string, unknown> }) {
	const items: {
		label: string;
		key: string;
		format?: (v: unknown) => string;
		highlight?: (v: unknown) => string;
	}[] = [
		// M4-specific
		{ label: "Up Price", key: "up_price", format: (v) => fmtPrice(Number(v)) },
		{
			label: "Down Price",
			key: "down_price",
			format: (v) => fmtPrice(Number(v)),
		},
		{ label: "Spread", key: "spread", format: (v) => Number(v).toFixed(4) },
		{
			label: "Volatility (Avg)",
			key: "volatility_avg",
			format: (v) => `σ ${Number(v).toFixed(6)}`,
			highlight: () => "text-yellow-400",
		},
		{
			label: "Volatility (Up)",
			key: "volatility_up",
			format: (v) => Number(v).toFixed(6),
		},
		{
			label: "Volatility (Down)",
			key: "volatility_down",
			format: (v) => Number(v).toFixed(6),
		},
		{ label: "Eval Second", key: "eval_second", format: (v) => `${v}s` },
		// M3-specific
		{
			label: "Spike Direction",
			key: "spike_direction",
			highlight: (v) =>
				v === "Up" ? "text-emerald-400" : "text-red-400",
		},
		{
			label: "Spike Price",
			key: "spike_price",
			format: (v) => fmtPrice(Number(v)),
		},
		{ label: "Spike Tick", key: "spike_tick" },
		{
			label: "Reversion Target",
			key: "reversion_target",
			format: (v) => fmtPrice(Number(v)),
		},
		{ label: "Reversion Tick", key: "reversion_tick" },
		{ label: "Reversion Ticks", key: "reversion_ticks_elapsed" },
		// Shared
		{
			label: "Entry Price",
			key: "entry_price",
			format: (v) => fmtPrice(Number(v)),
		},
		{ label: "Shares", key: "shares", format: (v) => Number(v).toFixed(0) },
		{ label: "Bet Cost", key: "bet_cost", format: (v) => fmtDollar(Number(v)) },
		{ label: "Bet Size", key: "bet_size", format: (v) => fmtDollar(Number(v)) },
		{
			label: "Stop Loss",
			key: "stop_loss_price",
			format: (v) => fmtPrice(Number(v)),
		},
		{
			label: "Balance",
			key: "balance_at_signal",
			format: (v) => fmtDollar(Number(v)),
		},
		{
			label: "Elapsed",
			key: "seconds_elapsed",
			format: (v) => `${v}s`,
		},
		{
			label: "Remaining",
			key: "seconds_remaining",
			format: (v) => `${v}s`,
		},
		// Legacy momentum fields
		{ label: "Price A", key: "price_a", format: (v) => fmtPrice(Number(v)) },
		{ label: "Price B", key: "price_b", format: (v) => fmtPrice(Number(v)) },
		{
			label: "Price Open",
			key: "price_open",
			format: (v) => fmtPrice(Number(v)),
		},
		{
			label: "Momentum",
			key: "momentum_value",
			format: (v) => {
				const n = Number(v);
				return `${n >= 0 ? "+" : ""}${n.toFixed(4)}`;
			},
			highlight: (v) =>
				Number(v) >= 0 ? "text-emerald-400" : "text-red-400",
		},
		{
			label: "Price A Offset",
			key: "price_a_seconds",
			format: (v) => `${v}s`,
		},
		{
			label: "Price B Offset",
			key: "price_b_seconds",
			format: (v) => `${v}s`,
		},
	];

	const available = items.filter((i) => data[i.key] != null);
	if (available.length === 0)
		return <p className="text-xs text-zinc-500">No signal data available.</p>;

	// Show thesis as a full-width row if present
	const thesis = data.profitability_thesis;

	return (
		<div>
			<div className="grid grid-cols-2 gap-x-8 gap-y-1.5 sm:grid-cols-3 md:grid-cols-4">
				{available.map((item) => {
					const raw = data[item.key];
					const formatted = item.format ? item.format(raw) : String(raw);
					const colorClass = item.highlight
						? item.highlight(raw)
						: "text-zinc-200";
					return (
						<div
							key={item.key}
							className="flex items-baseline justify-between gap-2"
						>
							<span className="text-xs text-zinc-500">{item.label}</span>
							<span
								className={cn(
									"font-mono text-sm tabular-nums",
									colorClass,
								)}
							>
								{formatted}
							</span>
						</div>
					);
				})}
			</div>
			{typeof thesis === "string" && (
				<p className="mt-2 text-xs text-zinc-500 italic">{thesis}</p>
			)}
		</div>
	);
}

function TradeHistory({ initialTrades }: { initialTrades: TradeRow[] }) {
	const router = useRouter();
	const [filter, setFilter] = useState("all");
	const [allTrades, setAllTrades] = useState<TradeRow[]>(initialTrades);
	const [loadingMore, setLoadingMore] = useState(false);
	const [hasMore, setHasMore] = useState(true);
	const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
	const sentinelRef = useRef<HTMLDivElement>(null);
	const scrollRef = useRef<HTMLDivElement>(null);
	const offsetRef = useRef(initialTrades.length);

	// Sync when parent refreshes initial data
	useEffect(() => {
		setAllTrades(initialTrades);
		offsetRef.current = initialTrades.length;
		setHasMore(true);
	}, [initialTrades]);

	// Only show filled trades — exclude skipped and no-fill
	const filledTrades = useMemo(
		() => allTrades.filter((t) => t.status === "filled"),
		[allTrades],
	);

	// Client-side filtering — no re-fetch
	const filtered = useMemo(() => {
		if (filter === "wins")
			return filledTrades.filter((t) => ["win", "win_resolution", "take_profit"].includes(t.final_outcome ?? ""));
		if (filter === "losses")
			return filledTrades.filter((t) => t.final_outcome === "loss");
		if (filter === "stop_loss")
			return filledTrades.filter((t) => t.final_outcome === "stop_loss");
		if (filter === "live") return filledTrades.filter((t) => !t.final_outcome);
		return filledTrades;
	}, [filledTrades, filter]);

	// Fetch next batch
	const fetchMore = useCallback(async () => {
		if (loadingMore || !hasMore) return;
		setLoadingMore(true);
		try {
			const res = await fetch(
				`/api/bot-activity?type=trades&limit=${TRADE_BATCH}&offset=${offsetRef.current}`,
			);
			const data = await res.json();
			const newTrades: TradeRow[] = data.trades ?? [];
			if (newTrades.length < TRADE_BATCH) setHasMore(false);
			if (newTrades.length > 0) {
				setAllTrades((prev) => {
					const existingIds = new Set(prev.map((t) => t.id));
					const deduped = newTrades.filter((t) => !existingIds.has(t.id));
					return [...prev, ...deduped];
				});
				offsetRef.current += newTrades.length;
			}
		} catch {
			// silently fail, user can scroll again
		} finally {
			setLoadingMore(false);
		}
	}, [loadingMore, hasMore]);

	// IntersectionObserver on sentinel
	useEffect(() => {
		const sentinel = sentinelRef.current;
		if (!sentinel) return;

		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting) fetchMore();
			},
			{ root: scrollRef.current, rootMargin: "200px" },
		);
		observer.observe(sentinel);
		return () => observer.disconnect();
	}, [fetchMore]);

	const COL_SPAN = 12;

	const toggleExpand = useCallback((id: string, e: React.MouseEvent) => {
		e.stopPropagation();
		setExpandedIds((prev) => {
			const next = new Set(prev);
			if (next.has(id)) next.delete(id);
			else next.add(id);
			return next;
		});
	}, []);

	return (
		<section className="mb-8 md:mb-14">
			<SectionHeader
				title="Trade History"
				description="All trades placed by the bot, most recent first."
			/>
			<GlassPanel variant="glow-wide">
				<div className="relative border-b border-zinc-800/60 px-6 py-3">
					<FilterRow
						options={TRADE_FILTERS}
						selected={filter}
						onSelect={setFilter}
					/>
				</div>
				<div className="overflow-x-auto">
					<div className="min-w-[900px]">
						{/* Fixed header */}
						<table className="w-full table-fixed">
							<thead className="bg-zinc-950">
								<tr className="border-b border-zinc-800/40">
									<th className="w-8 px-1 py-2.5" />
									<th className="w-32 px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
										Time
									</th>
									<th className="w-24 px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
										Market
									</th>
									<th className="w-36 px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
										Strategy
									</th>
									<th className="w-20 px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
										Dir
									</th>
									<th className="w-20 px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">
										Entry
									</th>
									<th className="w-20 px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">
										Size
									</th>
									<th className="w-24 px-3 py-2.5 text-center text-xs font-semibold uppercase tracking-wider text-zinc-500">
										Status
									</th>
									<th className="w-24 px-3 py-2.5 text-center text-xs font-semibold uppercase tracking-wider text-zinc-500">
										Outcome
									</th>
									<th className="w-24 px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">
										PnL
									</th>
									<th className="w-24 px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500">
										Signal
									</th>
									<th className="w-20 px-3 py-2.5 text-center text-xs font-semibold uppercase tracking-wider text-zinc-500">
										Detail
									</th>
								</tr>
							</thead>
						</table>
						{/* Scrollable body */}
						<div
							ref={scrollRef}
							className="h-[520px] overflow-y-auto scrollbar-thin"
						>
							<table className="w-full table-fixed">
								<tbody>
									{filtered.length === 0 ? (
										<tr>
											<td
												colSpan={COL_SPAN}
												className="py-12 text-center text-sm text-zinc-500"
											>
												No trades to show.
											</td>
										</tr>
									) : (
										filtered.map((t, idx) => {
											// PnL: recalculate from trade parameters (stored pnl is unreliable)
											const calculated = calcPnl(t);
											const tPnl = calculated ?? 0;
											const hasPnl = calculated != null;
											const style = getStrategyStyle(t.strategy_name);
											const signalMetric = getSignalMetric(t);
											const signalDetail = getSignalDetail(t);

											const marketUrl = buildMarketUrl(t);
											const isExpanded = expandedIds.has(t.id);
											const hasSignalData =
												t.signal_data && Object.keys(t.signal_data).length > 0;

											return (
												<React.Fragment key={t.id}>
													<tr
														onClick={(e) =>
															hasSignalData
																? toggleExpand(t.id, e)
																: marketUrl
																	? router.push(marketUrl)
																	: undefined
														}
														className={cn(
															"border-b border-zinc-800/20 hover:bg-zinc-800/20 transition-colors",
															idx % 2 === 1 && "bg-zinc-900/30",
															(hasSignalData || marketUrl) && "cursor-pointer",
															isExpanded && "bg-zinc-800/30",
														)}
													>
														<td className="w-8 px-1 py-3 text-center">
															{hasSignalData ? (
																isExpanded ? (
																	<ChevronDown
																		size={14}
																		className="text-zinc-400 inline-block"
																	/>
																) : (
																	<ChevronRight
																		size={14}
																		className="text-zinc-600 inline-block"
																	/>
																)
															) : null}
														</td>
														<td className="w-32 px-3 py-3 text-sm tabular-nums text-zinc-400 truncate">
															{fmtDateTime(t.placed_at)}
														</td>
														<td className="w-24 px-3 py-3 text-sm text-zinc-300 truncate">
															{fmtMarket(t.market_type)}
														</td>
														<td className="w-36 px-3 py-3">
															<span
																className={cn(
																	"rounded-md px-1.5 py-0.5 text-xs font-medium border truncate inline-block max-w-full",
																	style.badge,
																)}
															>
																{t.strategy_name}
															</span>
														</td>
														<td className="w-20 px-3 py-3">
															{t.direction.toLowerCase() === "up" ? (
																<span className="flex items-center gap-1 text-sm text-emerald-400">
																	<ArrowUpRight size={12} /> Up
																</span>
															) : (
																<span className="flex items-center gap-1 text-sm text-red-400">
																	<ArrowDownRight size={12} /> Down
																</span>
															)}
														</td>
														<td className="w-20 px-3 py-3 text-right font-mono text-sm tabular-nums text-zinc-200">
															{fmtPrice(pf(t.entry_price))}
														</td>
														<td className="w-20 px-3 py-3 text-right font-mono text-sm tabular-nums text-zinc-200">
															{fmtDollar(pf(t.bet_size_usd))}
														</td>
														<td className="w-24 px-3 py-3 text-center">
															{t.status === "filled" ? (
																<Badge variant="up">Filled</Badge>
															) : t.status === "fok_no_fill" ? (
																<Badge variant="default">No Fill</Badge>
															) : t.status.startsWith("skipped") ? (
																<Badge variant="default">Skipped</Badge>
															) : t.status === "dry_run" ? (
																<span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
																	Dry Run
																</span>
															) : (
																<Badge variant="default">{t.status}</Badge>
															)}
														</td>
														<td className="w-24 px-3 py-3 text-center">
															{t.status !==
															"filled" ? null : !t.final_outcome ? (
																<span className="text-xs font-medium text-yellow-400">
																	Pending...
																</span>
															) : t.final_outcome === "take_profit" ? (
																<span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
																	Take Profit
																</span>
															) : t.final_outcome === "win" || t.final_outcome === "win_resolution" ? (
																<span className="text-xs font-medium text-emerald-400">
																	Win
																</span>
															) : t.final_outcome === "stop_loss" ? (
																<span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium bg-orange-500/10 text-orange-400 border border-orange-500/20">
																	Stop Loss
																</span>
															) : (
																<span className="text-xs font-medium text-red-400">
																	Loss
																</span>
															)}
														</td>
														<td
															className={cn(
																"w-24 px-3 py-3 text-right font-mono text-sm font-bold tabular-nums",
																!hasPnl ? "text-zinc-600" : pnlColor(tPnl),
															)}
														>
															{hasPnl ? fmtPnl(tPnl) : ""}
														</td>
														<td className="w-24 px-3 py-3 text-right">
															{signalMetric ? (
																<span className="group relative inline-block">
																	<span
																		className={cn(
																			"font-mono text-sm tabular-nums",
																			signalMetric.color,
																		)}
																	>
																		{signalMetric.value}
																	</span>
																	<SignalTooltip trade={t} />
																</span>
															) : (
																<span className="text-sm text-zinc-600">
																	&mdash;
																</span>
															)}
														</td>
														<td className="w-20 px-3 py-3 text-center">
															{signalDetail ? (
																<span className={cn(
																	"inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium bg-zinc-800/60 border border-zinc-700/40",
																	signalDetail.color,
																)}>
																	{signalDetail.value}
																</span>
															) : (
																<span className="text-sm text-zinc-600">
																	&mdash;
																</span>
															)}
														</td>
													</tr>
													{isExpanded && hasSignalData && (
														<tr className="bg-zinc-900/60 border-b border-zinc-800/20">
															<td colSpan={COL_SPAN} className="px-6 py-4">
																<div className="flex items-center gap-2 mb-3">
																	<span className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
																		Signal Data
																	</span>
																	{marketUrl && (
																		<button
																			type="button"
																			onClick={(e) => {
																				e.stopPropagation();
																				router.push(marketUrl);
																			}}
																			className="text-xs text-primary/70 hover:text-primary transition-colors"
																		>
																			View Market →
																		</button>
																	)}
																</div>
																<SignalDataPanel
																	data={
																		t.signal_data as Record<string, unknown>
																	}
																/>
															</td>
														</tr>
													)}
												</React.Fragment>
											);
										})
									)}
								</tbody>
							</table>
							{/* Sentinel for infinite scroll */}
							<div ref={sentinelRef} className="h-1" />
							{loadingMore && (
								<div className="flex items-center justify-center py-4 gap-2">
									<div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-primary" />
									<span className="text-xs text-zinc-500">
										Loading more trades...
									</span>
								</div>
							)}
							{!hasMore && filtered.length > 0 && (
								<div className="py-3 text-center">
									<span className="text-xs text-zinc-600">
										All trades loaded
									</span>
								</div>
							)}
						</div>
					</div>
				</div>
			</GlassPanel>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Loading skeleton (matches dashboard patterns)
// ---------------------------------------------------------------------------

function LoadingSkeleton() {
	return (
		<>
			{/* Overview skeleton */}
			<section className="mb-8 md:mb-14">
				<div className="mb-5">
					<div className="flex items-center gap-3">
						<div className="h-3 w-32 animate-pulse rounded bg-zinc-800" />
						<div className="h-px flex-1 bg-gradient-to-r from-zinc-800/60 to-transparent" />
					</div>
				</div>
				<div className="relative grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-primary/20 bg-primary/[0.06] sm:grid-cols-3 lg:grid-cols-6">
					<div className="absolute inset-x-0 top-0 z-10 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />
					{Array.from({ length: 6 }).map((_, i) => (
						<div key={i} className="bg-zinc-950 p-6">
							<div className="h-2.5 w-16 animate-pulse rounded bg-zinc-800" />
							<div className="mt-3 h-8 w-20 animate-pulse rounded bg-zinc-800" />
						</div>
					))}
				</div>
			</section>

			{/* Chart skeleton */}
			<section className="mb-8 md:mb-14">
				<div className="mb-5">
					<div className="flex items-center gap-3">
						<div className="h-3 w-36 animate-pulse rounded bg-zinc-800" />
						<div className="h-px flex-1 bg-gradient-to-r from-zinc-800/60 to-transparent" />
					</div>
				</div>
				<div className="rounded-xl border border-primary/20 bg-zinc-950 p-6">
					<div className="h-[300px] animate-pulse rounded bg-zinc-800/30" />
				</div>
			</section>
		</>
	);
}

// ---------------------------------------------------------------------------
// Main Bot Monitor Component
// ---------------------------------------------------------------------------

export function BotMonitor() {
	const router = useRouter();
	const [overview, setOverview] = useState<OverviewData | null>(null);
	const [activity, setActivity] = useState<ActivityData | null>(null);
	const [lastUpdate, setLastUpdate] = useState(Date.now());
	const [secondsAgo, setSecondsAgo] = useState(0);

	const fetchData = useCallback(async () => {
		try {
			const [ovRes, actRes] = await Promise.all([
				fetch("/api/bot-overview"),
				fetch("/api/bot-activity?type=all&limit=100&offset=0"),
			]);
			const [ovData, actData] = await Promise.all([
				ovRes.json(),
				actRes.json(),
			]);
			setOverview(ovData);
			setActivity(actData);
			setLastUpdate(Date.now());
		} catch (err) {
			console.error("Failed to fetch bot data:", err);
		}
	}, []);

	useEffect(() => {
		fetchData();
	}, [fetchData]);

	// Auto-refresh every 30 seconds
	useEffect(() => {
		const interval = setInterval(() => {
			fetchData();
			router.refresh();
		}, 30000);
		return () => clearInterval(interval);
	}, [fetchData, router]);

	// Seconds-ago counter
	useEffect(() => {
		const interval = setInterval(() => {
			setSecondsAgo(Math.floor((Date.now() - lastUpdate) / 1000));
		}, 1000);
		return () => clearInterval(interval);
	}, [lastUpdate]);

	// Detect bot mode
	const botMode = useMemo(() => {
		if (!activity?.logs) return null;
		for (const log of activity.logs) {
			if (log.log_type === "trade_dry_run") return "DRY RUN";
			if (log.log_type === "trade_placed") return "LIVE";
		}
		return null;
	}, [activity]);

	// Last trade timestamp
	const lastTradeAt = useMemo(() => {
		if (!activity?.trades || activity.trades.length === 0) return null;
		return activity.trades[0].placed_at;
	}, [activity]);

	const loading = !overview || !activity;

	return (
		<>
			{/* Hero-style header (matches dashboard hero) */}
			<div className="mb-8 md:mb-14 flex flex-col items-center text-center">
				<div className="relative mb-4">
					<div className="absolute -inset-4 rounded-full bg-primary/10 blur-2xl" />
					<BotStatusDot lastTradeAt={lastTradeAt} />
				</div>
				<div className="flex items-center gap-3">
					<h1 className="text-2xl font-bold tracking-tight text-zinc-100">
						Bot Monitor
					</h1>
					{botMode && (
						<span
							className={cn(
								"rounded-md px-2 py-0.5 text-xs font-medium border",
								botMode === "LIVE"
									? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
									: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
							)}
						>
							{botMode}
						</span>
					)}
				</div>
				<p className="mt-1.5 text-sm text-zinc-500">
					Live trading activity — auto-refreshes every 30 seconds
				</p>
				<p className="mt-1 text-xs text-zinc-600 tabular-nums">
					Updated {secondsAgo}s ago
				</p>
				<div className="mt-4 flex items-center gap-2">
					<DownloadButton
						label="Export Trades"
						href="/api/bot-export-trades"
						iconSize={12}
					/>
					<DownloadButton
						label="Export Activity"
						href="/api/bot-export-activity"
						iconSize={12}
					/>
				</div>
			</div>

			{loading ? (
				<LoadingSkeleton />
			) : (
				<>
					<OverviewCards overview={overview} />
					<PnlChart />
					<TradeHistory initialTrades={activity.trades} />
					<ActivityFeed logs={activity.logs} />
				</>
			)}
		</>
	);
}
