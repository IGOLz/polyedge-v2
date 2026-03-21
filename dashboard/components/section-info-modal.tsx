"use client";

import { useState } from "react";
import { Info } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export interface SectionInfo {
  title: string;
  sections: {
    heading: string;
    content: string;
    bullets?: string[];
  }[];
}

const SECTION_INFO: Record<string, SectionInfo> = {
  "Edge Scanner": {
    title: "Edge Scanner",
    sections: [
      {
        heading: "What is this?",
        content:
          "The Edge Scanner identifies price buckets where the actual historical win rate significantly deviates from the implied probability. In prediction markets, the price of a contract reflects the market's implied probability of an outcome. When historical data shows a different reality, that gap is an \"edge\".",
      },
      {
        heading: "How to read it",
        content: "Each row represents a specific combination of market, time window, and price bucket where an edge was detected.",
        bullets: [
          "Market — The asset and interval (e.g., BTC 5m)",
          "Time — How far into the market window the snapshot was taken (e.g., 30s, 1m, 2m30s)",
          "Price — The contract price bucket at that moment (e.g., 35\u00a2)",
          "Implied Prob — What the market price suggests the probability is (35\u00a2 = 35%)",
          "Actual Win Rate — What historically happened at that price level",
          "Edge — The difference: Actual Win Rate minus Implied Probability",
        ],
      },
      {
        heading: "Example",
        content:
          "If BTC 5m is priced at 30\u00a2 (implying 30% chance of Up), but historically Up wins 48% of the time at that price, there is a +18% edge on Up. This means the market is underpricing the Up outcome at that level.",
      },
      {
        heading: "What makes a strong edge?",
        content: "Edges are categorized by size:",
        bullets: [
          "Strong (\u226515%) \u2014 Large deviation, high confidence if sample size is big enough",
          "Moderate (8\u201315%) \u2014 Meaningful deviation worth paying attention to",
          "Slight (<8%) \u2014 Small deviation, could be noise",
        ],
      },
      {
        heading: "Important note",
        content:
          "Edges are based on historical data and do not guarantee future results. Always consider the sample count \u2014 a 20% edge from 10 samples is far less reliable than a 10% edge from 500 samples. Market conditions change, and edges can disappear over time as the market adjusts.",
      },
    ],
  },
  "Calibration Heatmap": {
    title: "Calibration Heatmap",
    sections: [
      {
        heading: "What is this?",
        content:
          "The Calibration Heatmap is a 2D visualization that shows how the actual Up win rate varies across two dimensions simultaneously: the contract price (columns) and how much time has elapsed in the market window (rows). It helps you find the intersection of time and price where edges are strongest.",
      },
      {
        heading: "How to read it",
        content: "Each cell in the grid represents a specific combination of price and time:",
        bullets: [
          "Columns (left to right) \u2014 Price buckets from 5\u00a2 to 95\u00a2 in 5\u00a2 increments",
          "Rows (top to bottom) \u2014 Time elapsed since the market opened",
          "Cell color \u2014 Green = Up wins more than 50%, Red = Down wins more than 50%, Gray = roughly 50/50",
          "Cell value \u2014 The actual Up win rate percentage",
        ],
      },
      {
        heading: "Color intensity",
        content: "Darker/brighter colors indicate stronger edges:",
        bullets: [
          "Strong green (>65% Up) \u2014 Significant Up edge",
          "Light green (55\u201365%) \u2014 Moderate Up edge",
          "Gray (45\u201355%) \u2014 No clear edge, roughly 50/50",
          "Light red (35\u201345%) \u2014 Moderate Down edge",
          "Strong red (<35%) \u2014 Significant Down edge",
        ],
      },
      {
        heading: "Hover tooltip",
        content:
          "Hover over any cell to see detailed information: the exact win rate, edge size (deviation from 50%), price bucket, time offset, and number of samples used to calculate that value.",
      },
      {
        heading: "Practical use",
        content:
          "Look for clusters of green or red cells. A single bright cell might be noise, but a cluster of green cells in the same price range across multiple time offsets suggests a real pattern. Pay attention to sample sizes \u2014 cells with more samples are more reliable.",
      },
    ],
  },
  "Win Rate by Price Bucket": {
    title: "Win Rate by Price Bucket",
    sections: [
      {
        heading: "What is this?",
        content:
          "This section shows bar charts of the actual Up win rate grouped by price bucket, for each asset at a specific time snapshot. It answers the question: \"At a given point in time, if the contract is priced at X\u00a2, how often does Up actually win?\"",
      },
      {
        heading: "How to read it",
        content: "Each chart represents one asset (BTC, ETH, SOL, XRP):",
        bullets: [
          "X-axis \u2014 Price buckets (e.g., 10%, 20%, ..., 90%)",
          "Y-axis \u2014 Actual Up win rate (0\u2013100%)",
          "Dashed line at 50% \u2014 The baseline. Bars above = Up bias, bars below = Down bias",
          "Bar height \u2014 How far the actual win rate deviates from 50%",
        ],
      },
      {
        heading: "Time window selector",
        content:
          "The buttons at the top let you switch between different time snapshots. For 5m markets: 30s, 1m, 2m30s, 4m. For 15m markets: 1m30s, 3m, 7m30s, 12m. Earlier snapshots show how the market behaves shortly after opening, later snapshots show behavior closer to resolution.",
      },
      {
        heading: "What to look for",
        content:
          "In a perfectly calibrated market, all bars would sit at exactly 50% regardless of price. If you see that low-priced contracts (e.g., 20\u00a2) have an Up win rate of 60%, it means the market is systematically underpricing Up at that level. That's a potential edge.",
      },
    ],
  },
  "Time of Day Analysis": {
    title: "Time of Day Analysis",
    sections: [
      {
        heading: "What is this?",
        content:
          "This chart shows whether the time of day (in UTC) has any influence on whether markets resolve Up or Down. It breaks down the Up win rate by hour across the full 24-hour day.",
      },
      {
        heading: "How to read it",
        content: "Each bar represents one hour of the day:",
        bullets: [
          "Green bars (above 50%) \u2014 Up wins more often during this hour",
          "Red bars (below 50%) \u2014 Down wins more often during this hour",
          "Dashed line at 50% \u2014 The baseline of no edge",
        ],
      },
      {
        heading: "Why it matters",
        content:
          "If a specific hour consistently shows an Up or Down bias, it could reflect patterns in how market participants behave during those periods. For example, certain hours might see more buying or selling pressure due to global activity patterns.",
      },
    ],
  },
  "Cross-Asset Correlation": {
    title: "Cross-Asset Correlation",
    sections: [
      {
        heading: "What is this?",
        content:
          "Cross-Asset Correlation measures how often pairs of crypto assets move in the same direction within the same time window. When one asset resolves Up, does the other also resolve Up? This helps understand whether markets are moving together or independently.",
      },
      {
        heading: "How to read it",
        content: "Each card shows one pair of assets (e.g., BTC \u00d7 ETH):",
        bullets: [
          "Correlation % \u2014 How often both assets resolve in the same direction (both Up or both Down)",
          "Both Up \u2014 Number and percentage of times both went Up",
          "Both Down \u2014 Number and percentage of times both went Down",
          "Opposite \u2014 Times one went Up while the other went Down",
          "Color bar \u2014 Visual breakdown of green (both Up), red (both Down), and gray (opposite)",
        ],
      },
      {
        heading: "Correlation strength",
        content: "The percentage is color-coded:",
        bullets: [
          "Strongly correlated (\u226570%) \u2014 Assets almost always move together",
          "Moderately correlated (60\u201370%) \u2014 Strong tendency to move together",
          "Weakly correlated (55\u201360%) \u2014 Slight tendency to move together",
          "Independent (45\u201355%) \u2014 No meaningful relationship",
          "Inversely correlated (<45%) \u2014 Assets tend to move in opposite directions",
        ],
      },
      {
        heading: "Practical use",
        content:
          "High correlation means you're taking similar risk if you trade both assets. If BTC and ETH are 75% correlated, buying Up on both is almost like doubling your bet on a single outcome. Low correlation means the assets provide diversification \u2014 their outcomes are more independent of each other.",
      },
    ],
  },
  "Streak Detector": {
    title: "Streak Detector",
    sections: [
      {
        heading: "What is this?",
        content:
          "The Streak Detector shows the current consecutive outcome streak for each market. A streak is when the same outcome (Up or Down) happens multiple times in a row. This is live data that updates in real time.",
      },
      {
        heading: "How to read it",
        content: "Each card represents one market:",
        bullets: [
          "Badge (e.g., \"5x Up\") \u2014 The current streak length and direction",
          "Dot trail \u2014 The last 10 outcomes shown as colored dots (green = Up, red = Down), newest first",
          "Pulsing dot \u2014 Indicates this is live data",
        ],
      },
      {
        heading: "Does a streak mean anything?",
        content:
          "This is important to understand: in truly random 50/50 outcomes, streaks are completely normal and expected. A 5-game winning streak happens about 3% of the time, which is rare but not unusual across thousands of markets. The Streak Detector is useful for tracking what's happening right now, but a long streak does NOT mean the next outcome is more likely to be the opposite (that's the gambler's fallacy).",
      },
      {
        heading: "When streaks matter",
        content:
          "Streaks become interesting when combined with other data. If a market has a 7x Up streak AND the Edge Scanner shows an Up edge for that market, the streak might be reflecting a real underlying bias rather than random chance.",
      },
    ],
  },
  "Collection Health": {
    title: "Collection Health",
    sections: [
      {
        heading: "What is this?",
        content:
          "Collection Health monitors the data pipeline \u2014 the system that collects price ticks from Polymarket. Every market window generates price updates (ticks) at regular intervals. This section checks whether the pipeline is receiving the expected number of ticks.",
      },
      {
        heading: "How to read it",
        content: "Each card represents one market's data collection status, with an interval badge (5m or 15m) indicating the market type:",
        bullets: [
          "Healthy (green, \u226590%) \u2014 Pipeline is collecting data at or near the expected rate",
          "Degraded (yellow, 70\u201390%) \u2014 Some data is being missed, but most is still collected",
          "Critical (red, <70%) \u2014 Significant data loss, analysis may be unreliable",
          "Progress bar \u2014 Shows actual vs expected tick count as a percentage",
        ],
      },
      {
        heading: "Expected tick rates",
        content: "The system expects a specific number of ticks per market window:",
        bullets: [
          "5m markets \u2014 300 ticks per window (1 per second for 5 minutes)",
          "15m markets \u2014 900 ticks per window (1 per second for 15 minutes)",
        ],
      },
      {
        heading: "Why it matters",
        content:
          "All analytics on this dashboard depend on the quality of collected data. If Collection Health shows degraded or critical status, the data behind edge calculations, win rates, and other metrics may be incomplete or skewed. Always check this section if numbers in other sections seem unusual.",
      },
    ],
  },
  "Calibration Analysis": {
    title: "Calibration Analysis",
    sections: [
      {
        heading: "What is this?",
        content:
          "Calibration measures whether the market is pricing contracts accurately. When a contract trades at 40\u00a2, the market implies a 40% chance of Up. Calibration checks whether Up actually wins 40% of the time at that price level.",
      },
      {
        heading: "How to read it",
        content: "Each row represents a price bucket at a specific time checkpoint:",
        bullets: [
          "Price Bucket \u2014 The contract price range (e.g., 47.5\u00a2 means contracts trading around 47.5%)",
          "Expected Win Rate \u2014 What the market price implies (same as the bucket center)",
          "Actual Win Rate \u2014 What historically happened at that price level",
          "Deviation \u2014 The gap between expected and actual. Positive = Up wins more than priced, Negative = Up wins less",
          "Significant \u2014 Whether the deviation is statistically significant (p < 0.05)",
        ],
      },
      {
        heading: "Checkpoint selector",
        content:
          "The time tabs (30s, 60s, 120s, etc.) let you examine calibration at different points during the market window. Early checkpoints (30s) show how the market is priced shortly after opening. Later checkpoints (300s) show pricing closer to resolution.",
      },
      {
        heading: "What to look for",
        content:
          "Rows highlighted with a left border accent are statistically significant. Green deviations mean Up wins more than the market expects \u2014 the market is underpricing Up. Red deviations mean the opposite. Clusters of significant deviations in the same direction suggest systematic mispricing.",
      },
      {
        heading: "Important note",
        content:
          "A minimum of 10 samples per bucket is required. Small sample sizes can produce large but meaningless deviations. Focus on buckets with high sample counts for the most reliable signals.",
      },
    ],
  },
  "Price Trajectory": {
    title: "Price Trajectory \u2014 Momentum Analysis",
    sections: [
      {
        heading: "What is this?",
        content:
          "Price Trajectory examines whether the direction of price movement in the first 60 seconds of a market window predicts the final outcome. If the price is rising at the 60-second mark, does Up end up winning more often?",
      },
      {
        heading: "How to read it",
        content: "Each card represents one market type:",
        bullets: [
          "Rising at 60s \u2192 Up wins X% \u2014 When the price is trending upward at the 60-second mark, how often does Up win",
          "Sample count \u2014 Number of markets where this pattern was observed",
          "Reversal cases \u2014 Markets where the price direction reversed after 60 seconds, and what percentage still resolved Up",
          "Colored dot \u2014 Green = momentum > 60%, Red = momentum < 50%, Yellow = neutral",
        ],
      },
      {
        heading: "Summary banner",
        content:
          "The banner at the top shows how many of the 8 market types exhibit a momentum effect (Up win rate > 60% when rising at 60s). Green = strong momentum across markets, Yellow = moderate, Red = weak or no momentum effect.",
      },
      {
        heading: "Practical use",
        content:
          "If momentum is strong, it suggests that early price movement carries predictive power. This could mean that informed participants set direction early. If reversals are common, it suggests mean reversion \u2014 early moves often get corrected.",
      },
    ],
  },
  "Time of Day Patterns": {
    title: "Time of Day Patterns",
    sections: [
      {
        heading: "What is this?",
        content:
          "This chart shows whether the time of day (in UTC) has any influence on whether markets resolve Up or Down. It breaks down the Up win rate by hour across the full 24-hour day.",
      },
      {
        heading: "How to read it",
        content: "Each bar represents one hour of the day:",
        bullets: [
          "Green bars (above 60%) \u2014 Up wins significantly more often during this hour",
          "Red bars (below 40%) \u2014 Down wins significantly more often during this hour",
          "Grey bars (40\u201360%) \u2014 No clear directional bias",
          "Dashed line at 50% \u2014 The baseline of no edge",
          "Greyed-out bars \u2014 Hours with fewer than 10 samples, insufficient data",
        ],
      },
      {
        heading: "Stat boxes",
        content:
          "The two stat boxes below show the most bullish and most bearish hours. These are the hours with the highest and lowest Up win rates respectively, considering only hours with sufficient sample sizes (\u226510 samples).",
      },
      {
        heading: "Why it matters",
        content:
          "Time-of-day patterns can reflect global trading activity cycles. For example, certain hours might coincide with US/EU/Asian session opens where buying or selling pressure differs. If a specific hour consistently shows a bias, it could be a repeatable edge.",
      },
    ],
  },
  "Outcome Streaks": {
    title: "Outcome Streaks \u2014 Sequential Analysis",
    sections: [
      {
        heading: "What is this?",
        content:
          "The Streak Analysis examines what happens after a specific sequence of Up and Down outcomes. For example, after three consecutive Up results (\u2191\u2191\u2191), does the next market lean Up or Down? This tests whether past outcomes influence future results.",
      },
      {
        heading: "How to read it",
        content: "Each row represents a specific outcome pattern:",
        bullets: [
          "Pattern \u2014 The preceding sequence of outcomes (green arrows = Up, red arrows = Down)",
          "Sample Count \u2014 How many times this exact sequence occurred",
          "Next Up Win Rate \u2014 Probability that the next market resolves Up after this pattern",
          "Edge \u2014 Deviation from 50%. Positive = Up is more likely next, Negative = Down is more likely",
        ],
      },
      {
        heading: "Sorting and filtering",
        content:
          "Rows are sorted by absolute edge (largest deviations first) and filtered to show only patterns with at least 15 samples. This ensures you see the most actionable patterns with reasonable statistical backing.",
      },
      {
        heading: "Gambler's fallacy warning",
        content:
          "In truly random 50/50 outcomes, the previous results have no influence on the next one. However, prediction markets may not be perfectly random \u2014 participant behavior, momentum effects, and sentiment can create sequential dependencies. Always verify with sample size before acting on streak patterns.",
      },
    ],
  },
  "Previous Market Influence": {
    title: "Previous Market Influence",
    sections: [
      {
        heading: "What is this?",
        content:
          "This section examines whether the outcome of the previous market window affects the early pricing of the next market. Does a previous Up result cause the next market to start with a higher or lower price?",
      },
      {
        heading: "How to read it",
        content: "Each row shows what happens after a specific previous outcome:",
        bullets: [
          "Previous Outcome \u2014 Whether the prior market resolved Up or Down",
          "Avg Price at 30s \u2014 The average contract price 30 seconds into the next market window",
          "Sample Count \u2014 Number of transitions observed",
          "Interpretation \u2014 Whether the carry-over effect is bullish, bearish, or neutral",
        ],
      },
      {
        heading: "Interpretation thresholds",
        content: "The carry-over effect is categorized as:",
        bullets: [
          "Bullish carry-over (>55\u00a2) \u2014 Previous outcome pushes next market's price up significantly",
          "Slightly bullish (52\u201355\u00a2) \u2014 Small upward bias",
          "No significant effect (48\u201352\u00a2) \u2014 Previous outcome doesn't meaningfully affect the next market",
          "Slightly bearish (45\u201348\u00a2) \u2014 Small downward bias",
          "Bearish carry-over (<45\u00a2) \u2014 Previous outcome pushes next market's price down significantly",
        ],
      },
      {
        heading: "Practical use",
        content:
          "If there's a strong carry-over effect, it means the market hasn't fully absorbed the previous result. This could present an opportunity \u2014 for example, if after a Down result the next market consistently starts underpriced, there may be a systematic Up edge in early trading.",
      },
    ],
  },
  "Best Configuration": {
    title: "Best Configuration",
    sections: [
      {
        heading: "What is this?",
        content:
          "The single parameter combination with highest total PnL across all 15-minute markets, requiring a minimum of 20 trades to qualify.",
      },
      {
        heading: "How to read it",
        content: "The stat cards show the performance of this specific configuration:",
        bullets: [
          "Total PnL \u2014 Net profit/loss after all trades and 2% fees",
          "ROI \u2014 Return on investment as a percentage",
          "Win Rate \u2014 Percentage of trades that were profitable",
          "Wins / Stop Losses / Losses \u2014 Breakdown of trade outcomes",
          "Avg Entry Price \u2014 Average contract price at entry",
          "Avg Coin Delta \u2014 Average price movement from window open at entry",
        ],
      },
      {
        heading: "Configuration badges",
        content:
          "The badges below the cards show the exact parameter values: Trigger Point, Stop-Loss, Min Minute, and Min Delta. These are the settings that produced the best overall result.",
      },
    ],
  },
  "Top Configurations by PnL": {
    title: "Top Configurations by PnL",
    sections: [
      {
        heading: "What is this?",
        content:
          "All parameter combinations sorted by total PnL. Only combinations with at least 20 trades are shown. Green values indicate profit, red indicates loss.",
      },
      {
        heading: "How to read it",
        content: "Each row represents a unique parameter combination:",
        bullets: [
          "Market \u2014 Which market type (All, BTC 15m, etc.)",
          "Trigger / Stop-Loss \u2014 The entry and exit price thresholds",
          "Win Rate \u2014 Color-coded: green >70%, yellow 60-70%, red <60%",
          "W / SL / L \u2014 Wins, stop-loss exits, and full losses",
          "Total PnL \u2014 Net profit/loss after fees",
          "ROI \u2014 Return on investment percentage",
        ],
      },
      {
        heading: "Highlighted row",
        content:
          "The top row (highest PnL) is highlighted with a left border accent. Use the filters to narrow down by market type or minimum trade count.",
      },
    ],
  },
  "Parameter Impact": {
    title: "Parameter Impact",
    sections: [
      {
        heading: "What is this?",
        content:
          "Average total PnL grouped by each parameter value across all combinations where trades_taken >= 20. Shows which values tend to perform better.",
      },
      {
        heading: "How to read it",
        content: "Four charts, one per parameter:",
        bullets: [
          "Trigger Point \u2014 Which entry thresholds are most profitable on average",
          "Stop-Loss (Exit Point) \u2014 Which stop-loss levels work best",
          "Trigger Minute \u2014 How entry timing affects returns",
          "Min Coin Delta \u2014 Whether requiring minimum price movement helps",
        ],
      },
      {
        heading: "Bar colors",
        content:
          "Green bars indicate the average PnL is positive for that parameter value. Red bars indicate negative. The dashed line at $0 is the break-even reference.",
      },
    ],
  },
  "Win Rate vs Profitability": {
    title: "Win Rate vs Profitability",
    sections: [
      {
        heading: "What is this?",
        content:
          "Each dot is one parameter combination. High win rate does not always mean positive PnL \u2014 fees matter. The best combinations are top-right (high win rate AND positive PnL).",
      },
      {
        heading: "How to read it",
        content: "The scatter chart plots win rate (x-axis) against total PnL (y-axis):",
        bullets: [
          "Green dots \u2014 Profitable combinations (positive PnL)",
          "Red dots \u2014 Losing combinations (negative PnL)",
          "Dot size \u2014 Proportional to number of trades taken",
          "Dashed lines \u2014 50% win rate (vertical) and $0 PnL (horizontal)",
        ],
      },
      {
        heading: "Key insight",
        content:
          "A strategy can have a high win rate but still lose money if the average loss is larger than the average win. Look for dots in the top-right quadrant \u2014 both high win rate and positive PnL.",
      },
    ],
  },
  "PnL Heatmap": {
    title: "PnL Heatmap",
    sections: [
      {
        heading: "What is this?",
        content:
          "A 2D view of total PnL for each trigger/stop-loss combination. Green cells are profitable, red cells are losing. Use the filters to explore different time and delta configurations.",
      },
      {
        heading: "How to read it",
        content: "The grid shows trigger points (columns) vs exit points (rows):",
        bullets: [
          "Dark green \u2014 Highest PnL in the current view",
          "Dark red \u2014 Lowest PnL (biggest losses)",
          "Grey with dash \u2014 Fewer than 20 trades, insufficient data",
          "Cell value \u2014 Total PnL rounded to nearest dollar",
        ],
      },
      {
        heading: "Filters",
        content:
          "Use the market type dropdown, trigger minute buttons, and min delta selector to slice the data. Each filter combination shows a different view of the parameter space.",
      },
    ],
  },
  "Strategy Performance": {
    title: "Strategy Performance",
    sections: [
      {
        heading: "What is this?",
        content:
          "Best backtest result per strategy across all 15m markets. Updated every 4 hours. Minimum 20 trades required.",
      },
      {
        heading: "How to read it",
        content: "Each card represents one strategy's best-performing configuration:",
        bullets: [
          "Total PnL — Net profit/loss from the best parameter combination",
          "ROI — Return on investment as a percentage",
          "Win Rate — Percentage of trades that were profitable",
          "Trades — Total number of trades taken by this configuration",
        ],
      },
      {
        heading: "Strategies",
        content: "Four strategies are backtested:",
        bullets: [
          "S1 Farming — Trigger/exit point based entries",
          "S2 Calibration — Entry price range based entries",
          "S3 Momentum — Minimum momentum threshold entries",
          "S4 Streak Reversal — Streak length based reversal entries",
        ],
      },
    ],
  },
  "Bot Overview": {
    title: "Bot Overview",
    sections: [
      {
        heading: "What is this?",
        content:
          "This section summarizes how the live trading bot is performing right now using the current bot trade database. The headline metrics focus on realized P&L and exit behavior, so the dashboard reflects how the bot is actually trading rather than treating it like a simple win-loss betting counter.",
      },
      {
        heading: "Exit profile",
        content:
          "Take Profit counts profitable exits, Stop Loss counts trades closed early at the protective stop, and Held to Expiry Losses counts positions that were carried through resolution and finished negative. Those three outcomes are the key trading signals on this page.",
      },
      {
        heading: "Last 24 Hours",
        content:
          "The activity block isolates the most recent 24 hours so short-term changes stand out from the full-history numbers. It shows realized P&L, recent take-profit and stop-loss behavior, and an hourly activity chart for the latest trading window.",
      },
    ],
  },
  "Strategy Results": {
    title: "Strategy Results",
    sections: [
      {
        heading: "What is this?",
        content:
          "Each card is generated from the latest strategy artifacts found in the repo's optimization and validation result folders. The dashboard surfaces the strongest metrics available for that strategy instead of assuming every file has the same schema.",
      },
      {
        heading: "How to read it",
        content:
          "Validated strategies pull from the newest validation candidate files when available. Otherwise the cards fall back to the newest optimization summaries, best-configuration files, and result CSV headers for the most recent run.",
      },
    ],
  },
  "Trade History": {
    title: "Trade History",
    sections: [
      {
        heading: "What is this?",
        content:
          "This table shows the most recent live bot trades from the existing trade history source. Exit prices use the actual settlement convention already present in the project: winners resolve at $1, losing contracts at $0, and stop-loss exits use the stored stop-loss execution price.",
      },
      {
        heading: "Why it matters",
        content:
          "The table helps verify that the bot overview is grounded in real individual trades instead of only aggregate stats. It also lets you spot which markets, strategies, and directions are driving recent P&L.",
      },
    ],
  },
  Markets: {
    title: "Markets Overview",
    sections: [
      {
        heading: "What is this?",
        content:
          "The Markets section provides a high-level overview of all tracked prediction markets, organized by asset (BTC, ETH, SOL, XRP) and interval (5m, 15m). Each card shows key metrics for that market type.",
      },
      {
        heading: "Card metrics",
        content: "Each market card displays:",
        bullets: [
          "Win Rate 24h \u2014 The Up win rate over the last 24 hours, colored green (\u226550%) or red (<50%)",
          "Total Markets \u2014 Total number of resolved markets across all time",
        ],
      },
      {
        heading: "Clicking a card",
        content:
          "Click any market card to open the detailed Markets page, filtered to that specific market type. There you can browse individual markets and view price charts.",
      },
    ],
  },
};

function downloadJSON(data: unknown, filename: string) {
  const json = JSON.stringify(data, null, 2);
  const blob = new Blob([json], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

interface SectionInfoButtonProps {
  sectionTitle: string;
  exportData?: unknown;
  info?: SectionInfo;
}

export function SectionInfoButton({ sectionTitle, exportData, info: infoOverride }: SectionInfoButtonProps) {
  const [open, setOpen] = useState(false);
  const info = infoOverride ?? SECTION_INFO[sectionTitle];

  if (!info) return null;

  const filename = sectionTitle.toLowerCase().replace(/\s+/g, "-") + ".json";

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          className="flex h-5 w-5 items-center justify-center rounded-full border border-zinc-700/60 bg-zinc-800/60 text-xs font-semibold text-zinc-400 transition-colors hover:border-primary/40 hover:text-primary hover:bg-primary/10"
          aria-label={`Learn more about ${sectionTitle}`}
        >
          <Info className="h-3.5 w-3.5" />
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto border-primary/20 bg-zinc-950 backdrop-blur-xl">
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold text-zinc-100">
            {info.title}
          </DialogTitle>
        </DialogHeader>

        <div className="mt-4 space-y-6">
          {info.sections.map((section, i) => (
            <div key={i}>
              <h3 className="mb-2 text-sm font-semibold text-primary/80">
                {section.heading}
              </h3>
              <p className="text-sm leading-relaxed text-zinc-300">
                {section.content}
              </p>
              {section.bullets && (
                <ul className="mt-2 space-y-1.5">
                  {section.bullets.map((bullet, j) => (
                    <li
                      key={j}
                      className="flex gap-2 text-sm leading-relaxed text-zinc-400"
                    >
                      <span className="text-primary/40 shrink-0">•</span>
                      <span>{bullet}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>

        {!!exportData && (
          <div className="mt-6 border-t border-zinc-800/60 pt-4">
            <button
              onClick={() => downloadJSON(exportData, filename)}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-zinc-700/60 bg-zinc-800/60 px-4 py-2.5 text-sm font-medium text-zinc-300 transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Export data as JSON
            </button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
