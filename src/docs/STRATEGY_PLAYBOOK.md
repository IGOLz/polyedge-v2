# Strategy Playbook: Backtest Operation & Deployment Guide

**Version:** M003 (March 2026)  
**Audience:** Strategy operators, quant analysts, deployment decision-makers

This playbook teaches you how to run backtests on 7 research-backed strategies for 5-minute crypto up/down prediction markets, interpret performance metrics, and make data-driven deployment decisions.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Strategy Reference](#strategy-reference)
4. [CLI Reference](#cli-reference)
5. [Metric Interpretation](#metric-interpretation)
6. [Go/No-Go Decision Framework](#gono-go-decision-framework)
7. [Parameter Optimization](#parameter-optimization)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Run a Single Strategy

```bash
cd src
PYTHONPATH=. python3 -m analysis.backtest_strategies \
  --strategy S1 \
  --assets BTC,ETH \
  --durations 5 \
  --slippage 0.01 \
  --output-dir ../backtest_results
```

### Run All Strategies

```bash
cd src
PYTHONPATH=. python3 -m analysis.backtest_strategies \
  --assets BTC,ETH,SOL,XRP \
  --durations 5 \
  --slippage 0.01 \
  --output-dir ../backtest_results
```

**Output:** CSV files with per-strategy metrics in `backtest_results/` directory.

---

## Prerequisites

### Data Dependency

**Real backtests require TimescaleDB data.** The backtest engine queries historical market price timeseries to simulate trades. If your worktree database is empty, strategies will execute correctly but find no markets to backtest.

**To verify database status:**

```bash
# Check if DB has market data
psql -U polymarket -d polymarket -c "SELECT COUNT(*) FROM market_timeseries;"
```

**Expected:** 50,000+ rows for meaningful backtest results. If count is 0, the strategies are correct but there's no data to evaluate them against.

**Solution:** Either populate the database with historical data collection scripts, or copy database from main repository where data collection has been running.

### Environment

- **Python 3.9+** with dependencies installed (`pip install -r requirements.txt`)
- **PostgreSQL/TimescaleDB** connection configured in `.env`
- **Working directory:** All commands run from `src/` directory with `PYTHONPATH=.`

---

## Strategy Reference

All 7 strategies implement contrarian entry logic based on mean reversion / overreaction hypothesis. They detect specific market patterns and bet against the observed pattern.

### S1: Calibration Mispricing

**Family:** Calibration inefficiency  
**Entry Condition:** Price deviates significantly from balanced (0.50)  
**Logic:** Markets that should be 50/50 but are priced extreme suggest systematic mispricing → fade it

**Entry Rules:**
- Scan 30-60 second window for price deviation from 0.50
- If price < 0.45 with deviation ≥ 0.08, enter **Up** (bet price rises toward middle)
- If price > 0.55 with deviation ≥ 0.08, enter **Down** (bet price falls toward middle)

**Parameters:**
- `entry_window_start`: 30-60s (when to start scanning)
- `entry_window_end`: 60-120s (when to stop scanning)
- `price_low_threshold`: 0.40-0.45 (trigger level for Up bet)
- `price_high_threshold`: 0.55-0.60 (trigger level for Down bet)
- `min_deviation`: 0.05-0.10 (minimum absolute deviation from 0.50)

**Grid Size:** 108 combinations  
**Best For:** Markets with systematic pricing bias near market open

**Behavioral Notes:**
- Fires quickly (30-60s) or not at all
- Zero trades expected if all prices are near 0.50 (balanced markets)
- Sensitive to entry window timing

---

### S2: Early Momentum

**Family:** Momentum fade  
**Entry Condition:** Strong directional velocity detected in first 30-60 seconds  
**Logic:** Rapid price moves in first minute often overreact → fade the momentum

**Entry Rules:**
- Calculate velocity = (price_60s - price_30s) / 30 seconds
- If velocity ≥ +0.03, enter **Down** (fade upward momentum)
- If velocity ≤ -0.03, enter **Up** (fade downward momentum)

**Parameters:**
- `eval_window_start`: 25-35s (start of velocity measurement)
- `eval_window_end`: 55-65s (end of velocity measurement)
- `momentum_threshold`: 0.02-0.08 (minimum velocity to trigger entry)
- `tolerance`: 5-10s (NaN scanning tolerance for price lookup)

**Grid Size:** 72 combinations  
**Best For:** Markets with high initial volatility that settles

**Behavioral Notes:**
- Requires sufficient price data at 30s and 60s marks
- NaN-heavy markets will produce zero trades (graceful degradation)
- High thresholds (0.08) produce very few trades but higher conviction

---

### S3: Mean Reversion

**Family:** Spike fade  
**Entry Condition:** Price spikes early then partially reverts  
**Logic:** Spikes that partially revert suggest overreaction → bet on continued reversion

**Entry Rules:**
- **Phase 1:** Scan first 15-60s for spike
  - Up spike: price ≥ 0.70-0.85
  - Down spike: price ≤ 0.15-0.30
- **Phase 2:** Wait for partial reversion (5-15% from peak within 30-120s)
- Enter **Down** if Up spike reverts, **Up** if Down spike reverts

**Parameters:**
- `spike_threshold`: 0.70-0.85 (price threshold for spike detection)
- `spike_lookback`: 15-60s (window to scan for spike)
- `reversion_pct`: 0.05-0.15 (fraction of peak-to-balanced that must revert)
- `min_reversion_sec`: 30-120s (how long to wait for reversion after spike)

**Grid Size:** 144 combinations  
**Best For:** Volatile markets with early extreme price swings

**Behavioral Notes:**
- Two-phase logic means longer evaluation time (30-180s)
- Legitimately produces zero trades if no spikes occur
- Hold-to-resolution only (no mid-market exits)

---

### S4: Volatility Regime

**Family:** Regime-conditional fade  
**Entry Condition:** High volatility + extreme price  
**Logic:** High volatility + extreme price suggests overreaction → fade it

**Entry Rules:**
- Calculate rolling std dev over 30-90s lookback at evaluation point (60/120/180s)
- If volatility ≥ threshold (0.05-0.10) AND:
  - Price ≤ 0.25-0.30 → enter **Up** (fade low extreme)
  - Price ≥ 0.70-0.75 → enter **Down** (fade high extreme)

**Parameters:**
- `lookback_window`: 30-90s (window for volatility calculation)
- `vol_threshold`: 0.05-0.10 (minimum std dev to consider high volatility)
- `eval_second`: 60-180s (when to evaluate volatility and price)
- `extreme_price_low`: 0.25-0.30 (low extreme threshold)
- `extreme_price_high`: 0.70-0.75 (high extreme threshold)

**Grid Size:** 108 combinations  
**Best For:** Markets that oscillate violently before settling

**Behavioral Notes:**
- Requires minimum 10 valid price points in lookback window
- Sparse data causes graceful exit (return None)
- Later entry timing (60-180s) than S1/S2

---

### S5: Time-Phase Entry

**Family:** Temporal filtering  
**Entry Condition:** Price in target range during specific time window  
**Logic:** Certain time phases have better entry characteristics → filter by timing

**Entry Rules:**
- Scan entry window (60-240s) for price in target range (0.45-0.55 typical)
- Optional hour-of-day filter (e.g., only trade during [10-15] hours or [14-18] hours)
- Direction: if price < 0.50, bet **Up** (toward middle); if price > 0.50, bet **Down**

**Parameters:**
- `entry_window_start`: 30-90s (when to start scanning)
- `entry_window_end`: 120-240s (when to stop scanning)
- `allowed_hours`: None (all hours) or list like [10,11,12,13,14,15]
- `price_range_low`: 0.40-0.45 (low bound of target range)
- `price_range_high`: 0.55-0.60 (high bound of target range)

**Grid Size:** 108 combinations  
**Best For:** Markets with time-of-day patterns or entries near balanced price

**Behavioral Notes:**
- Hour filter requires `hour` metadata in MarketSnapshot (from database)
- If no hour metadata, hour filter is ignored (trades all hours)
- Wide entry windows increase signal frequency but may reduce quality

---

### S6: Streak/Sequence

**Family:** Momentum exhaustion  
**Entry Condition:** Consecutive same-direction price moves detected  
**Logic:** Consecutive same-direction moves suggest momentum exhaustion → fade the streak

**Entry Rules:**
- Divide market into fixed windows (10-30s each)
- Calculate direction for each window (up/down/flat based on start-to-end delta)
- Count consecutive same-direction windows
- Enter contrarian when streak_length ≥ threshold (3-5 windows)
  - If streak is "up", enter **Down**
  - If streak is "down", enter **Up**

**Parameters:**
- `window_size`: 10-30s (size of each analysis window)
- `streak_length`: 3-5 (consecutive same-direction windows to trigger entry)
- `min_move_threshold`: 0.02-0.05 (minimum price move to classify window as up/down vs. flat)
- `min_windows`: 4-5 (minimum total windows required before evaluating)

**Grid Size:** 72 combinations  
**Best For:** Markets with sustained directional pressure that reverses

**Behavioral Notes:**
- **Zero trades are valid:** If no consecutive streaks occur, strategy correctly returns None
- Window alignment: analyzes only complete windows (last partial window ignored)
- Simplified intra-market version (not cross-market streak detection)
- May produce fewer signals than other strategies (requires specific pattern)

**Known Limitation:** This is a simplified intra-market streak detector. True cross-market streak detection (tracking consecutive same-outcome markets across different markets) requires state that violates the pure function contract. Current implementation detects consecutive same-direction price moves within a single market.

---

### S7: Composite Ensemble

**Family:** Multi-signal consensus  
**Entry Condition:** Multiple detection patterns agree on direction  
**Logic:** Multiple independent signals agreeing suggests higher confidence → enter only on consensus

**Entry Rules:**
- Run three detection patterns inline (calibration, momentum, volatility)
- Collect signals from each enabled pattern
- Count votes by direction (Up vs. Down)
- Enter only if ≥ `min_agreement` patterns agree (2-3 required)

**Parameters:**
- `min_agreement`: 2-3 (minimum patterns that must agree)
- `calibration_enabled`: True/False (enable S1-style calibration detection)
- `momentum_enabled`: True/False (enable S2-style momentum detection)
- `volatility_enabled`: True/False (enable S4-style volatility detection)
- Per-pattern thresholds:
  - `calibration_deviation`: 0.05-0.10
  - `momentum_threshold`: 0.03-0.05
  - `volatility_threshold`: 0.08-0.10

**Grid Size:** 192 combinations  
**Best For:** High-confidence trades where multiple inefficiencies align

**Behavioral Notes:**
- **Inline duplication:** Duplicates logic from S1/S2/S4 inline (architectural constraint)
- Fewer signals than standalone strategies (requires consensus)
- Check `signal_data['up_votes']` and `signal_data['down_votes']` to see voting breakdown
- If only 1 pattern triggers and `min_agreement=2`, correctly returns None

**Known Limitation:** S7 duplicates detection logic from S1 (calibration), S2 (momentum), and S4 (volatility) inline rather than calling those strategies. If S1/S2/S4 logic changes in future, S7 must be updated manually. This is an architectural constraint of the pure function contract (evaluate() cannot access the registry).

---

## CLI Reference

### backtest_strategies.py

**Purpose:** Run backtests on one or all strategies using historical market data from TimescaleDB.

**Usage:**

```bash
cd src
PYTHONPATH=. python3 -m analysis.backtest_strategies [OPTIONS]
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--strategy` | str | None | Strategy ID to backtest (e.g., `S1`, `S2`, `S7`). If omitted, runs all strategies. |
| `--assets` | str | None | Comma-separated asset filter (e.g., `BTC,ETH,SOL`). If omitted, uses all assets. |
| `--durations` | str | None | Comma-separated duration filter in minutes (e.g., `5,15`). If omitted, uses all durations. |
| `--slippage` | float | 0.0 | Slippage penalty in price units. Models execution lag — Up bets pay more, Down bets get worse fill. Typical: 0.01. |
| `--fee-base-rate` | float | 0.063 | Polymarket dynamic fee base rate. Default produces ~3.15% peak fee at 50/50 prices. |
| `--output-dir` | str | `backtest_results` | Directory where CSV reports are written. |

**Examples:**

```bash
# Single strategy, all assets, 5-minute markets only
PYTHONPATH=. python3 -m analysis.backtest_strategies \
  --strategy S1 \
  --durations 5 \
  --slippage 0.01

# All strategies, BTC only
PYTHONPATH=. python3 -m analysis.backtest_strategies \
  --assets BTC \
  --slippage 0.01

# S3 mean reversion, multiple assets, no slippage (test mode)
PYTHONPATH=. python3 -m analysis.backtest_strategies \
  --strategy S3 \
  --assets BTC,ETH,SOL \
  --durations 5

# All strategies, all assets, realistic costs
PYTHONPATH=. python3 -m analysis.backtest_strategies \
  --slippage 0.01 \
  --fee-base-rate 0.063 \
  --output-dir production_backtest
```

**Output Files:**

- `{output_dir}/{strategy_name}_results.csv` — Per-trade details with PnL, entry/exit prices, timestamps
- `{output_dir}/{strategy_name}_metrics.csv` — Aggregated performance metrics (Sharpe, Sortino, profit factor, win rate, etc.)

---

### optimize.py

**Purpose:** Grid-search parameter optimization. Tests all combinations from a strategy's `get_param_grid()` and ranks results by performance.

**Usage:**

```bash
cd src
PYTHONPATH=. python3 -m analysis.optimize [OPTIONS]
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--strategy` | str | **Required** | Strategy ID to optimize (e.g., `S1`, `S2`, `S7`). Cannot optimize `TEMPLATE`. |
| `--assets` | str | None | Comma-separated asset filter. If omitted, uses all assets. |
| `--durations` | str | None | Comma-separated duration filter in minutes. If omitted, uses all durations. |
| `--dry-run` | flag | False | Print parameter grid summary without running backtests. Use to preview grid size. |
| `--output-dir` | str | `optimization_results` | Directory where ranked results are written. |

**Examples:**

```bash
# Dry run: preview S1 parameter grid
PYTHONPATH=. python3 -m analysis.optimize \
  --strategy S1 \
  --dry-run

# Optimize S2 on BTC markets only
PYTHONPATH=. python3 -m analysis.optimize \
  --strategy S2 \
  --assets BTC \
  --output-dir s2_btc_optimization

# Optimize S7 ensemble across all assets
PYTHONPATH=. python3 -m analysis.optimize \
  --strategy S7 \
  --output-dir s7_optimization

# Optimize S3 mean reversion with realistic costs
PYTHONPATH=. python3 -m analysis.optimize \
  --strategy S3 \
  --assets BTC,ETH,SOL,XRP \
  --durations 5
```

**Output Files:**

- `{output_dir}/{strategy_name}_optimization_ranked.csv` — All parameter combinations ranked by total_pnl, with full metrics for each config
- Console output shows top 5 configurations by total_pnl

**Runtime Expectations:**

- **S1 (108 combinations):** 3-8 minutes per asset
- **S2 (72 combinations):** 2-5 minutes per asset
- **S3 (144 combinations):** 5-12 minutes per asset
- **S4 (108 combinations):** 3-8 minutes per asset
- **S5 (108 combinations):** 3-8 minutes per asset
- **S6 (72 combinations):** 2-5 minutes per asset
- **S7 (192 combinations):** 7-20 minutes per asset

**Recommendation:** Start with single-asset optimization (`--assets BTC`) to get quick results, then expand to multi-asset once you've identified promising parameter regions.

---

## Metric Interpretation

The backtest engine computes 18 performance metrics. This section explains what each metric means, how it's calculated, and what values indicate real edge vs. noise for 5-minute crypto prediction markets with dynamic fees and slippage.

### Core Profitability

#### total_pnl

**Definition:** Sum of all trade PnLs (wins + losses).

**Formula:**
```
total_pnl = Σ(trade.pnl for all trades)
```

**What it means:**
- Net profit/loss across all backtested trades
- **Positive** = strategy made money
- **Negative** = strategy lost money

**Context for 5-minute markets:**
- Each trade risks $1.00 position size (normalized)
- Typical single-trade PnL range: -$0.90 to +$0.90 (after fees + slippage)
- **Good threshold:** total_pnl > 0 (profitable over sample period)
- **Strong threshold:** total_pnl > 5% of total capital deployed (5 units profit on 100 trades)

**Caution:** Total PnL alone doesn't account for risk or consistency. A strategy with total_pnl = +$10 from 1000 trades is weaker than one with total_pnl = +$8 from 100 trades.

---

#### avg_bet_pnl

**Definition:** Average profit per trade.

**Formula:**
```
avg_bet_pnl = total_pnl / total_bets
```

**What it means:**
- Expected value per $1.00 bet
- Accounts for both wins and losses
- **Positive** = positive expectancy strategy
- **Negative** = losing strategy on average

**Context for 5-minute markets:**
- **Breakeven:** 0.00 (strategy doesn't make or lose money over time)
- **Weak edge:** +0.001 to +0.01 (0.1%-1.0% per trade)
- **Good edge:** +0.01 to +0.03 (1%-3% per trade)
- **Strong edge:** > +0.03 (>3% per trade — rare for 5-minute markets with fees)

**Example:**
- avg_bet_pnl = +0.015 → expect +$1.50 profit per 100 trades ($1.00 position size)
- avg_bet_pnl = -0.005 → expect -$0.50 loss per 100 trades (do not deploy)

---

### Win Rate

#### win_rate_pct

**Definition:** Percentage of trades that ended with profit > 0.

**Formula:**
```
win_rate_pct = (wins / total_bets) × 100
```

**What it means:**
- Hit rate: how often the strategy is right
- **Important:** Win rate alone doesn't indicate profitability (a strategy can have 60% win rate but lose money if avg loss > avg win)

**Context for 5-minute markets:**
- **Random baseline:** ~50% (coin flip)
- **Weak edge:** 51%-52% (slightly better than random)
- **Good edge:** 53%-56% (consistent directional accuracy)
- **Strong edge:** > 56% (rare for short-horizon markets)
- **Caution zone:** < 50% (losing more often than winning — only viable if avg win >> avg loss)

**Profitability threshold:** Win rate > 52% is a positive signal, but must be combined with profit factor and Sharpe to confirm edge.

---

### Risk-Adjusted Performance

#### sharpe_ratio

**Definition:** Ratio of average return to standard deviation of returns. Measures return per unit of volatility.

**Formula:**
```
sharpe_ratio = avg_bet_pnl / std_dev_pnl
```

where `std_dev_pnl` is the standard deviation of per-trade PnLs.

**What it means:**
- Higher = more consistent returns relative to volatility
- **Positive Sharpe** = positive expectancy with manageable volatility
- **Negative Sharpe** = losing strategy or high volatility relative to returns

**Context for 5-minute markets:**
- **Breakeven:** 0.0 (no excess return over risk)
- **Weak edge:** 0.5-1.0 (positive but volatile)
- **Good edge:** 1.0-2.0 (consistent positive returns)
- **Strong edge:** > 2.0 (very consistent — rare for high-frequency markets)

**Deployment threshold:** Sharpe > 1.0 is a positive signal for consideration.

**Why it matters:** A strategy with avg_bet_pnl = +0.02 and Sharpe = 0.3 is riskier than one with avg_bet_pnl = +0.01 and Sharpe = 1.5. The second strategy has lower absolute returns but much more consistent performance.

**Interpretation:**
- Sharpe = 1.5 → expect avg_bet_pnl with ±(avg_bet_pnl / 1.5) variability per trade
- Example: avg_bet_pnl = +0.015, Sharpe = 1.2 → typical trade PnL is +0.015 ± 0.0125

---

#### sortino_ratio

**Definition:** Like Sharpe, but only penalizes downside volatility (losses). Measures return per unit of downside risk.

**Formula:**
```
sortino_ratio = avg_bet_pnl / downside_std
```

where `downside_std` is the standard deviation of negative PnLs only.

**What it means:**
- Higher = better return relative to loss volatility
- Sharpe penalizes both upside and downside volatility equally; Sortino only penalizes downside
- **Useful when:** Strategy has asymmetric returns (big wins, small consistent losses)

**Context for 5-minute markets:**
- **Breakeven:** 0.0
- **Weak edge:** 0.5-1.0
- **Good edge:** 1.0-2.0
- **Strong edge:** > 2.0

**Comparison to Sharpe:**
- If Sortino >> Sharpe → strategy has asymmetric upside (big wins, controlled losses)
- If Sortino ≈ Sharpe → symmetric returns (wins and losses similar magnitude)
- If Sortino < Sharpe → impossible (indicates calculation error)

**Deployment threshold:** Sortino > 1.0 is a positive signal, especially if higher than Sharpe.

---

### Robustness

#### profit_factor

**Definition:** Ratio of gross profits to gross losses.

**Formula:**
```
profit_factor = sum(winning_pnls) / abs(sum(losing_pnls))
```

**What it means:**
- How much money you make per dollar you lose
- **1.0** = breakeven (wins equal losses)
- **> 1.0** = profitable (wins exceed losses)
- **< 1.0** = losing (losses exceed wins)

**Context for 5-minute markets:**
- **Breakeven:** 1.0
- **Weak edge:** 1.05-1.2 (5%-20% more wins than losses)
- **Good edge:** 1.2-1.5 (20%-50% more wins than losses)
- **Strong edge:** > 1.5 (50%+ more wins than losses — rare)

**Deployment threshold:** Profit factor > 1.2 is a positive signal.

**Why it matters:** Profit factor is robust to sample size and doesn't require stationarity assumptions (unlike Sharpe). A strategy with profit factor = 1.4 can sustain occasional large losses because wins outweigh losses 1.4:1.

**Example:**
- Profit factor = 1.3 → for every $1.00 you lose, you make $1.30 back
- Over 100 trades with $50 total losses → expect $65 total wins → +$15 net profit

---

#### max_drawdown

**Definition:** Largest peak-to-trough decline in cumulative PnL.

**Formula:**
```
cumulative_pnl = cumsum(trade.pnl for all trades)
peak = cummax(cumulative_pnl)
drawdown = peak - cumulative_pnl
max_drawdown = max(drawdown)
```

**What it means:**
- Worst losing streak in absolute PnL terms
- Measures downside risk: how much capital you'd lose from peak before recovering
- **Lower is better** (smaller drawdowns = less pain)

**Context for 5-minute markets:**
- **Good:** max_drawdown < 10% of total_pnl (drawdowns are small relative to profits)
- **Acceptable:** max_drawdown < 50% of total_pnl (drawdowns manageable)
- **Caution:** max_drawdown > 50% of total_pnl (large drawdowns relative to profits — high volatility)
- **Red flag:** max_drawdown > total_pnl (largest losing streak exceeds total profits)

**Deployment threshold:** max_drawdown < 50% of total_pnl is recommended before going live.

**Why it matters:** Max drawdown tells you how much capital you need to survive the worst historical losing streak. If total_pnl = +$10 but max_drawdown = -$15, you'd need >$15 risk capital to avoid ruin during the worst streak.

**Example:**
- total_pnl = +$12, max_drawdown = -$5 → healthy 42% drawdown-to-profit ratio
- total_pnl = +$5, max_drawdown = -$8 → risky 160% drawdown-to-profit ratio (don't deploy)

---

#### consistency_score

**Definition:** Measures how consistent win rates are across different assets. Lower variance in per-asset win rates → higher consistency.

**Formula:**
```
asset_win_rates = [win_rate for each asset]
consistency_score = 100 - std(asset_win_rates)
consistency_score = clamp(consistency_score, 0, 100)
```

**What it means:**
- **100** = perfect consistency (same win rate on every asset)
- **50** = moderate consistency (some assets better than others)
- **0** = no consistency (win rate varies wildly by asset)

**Context for 5-minute markets:**
- **Good:** consistency > 70 (strategy works across most assets)
- **Acceptable:** consistency 50-70 (strategy has some asset-specific behavior)
- **Caution:** consistency < 50 (strategy only works on specific assets — risk of overfitting)

**Deployment threshold:** consistency > 60 indicates the strategy generalizes well across assets.

**Why it matters:** High consistency means the strategy's edge is market-structure-driven (not asset-specific noise). Low consistency suggests the strategy may be overfitted to specific assets and won't generalize to new markets.

---

### Quarter Breakdown

#### q1_pnl, q2_pnl, q3_pnl, q4_pnl

**Definition:** Cumulative PnL split into four equal time periods (chronological).

**What it means:**
- Shows PnL trajectory over time
- **Consistent quarters** (all positive or similar magnitude) = stable strategy
- **Declining quarters** (q1 > q2 > q3 > q4) = degrading edge (possible overfitting or regime change)
- **Single outlier quarter** = one-time lucky/unlucky streak

**Context for 5-minute markets:**
- **Good pattern:** All four quarters positive, roughly equal magnitude
- **Acceptable pattern:** 3/4 quarters positive, one neutral/small negative
- **Caution pattern:** Only 1-2 quarters positive (edge may not be real)
- **Red flag pattern:** Strongly declining (q1 >> q2 >> q3 >> q4 — edge is fading)

**Why it matters:** Consistent performance across quarters suggests the edge is structural, not a lucky streak. Declining quarters may indicate the market adapted to the pattern.

---

### Other Metrics

#### expected_value

**Definition:** Weighted average of avg_win and avg_loss by their probabilities.

**Formula:**
```
expected_value = (win_rate × avg_win) - (loss_rate × avg_loss)
```

**What it means:**
- Theoretical long-run average per bet
- Should be very close to `avg_bet_pnl` (sanity check)

**Deployment use:** Cross-check with avg_bet_pnl. If they differ significantly, investigate data quality.

---

#### pct_profitable_assets

**Definition:** Percentage of assets where strategy made net profit.

**What it means:**
- Measures asset-level robustness
- **100%** = profitable on every asset
- **50%** = profitable on half the assets (may indicate asset-specific overfitting)

**Context for 5-minute markets:**
- **Good:** > 70% (strategy works on most assets)
- **Acceptable:** 50-70% (some asset variability)
- **Caution:** < 50% (may be overfitted to specific assets)

---

#### pct_profitable_durations

**Definition:** Percentage of duration buckets (e.g., 5-minute, 15-minute markets) where strategy made net profit.

**What it means:**
- Measures duration-level robustness
- For 5-minute only backtests, this will be 100% or 0%

**Context:** Less important when backtesting single duration. Useful for multi-duration strategies.

---

## Go/No-Go Decision Framework

Use this framework to decide whether a strategy has real edge and is ready for deployment.

### Minimum Deployment Criteria

A strategy must meet **ALL** of the following thresholds to be considered for live deployment:

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| **total_pnl** | > 0 | Strategy must be net profitable over backtest period |
| **sharpe_ratio** | > 1.0 | Positive returns must be consistent (not just lucky streaks) |
| **profit_factor** | > 1.2 | Wins must exceed losses by ≥20% (robust profitability) |
| **win_rate_pct** | > 52% | Strategy must beat coin-flip baseline with meaningful margin |
| **max_drawdown** | < 50% of total_pnl | Worst losing streak must be manageable relative to profits |
| **consistency_score** | > 60 | Strategy must work across most assets (not overfitted to one) |

### Decision Matrix

| Outcome | Action | Interpretation |
|---------|--------|----------------|
| **All 6 thresholds met** | **GO** — Ready for small-scale live testing | Strategy shows real edge with acceptable risk profile |
| **5/6 thresholds met** | **CONDITIONAL GO** — Review the failing metric and assess impact | May be deployable with caveats (e.g., if only consistency is weak but other metrics strong) |
| **4/6 or fewer met** | **NO-GO** — Do not deploy | Strategy does not have sufficient edge or risk profile is unacceptable |

### Example Evaluations

#### Example 1: Strong Strategy (GO)

```
Strategy: S1 (Calibration Mispricing)
total_pnl: +12.45
sharpe_ratio: 1.8
profit_factor: 1.4
win_rate_pct: 54.3
max_drawdown: -4.2 (34% of total_pnl)
consistency_score: 72

✅ All thresholds met → GO for live testing
```

---

#### Example 2: Marginal Strategy (CONDITIONAL GO)

```
Strategy: S3 (Mean Reversion)
total_pnl: +6.2
sharpe_ratio: 1.1
profit_factor: 1.25
win_rate_pct: 53.1
max_drawdown: -5.8 (94% of total_pnl)
consistency_score: 58

⚠️ 5/6 thresholds met (max_drawdown and consistency are marginal)
→ CONDITIONAL GO with extra caution
→ Consider: lower position sizing, asset filtering, shorter evaluation periods
```

---

#### Example 3: Weak Strategy (NO-GO)

```
Strategy: S6 (Streak/Sequence)
total_pnl: +2.1
sharpe_ratio: 0.7
profit_factor: 1.08
win_rate_pct: 51.2
max_drawdown: -3.5 (167% of total_pnl)
consistency_score: 45

❌ Only 2/6 thresholds met (total_pnl > 0, win_rate > 52%)
→ NO-GO — Strategy does not have sufficient edge
→ Recommendation: Re-optimize parameters or discard
```

---

### Additional Considerations

Beyond the 6 core thresholds, consider:

1. **Quarter consistency:** Are all 4 quarters profitable? If only q1 is positive, edge may have been temporary.
2. **Sample size:** How many trades? < 100 trades may not be statistically significant. Prefer > 200 trades for confidence.
3. **Asset coverage:** Does the strategy work on all major assets (BTC, ETH, SOL) or only one? Single-asset profitability may indicate overfitting.
4. **Sortino vs. Sharpe:** Is Sortino higher than Sharpe? This indicates asymmetric upside (desirable).
5. **Expected value:** Is expected_value ≈ avg_bet_pnl? If they differ significantly, investigate data quality.

---

## Parameter Optimization

Use the `optimize.py` script to explore a strategy's parameter space and identify the most profitable configurations.

### How Parameter Grids Work

Each strategy defines a `get_param_grid()` function that returns all parameters to explore and their candidate values. The optimizer generates the **Cartesian product** of all parameter values and backtests every combination.

**Example:** S1 (Calibration Mispricing) grid:

```python
{
    "entry_window_start": [30, 45, 60],        # 3 values
    "entry_window_end": [60, 90, 120],         # 3 values
    "price_low_threshold": [0.40, 0.45],       # 2 values
    "price_high_threshold": [0.55, 0.60],      # 2 values
    "min_deviation": [0.05, 0.08, 0.10],       # 3 values
}
# Total combinations: 3×3×2×2×3 = 108
```

The optimizer backtests all 108 parameter combinations, ranks them by `total_pnl`, and writes results to CSV.

---

### Running Optimization

#### Step 1: Dry Run (Preview Grid)

Before running a full optimization, preview the parameter grid to understand grid size and expected runtime:

```bash
cd src
PYTHONPATH=. python3 -m analysis.optimize --strategy S1 --dry-run
```

**Output:**
```
============================================================
Grid-Search Optimization: S1
============================================================

Parameters (5):
  entry_window_start: [30, 45, 60]
  entry_window_end: [60, 90, 120]
  price_low_threshold: [0.40, 0.45]
  price_high_threshold: [0.55, 0.60]
  min_deviation: [0.05, 0.08, 0.10]

Total combinations: 108
Estimated runtime: 3-8 minutes (single asset)
```

---

#### Step 2: Run Optimization

After confirming grid size, run the full optimization:

```bash
cd src
PYTHONPATH=. python3 -m analysis.optimize \
  --strategy S1 \
  --assets BTC \
  --output-dir s1_btc_optimization
```

**Output:**
- Console: Top 5 configurations by total_pnl
- File: `s1_btc_optimization/S1_optimization_ranked.csv` with all 108 configurations ranked

---

#### Step 3: Interpret Results

**CSV columns:**
- `config_id`: Unique identifier for parameter combination
- `total_pnl`: Net profit/loss for this configuration
- `sharpe_ratio`: Risk-adjusted return
- `profit_factor`: Gross wins / gross losses
- `win_rate_pct`: Hit rate
- `max_drawdown`: Worst losing streak
- `consistency_score`: Cross-asset consistency
- `q1_pnl`, `q2_pnl`, `q3_pnl`, `q4_pnl`: Quarterly PnL breakdown
- Parameter columns (e.g., `entry_window_start`, `price_low_threshold`, etc.)

**How to read:**

1. **Sort by total_pnl descending** — Top row is the most profitable configuration
2. **Check top 5-10 configurations** — Look for common parameter values (parameter sensitivity)
3. **Apply Go/No-Go framework** — Does the top configuration meet all 6 deployment thresholds?
4. **Check consistency across parameters** — Do similar parameter values cluster at the top? (Good sign) Or is top config an outlier? (Overfitting risk)

**Example interpretation:**

```csv
config_id,total_pnl,sharpe_ratio,profit_factor,win_rate_pct,entry_window_start,min_deviation
cfg_042,+15.2,1.9,1.45,55.1,45,0.08
cfg_041,+14.8,1.8,1.42,54.7,45,0.10
cfg_021,+14.1,1.7,1.38,54.2,30,0.08
cfg_043,+13.9,1.6,1.35,53.8,45,0.05
cfg_022,+13.5,1.7,1.40,54.0,30,0.10
```

**Insight:** `entry_window_start=45` and `min_deviation=0.08` appear in top configs → these parameters likely matter. `entry_window_start=60` doesn't appear in top 5 → probably suboptimal.

---

### Optimization Best Practices

1. **Start with single asset:** Optimize on `--assets BTC` first to get quick feedback, then expand to multi-asset once you've narrowed the parameter space.

2. **Dry run first:** Always run `--dry-run` to preview grid size before committing to full optimization.

3. **Beware overfitting:** Top configuration on historical data may not generalize to live markets. Look for **robustness**:
   - Top 5-10 configs should have similar parameter values (not scattered)
   - Consistency_score should be high (> 60)
   - All 4 quarters should be positive

4. **Cross-validate:** After identifying best config on one asset (e.g., BTC), run backtest on another asset (e.g., ETH) with the same config. If performance drops significantly, config may be overfitted.

5. **Sample size matters:** Optimization results are only meaningful if each configuration produces > 50 trades. If top configs have < 20 trades, results may not be statistically significant.

6. **Don't chase perfect parameters:** A configuration with total_pnl = +15.2 is not meaningfully better than one with +14.8. Focus on robustness (consistency, drawdown, Sharpe) over maximizing total_pnl.

---

## Troubleshooting

### Issue: Strategy produces zero trades

**Symptoms:**
- Backtest completes without errors
- CSV output shows 0 trades
- Metrics are all zero or NaN

**Possible causes:**

1. **No data in database (most common)**
   - Check: `psql -U polymarket -d polymarket -c "SELECT COUNT(*) FROM market_timeseries;"`
   - Fix: Populate database with historical data or copy from main repository

2. **Legitimately no signals detected (valid outcome for some strategies)**
   - **S6 (Streak):** Requires consecutive same-direction windows. If markets don't have streaks, zero trades is correct behavior.
   - **S3 (Mean Reversion):** Requires spike → reversion pattern. If no spikes in data, zero trades is correct.
   - **S7 (Composite Ensemble):** Requires ≥2 patterns to agree. If patterns rarely align, few/zero trades is expected.
   - **Check:** Run a different strategy on the same data. If other strategies produce trades but this one doesn't, it's likely the pattern isn't present (not a bug).

3. **Parameter configuration too restrictive**
   - Example: S1 with `min_deviation=0.15` may be too strict (price rarely deviates ≥15% from 0.50)
   - Fix: Run optimizer to explore parameter space, or manually relax thresholds

4. **Asset/duration filter too narrow**
   - Check: Are you filtering to a single asset with `--assets BTC`? Try expanding to `--assets BTC,ETH,SOL`
   - Check: Are you filtering to a specific duration that has no data? Try omitting `--durations` flag

**Diagnostic steps:**

```bash
# 1. Verify database has data
psql -U polymarket -d polymarket -c "SELECT COUNT(*) FROM market_timeseries WHERE asset = 'BTC' AND duration_minutes = 5;"

# 2. Run a known-working strategy (S1) on same filters
PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1 --assets BTC --durations 5

# 3. If S1 produces trades but your strategy doesn't, the pattern is missing (not a bug)

# 4. Check parameter grid with dry run
PYTHONPATH=. python3 -m analysis.optimize --strategy SN --dry-run

# 5. If grid is too restrictive, manually test looser parameters
```

---

### Issue: _get_price() returns None (sparse data)

**Symptoms:**
- Strategy evaluates but returns None more often than expected
- Console logs show "No price found at target_sec" (if debugging enabled)

**Cause:** Sparse timeseries data. If ticks are recorded every 10-15 seconds but strategy looks for price at 60s ± 5s tolerance, it may miss data points.

**Current behavior:** `_get_price(prices, target_sec=60, tolerance=5)` scans seconds 55-65 for valid (non-NaN) price. If all values in that range are NaN, returns None and strategy gracefully exits.

**Solutions:**

1. **Increase tolerance in strategy config** (if strategy supports it):
   - S2 has `tolerance` parameter (default 10s)
   - Increase to 15s if data is very sparse

2. **Improve data collection frequency:**
   - If ticks are recorded every 15s, consider increasing collection frequency to every 5-10s

3. **Accept lower signal frequency:**
   - Sparse data legitimately reduces tradeable opportunities
   - This is correct behavior (don't force trades on missing data)

**Not recommended:** Reducing tolerance below 5s (may miss valid data due to minor delays).

---

### Issue: Optimizer runtime is very long (> 30 minutes)

**Symptoms:**
- Optimizer runs for 30+ minutes without completing
- Console shows "Backtesting config X/192..."

**Causes:**

1. **Large parameter grid × large market dataset:**
   - S7 has 192 combinations
   - If you're optimizing across all assets and 12+ months of data, runtime can exceed 60 minutes

2. **Database query slowness:**
   - Timeseries queries may be slow if database isn't indexed properly

**Solutions:**

1. **Start with single asset:**
   ```bash
   PYTHONPATH=. python3 -m analysis.optimize --strategy S7 --assets BTC
   ```

2. **Use smaller date range (if supported in future):**
   - Future enhancement: Add `--start-date` and `--end-date` filters

3. **Reduce grid size (if you're willing to sacrifice coverage):**
   - Edit strategy's `config.py` → `get_param_grid()` to return fewer parameter values
   - Example: Change `[3, 4, 5]` to `[3, 5]` (2 values instead of 3)

4. **Check database performance:**
   ```sql
   EXPLAIN ANALYZE SELECT * FROM market_timeseries WHERE asset = 'BTC' LIMIT 1000;
   ```
   - If query takes > 100ms, consider adding indexes

**Expected runtimes (per asset):**

- S1 (108 combinations): 3-8 minutes
- S2 (72 combinations): 2-5 minutes
- S3 (144 combinations): 5-12 minutes
- S7 (192 combinations): 7-20 minutes

---

### Issue: All strategies show negative total_pnl

**Symptoms:**
- Every strategy loses money
- total_pnl is negative for all strategies, even simple ones like S1

**Possible causes:**

1. **Fees + slippage too high:**
   - Check: Are you using realistic fee_base_rate (default 0.063)?
   - Check: Is slippage too high (e.g., 0.05 = 5% slippage)?
   - Fix: Run backtest with `--slippage 0.0` to test without execution costs

2. **Market regime changed:**
   - Strategies may have been researched on older market data but backtested on newer data where patterns no longer exist
   - Check: Run backtests on different time ranges to see if edge exists in some periods but not others

3. **Data quality issues:**
   - Check: Are there large gaps in timeseries data?
   - Check: Are prices clamped to [0.01, 0.99] in database or showing extreme outliers?

**Diagnostic steps:**

```bash
# 1. Run S1 with no slippage, default fees
PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1 --assets BTC --durations 5 --slippage 0.0

# 2. If still negative, check data quality
psql -U polymarket -d polymarket -c "SELECT MIN(price), MAX(price), COUNT(*) FROM market_timeseries WHERE asset = 'BTC';"

# 3. If prices look reasonable, strategies may not have edge in this dataset
# Recommendation: Re-research strategies or collect more representative data
```

---

### Issue: Optimizer results are inconsistent

**Symptoms:**
- Running optimizer twice on same data produces different rankings
- Top config in one run is not in top 10 in another run

**Likely causes:**

1. **Random tie-breaking (not a bug):**
   - If two configs have identical total_pnl, ranking order is arbitrary
   - Check: Are top configs clustered within narrow PnL range (e.g., +14.5 to +15.2)? This is expected.

2. **Database state changed between runs:**
   - If data collection ran between optimizer runs, new markets may have been added
   - Fix: Snapshot database or use fixed date range

3. **Bug in optimizer (unlikely):**
   - Optimizer uses deterministic logic and doesn't introduce randomness
   - If results differ significantly (e.g., top config in run 1 is bottom in run 2), file a bug report

**Not a bug:** Minor ranking changes within clustered PnL ranges (±1-2 positions) are expected and not meaningful.

---

### Issue: Verification script fails

**Symptoms:**
- `bash scripts/verify_s03_strategies.sh` exits 1
- Error message shows which check failed

**Common failures:**

1. **Import error:**
   - Message: "ERROR: Strategy SN failed to import"
   - Cause: Syntax error in strategy.py or config.py
   - Fix: Run `python3 -c "from shared.strategies.SN.strategy import SNStrategy"` to see full traceback

2. **Parameter grid too small:**
   - Message: "ERROR: Strategy SN param grid has < 2 parameters or < 2 values per parameter"
   - Cause: `get_param_grid()` returned insufficient parameter space
   - Fix: Add more parameters or more values per parameter

3. **Signal structure invalid:**
   - Message: "ERROR: Signal from SN missing required field"
   - Cause: evaluate() returned Signal without `direction`, `entry_price`, or `entry_second` in signal_data
   - Fix: Ensure Signal includes all required fields (see signal structure schema in S03 forward intelligence)

**Diagnostic steps:**

```bash
# Run verification script with verbose output
bash -x scripts/verify_s03_strategies.sh

# Test specific strategy manually
cd src
python3 -c "
from shared.strategies.S1.strategy import S1Strategy
from shared.strategies.S1.config import get_default_config
import numpy as np
from shared.strategies.base import MarketSnapshot

s = S1Strategy(get_default_config())
snapshot = MarketSnapshot(
    prices=np.array([0.50, 0.48, 0.45, 0.42, 0.44]),  # spike pattern
    elapsed_seconds=5,
    total_seconds=300,
    metadata={}
)
signal = s.evaluate(snapshot)
print(signal)
"
```

---

## Summary

This playbook provides everything you need to:

1. **Run backtests:** Use `backtest_strategies.py` to evaluate strategies on historical data
2. **Interpret metrics:** Understand what Sharpe, Sortino, profit factor, win rate, drawdown, and consistency mean for 5-minute markets
3. **Make deployment decisions:** Apply the 6-threshold Go/No-Go framework to objectively evaluate strategies
4. **Optimize parameters:** Use `optimize.py` to explore parameter space and identify profitable configurations
5. **Troubleshoot issues:** Diagnose zero trades, sparse data, optimizer runtime, and verification failures

**Next steps:**

- Run backtests on your database
- Apply Go/No-Go framework to decide which strategies to deploy
- Optimize parameters for strategies that pass initial screening
- Start with small position sizes in live testing before scaling up

**Questions?** Refer to strategy docstrings in `src/shared/strategies/SN/strategy.py` for implementation details.
